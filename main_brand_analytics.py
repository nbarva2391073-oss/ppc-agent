import sys
from datetime import datetime
from brand_analytics import (
    get_access_token,
    request_sqp_report, format_for_sheets,
    request_search_catalog_report, format_search_catalog_for_sheets,
    check_report_status, download_report
)
from sheets import append, get_sheet, SHEETS_USA, SHEETS_CA


def ensure_headers(sheet_name: str, headers: list):
    """Гарантовано додає заголовки в перший рядок, якщо їх там нема."""
    sh = get_sheet(sheet_name)
    first_row = sh.row_values(1)
    if not first_row:
        sh.update("A1", [headers])
        print(f"📝 Заголовки додано в '{sheet_name}'")

PENDING_SHEET = "BA_Pending_Reports"
MARKETS = ["USA", "CA"]
SHEETS_BY_MARKET = {"USA": SHEETS_USA, "CA": SHEETS_CA}

SQP_SHEET = "keyword_intelligence"  # старий аркуш для SQP (як і раніше)
SEARCH_CATALOG_SHEETS = {"USA": "BA_SearchCatalog_USA", "CA": "BA_SearchCatalog_CA"}

# Типи звітів, які ми збираємо. Кожен — окрема функція запиту і форматування.
REPORT_TYPES = {
    "SQP": {
        "request_fn": request_sqp_report,
        "format_fn": format_for_sheets,
    },
    "SEARCH_CATALOG": {
        "request_fn": request_search_catalog_report,
        "format_fn": format_search_catalog_for_sheets,
    },
}


# ============================================================
# РЕЖИМ 1: --request — тільки запитати звіти, нічого не чекати
# ============================================================
def run_request():
    print("=" * 60)
    print(f"📋 BRAND ANALYTICS — ЗАПИТ ЗВІТІВ")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    today = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    new_rows = []

    for market in MARKETS:
        token = None
        for report_type, funcs in REPORT_TYPES.items():
            print(f"\n🌎 {market} / {report_type}...")
            try:
                if token is None:
                    token = get_access_token(market)
                report_id = funcs["request_fn"](market, token)
                if report_id:
                    new_rows.append([today, report_id, market, "очікує", "", report_type])
                    print(f"✅ {market}/{report_type}: звіт запрошено, report_id={report_id}")
                else:
                    print(f"❌ {market}/{report_type}: не вдалось запросити звіт")
            except Exception as e:
                print(f"❌ {market}/{report_type} помилка: {e}")

    if new_rows:
        headers = ["Дата запиту", "Report ID", "Ринок", "Статус", "Дата виконання", "Тип звіту"]
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
    required_cols = ["Статус", "Report ID", "Ринок", "Дата виконання"]
    missing = [c for c in required_cols if c not in header]
    if missing:
        print(f"❌ В аркуші '{PENDING_SHEET}' немає колонок: {missing}")
        print(f"   Заголовки мають бути: Дата запиту, Report ID, Ринок, Статус, Дата виконання, Тип звіту")
        print(f"   Зараз у рядку 1: {header}")
        return

    col_status = header.index("Статус")
    col_report_id = header.index("Report ID")
    col_market = header.index("Ринок")
    col_done_date = header.index("Дата виконання")
    # "Тип звіту" — необов'язкова колонка для зворотної сумісності зі старими рядками (SQP)
    col_report_type = header.index("Тип звіту") if "Тип звіту" in header else None

    pending_found = 0
    fetched_count = {}

    for i, row in enumerate(all_values[1:], start=2):
        status = row[col_status] if len(row) > col_status else ""
        if status != "очікує":
            continue

        pending_found += 1
        report_id = row[col_report_id]
        market = row[col_market]
        report_type = row[col_report_type] if col_report_type is not None and len(row) > col_report_type and row[col_report_type] else "SQP"

        print(f"\n🔍 Перевіряю [{market}/{report_type}] report_id={report_id}...")

        try:
            token = get_access_token(market)
            result = check_report_status(market, token, report_id)
            report_status = result["status"]

            if report_status == "DONE":
                doc_id = result["document_id"]
                records = download_report(market, token, doc_id)

                if records:
                    if report_type == "SEARCH_CATALOG":
                        headers, rows = format_search_catalog_for_sheets(records, market)
                        target_sheet = SEARCH_CATALOG_SHEETS[market]
                    else:  # SQP
                        headers, rows = format_for_sheets(records, market)
                        target_sheet = SHEETS_BY_MARKET[market][SQP_SHEET]

                    ensure_headers(target_sheet, headers)
                    append(target_sheet, rows, headers)
                    key = f"{market}/{report_type}"
                    fetched_count[key] = fetched_count.get(key, 0) + len(rows)
                    print(f"✅ {market}/{report_type}: {len(rows)} записів збережено в '{target_sheet}'")
                else:
                    print(f"⚠️ {market}/{report_type}: звіт готовий, але даних немає")

                done_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
                sh.update_cell(i, col_status + 1, "виконано")
                sh.update_cell(i, col_done_date + 1, done_date)

            elif report_status in ("FATAL", "CANCELLED"):
                sh.update_cell(i, col_status + 1, "помилка")
                print(f"❌ {market}/{report_type}: звіт завершився статусом {report_status}")

            else:
                print(f"⏳ {market}/{report_type}: ще не готовий ({report_status}), чекаємо наступного запуску")

        except Exception as e:
            print(f"❌ {market}/{report_type} помилка перевірки: {e}")

    if pending_found == 0:
        print("\n✅ Немає звітів зі статусом 'очікує' — перевіряти нічого")

    print(f"\n📊 Підсумок завантаження:")
    for key, count in fetched_count.items():
        print(f"   {key}: {count} записів")
    if not fetched_count:
        print("   (нічого не завантажено)")

    print("\n✅ ПЕРЕВІРКА ЗАВЕРШЕНА")


if __name__ == "__main__":
    if "--request" in sys.argv:
        run_request()
    elif "--fetch" in sys.argv:
        run_fetch()
    else:
        print("⚠️ Вкажи режим: python main_brand_analytics.py --request  АБО  --fetch")
        sys.exit(1)
