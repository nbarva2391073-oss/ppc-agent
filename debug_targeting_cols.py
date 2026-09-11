import requests
from datetime import datetime, timedelta
from amazon_ads import get_access_token, headers, ADS_BASE_URL
from config import ADS_PROFILE_ID_USA

today = datetime.now()
start_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
end_date = today.strftime("%Y-%m-%d")

token = get_access_token()

candidates = ["keyword", "targeting", "targetingExpression", "targetingText", "keywordId"]

for col in candidates:
    payload = {
        "name": f"debug col {col}",
        "startDate": start_date,
        "endDate": end_date,
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": ["targeting"],
            "columns": ["campaignName", "matchType", col],
            "reportTypeId": "spTargeting",
            "timeUnit": "SUMMARY",
            "format": "GZIP_JSON",
        },
    }
    r = requests.post(
        f"{ADS_BASE_URL}/reporting/reports",
        headers=headers(token, ADS_PROFILE_ID_USA),
        json=payload,
    )
    status = "✅ ВАЛІДНА" if r.status_code == 200 else "❌ невалідна"
    print(f"\n{col}: {status} (status={r.status_code})")
    if r.status_code != 200:
        print(f"  {r.text[:150]}")
