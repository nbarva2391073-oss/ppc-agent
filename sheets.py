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
from datetime import datetime, timedelta
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
_creds_cache = None


def client():
    global _client_cache, _creds_cache
    if _client_cache is None:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        _creds_cache = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _client_cache = gspread.Client(auth=_creds_cache)
    return _client_cache


@_retry_sheets(max_retries=5, base_delay=5)
def get_sheet(name: str):
    ss = client().open_by_key(SPREADSHEET_ID)
    try:
        return ss.worksheet(name)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title=name, rows=2000, cols=60)



def _remove_tables(sh):
    """Видаляє всі TABLE об'єкти з аркуша через Google Sheets API v4."""
    try:
        import requests as _req
        import google.auth.transport.requests as _tr
        client()  # ініціалізуємо якщо ще не було
        if _creds_cache is None:
            print(f"  ⚠️ _remove_tables: credentials не ініціалізовано")
            return
        creds = _creds_cache
        if not creds.valid:
            creds.refresh(_tr.Request())
        token = creds.token
        if not token:
            print(f"  ⚠️ _remove_tables: токен порожній")
            return
        spreadsheet_id = sh.spreadsheet.id
        sheet_id = sh.id
        resp = _req.get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"includeGridData": "false"},
        )
        data = resp.json()
        table_ids = []
        for s in data.get("sheets", []):
            if s["properties"]["sheetId"] == sheet_id:
                for t in s.get("tables", []):
                    table_ids.append(t["tableId"])
                break
        if not table_ids:
            return
        batch_resp = _req.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"requests": [{"deleteTable": {"tableId": tid}} for tid in table_ids]},
        )
        if batch_resp.status_code == 200:
            print(f"  🗑️ Видалено {len(table_ids)} TABLE об'єкт(ів) з '{sh.title}'")
        else:
            print(f"  ⚠️ Помилка видалення TABLE: {batch_resp.status_code} {batch_resp.text[:200]}")
    except Exception as e:
        print(f"  ⚠️ Не вдалось видалити TABLE: {e}")


def append(sheet_name: str, rows: list, headers: list = None):
    """Додати рядки в аркуш (з заголовками якщо порожній)."""
    sh = get_sheet(sheet_name)

    # Видаляємо TABLE об'єкти якщо є — вони блокують запис
    _remove_tables(sh)

    existing = sh.get_all_values()
    if not existing:
        if headers:
            sh.append_row(headers)
    if rows:
        before = len(sh.get_all_values())
        next_row = before + 1
        sh.update(f"A{next_row}", rows)
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
        # ВИПРАВЛЕНО: Amazon Reporting API повертає 'cost', не 'spend'.
        # Через це поле раніше завжди читалось як 0, попри реальні Clicks.
        spend = float(r.get("cost") or r.get("spend") or 0)
        sales = float(r.get("sales7d", 0))
        ctr_raw = r.get("clickThroughRate")
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
            round(float(ctr_raw) * 100, 2) if ctr_raw else 0,
            round(spend, 2),
            round(sales, 2),
            round(spend / sales * 100 if sales > 0 else 0, 1),
            round(sales / spend if spend > 0 else 0, 2),
            r.get("purchases7d", 0),
            round(float(r.get("costPerClick", 0)), 2),
        ])
    append(sheets["raw_data"], rows, headers)
    print(f"  ✅ Raw Data {market}: {len(rows)} рядків")


# ── Suggested Bids (читання з Sheets) ───────────────────────────

def read_suggested_bids(market: str) -> dict:
    """
    Читає suggested bids з аркуша 'Suggested Bids USA/CA'.
    Повертає dict {keyword_text|match_type: {suggested, min, max}}.
    Ключ: 'keyword_text|EXACT' — однозначна ідентифікація.
    """
    sheet_name = f"Suggested Bids {market}"
    try:
        rows = read_all(sheet_name)
        if len(rows) <= 1:
            print(f"  ⚠️ Suggested Bids {market}: аркуш порожній")
            return {}
        header = rows[0]
        try:
            col_kw        = header.index("Keyword")
            col_match     = header.index("MatchType")
            col_suggested = header.index("SuggestedBid")
            col_min       = header.index("BidRangeMin")
            col_max       = header.index("BidRangeMax")
        except ValueError as e:
            print(f"  ⚠️ Suggested Bids {market}: колонка не знайдена — {e}")
            return {}

        result = {}
        for row in rows[1:]:
            if len(row) <= max(col_kw, col_match, col_suggested):
                continue
            kw        = row[col_kw]
            match     = row[col_match]
            suggested = row[col_suggested]
            bid_min   = row[col_min] if len(row) > col_min else ""
            bid_max   = row[col_max] if len(row) > col_max else ""

            def _f(v):
                try:
                    return float(str(v).replace(",", ".")) if v else 0.0
                except ValueError:
                    return 0.0

            key = f"{kw}|{match}"
            result[key] = {
                "suggested": _f(suggested),
                "min":       _f(bid_min),
                "max":       _f(bid_max),
            }

        print(f"  ✅ Suggested Bids {market}: {len(result)} ключів завантажено")
        return result
    except Exception as e:
        print(f"  ⚠️ Не вдалось прочитати Suggested Bids {market}: {e}")
        return {}


# ── Bid History ───────────────────────────────────────────────

BID_HEADERS = [
    "Date", "Campaign", "AdGroup", "Keyword",
    "OldBid", "NewBid", "SuggestedBid",
    "BidRangeMin", "BidRangeMax", "Reason",
    "ACoS_before", "Impressions_before", "over_breakeven",
]


def _get_last_bids(sheet_name: str) -> dict:
    """Читає останню записану ставку по кожному ключу з Bid History."""
    try:
        rows = read_all(sheet_name)
        if len(rows) <= 1:
            return {}
        headers_row = rows[0]
        try:
            col_kw   = headers_row.index("Keyword")
            col_bid  = headers_row.index("NewBid")
            col_acos = headers_row.index("ACoS_before")
            col_imp  = headers_row.index("Impressions_before")
        except ValueError:
            return {}
        last = {}
        for row in rows[1:]:
            if len(row) <= max(col_kw, col_bid):
                continue
            kw   = row[col_kw]
            bid  = row[col_bid]
            acos = row[col_acos] if len(row) > col_acos else ""
            imp  = row[col_imp]  if len(row) > col_imp  else ""
            if kw:
                def _f(v):
                    try:
                        return float(str(v).replace(",", ".")) if v else 0.0
                    except ValueError:
                        return 0.0
                last[kw] = {
                    "bid":  _f(bid),
                    "acos": _f(acos),
                    "imp":  _f(imp),
                }
        return last
    except Exception as e:
        print(f"  ⚠️ Не вдалось прочитати Bid History: {e}")
        return {}


def write_bid_snapshot(campaigns: list, keywords: list,
                       week: str, market: str,
                       suggested_bids: dict = None,
                       raw_data: list = None):
    """
    Записує зміни ставок в Bid History.
    Умова А: ставка змінилась порівняно з останнім записом.
    Умова Б: ACoS виріс >20% або покази впали >30% за останні 7 днів.
    """
    from amazon_ads import ASIN_PRICE_CONFIG, BID_CONFIG

    sheets     = SHEETS_USA if market == "USA" else SHEETS_CA
    sheet_name = sheets["bid_history"]
    today      = datetime.now().strftime("%Y-%m-%d")

    last_bids = _get_last_bids(sheet_name)

    # ACoS і покази з raw_data по ключовому слову
    recent_metrics = {}
    if raw_data:
        for r in raw_data:
            kw = r.get("keyword") or r.get("searchTerm", "")
            if not kw:
                continue
            recent_metrics.setdefault(kw, {"spend": 0.0, "sales": 0.0, "impressions": 0})
            recent_metrics[kw]["spend"]       += float(r.get("cost") or r.get("spend") or 0)
            recent_metrics[kw]["sales"]       += float(r.get("sales7d", 0))
            recent_metrics[kw]["impressions"] += int(r.get("impressions", 0))

    # Тільки активні кампанії
    active_campaigns = [c for c in campaigns
                        if str(c.get("state", "")).upper() == "ENABLED"]
    print(f"  📊 Bid History: {len(active_campaigns)} активних з {len(campaigns)} кампаній")

    kw_by_camp = {}
    for kw in keywords:
        cid = str(kw.get("campaignId", ""))
        kw_by_camp.setdefault(cid, []).append(kw)

    suggested_bids = suggested_bids or {}
    rows = []

    for c in active_campaigns:
        camp_name = c.get("name", "")
        camp_id   = str(c.get("campaignId", ""))
        camp_kws  = kw_by_camp.get(camp_id, [])

        for kw in camp_kws:
            kw_text     = kw.get("keywordText", "")
            kw_id       = str(kw.get("keywordId", ""))
            adgroup     = kw.get("adGroupName", "")
            current_bid = float(kw.get("bid", 0))

            last    = last_bids.get(kw_text, {})
            old_bid = last.get("bid", 0.0)
            old_acos = last.get("acos", 0.0)
            old_imp  = last.get("imp", 0.0)

            # Ключ для пошуку: keyword_text|match_type
            match_type = str(kw.get("matchType", kw.get("match_type", ""))).upper()
            sb_key    = f"{kw_text}|{match_type}"
            sb_data   = suggested_bids.get(sb_key, {})
            suggested = sb_data.get("suggested", 0.0)
            bid_min   = sb_data.get("min", 0.0)
            bid_max   = sb_data.get("max", 0.0)

            metrics    = recent_metrics.get(kw_text, {})
            curr_spend = metrics.get("spend", 0.0)
            curr_sales = metrics.get("sales", 0.0)
            curr_imp   = metrics.get("impressions", 0)
            curr_acos  = round(curr_spend / curr_sales * 100
                               if curr_sales > 0 else 0, 1)

            # Умова А або Б
            reason = None
            if old_bid == 0 or abs(current_bid - old_bid) > 0.001:
                reason = "bid_changed"
            elif old_acos > 0 and curr_acos > old_acos * 1.20:
                reason = "market_shift"
            elif old_imp > 0 and curr_imp < old_imp * 0.70:
                reason = "market_shift"

            if reason is None:
                continue

            # over_breakeven по ASIN з назви кампанії
            max_cpc = 0.55
            for asin, cfg in ASIN_PRICE_CONFIG.items():
                if asin in camp_name:
                    max_cpc = cfg["max_cpc"]
                    break
            over_breakeven = suggested > max_cpc if suggested > 0 else False

            rows.append([
                today, camp_name, adgroup, kw_text,
                round(old_bid, 2), round(current_bid, 2),
                round(suggested, 2), round(bid_min, 2), round(bid_max, 2),
                reason,
                round(curr_acos, 1), curr_imp,
                "true" if over_breakeven else "false",
            ])

    if rows:
        append(sheet_name, rows, BID_HEADERS)
        print(f"  ✅ Bid History {market}: {len(rows)} змін записано")
    else:
        print(f"  ℹ️ Bid History {market}: змін ставок не виявлено")

# ── Placement Analysis ────────────────────────────────────────

def _cleanup_placement(sh, headers: list):
    """Видаляє рядки старші 730 днів і записи з форматом YYYY-W## (некоректні)."""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=730)

    try:
        rows = sh.get_all_values()
        if len(rows) <= 1:
            return

        keep = [rows[0]]  # заголовок завжди лишаємо
        removed = 0

        for row in rows[1:]:
            if not row or not row[0]:
                continue
            week_val = row[0]

            # Видаляємо старий формат YYYY-W## (наприклад 2026-W22)
            if len(week_val) <= 8 and "-W" in week_val:
                removed += 1
                continue

            # Парсимо формат DD.MM-DD.MM.YYYY
            try:
                end_part = week_val.split("-")[-1]  # DD.MM.YYYY
                row_date = datetime.strptime(end_part, "%d.%m.%Y")
                if row_date < cutoff:
                    removed += 1
                    continue
            except ValueError:
                pass  # невідомий формат — лишаємо

            keep.append(row)

        if removed > 0:
            sh.clear()
            sh.update(keep, "A1")
            print(f"  🧹 Placement Analysis: видалено {removed} застарілих/некоректних рядків")
    except Exception as e:
        print(f"  ⚠️ _cleanup_placement: {e}")


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
            r.get("placementClassification") or r.get("placement") or r.get("campaignPlacement", ""),
            r.get("impressions", 0),
            r.get("clicks", 0),
            round(float(r.get("clickThroughRate", 0)) * 100, 2),
            round(spend, 2),
            round(sales, 2),
            round(spend / sales * 100 if sales > 0 else 0, 1),
            status, issue_text,
        ])
    sheet_name = sheets["placement_analysis"]

    # Гарантуємо заголовки
    sh = get_sheet(sheet_name)
    first_row = sh.row_values(1)
    if not first_row or first_row[0] != "Week":
        sh.update([headers], "A1")
        print(f"  📝 Заголовки додано в '{sheet_name}'")

    # Ротація: видаляємо записи старші 730 днів
    _cleanup_placement(sh, headers)

    append(sheet_name, rows, headers)
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
                                week: str, market: str, run_date: str = None):
    """
    Кожен виклик передає дані ОДНОГО дня (targeting-звіт monitor.py
    запитує тільки за вчора). Щоб повторний запуск того самого дня
    (ручний тест, retry) не дублював рядки і не накручував Sales/Orders
    у тижневому підсумку — робимо upsert по (Week, Keyword, Match Type,
    Campaign, Run Date): видаляємо старий рядок з тим самим ключем
    перед записом нового.
    """
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Week", "Keyword", "Match Type", "Campaign", "Run Date",
               "Impressions", "Clicks", "Orders",
               "Spend", "Sales", "ACoS%", "ROAS",
               "Lifetime Sales", "Weeks Active",
               "Status", "Recommendation",
               "Listing Indexed", "Action"]

    if run_date is None:
        from datetime import datetime
        run_date = datetime.utcnow().strftime("%Y-%m-%d")

    rows = []
    for kw in keywords_analysis:
        rows.append([
            week,
            kw.get("keyword", ""),
            kw.get("match_type", ""),
            kw.get("campaign", ""),
            run_date,
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

    sheet_name = sheets["keyword_intelligence"]
    sh = get_sheet(sheet_name)
    existing = sh.get_all_values()

    if not existing or not existing[0] or existing[0][0] != "Week":
        sh.clear()
        sh.update([headers] + rows, "A1")
        print(f"  📝 '{sheet_name}': заголовки (з Run Date) + {len(rows)} рядків записано")
        return

    header_row = existing[0]
    if "Run Date" not in header_row:
        # Старий формат без Run Date — не можемо коректно робити upsert,
        # просто дописуємо (backward compatibility для вже існуючих даних)
        append(sheet_name, rows, headers)
        return

    idx_week   = header_row.index("Week")
    idx_kw     = header_row.index("Keyword")
    idx_match  = header_row.index("Match Type")
    idx_camp   = header_row.index("Campaign")
    idx_rundate = header_row.index("Run Date")

    def key_of(row):
        return (row[idx_week], row[idx_kw], row[idx_match], row[idx_camp], row[idx_rundate])

    new_keys = {(week, r[1], r[2], r[3], run_date) for r in rows}

    kept = [header_row]
    removed = 0
    for row in existing[1:]:
        if len(row) > idx_rundate and key_of(row) in new_keys:
            removed += 1
            continue
        kept.append(row)

    if removed:
        print(f"  🔄 '{sheet_name}': замінено {removed} рядків за {run_date} (upsert)")

    final_rows = kept + rows
    sh.clear()
    sh.update(final_rows, "A1")
    print(f"  ✅ '{sheet_name}': {len(rows)} рядків записано")
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


# ── Автоочищення Bid History ──────────────────────────────────

def cleanup_bid_history(market: str):
    """
    Видаляє записи старші 90 днів де метрики не змінились значимо
    за 14 днів після запису (ACoS ±5%, покази ±10%).
    Записи зі значимим результатом — не видаляти ніколи.
    Запускати раз на тиждень.
    """
    sheets     = SHEETS_USA if market == "USA" else SHEETS_CA
    sheet_name = sheets["bid_history"]
    today      = datetime.now()
    cutoff_90  = today - timedelta(days=90)
    cutoff_14  = today - timedelta(days=14)

    try:
        sh   = get_sheet(sheet_name)
        rows = sh.get_all_values()
        if len(rows) <= 1:
            return

        header = rows[0]
        try:
            col_date = header.index("Date")
            col_acos = header.index("ACoS_before")
            col_imp  = header.index("Impressions_before")
        except ValueError:
            print(f"  ⚠️ cleanup_bid_history: не знайдено потрібних колонок")
            return

        keep   = [header]
        removed = 0

        for row in rows[1:]:
            if len(row) <= col_date:
                keep.append(row)
                continue
            try:
                row_date = datetime.strptime(row[col_date], "%Y-%m-%d")
            except ValueError:
                keep.append(row)
                continue

            # Свіжіші 90 днів — завжди лишаємо
            if row_date >= cutoff_90:
                keep.append(row)
                continue

            # Старіші 90 днів — перевіряємо чи були значимі зміни
            # Якщо запис зроблено менше ніж 14 днів тому — ще рано видаляти
            if row_date >= cutoff_14:
                keep.append(row)
                continue

            acos_val = row[col_acos] if len(row) > col_acos else ""
            imp_val  = row[col_imp]  if len(row) > col_imp  else ""

            try:
                acos = float(acos_val) if acos_val else 0.0
                imp  = float(imp_val)  if imp_val  else 0.0
            except ValueError:
                keep.append(row)
                continue

            # Вважаємо запис "без значимого результату" якщо
            # ACoS і покази близькі до нуля (немає даних після зміни)
            has_significant = (acos > 5.0 or imp > 100)

            if has_significant:
                keep.append(row)
            else:
                removed += 1

        if removed > 0:
            sh.clear()
            sh.update(keep, "A1")
            print(f"  🧹 Bid History {market}: видалено {removed} застарілих записів")
        else:
            print(f"  ✅ Bid History {market}: застарілих записів немає")

    except Exception as e:
        print(f"  ❌ cleanup_bid_history {market}: {e}")


# ── Автоочищення Raw Data ─────────────────────────────────────

def cleanup_raw_data(market: str):
    """
    Зберігає тільки останні 30 днів у Raw Data.
    Старіші записи видаляються автоматично щодня.
    """
    sheets     = SHEETS_USA if market == "USA" else SHEETS_CA
    sheet_name = sheets["raw_data"]
    cutoff     = datetime.now() - timedelta(days=30)

    try:
        sh   = get_sheet(sheet_name)
        rows = sh.get_all_values()
        if len(rows) <= 1:
            return

        header = rows[0]
        try:
            col_week = header.index("Week")
        except ValueError:
            print(f"  ⚠️ cleanup_raw_data: колонка 'Week' не знайдена")
            return

        keep    = [header]
        removed = 0

        for row in rows[1:]:
            if len(row) <= col_week:
                keep.append(row)
                continue

            week_val = row[col_week]
            # Формат тижня: DD.MM-DD.MM.YYYY — беремо кінцеву дату
            try:
                if "-" in week_val and "." in week_val:
                    end_part = week_val.split("-")[-1]  # DD.MM.YYYY
                    row_date = datetime.strptime(end_part, "%d.%m.%Y")
                else:
                    # Формат YYYY-MM-DD або інший
                    row_date = datetime.strptime(week_val[:10], "%Y-%m-%d")
            except ValueError:
                keep.append(row)
                continue

            if row_date >= cutoff:
                keep.append(row)
            else:
                removed += 1

        if removed > 0:
            sh.clear()
            sh.update(keep, "A1")
            print(f"  🧹 Raw Data {market}: видалено {removed} записів старших 30 днів")
        else:
            print(f"  ✅ Raw Data {market}: всі записи в межах 30 днів")

    except Exception as e:
        print(f"  ❌ cleanup_raw_data {market}: {e}")


# ── Advertised Product ──────────────────────────────────────

def write_advertised_product(data: list[dict], date: str, market: str):
    """
    Продажі окремо по ASIN через рекламу (Advertised Product Report).
    date — конкретний день (YYYY-MM-DD), НЕ тиждень — звіт фактично
    містить дані за один день, і date потрібен для точного зіставлення
    з Business Report при розрахунку TACoS.
    """
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    headers = ["Date", "Campaign", "Ad Group", "ASIN",
               "Impressions", "Clicks", "Spend",
               "Orders (Ad)", "Sales (Ad)", "ACoS%", "CPC"]
    rows = []
    for r in data:
        spend = float(r.get("cost", 0))
        sales = float(r.get("sales14d", 0))
        clicks = int(r.get("clicks", 0))
        rows.append([
            date,
            r.get("campaignName", ""),
            r.get("adGroupName", ""),
            r.get("advertisedAsin", ""),
            r.get("impressions", 0),
            clicks,
            round(spend, 2),
            r.get("purchases14d", 0),
            round(sales, 2),
            round(spend / sales * 100 if sales > 0 else 0, 1),
            round(spend / clicks if clicks > 0 else 0, 2),
        ])

    sheet_name = sheets.get("advertised_product", f"Advertised Product {market}")
    ensure_headers = _ensure_headers if "_ensure_headers" in globals() else None
    sh = get_sheet(sheet_name)
    first_row = sh.row_values(1)
    if not first_row or first_row[0] != "Week":
        sh.update([headers], "A1")
        print(f"  📝 Заголовки додано в '{sheet_name}'")

    append(sheet_name, rows, headers)
    print(f"  ✅ Advertised Product {market}: {len(rows)} рядків")


# ── TACoS (Total ACoS) — органіка vs реклама по ASIN ──────────

def calculate_tacos(market: str, date: str):
    """
    Зводить Advertised Product і Business Report по ASIN за конкретний день.
    Пише результат у TACoS_USA/CA.

    Edge cases:
    - ASIN є в Business Report, немає в Advertised Product → Ad_Spend=0, Ad_Sales=0, Organic_Share=100%
    - ASIN є в Advertised Product, немає в Business Report → Total_Sales=0, TACoS%=None, Organic_Share%=None
    """
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA
    adv_sheet_name = sheets.get("advertised_product", f"Advertised Product {market}")
    biz_sheet_name = f"Business_Report_{market}"
    tacos_sheet_name = f"TACoS_{market}"

    # Читаємо Advertised Product за цей день
    adv_by_asin = {}
    try:
        rows = read_all(adv_sheet_name)
        if len(rows) > 1:
            header = rows[0]
            col_date = header.index("Date")
            col_asin = header.index("ASIN")
            col_spend = header.index("Spend")
            col_sales = header.index("Sales (Ad)")
            for row in rows[1:]:
                if len(row) <= max(col_date, col_asin, col_spend, col_sales):
                    continue
                if row[col_date] != date:
                    continue
                asin = row[col_asin]
                if not asin:
                    continue
                if asin not in adv_by_asin:
                    adv_by_asin[asin] = {"spend": 0.0, "sales": 0.0}
                try:
                    adv_by_asin[asin]["spend"] += float(str(row[col_spend]).replace(",", "."))
                except ValueError:
                    pass
                try:
                    adv_by_asin[asin]["sales"] += float(str(row[col_sales]).replace(",", "."))
                except ValueError:
                    pass
    except Exception as e:
        print(f"  ⚠️ TACoS: не вдалось прочитати {adv_sheet_name}: {e}")

    # Читаємо Business Report за цей день
    total_sales_by_asin = {}
    try:
        rows = read_all(biz_sheet_name)
        if len(rows) > 1:
            header = rows[0]
            col_date = header.index("Дата")
            col_asin = header.index("ASIN")
            col_sales = header.index("Ordered Product Sales")
            for row in rows[1:]:
                if len(row) <= max(col_date, col_asin, col_sales):
                    continue
                if row[col_date] != date:
                    continue
                asin = row[col_asin]
                if not asin:
                    continue
                try:
                    val = float(str(row[col_sales]).replace(",", "."))
                except ValueError:
                    val = 0.0
                total_sales_by_asin[asin] = total_sales_by_asin.get(asin, 0.0) + val
    except Exception as e:
        print(f"  ⚠️ TACoS: не вдалось прочитати {biz_sheet_name}: {e}")

    # Об'єднуємо всі ASIN з обох джерел — тільки наші активні ASIN
    from amazon_ads import ASIN_PRICE_CONFIG
    our_asins = set(ASIN_PRICE_CONFIG.keys())
    all_asins = (set(adv_by_asin.keys()) | set(total_sales_by_asin.keys())) & our_asins
    if not all_asins:
        print(f"  ℹ️ TACoS {market}: немає даних за {date}")
        return

    headers = ["Date", "ASIN", "Ad_Spend", "Ad_Sales",
               "Total_Sales", "Organic_Sales",
               "TACoS%", "ACoS%", "Organic_Share%"]
    rows_out = []

    for asin in sorted(all_asins):
        ad_spend = round(adv_by_asin.get(asin, {}).get("spend", 0.0), 2)
        ad_sales = round(adv_by_asin.get(asin, {}).get("sales", 0.0), 2)
        total_sales = total_sales_by_asin.get(asin)  # None якщо ASIN не в Business Report

        if total_sales is None:
            # Edge case: є в Advertised Product, немає в Business Report
            total_sales_val = ""
            organic_sales = ""
            tacos_pct = ""
            organic_share_pct = ""
        else:
            total_sales_val = round(total_sales, 2)
            organic_sales = round(total_sales - ad_sales, 2)
            tacos_pct = round(ad_spend / total_sales * 100, 1) if total_sales > 0 else ""
            organic_share_pct = round(organic_sales / total_sales * 100, 1) if total_sales > 0 else ""

        acos_pct = round(ad_spend / ad_sales * 100, 1) if ad_sales > 0 else ""

        rows_out.append([
            date, asin, ad_spend, ad_sales,
            total_sales_val, organic_sales,
            tacos_pct, acos_pct, organic_share_pct,
        ])

    sh = get_sheet(tacos_sheet_name)
    existing = sh.get_all_values()

    if not existing or not existing[0] or existing[0][0] != "Date":
        sh.clear()
        sh.update([headers] + rows_out, "A1")
        print(f"  📝 Заголовки додано в '{tacos_sheet_name}'")
        print(f"  ✅ TACoS {market}: {len(rows_out)} ASIN записано")
        return

    kept = [existing[0]]
    removed = 0
    for row in existing[1:]:
        if row and row[0] == date:
            removed += 1
            continue
        kept.append(row)

    if removed > 0:
        print(f"  🔄 TACoS {market}: замінено {removed} старих рядків за {date}")

    final_rows = kept + rows_out
    sh.clear()
    sh.update(final_rows, "A1")
    print(f"  ✅ TACoS {market}: {len(rows_out)} ASIN записано")


def cleanup_tacos(market: str):
    """Видаляє записи TACoS старші 730 днів (24 місяці)."""
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=730)
    sheet_name = f"TACoS_{market}"

    try:
        sh = get_sheet(sheet_name)
        rows = sh.get_all_values()
        if len(rows) <= 1:
            return

        keep = [rows[0]]
        removed = 0
        for row in rows[1:]:
            if not row or not row[0]:
                continue
            try:
                row_date = datetime.strptime(row[0], "%Y-%m-%d")
                if row_date < cutoff:
                    removed += 1
                    continue
            except ValueError:
                pass  # невідомий формат — лишаємо
            keep.append(row)

        if removed > 0:
            sh.clear()
            sh.update(keep, "A1")
            print(f"  🧹 TACoS {market}: видалено {removed} записів старших 730 днів")
    except Exception as e:
        print(f"  ⚠️ cleanup_tacos {market}: {e}")
