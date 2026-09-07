# ============================================================
# SPONSORED BRANDS — окрема інтеграція для SB кампаній
# Перевикористовує ту саму v3 Reporting API логіку, що SP,
# з adProduct=SPONSORED_BRANDS і власними назвами колонок
# (sales/purchases, не sales14d/purchases14d як у SP).
# Тільки USA. Тільки активні (ENABLED) кампанії.
# ============================================================

import requests
from datetime import datetime, timedelta
from amazon_ads import (
    get_access_token, headers, ADS_BASE_URL,
    submit_report, wait_and_download,
)
from sheets import append, get_sheet

COLS_SB_CAMPAIGN = [
    "campaignId", "campaignName", "campaignStatus",
    "impressions", "clicks", "cost",
    "sales", "purchases", "unitsSold",
    "newToBrandSales", "newToBrandPurchases",
]

COLS_SB_SEARCH_TERM = [
    "campaignId", "campaignName", "adGroupName",
    "keywordText", "matchType", "searchTerm",
    "impressions", "clicks", "cost",
    "sales", "purchases", "unitsSold",
]

SB_CAMPAIGN_SHEET    = "SB_Campaign_USA"
SB_SEARCH_TERM_SHEET = "SB_SearchTerm_USA"


def get_sb_campaigns(token: str, profile_id: str) -> list:
    """Отримати активні (ENABLED) Sponsored Brands кампанії."""
    url = f"{ADS_BASE_URL}/sb/v4/campaigns/list"
    h = {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": headers(token, profile_id)["Amazon-Advertising-API-ClientId"],
        "Amazon-Advertising-API-Scope": str(profile_id),
        "Content-Type": "application/vnd.sbcampaignresource.v4+json",
        "Accept": "application/vnd.sbcampaignresource.v4+json",
    }
    payload = {"stateFilter": {"include": ["ENABLED"]}}

    r = requests.post(url, headers=h, json=payload)
    if r.status_code != 200:
        print(f"  ⚠️ SB campaigns list: {r.status_code} {r.text[:200]}")
        return []

    campaigns = r.json().get("campaigns", [])
    print(f"  ✅ SB кампанії (ENABLED): {len(campaigns)}")
    return campaigns


def ensure_headers(sheet_name: str, headers_row: list):
    sh = get_sheet(sheet_name)
    first_row = sh.row_values(1)
    if not first_row:
        sh.update([headers_row], "A1")
        print(f"  📝 Заголовки додано в '{sheet_name}'")


def format_sb_campaign_for_sheets(data: list, week: str, market: str) -> tuple:
    headers_out = ["Week", "Campaign", "Status",
                   "Impressions", "Clicks", "Cost",
                   "Sales", "Purchases", "Units Sold",
                   "New-to-Brand Sales", "New-to-Brand Purchases",
                   "ACoS%", "Ринок"]
    rows = []
    for r in data:
        cost  = float(r.get("cost", 0))
        sales = float(r.get("sales", 0))
        rows.append([
            week,
            r.get("campaignName", ""),
            r.get("campaignStatus", ""),
            r.get("impressions", 0),
            r.get("clicks", 0),
            round(cost, 2),
            round(sales, 2),
            r.get("purchases", 0),
            r.get("unitsSold", 0),
            round(float(r.get("newToBrandSales", 0)), 2),
            r.get("newToBrandPurchases", 0),
            round(cost / sales * 100 if sales > 0 else 0, 1),
            market,
        ])
    return headers_out, rows


def format_sb_search_term_for_sheets(data: list, week: str, market: str) -> tuple:
    headers_out = ["Week", "Campaign", "Ad Group",
                   "Keyword", "Match Type", "Search Term",
                   "Impressions", "Clicks", "Cost",
                   "Sales", "Purchases", "Units Sold",
                   "ACoS%", "Ринок"]
    rows = []
    for r in data:
        cost  = float(r.get("cost", 0))
        sales = float(r.get("sales", 0))
        rows.append([
            week,
            r.get("campaignName", ""),
            r.get("adGroupName", ""),
            r.get("keywordText", ""),
            r.get("matchType", ""),
            r.get("searchTerm", ""),
            r.get("impressions", 0),
            r.get("clicks", 0),
            round(cost, 2),
            round(sales, 2),
            r.get("purchases", 0),
            r.get("unitsSold", 0),
            round(cost / sales * 100 if sales > 0 else 0, 1),
            market,
        ])
    return headers_out, rows


def collect_sponsored_brands(profile_id: str, market: str, week: str,
                              start_date: str, end_date: str):
    """Головна функція — щоденний збір SB даних (тільки USA)."""
    token = get_access_token()

    campaigns = get_sb_campaigns(token, profile_id)
    if not campaigns:
        print(f"  ℹ️ SB {market}: немає активних кампаній")
        return

    # Campaign report
    try:
        try:
            report_id = submit_report(
                token, profile_id,
                f"SB Campaign {start_date}", "sbCampaigns",
                COLS_SB_CAMPAIGN, ["campaign"],
                start_date, end_date,
                ad_product="SPONSORED_BRANDS",
            )
        except Exception as submit_e:
            # 425 duplicate — Amazon вже має звіт за цей самий період,
            # витягуємо його report_id і перевикористовуємо замість помилки
            import re
            m = re.search(r"duplicate of\s*:\s*([\w-]+)", str(submit_e))
            if m:
                report_id = m.group(1)
                print(f"  ℹ️ SB Campaign {market}: duplicate, перевикористовуємо report_id={report_id}")
            else:
                raise

        t = get_access_token()
        data = wait_and_download(t, profile_id, report_id, max_wait=2700, token_fn=get_access_token)
        headers_out, rows = format_sb_campaign_for_sheets(data, week, market)
        ensure_headers(SB_CAMPAIGN_SHEET, headers_out)
        append(SB_CAMPAIGN_SHEET, rows, headers_out)
        print(f"  ✅ SB Campaign {market}: {len(rows)} рядків")
    except Exception as e:
        import traceback
        print(f"  ❌ SB Campaign {market}: {e}")
        traceback.print_exc()

    # Пауза перед другим запитом, щоб зменшити ризик 429 Throttled
    import time
    time.sleep(65)

    # Search Term report
    try:
        report_id = submit_report(
            token, profile_id,
            f"SB Search Term {start_date}", "sbSearchTerm",
            COLS_SB_SEARCH_TERM, ["searchTerm"],
            start_date, end_date,
            ad_product="SPONSORED_BRANDS",
        )
        t = get_access_token()
        data = wait_and_download(t, profile_id, report_id, max_wait=2700, token_fn=get_access_token)
        headers_out, rows = format_sb_search_term_for_sheets(data, week, market)
        ensure_headers(SB_SEARCH_TERM_SHEET, headers_out)
        append(SB_SEARCH_TERM_SHEET, rows, headers_out)
        print(f"  ✅ SB Search Term {market}: {len(rows)} рядків")
    except Exception as e:
        import traceback
        print(f"  ❌ SB Search Term {market}: {e}")
        traceback.print_exc()


def run_sponsored_brands():
    from config import ADS_PROFILE_ID_USA

    print("=" * 60)
    print(f"📢 SPONSORED BRANDS — ЗБІР ДАНИХ (USA)")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    today = datetime.now()
    start_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date   = today.strftime("%Y-%m-%d")
    monday = today - timedelta(days=today.weekday() + 7)
    sunday = monday + timedelta(days=6)
    week   = f"{monday.strftime('%d.%m')}-{sunday.strftime('%d.%m.%Y')}"

    if not ADS_PROFILE_ID_USA:
        print("⏭️  profile_id USA не задано, пропускаємо")
        return

    collect_sponsored_brands(ADS_PROFILE_ID_USA, "USA", week, start_date, end_date)

    print("\n✅ SPONSORED BRANDS ЗАВЕРШЕНО")


if __name__ == "__main__":
    run_sponsored_brands()
