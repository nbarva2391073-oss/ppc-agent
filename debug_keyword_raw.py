from datetime import datetime, timedelta
from amazon_ads import get_access_token, submit_report, wait_and_download
from config import ADS_PROFILE_ID_USA

today = datetime.now()
monday = today - timedelta(days=today.weekday() + 7)
sunday = monday + timedelta(days=6)
start_date = monday.strftime("%Y-%m-%d")
end_date = sunday.strftime("%Y-%m-%d")

print(f"Період: {start_date} → {end_date}")

token = get_access_token()

COLS_TARGETING = [
    "campaignName", "adGroupName", "matchType",
    "impressions", "clicks",
    "cost", "sales7d", "purchases7d", "costPerClick",
]

report_id = submit_report(
    token, ADS_PROFILE_ID_USA,
    f"debug targeting {start_date}", "spTargeting",
    COLS_TARGETING, ["targeting"], start_date, end_date,
)

t = get_access_token()
data = wait_and_download(t, ADS_PROFILE_ID_USA, report_id, token_fn=get_access_token)

print(f"\nВсього рядків у звіті: {len(data)}")

target = [r for r in data if "alpha marker" in str(r.get("keyword", "")).lower()
          or "alpha marker" in str(r.get("targetingExpression", "")).lower()]

print(f"\nРядків з 'alpha marker': {len(target)}")
for r in target:
    print(f"  {r}")
