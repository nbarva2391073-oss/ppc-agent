# ============================================================
# GOOGLE SHEETS — читання і запис всіх даних
# ============================================================

import json
import time as _sheets_time
import random as _sheets_random
from functools import wraps as _wraps

def _retry_sheets(max_retries=5, base_delay=5):
    """Exponential backoff для Google Sheets API."""
    def decorator(func):
        @_wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "429" in str(e) or "Quota exceeded" in str(e):
                        delay = base_delay * (2 ** attempt) + _sheets_random.uniform(0, 2)
                        print(f"⏳ Sheets 429, чекаємо {delay:.1f}с (спроба {attempt+1}/{max_retries})...")
                        _sheets_time.sleep(delay)
                        if attempt == max_retries - 1:
                            raise
                    else:
                        raise
        return wrapper
    return decorator
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from config import (SPREADSHEET_ID, SHEETS_USA, SHEETS_CA,
                    SHEETS_COMMON, GOOGLE_CREDENTIALS_JSON)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# БАГ ВИПРАВЛЕНО: кешуємо client щоб не створювати новий при кожному виклику
_client_cache = None


def client():
    global _client_cache
    if _client_cache is None:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        print(f"  🔑 Sheets: client_email={creds_dict.get('client_email')}")
        print(f"  🔑 Sheets: private_key_id={creds_dict.get('private_key_id')}")
        print(f"  🔑 Sheets: SPREADSHEET_ID={SPREADSHEET_ID}")
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _client_cache = gspread.Client(auth=creds)
    return _client_cache


@_retry_sheets(max_retries=5, base_delay=5)
def get_sheet(name: str):
    ss = client().open_by_key(SPREADSHEET_ID)
    try:
        return ss.worksheet(name)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title=name, rows=2000, cols=60)



def append(sheet_name: str, rows: list, headers: list = None):
    """Додати рядки в аркуш (з заголовками якщо порожній)."""
    sh = get_sheet(sheet_name)
    existing = sh.get_all_values()
    if not existing:
        if headers:
            sh.append_row(headers)
    elif headers and not existing:
        sh.append_row(headers)
    if rows:
        before = len(sh.get_all_values())
        # Пряме оновлення — обходить обмеження append_rows
        next_row = before + 1
        sh.update(f"A{next_row}", rows)
        after = len(sh.get_all_values())
        print(f"  📝 write: рядків до={before}, після={after}, додано={after-before}")
        _sheets_time.sleep(5)  # уникаємо Google Sheets rate limit


@_retry_sheets(max_retries=5, base_delay=5)
def read_all(sheet_name: str) -> list[list]:
    """Прочитати всі дані з аркуша."""
    try:
        return get_sheet(sheet_name).get_all_values()
    except Exception:
        return []


# ── Raw Data ─────────────────────────────────────────────────

def write_raw_data(data: list[dict], week: str, market: str):
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Week", "Campaign", "Ad Group", "ASIN",
               "Search Term", "Keyword", "Match Type",
               "Impressions", "Clicks", "CTR%",
               "Spend", "Sales", "ACoS%", "ROAS",
               "Orders", "CPC"]
    rows = []
    for r in data:
        spend = float(r.get("spend", 0))
        sales = float(r.get("sales7d", 0))
        rows.append([
            week,
            r.get("campaignName", ""),
            r.get("adGroupName", ""),
            r.get("advertisedAsin", ""),
            r.get("searchTerm", ""),
            r.get("keyword", ""),
            r.get("matchType", ""),
            r.get("impressions", 0),
            r.get("clicks", 0),
            round(float(r.get("clickThroughRate", 0)) * 100, 2),
            round(spend, 2),
            round(sales, 2),
            round(spend / sales * 100 if sales > 0 else 0, 1),
            round(sales / spend if spend > 0 else 0, 2),
            r.get("purchases7d", 0),
            round(float(r.get("costPerClick", 0)), 2),
        ])
    append(sheets["raw_data"], rows, headers)
    print(f"  ✅ Raw Data {market}: {len(rows)} рядків")


# ── Bid History ───────────────────────────────────────────────

def write_bid_snapshot(campaigns: list[dict], keywords: list[dict],
                       week: str, market: str):
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Week", "Campaign", "State", "Bidding Strategy",
               "ToS Adj%", "PP Adj%", "RoS Adj%",
               "Daily Budget", "Keyword", "Keyword Bid",
               "Match Type", "KW State"]
    rows = []

    kw_by_camp = {}
    for kw in keywords:
        cid = kw.get("campaignId", "")
        if cid not in kw_by_camp:
            kw_by_camp[cid] = []
        kw_by_camp[cid].append(kw)

    for c in campaigns:
        bidding = c.get("bidding", {})
        adj = {a["placement"]: a["percentage"]
               for a in bidding.get("adjustments", [])}
        camp_kws = kw_by_camp.get(str(c.get("campaignId", "")), [])

        if camp_kws:
            for kw in camp_kws:
                rows.append([
                    week,
                    c.get("name", ""),
                    c.get("state", ""),
                    bidding.get("strategy", ""),
                    adj.get("PLACEMENT_TOP", 0),
                    adj.get("PLACEMENT_PRODUCT_PAGE", 0),
                    adj.get("PLACEMENT_REST_OF_SEARCH", 0),
                    c.get("budget", {}).get("budget", 0),
                    kw.get("keywordText", ""),
                    kw.get("bid", 0),
                    kw.get("matchType", ""),
                    kw.get("state", ""),
                ])
        else:
            rows.append([
                week,
                c.get("name", ""),
                c.get("state", ""),
                bidding.get("strategy", ""),
                adj.get("PLACEMENT_TOP", 0),
                adj.get("PLACEMENT_PRODUCT_PAGE", 0),
                adj.get("PLACEMENT_REST_OF_SEARCH", 0),
                c.get("budget", {}).get("budget", 0),
                "", "", "", "",
            ])

    append(sheets["bid_history"], rows, headers)
    print(f"  ✅ Bid History {market}: {len(rows)} рядків")


# ── Placement Analysis ────────────────────────────────────────

def write_placement_analysis(placement_data: list[dict],
                              issues: list[dict],
                              week: str, market: str):
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Week", "Campaign", "Placement",
               "Impressions", "Clicks", "CTR%",
               "Spend", "Sales", "ACoS%",
               "Status", "Issue"]
    rows = []
    issue_camps = {i["campaign"] for i in issues}

    for r in placement_data:
        camp = r.get("campaignName", "")
        spend = float(r.get("spend", 0))
        sales = float(r.get("sales7d", 0))
        status = "⚠️ Проблема" if camp in issue_camps else "✅"
        issue_text = ""
        if camp in issue_camps:
            issue = next(i for i in issues if i["campaign"] == camp)
            issue_text = (f"PP={issue['pp_pct']}% при ToS adj "
                          f"{issue['tos_adj']}%")
        rows.append([
            week, camp,
            r.get("placement", ""),
            r.get("impressions", 0),
            r.get("clicks", 0),
            round(float(r.get("clickThroughRate", 0)) * 100, 2),
            round(spend, 2),
            round(sales, 2),
            round(spend / sales * 100 if sales > 0 else 0, 1),
            status, issue_text,
        ])
    append(sheets["placement_analysis"], rows, headers)
    print(f"  ✅ Placement Analysis {market}: {len(rows)} рядків")


# ── Campaign Analysis ─────────────────────────────────────────

def write_campaign_analysis(metrics: dict, week: str, market: str):
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Week", "Campaign", "Spend", "Sales",
               "Orders", "ACoS%", "ROAS", "Break-even ACoS%",
               "Impressions", "Status", "Budget Issue"]
    rows = []
    breakeven = metrics.get("breakeven_acos", 25)
    budget_issues = metrics.get("budget_issues", [])

    for name, vals in metrics.get("by_campaign", {}).items():
        spend = vals["spend"]
        sales = vals["sales"]
        acos  = spend / sales * 100 if sales > 0 else 0
        roas  = sales / spend if spend > 0 else 0

        if spend > 0 and sales == 0:
            status = "⚠️ Немає продажів"
        elif spend == 0:
            status = "😴 Немає активності"
        elif acos <= breakeven * 0.8:
            status = "✅ Прибутково"
        elif acos <= breakeven:
            status = "🟡 На межі"
        else:
            status = "🔴 Збитково"

        rows.append([
            week, name,
            round(spend, 2),
            round(sales, 2),
            vals["orders"],
            round(acos, 1),
            round(roas, 2),
            breakeven,
            vals["impressions"],
            status,
            "⚠️ Бюджет вичерпано" if name in budget_issues else "",
        ])
    append(sheets["campaign_analysis"], rows, headers)
    print(f"  ✅ Campaign Analysis {market}: {len(rows)} рядків")


# ── Keyword Intelligence ──────────────────────────────────────

def write_keyword_intelligence(keywords_analysis: list[dict],
                                week: str, market: str):
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Week", "Keyword", "Match Type", "Campaign",
               "Impressions", "Clicks", "Orders",
               "Spend", "Sales", "ACoS%", "ROAS",
               "Lifetime Sales", "Weeks Active",
               "Status", "Recommendation",
               "Listing Indexed", "Action"]
    rows = []
    for kw in keywords_analysis:
        rows.append([
            week,
            kw.get("keyword", ""),
            kw.get("match_type", ""),
            kw.get("campaign", ""),
            kw.get("impressions", 0),
            kw.get("clicks", 0),
            kw.get("orders", 0),
            round(kw.get("spend", 0), 2),
            round(kw.get("sales", 0), 2),
            round(kw.get("acos", 0), 1),
            round(kw.get("roas", 0), 2),
            round(kw.get("lifetime_sales", 0), 2),
            kw.get("weeks_active", 0),
            kw.get("status", ""),
            kw.get("recommendation", ""),
            kw.get("listing_indexed", ""),
            kw.get("action", ""),
        ])
    append(sheets["keyword_intelligence"], rows, headers)
    print(f"  ✅ Keyword Intelligence {market}: {len(rows)} рядків")


# ── AI Recommendations ────────────────────────────────────────

def write_ai_recommendations(text: str, week: str, market: str):
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Week", "Date", "Market", "AI Analysis"]
    sh = get_sheet(sheets["ai_recommendations"])
    existing = sh.get_all_values()
    if not existing:
        sh.append_row(headers)
    sh.append_row([week, datetime.now().strftime("%Y-%m-%d %H:%M"),
                   market, text])
    print(f"  ✅ AI Recommendations {market}: збережено")


# ── Weekly Summary ────────────────────────────────────────────

def write_weekly_summary(usa_metrics: dict, ca_metrics: dict,
                         week: str):
    headers = ["Week", "Market", "Spend", "Sales", "Net Profit",
               "Orders", "ACoS%", "ROAS", "TACoS%",
               "Break-even ACoS%", "Campaigns",
               "Top Campaign", "Worst Campaign",
               "Budget Issues"]
    rows = []
    for market, m in [("USA", usa_metrics), ("CA", ca_metrics)]:
        if not m:
            continue
        rows.append([
            week, market,
            m.get("total_spend", 0),
            m.get("total_sales", 0),
            m.get("net_profit", 0),
            m.get("total_orders", 0),
            m.get("overall_acos", 0),
            m.get("overall_roas", 0),
            round(m.get("tacos", 0) * 100, 2),
            m.get("breakeven_acos", 0),
            m.get("campaigns_count", 0),
            m.get("top_campaign", ""),
            m.get("worst_campaign", ""),
            ", ".join(m.get("budget_issues", [])),
        ])
    append(SHEETS_COMMON["weekly_summary"], rows, headers)
    print(f"  ✅ Weekly Summary: збережено")


# ── Alert Log ─────────────────────────────────────────────────

def log_alert(market: str, level: str, problem: str,
              diagnosis: str, action: str):
    headers = ["Date", "Market", "Level", "Problem",
               "Diagnosis", "Action"]
    sh = get_sheet(SHEETS_COMMON["alert_log"])
    existing = sh.get_all_values()
    if not existing:
        sh.append_row(headers)
    sh.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        market, level, problem, diagnosis, action,
    ])


# ── Читання всієї історії ─────────────────────────────────────

def get_full_history(market: str) -> dict:
    """Прочитати всю историю для AI аналізу."""
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    history = {}
    for key, name in sheets.items():
        history[key] = read_all(name)
        _sheets_time.sleep(5)  # уникаємо rate limit
    history["weekly_summary"] = read_all(SHEETS_COMMON["weekly_summary"])
    _sheets_time.sleep(5)
    history["monthly_summary"] = read_all(SHEETS_COMMON["monthly_summary"])
    return history
