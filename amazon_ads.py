# ============================================================
# AMAZON ADS API — повне завантаження звітів
# ============================================================

import requests
import time
import json
import gzip
import io
from datetime import datetime, timedelta
from config import (ADS_CLIENT_ID, ADS_CLIENT_SECRET, ADS_REFRESH_TOKEN)

ADS_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
ADS_BASE_URL  = "https://advertising-api.amazon.com"


def get_access_token() -> str:
    """Отримати access token."""
    r = requests.post(ADS_TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": ADS_REFRESH_TOKEN,
        "client_id":     ADS_CLIENT_ID,
        "client_secret": ADS_CLIENT_SECRET,
    })
    r.raise_for_status()
    return r.json()["access_token"]


def headers(token: str, profile_id: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
        "Amazon-Advertising-API-Scope": profile_id,
        "Content-Type": "application/json",
    }


# ── Кампанії та біди ─────────────────────────────────────────

def get_campaigns(token: str, profile_id: str) -> list[dict]:
    """Отримати всі кампанії з бідами і adjustments."""
    url = f"{ADS_BASE_URL}/sp/campaigns"
    r = requests.get(url, headers=headers(token, profile_id),
                     params={"stateFilter": "enabled,paused", "count": 100})
    r.raise_for_status()
    campaigns = r.json().get("campaigns", [])
    print(f"  ✅ Кампанії: {len(campaigns)}")
    return campaigns


def get_keywords(token: str, profile_id: str) -> list[dict]:
    """Отримати всі ключові слова з бідами."""
    url = f"{ADS_BASE_URL}/sp/keywords"
    r = requests.get(url, headers=headers(token, profile_id),
                     params={"stateFilter": "enabled", "count": 1000})
    r.raise_for_status()
    keywords = r.json().get("keywords", [])
    print(f"  ✅ Ключові слова: {len(keywords)}")
    return keywords


def get_negative_keywords(token: str, profile_id: str) -> list[dict]:
    """Отримати всі негативні ключові слова."""
    url = f"{ADS_BASE_URL}/sp/negativeKeywords"
    r = requests.get(url, headers=headers(token, profile_id),
                     params={"stateFilter": "enabled", "count": 1000})
    r.raise_for_status()
    return r.json().get("negativeKeywords", [])


# ── Звіти ────────────────────────────────────────────────────

def _request_report(token: str, profile_id: str,
                    name: str, report_type: str,
                    columns: list, group_by: list,
                    start_date: str, end_date: str) -> str:
    """Запросити звіт і повернути reportId."""
    url = f"{ADS_BASE_URL}/reporting/reports"
    payload = {
        "name": name,
        "startDate": start_date,
        "endDate": end_date,
        "configuration": {
            "adProduct": "SPONSORED_PRODUCTS",
            "groupBy": group_by,
            "columns": columns,
            "reportTypeId": report_type,
            "timeUnit": "SUMMARY",
            "format": "GZIP_JSON",
        },
    }
    r = requests.post(url, headers=headers(token, profile_id), json=payload)
    r.raise_for_status()
    report_id = r.json()["reportId"]
    print(f"  ✅ Звіт запрошено: {name} ({report_id})")
    return report_id


def wait_and_download(token: str, profile_id: str,
                      report_id: str, max_wait: int = 600) -> list[dict]:
    """Чекати поки звіт готовий і завантажити."""
    url = f"{ADS_BASE_URL}/reporting/reports/{report_id}"
    waited = 0
    while waited < max_wait:
        r = requests.get(url, headers=headers(token, profile_id))
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status == "COMPLETED":
            # Завантажити і розпакувати
            resp = requests.get(data["url"])
            with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as f:
                result = json.loads(f.read().decode("utf-8"))
            print(f"  ✅ Завантажено: {len(result)} рядків")
            return result
        elif status == "FAILED":
            raise Exception(f"Звіт провалився: {report_id}")
        print(f"  ⏳ Очікуємо звіт ({status})...")
        time.sleep(30)
        waited += 30
    raise Exception(f"Timeout: звіт {report_id}")


def get_search_term_report(token: str, profile_id: str,
                           start_date: str, end_date: str) -> list[dict]:
    """Search Term Report — по яких словах купують."""
    rid = _request_report(
        token, profile_id,
        f"SearchTerm {start_date}",
        "spSearchTerm",
        ["campaignName", "adGroupName", "keyword", "matchType",
         "searchTerm", "impressions", "clicks", "clickThroughRate",
         "spend", "sales7d", "purchases7d", "costPerClick",
         "advertisedAsin"],
        ["searchTerm"],
        start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


def get_campaign_report(token: str, profile_id: str,
                        start_date: str, end_date: str) -> list[dict]:
    """Campaign Performance Report."""
    rid = _request_report(
        token, profile_id,
        f"Campaign {start_date}",
        "spCampaigns",
        ["campaignName", "campaignId", "impressions", "clicks",
         "clickThroughRate", "spend", "sales7d", "purchases7d",
         "costPerClick", "campaignBudgetAmount"],
        ["campaign"],
        start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


def get_placement_report(token: str, profile_id: str,
                         start_date: str, end_date: str) -> list[dict]:
    """Placement Report — де показуються оголошення."""
    rid = _request_report(
        token, profile_id,
        f"Placement {start_date}",
        "spCampaigns",
        ["campaignName", "placement", "impressions", "clicks",
         "spend", "sales7d", "purchases7d", "clickThroughRate"],
        ["campaign", "placement"],
        start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


def get_targeting_report(token: str, profile_id: str,
                         start_date: str, end_date: str) -> list[dict]:
    """Targeting Report — по кожному ключовому слову."""
    rid = _request_report(
        token, profile_id,
        f"Targeting {start_date}",
        "spTargeting",
        ["campaignName", "adGroupName", "targetingExpression",
         "targetingText", "matchType", "impressions", "clicks",
         "spend", "sales7d", "purchases7d", "costPerClick",
         "clickThroughRate"],
        ["targeting"],
        start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


# ── Аналітика ────────────────────────────────────────────────

def calculate_metrics(campaign_data: list[dict],
                      margin: float) -> dict:
    """Розрахувати зведені метрики тижня."""
    if not campaign_data:
        return {}

    total_spend  = sum(float(r.get("spend", 0)) for r in campaign_data)
    total_sales  = sum(float(r.get("sales7d", 0)) for r in campaign_data)
    total_orders = sum(int(r.get("purchases7d", 0)) for r in campaign_data)

    acos  = (total_spend / total_sales * 100) if total_sales > 0 else 0
    roas  = (total_sales / total_spend) if total_spend > 0 else 0
    tacos = (total_spend / total_sales) if total_sales > 0 else 0

    # Оцінюємо прибуток
    gross_profit = total_sales * margin
    net_profit   = gross_profit - total_spend

    # Групуємо по кампаніях
    by_campaign = {}
    for row in campaign_data:
        name = row.get("campaignName", "Unknown")
        if name not in by_campaign:
            by_campaign[name] = {"spend": 0, "sales": 0, "orders": 0,
                                  "impressions": 0}
        by_campaign[name]["spend"]      += float(row.get("spend", 0))
        by_campaign[name]["sales"]      += float(row.get("sales7d", 0))
        by_campaign[name]["orders"]     += int(row.get("purchases7d", 0))
        by_campaign[name]["impressions"]+= int(row.get("impressions", 0))

    campaign_acos = {}
    for name, vals in by_campaign.items():
        if vals["sales"] > 0:
            campaign_acos[name] = vals["spend"] / vals["sales"] * 100

    top   = min(campaign_acos, key=campaign_acos.get) if campaign_acos else ""
    worst = max(campaign_acos, key=campaign_acos.get) if campaign_acos else ""

    # Перевірка бюджет пейсинг
    budget_issues = []
    for row in campaign_data:
        budget = float(row.get("campaignBudgetAmount", 0))
        spend  = float(row.get("spend", 0))
        if budget > 0 and spend >= budget * 0.95:
            budget_issues.append(row.get("campaignName", ""))

    return {
        "total_spend":        round(total_spend, 2),
        "total_sales":        round(total_sales, 2),
        "total_orders":       total_orders,
        "overall_acos":       round(acos, 2),
        "overall_roas":       round(roas, 2),
        "tacos":              round(tacos, 4),
        "net_profit":         round(net_profit, 2),
        "campaigns_count":    len(by_campaign),
        "top_campaign":       top,
        "worst_campaign":     worst,
        "by_campaign":        by_campaign,
        "budget_issues":      budget_issues,
        "breakeven_acos":     round(margin * 100, 1),
    }


def analyze_placement_issues(placement_data: list[dict],
                              campaigns: list[dict]) -> list[dict]:
    """
    Аналіз placement проблем:
    Де кампанія орієнтована на ToS але показується на PP.
    """
    issues = []

    # Групуємо placement дані по кампаніях
    by_campaign = {}
    for row in placement_data:
        name = row.get("campaignName", "")
        pl   = row.get("placement", "")
        if name not in by_campaign:
            by_campaign[name] = {}
        by_campaign[name][pl] = {
            "impressions": int(row.get("impressions", 0)),
            "spend":       float(row.get("spend", 0)),
            "sales":       float(row.get("sales7d", 0)),
        }

    # Знаходимо кампанії де PP > ToS (підозра на проблему)
    for camp_name, placements in by_campaign.items():
        tos_imp = placements.get("Top of Search on-Amazon",
                  {}).get("impressions", 0)
        pp_imp  = placements.get("Detail Page on-Amazon",
                  {}).get("impressions", 0)
        total   = tos_imp + pp_imp + placements.get(
                  "Other on-Amazon", {}).get("impressions", 0)

        if total == 0:
            continue

        tos_pct = tos_imp / total * 100
        pp_pct  = pp_imp  / total * 100

        # Знаходимо bid adjustments для цієї кампанії
        camp_data = next(
            (c for c in campaigns if c.get("name") == camp_name), {})
        bidding = camp_data.get("bidding", {})
        adj     = {a["placement"]: a["percentage"]
                   for a in bidding.get("adjustments", [])}
        tos_adj = adj.get("PLACEMENT_TOP", 0)
        pp_adj  = adj.get("PLACEMENT_PRODUCT_PAGE", 0)

        # Проблема: висока ToS adjustment але мало ToS показів
        if tos_adj >= 50 and tos_pct < 30 and pp_pct > 40:
            pp_spend  = placements.get(
                "Detail Page on-Amazon", {}).get("spend", 0)
            pp_sales  = placements.get(
                "Detail Page on-Amazon", {}).get("sales", 0)
            pp_acos   = (pp_spend / pp_sales * 100
                         if pp_sales > 0 else 999)

            issues.append({
                "campaign":    camp_name,
                "tos_pct":     round(tos_pct, 1),
                "pp_pct":      round(pp_pct, 1),
                "tos_adj":     tos_adj,
                "pp_adj":      pp_adj,
                "pp_spend":    round(pp_spend, 2),
                "pp_acos":     round(pp_acos, 1),
                "base_bid":    camp_data.get("budget", {}).get("budget", 0),
            })

    return issues
