from datetime import datetime, timedelta
from amazon_ads import get_access_token, submit_report, wait_and_download
from config import ADS_PROFILE_ID_USA

today = datetime.now()
start_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
end_date = today.strftime("%Y-%m-%d")

print(f"Період: {start_date} → {end_date}")

token = get_access_token()

COLS_TARGETING = [
    "campaignName", "adGroupName", "matchType",
    "keywordText", "targeting",
    "impressions", "clicks",
    "cost", "sales7d", "purchases7d", "costPerClick",
]

report_id = submit_report(
    token, ADS_PROFILE_ID_USA,
    f"debug targeting cols {start_date}", "spTargeting",
    COLS_TARGETING, ["targeting"], start_date, end_date,
)

t = get_access_token()
data = wait_and_download(t, ADS_PROFILE_ID_USA, report_id, token_fn=get_access_token)

print(f"\nВсього рядків: {len(data)}")
print(f"\nПерші 3 рядки (повна структура):")
for r in data[:3]:
    print(f"  {r}")
