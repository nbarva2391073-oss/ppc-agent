# ============================================================
# ОДНОРАЗОВИЙ BACKFILL — Business Report USA за 31.08-06.09
# Дірка утворилась через ранній час запуску (09:00 UTC),
# коли Amazon ще не встигав консолідувати дані за попередню добу.
# Виправлено на 14:00 UTC, цей backfill закриває вже пропущені дні.
# ============================================================

import sys
import time
from business_report import (
    get_access_token, request_business_report, wait_for_report,
    download_and_parse, format_rows, ensure_headers,
    BUSINESS_REPORT_SHEETS, HEADERS_BR,
)
from sheets import append

DATES = sys.argv[1:]

MARKET = "USA"


def backfill_date(date: str):
    print(f"\n{'='*50}")
    print(f"📅 Backfill Business Report USA за {date}")
    print(f"{'='*50}")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            token     = get_access_token(MARKET)
            report_id = request_business_report(MARKET, token, date)
            if not report_id:
                print(f"  ❌ Не вдалось запросити звіт за {date}")
                return

            document_id = wait_for_report(MARKET, token, report_id)
            if not document_id:
                print(f"  ❌ Звіт не готовий за {date}")
                return

            token   = get_access_token(MARKET)
            records = download_and_parse(MARKET, token, document_id)

            if records:
                rows       = format_rows(records, MARKET, date)
                sheet_name = BUSINESS_REPORT_SHEETS[MARKET]
                ensure_headers(sheet_name, HEADERS_BR)
                append(sheet_name, rows, HEADERS_BR)
                print(f"  ✅ {date}: {len(rows)} записів збережено")
                return
            else:
                if attempt < max_attempts:
                    print(f"  ⚠️ {date}: 0 записів, повторюємо через 90с...")
                    time.sleep(90)
                else:
                    print(f"  ⚠️ {date}: 0 записів після {max_attempts} спроб")

        except Exception as e:
            import traceback
            print(f"  ❌ Помилка за {date} (спроба {attempt}): {e}")
            traceback.print_exc()


if __name__ == "__main__":
    if not DATES:
        print("⚠️ Передай дати як аргументи")
        sys.exit(1)

    print(f"📋 Backfill {len(DATES)} днів: {DATES[0]} — {DATES[-1]}")

    for i, date in enumerate(DATES):
        backfill_date(date)
        if i < len(DATES) - 1:
            print("  ⏳ Пауза 65с перед наступним днем (rate limit)...")
            time.sleep(65)

    print("\n✅ Backfill завершено")
