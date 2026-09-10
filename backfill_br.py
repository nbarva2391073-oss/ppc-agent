import sys
from business_report import (
    get_access_token, request_business_report, wait_for_report,
    download_and_parse, format_rows, ensure_headers,
    BUSINESS_REPORT_SHEETS, HEADERS_BR,
)
from sheets import append
import time

MARKET = sys.argv[1]
DATES = sys.argv[2:]

for i, date in enumerate(DATES):
    print(f"\n📅 Business Report {MARKET} за {date}")
    try:
        token     = get_access_token(MARKET)
        report_id = request_business_report(MARKET, token, date)
        if not report_id:
            print(f"❌ не вдалось запросити")
            continue
        document_id = wait_for_report(MARKET, token, report_id)
        if not document_id:
            print(f"❌ звіт не готовий")
            continue
        token   = get_access_token(MARKET)
        records = download_and_parse(MARKET, token, document_id)
        if records:
            rows       = format_rows(records, MARKET, date)
            sheet_name = BUSINESS_REPORT_SHEETS[MARKET]
            ensure_headers(sheet_name, HEADERS_BR)
            append(sheet_name, rows, HEADERS_BR)
            print(f"✅ {len(rows)} записів збережено")
        else:
            print(f"⚠️ 0 записів")
    except Exception as e:
        import traceback
        print(f"❌ {e}")
        traceback.print_exc()

    if i < len(DATES) - 1:
        print("⏳ Пауза 70с...")
        time.sleep(70)

print("\n✅ Backfill завершено")
