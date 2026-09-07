from business_report import get_access_token, request_business_report, wait_for_report, download_and_parse

market = "USA"
token = get_access_token(market)

# Той самий запит, але напряму з кастомним діапазоном 01-06.09
import requests
from business_report import SP_API_BASE, MARKETPLACE_IDS

payload = {
    "reportType": "GET_SALES_AND_TRAFFIC_REPORT",
    "dataStartTime": "2026-09-01T00:00:00Z",
    "dataEndTime": "2026-09-06T23:59:59Z",
    "reportOptions": {"dateGranularity": "DAY", "asinGranularity": "CHILD"},
    "marketplaceIds": [MARKETPLACE_IDS[market]],
}

resp = requests.post(
    f"{SP_API_BASE}/reports/2021-06-30/reports",
    headers={"x-amz-access-token": token, "Content-Type": "application/json"},
    json=payload,
)
print(f"Submit status: {resp.status_code}")
report_id = resp.json().get("reportId")
print(f"report_id={report_id}")

document_id = wait_for_report(market, token, report_id)
print(f"document_id={document_id}")

if document_id:
    token = get_access_token(market)
    records = download_and_parse(market, token, document_id)
    print(f"Записів: {len(records)}")
    if records:
        print(f"Перший запис: {records[0]}")
