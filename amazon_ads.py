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


def headers(token: str, profile_id: str,
            version: str = None, content_type: str = None) -> dict:
    """
    ВИПРАВЛЕНО: Amazon v3 SP endpoints вимагають специфічний
    Content-Type і Accept заголовок. Без них — 403 Forbidden.
    """
    ct = content_type or "application/json"
    h = {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
        "Amazon-Advertising-API-Scope": str(profile_id),
        "Content-Type": ct,
        "Accept": ct,
    }
    if version:
        h["Amazon-Advertising-API-Version"] = version
    return h


# ── Кампанії та біди ─────────────────────────────────────────

def get_campaigns(token: str, profile_id: str) -> list[dict]:
    """
    Отримати всі кампанії.

    ВИПРАВЛЕНО: 403 Forbidden — v3 endpoint вимагає
    Content-Type: application/vnd.spCampaign.v3+json
    """
    # Варіант 1: v3 з правильним content-type
    try:
        url = f"{ADS_BASE_URL}/sp/campaigns/list"
        ct  = "application/vnd.spCampaign.v3+json"
        payload = {
            "stateFilter": {"include": ["ENABLED", "PAUSED"]},
            "maxResults": 100,
        }
        r = requests.post(url,
                          headers=headers(token, profile_id, content_type=ct),
                          json=payload)
        if r.status_code == 200:
            data      = r.json()
            campaigns = data.get("campaigns", [])
            campaigns = _normalize_campaigns(campaigns)
            print(f"  ✅ Кампанії (v3): {len(campaigns)}")
            return campaigns
        else:
            print(f"  ⚠️ v3 повернув {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  ⚠️ v3 exception: {e}")

    # Варіант 2: v2 GET endpoint
    try:
        url = f"{ADS_BASE_URL}/v2/sp/campaigns"
        r   = requests.get(
            url,
            headers=headers(token, profile_id),
            params={"stateFilter": "enabled,paused", "count": 100},
        )
        if r.status_code == 200:
            data      = r.json()
            campaigns = data if isinstance(data, list) else data.get("campaigns", [])
            campaigns = _normalize_campaigns(campaigns)
            print(f"  ✅ Кампанії (v2): {len(campaigns)}")
            return campaigns
        else:
            print(f"  ⚠️ v2 повернув {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"  ⚠️ v2 exception: {e}")

    # Варіант 3: без префіксу версії (деякі регіони)
    url = f"{ADS_BASE_URL}/sp/campaigns"
    r   = requests.get(
        url,
        headers=headers(token, profile_id),
        params={"stateFilter": "enabled,paused", "count": 100},
    )
    r.raise_for_status()
    data      = r.json()
    campaigns = data if isinstance(data, list) else data.get("campaigns", [])
    campaigns = _normalize_campaigns(campaigns)
    print(f"  ✅ Кампанії (fallback): {len(campaigns)}")
    return campaigns


def _normalize_campaigns(campaigns: list) -> list:
    """Нормалізувати поля кампаній між v2 і v3."""
    normalized = []
    for c in campaigns:
        if "dailyBudget" in c and "budget" not in c:
            c["budget"] = {"budget": c["dailyBudget"], "budgetType": "DAILY"}
        if "dynamicBidding" in c and "bidding" not in c:
            dynamic     = c["dynamicBidding"]
            adjustments = []
            for adj in dynamic.get("placementBidding", []):
                adjustments.append({
                    "placement": adj.get("placement", ""),
                    "percentage": adj.get("percentage", 0),
                })
            c["bidding"] = {
                "strategy":    dynamic.get("strategy", ""),
                "adjustments": adjustments,
            }
        normalized.append(c)
    return normalized


def get_keywords(token: str, profile_id: str) -> list[dict]:
    """Отримати всі ключові слова."""
    # v3 з правильним content-type
    try:
        url = f"{ADS_BASE_URL}/sp/keywords/list"
        ct  = "application/vnd.spKeyword.v3+json"
        payload = {"stateFilter": {"include": ["ENABLED"]}, "maxResults": 1000}
        r = requests.post(url,
                          headers=headers(token, profile_id, content_type=ct),
                          json=payload)
        if r.status_code == 200:
            data     = r.json()
            keywords = data.get("keywords", data if isinstance(data, list) else [])
            print(f"  ✅ Ключові слова (v3): {len(keywords)}")
            return keywords
        else:
            print(f"  ⚠️ keywords v3: {r.status_code}")
    except Exception as e:
        print(f"  ⚠️ keywords v3 exception: {e}")

    # v2 fallback
    url = f"{ADS_BASE_URL}/v2/sp/keywords"
    r   = requests.get(url, headers=headers(token, profile_id),
                       params={"stateFilter": "enabled", "count": 1000})
    r.raise_for_status()
    keywords = r.json()
    if isinstance(keywords, list):
        pass
    else:
        keywords = keywords.get("keywords", [])
    print(f"  ✅ Ключові слова (v2): {len(keywords)}")
    return keywords


def get_negative_keywords(token: str, profile_id: str) -> list[dict]:
    url = f"{ADS_BASE_URL}/v2/sp/negativeKeywords"
    r   = requests.get(url, headers=headers(token, profile_id),
                       params={"stateFilter": "enabled", "count": 1000})
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("negativeKeywords", [])


# ── Звіти ────────────────────────────────────────────────────

def _request_report(token: str, profile_id: str,
                    name: str, report_type: str,
                    columns: list, group_by: list,
                    start_date: str, end_date: str) -> str:
    url     = f"{ADS_BASE_URL}/reporting/reports"
    payload = {
        "name":      name,
        "startDate": start_date,
        "endDate":   end_date,
        "configuration": {
            "adProduct":    "SPONSORED_PRODUCTS",
            "groupBy":      group_by,
            "columns":      columns,
            "reportTypeId": report_type,
            "timeUnit":     "SUMMARY",
            "format":       "GZIP_JSON",
        },
    }
    r = requests.post(url, headers=headers(token, profile_id), json=payload)
    print(f"  📡 Звіт {name}: {r.status_code} {r.text[:200]}")
    if r.status_code not in (200, 202):
        raise Exception(f"Звіт не створено ({r.status_code}): {r.text[:300]}")
    report_id = r.json()["reportId"]
    print(f"  ✅ Звіт запрошено: {name} ({report_id})")
    return report_id


def wait_and_download(token: str, profile_id: str,
                      report_id: str, max_wait: int = 1800) -> list[dict]:
    url    = f"{ADS_BASE_URL}/reporting/reports/{report_id}"
    waited = 0
    while waited < max_wait:
        r = requests.get(url, headers=headers(token, profile_id))
        r.raise_for_status()
        data   = r.json()
        status = data.get("status")

        if status == "COMPLETED":
            dl_url = data.get("url") or data.get("location")
            if not dl_url:
                raise Exception(f"Звіт COMPLETED але немає url: {data}")
            resp = requests.get(dl_url)
            with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as f:
                result = json.loads(f.read().decode("utf-8"))
            print(f"  ✅ Завантажено: {len(result)} рядків")
            return result

        elif status == "FAILED":
            failure = data.get("failureReason", "невідома причина")
            raise Exception(f"Звіт провалився ({report_id}): {failure}")

        print(f"  ⏳ Очікуємо звіт [{waited}s] ({status})...")
        time.sleep(30)
        waited += 30

    raise Exception(f"Timeout {max_wait}s: звіт {report_id}")


def get_search_term_report(token, profile_id, start_date, end_date):
    """
    ВИПРАВЛЕНО: видалено невалідні колонки clickThroughRate, advertisedAsin.
    У звітах спендтип — 'cost', не 'spend'.
    """
    rid = _request_report(
        token, profile_id, f"SearchTerm {start_date}",
        "spSearchTerm",
        [
            "campaignName", "adGroupName", "keyword", "matchType",
            "searchTerm", "impressions", "clicks",
            "spend", "sales7d", "purchases7d", "costPerClick",
        ],
        ["searchTerm"], start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


def get_campaign_report(token, profile_id, start_date, end_date):
    """
    ВИПРАВЛЕНО:
    - 'spend' → 'cost' (правильна назва в reporting API)
    - видалено 'clickThroughRate' — не існує в spCampaigns
    - видалено 'campaignBudgetAmount' — не існує в spCampaigns
    Невалідні колонки = звіт зависає в IN_PROGRESS вічно.
    """
    rid = _request_report(
        token, profile_id, f"Campaign {start_date}",
        "spCampaigns",
        [
            "campaignName", "campaignId",
            "impressions", "clicks",
            "spend", "sales7d", "purchases7d", "costPerClick",
        ],
        ["campaign"], start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


def get_placement_report(token, profile_id, start_date, end_date):
    rid = _request_report(
        token, profile_id, f"Placement {start_date}",
        "spCampaigns",
        [
            "campaignName",
            "impressions", "clicks",
            "spend", "sales7d", "purchases7d",
        ],
        ["campaignPlacement"], start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


def get_targeting_report(token, profile_id, start_date, end_date):
    rid = _request_report(
        token, profile_id, f"Targeting {start_date}",
        "spTargeting",
        [
            "campaignName", "adGroupName",
            "matchType", "impressions", "clicks",
            "spend", "sales7d", "purchases7d", "costPerClick",
        ],
        ["targeting"], start_date, end_date,
    )
    return wait_and_download(token, profile_id, rid)


# ── Аналітика ────────────────────────────────────────────────

def calculate_metrics(campaign_data: list[dict], margin: float) -> dict:
    if not campaign_data:
        return {}

    # ВИПРАВЛЕНО: підтримка обох назв — 'cost' (reporting API) і 'spend' (legacy)
    def _spend(r):
        return float(r.get("cost") or r.get("spend") or 0)

    total_spend  = sum(_spend(r) for r in campaign_data)
    total_sales  = sum(float(r.get("sales7d", 0)) for r in campaign_data)
    total_orders = sum(int(r.get("purchases7d", 0)) for r in campaign_data)

    acos  = (total_spend / total_sales * 100) if total_sales > 0 else 0
    roas  = (total_sales / total_spend)       if total_spend > 0 else 0
    tacos = (total_spend / total_sales)       if total_sales > 0 else 0

    gross_profit = total_sales * margin
    net_profit   = gross_profit - total_spend

    by_campaign = {}
    for row in campaign_data:
        name = row.get("campaignName", "Unknown")
        if name not in by_campaign:
            by_campaign[name] = {"spend": 0, "sales": 0, "orders": 0,
                                  "impressions": 0}
        by_campaign[name]["spend"]       += _spend(row)
        by_campaign[name]["sales"]       += float(row.get("sales7d", 0))
        by_campaign[name]["orders"]      += int(row.get("purchases7d", 0))
        by_campaign[name]["impressions"] += int(row.get("impressions", 0))

    campaign_acos = {}
    for name, vals in by_campaign.items():
        if vals["sales"] > 0:
            campaign_acos[name] = vals["spend"] / vals["sales"] * 100

    top   = min(campaign_acos, key=campaign_acos.get) if campaign_acos else ""
    worst = max(campaign_acos, key=campaign_acos.get) if campaign_acos else ""

    # ВИПРАВЛЕНО: бюджет тепер з поля 'campaignBudget'
    budget_issues = []
    for row in campaign_data:
        budget = float(row.get("campaignBudget") or row.get("campaignBudgetAmount") or 0)
        spend  = _spend(row)
        if budget > 0 and spend >= budget * 0.95:
            budget_issues.append(row.get("campaignName", ""))

    return {
        "total_spend":     round(total_spend, 2),
        "total_sales":     round(total_sales, 2),
        "total_orders":    total_orders,
        "overall_acos":    round(acos, 2),
        "overall_roas":    round(roas, 2),
        "tacos":           round(tacos, 4),
        "net_profit":      round(net_profit, 2),
        "campaigns_count": len(by_campaign),
        "top_campaign":    top,
        "worst_campaign":  worst,
        "by_campaign":     by_campaign,
        "budget_issues":   budget_issues,
        "breakeven_acos":  round(margin * 100, 1),
    }


def analyze_placement_issues(placement_data, campaigns):
    issues     = []
    by_campaign = {}
    for row in placement_data:
        name = row.get("campaignName", "")
        pl   = row.get("placement", "")
        if name not in by_campaign:
            by_campaign[name] = {}
        by_campaign[name][pl] = {
            "impressions": int(row.get("impressions", 0)),
            "spend":       float(row.get("cost") or row.get("spend") or 0),
            "sales":       float(row.get("sales7d", 0)),
        }

    for camp_name, placements in by_campaign.items():
        tos_imp = placements.get("Top of Search on-Amazon",  {}).get("impressions", 0)
        pp_imp  = placements.get("Detail Page on-Amazon",    {}).get("impressions", 0)
        other   = placements.get("Other on-Amazon",          {}).get("impressions", 0)
        total   = tos_imp + pp_imp + other
        if total == 0:
            continue
        tos_pct = tos_imp / total * 100
        pp_pct  = pp_imp  / total * 100

        camp_data = next(
            (c for c in campaigns if c.get("name") == camp_name), {})
        bidding = camp_data.get("bidding", {})
        adj     = {a["placement"]: a["percentage"]
                   for a in bidding.get("adjustments", [])}
        tos_adj = adj.get("PLACEMENT_TOP", 0)
        pp_adj  = adj.get("PLACEMENT_PRODUCT_PAGE", 0)

        if tos_adj >= 50 and tos_pct < 30 and pp_pct > 40:
            pp_spend = placements.get("Detail Page on-Amazon", {}).get("spend", 0)
            pp_sales = placements.get("Detail Page on-Amazon", {}).get("sales", 0)
            pp_acos  = (pp_spend / pp_sales * 100 if pp_sales > 0 else 999)
            issues.append({
                "campaign": camp_name,
                "tos_pct":  round(tos_pct, 1),
                "pp_pct":   round(pp_pct, 1),
                "tos_adj":  tos_adj,
                "pp_adj":   pp_adj,
                "pp_spend": round(pp_spend, 2),
                "pp_acos":  round(pp_acos, 1),
                "base_bid": camp_data.get("budget", {}).get("budget", 0),
            })
    return issues
