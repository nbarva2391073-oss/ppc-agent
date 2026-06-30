import sys
from datetime import datetime
from brand_analytics import (
    get_access_token, request_sqp_report,
    check_report_status, download_report, format_for_sheets
)
from sheets import append, get_sheet, SHEETS_USA, SHEETS_CA

PENDING_SHEET = "BA_Pending_Reports"
MARKETS = ["USA", "CA"]
SHEETS_BY_MARKET = {"USA": SHEETS_USA, "CA": SHEETS_CA}


# ============================================================
# РЕЖИМ 1: --request — тільки запитати звіт, нічого не чекати
# ============================================================
def run_request():
    print("=" * 60)
    print(f"📋 BRAND ANALYTICS — ЗАПИТ ЗВІТІВ")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    new_rows = []

    for market in MARKETS:
        print(f"\n🌎 {market}...")
        try:
            token = get_access_token(market)
            report_id = request_sqp_report(market, token)
            if report_id:
                new_rows.append([today, report_id, market, "очікує", ""])
                print(f"✅ {market}: звіт запрошено, report_id={report_id}")
            else:
                print(f"❌ {market}: не вдалось запросити звіт")
        except Exception as e:
            print(f"❌ {market} помилка: {e}")

    if new_rows:
        headers = ["Дата запиту", "Report ID", "Ринок", "Статус", "Дата виконання"]
        append(PENDING_SHEET, new_rows, headers)
        print(f"\n✅ Записано {len(new_rows)} рядків у '{PENDING_SHEET}'")
    else:
        print("\n⚠️ Жодного звіту не запрошено")

    print("\n✅ ЗАПИТ ЗАВЕРШЕНО")


# ============================================================
# РЕЖИМ 2: --fetch — перевірити статус, забрати готові звіти
# ============================================================
def run_fetch():
    print("=" * 60)
    print(f"📥 BRAND ANALYTICS — ПЕРЕВІРКА ТА ЗАВАНТАЖЕННЯ")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    sh = get_sheet(PENDING_SHEET)
    all_values = sh.get_all_values()

    if len(all_values) <= 1:
        print("⚠️ Немає рядків для перевірки (аркуш порожній)")
        return

    header = all_values[0]
    col_status = header.index("Статус")
    col_report_id = header.index("Report ID")
    col_market = header.index("Ринок")
    col_done_date = header.index("Дата виконання")

    pending_found = 0
    fetched_count = {"USA": 0, "CA": 0}

    # Перебираємо рядки знизу нема значення, але індекс рядка в Sheets = i + 1
    for i, row in enumerate(all_values[1:], start=2):
        status = row[col_status] if len(row) > col_status else ""
        if status != "очікує":
            continue

        pending_found += 1
        report_id = row[col_report_id]
        market = row[col_market]
        print(f"\n🔍 Перевіряю [{market}] report_id={report_id}...")

        try:
            token = get_access_token(market)
            result = check_report_status(market, token, report_id)
            report_status = result["status"]

            if report_status == "DONE":
                doc_id = result["document_id"]
                records = download_report(market, token, doc_id)
                if records:
                    headers, rows = format_for_sheets(records, market)
                    append(SHEETS_BY_MARKET[market]["keyword_intelligence"], rows, headers)
                    fetched_count[market] += len(rows)
                    print(f"✅ {market}: {len(rows)} записів збережено")
                else:
                    print(f"⚠️ {market}: звіт готовий, але даних немає")

                # Позначаємо рядок виконаним
                done_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
                sh.update_cell(i, col_status + 1, "виконано")
                sh.update_cell(i, col_done_date + 1, done_date)

            elif report_status in ("FATAL", "CANCELLED"):
                sh.update_cell(i, col_status + 1, "помилка")
                print(f"❌ {market}: звіт завершився статусом {report_status}")

            else:
                # IN_PROGRESS, IN_QUEUE тощо — лишаємо як є, перевіримо пізніше
                print(f"⏳ {market}: ще не готовий ({report_status}), чекаємо наступного запуску")

        except Exception as e:
            print(f"❌ {market} помилка перевірки: {e}")

    if pending_found == 0:
        print("\n✅ Немає звітів зі статусом 'очікує' — перевіряти нічого")

    print(f"\n📊 Підсумок завантаження: USA={fetched_count['USA']}, CA={fetched_count['CA']}")
    print("\n✅ ПЕРЕВІРКА ЗАВЕРШЕНА")


if __name__ == "__main__":
    if "--request" in sys.argv:
        run_request()
    elif "--fetch" in sys.argv:
        run_fetch()
    else:
        print("⚠️ Вкажи режим: python main_brand_analytics.py --request  АБО  --fetch")
        sys.exit(1)
