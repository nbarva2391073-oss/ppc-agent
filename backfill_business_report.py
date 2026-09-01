# ============================================================
# ОДНОРАЗОВИЙ BACKFILL — Business Report USA за пропущений період
# 08.07-24.08.2026 (48 днів), тільки USA, без Канади.
# Rate limit createReport ~0.0167 req/s (burst 15) — тому пауза
# між запитами і послідовна обробка одного дня за раз.
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

    max_attempts = 2
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
                    print(f"  ⚠️ {date}: 0 записів, повторюємо через 60с...")
                    time.sleep(60)
                else:
                    print(f"  ⚠️ {date}: 0 записів після {max_attempts} спроб — даних дійсно немає")

        except Exception as e:
            import traceback
            print(f"  ❌ Помилка за {date} (спроба {attempt}): {e}")
            traceback.print_exc()


if __name__ == "__main__":
    if not DATES:
        print("⚠️ Передай дати як аргументи: python backfill_business_report.py 2026-07-08 2026-07-09 ...")
        sys.exit(1)

    print(f"📋 Backfill {len(DATES)} днів: {DATES[0]} — {DATES[-1]}")

    for i, date in enumerate(DATES):
        backfill_date(date)
        if i < len(DATES) - 1:
            print("  ⏳ Пауза 65с перед наступним днем (rate limit)...")
            time.sleep(65)

    print("\n✅ Backfill частини завершено")
