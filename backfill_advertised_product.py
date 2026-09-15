from datetime import datetime
from amazon_ads import get_access_token, submit_report, wait_and_download
from sheets import write_advertised_product
from config import ADS_PROFILE_ID_USA

date = "2026-09-13"
token = get_access_token()

COLS_ADVERTISED_PRODUCT = [
    "campaignName", "adGroupName", "advertisedAsin",
    "impressions", "clicks", "cost", "purchases14d", "sales14d",
]

report_id = submit_report(
    token, ADS_PROFILE_ID_USA,
    f"backfill advertised_product {date}", "spAdvertisedProduct",
    COLS_ADVERTISED_PRODUCT, ["advertiser"], date, date,
)

t = get_access_token()
data = wait_and_download(t, ADS_PROFILE_ID_USA, report_id, token_fn=get_access_token)
write_advertised_product(data, date, "USA")
print(f"✅ Backfill Advertised Product USA за {date} завершено")
