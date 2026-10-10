# ============================================================
# SPONSORED BRANDS — збір SB даних (USA)
#
# Переписано 10.10.2026 за результатами аудиту (див. diag/sb_audit):
#  - звіти DAILY: у кожному рядку фактична дата (колонка Date) і ID;
#  - тиждень (Week) рахується від Date рядка, а не від today;
#  - upsert: усі рядки з Date у запитаному вікні ЗАМІНЮЮТЬСЯ новими
#    (повторний запуск не міняє кількість рядків і не дублює;
#    пізня атрибуція покупок підтягується перезбором останніх днів);
#  - вікно запиту = рівні дні [start, end]; раніше start=вчора,end=сьогодні
#    захоплювало ДВА дні;
#  - кампанії всіх станів (пагінація) для перевірки покриття;
#  - Campaign: ключ (Date, CampaignId); SearchTerm: ключ
#    (Date, CampaignId, AdGroupId, KeywordId, Search Term).
#
# Запуск:
#   python sponsored_brands.py                       # останні 3 дні
#   python sponsored_brands.py --backfill FROM TO    # історія, з бекапом
# ============================================================

import csv
import os
import re
import sys
import time
from datetime import datetime, timedelta, date as _date

import requests

from amazon_ads import (
    get_access_token, headers, ADS_BASE_URL, wait_and_download,
)
from sheets import get_sheet

SB_CAMPAIGN_SHEET    = "SB_Campaign_USA"
SB_SEARCH_TERM_SHEET = "SB_SearchTerm_USA"
REFRESH_DAYS = 3          # скільки останніх днів перезбирати щодня
MAX_CHUNK_DAYS = 31       # ліміт DAILY-звіту Amazon

COLS_SB_CAMPAIGN = [
    "date", "campaignId", "campaignName", "campaignStatus",
    "impressions", "clicks", "cost", "sales", "purchases", "unitsSold",
    "newToBrandSales", "newToBrandPurchases",
]
COLS_SB_SEARCH_TERM = [
    "date", "campaignId", "campaignName", "adGroupId", "adGroupName",
    "keywordId", "keywordText", "matchType", "searchTerm",
    "impressions", "clicks", "cost", "sales", "purchases", "unitsSold",
]

# Існуючі колонки не зсуваємо; нові дописуються праворуч.
CAMPAIGN_HEADERS = ["Week", "Campaign", "Status", "Impressions", "Clicks", "Cost",
                    "Sales", "Purchases", "Units Sold", "New-to-Brand Sales",
                    "New-to-Brand Purchases", "ACoS%", "Ринок",
                    "Date", "CampaignId"]
SEARCH_HEADERS = ["Week", "Campaign", "Ad Group", "Keyword", "Match Type", "Search Term",
                  "Impressions", "Clicks", "Cost", "Sales", "Purchases", "Units Sold",
                  "ACoS%", "Ринок",
                  "Date", "CampaignId", "AdGroupId", "KeywordId"]
ID_COLS = {"CampaignId", "AdGroupId", "KeywordId"}


# ── Допоміжне ────────────────────────────────────────────────

def week_label(d: str) -> str:
    x = _date.fromisoformat(d)
    mon = x - timedelta(days=x.weekday())
    return f"{mon.strftime('%d.%m')}-{(mon + timedelta(days=6)).strftime('%d.%m.%Y')}"


def _acos(cost, sales):
    return round(cost / sales * 100, 1) if sales > 0 else 0


def _num(v):
    return float(v or 0)


def build_campaign_rows(data: list, market: str = "USA") -> list:
    """list[dict] з Amazon → list[dict] за назвами колонок аркуша."""
    rows = []
    for r in data:
        cost, sales = _num(r.get("cost")), _num(r.get("sales"))
        rows.append({
            "Week": week_label(r["date"]), "Campaign": r.get("campaignName", ""),
            "Status": r.get("campaignStatus", ""),
            "Impressions": r.get("impressions", 0), "Clicks": r.get("clicks", 0),
            "Cost": round(cost, 2), "Sales": round(sales, 2),
            "Purchases": r.get("purchases", 0), "Units Sold": r.get("unitsSold", 0),
            "New-to-Brand Sales": round(_num(r.get("newToBrandSales")), 2),
            "New-to-Brand Purchases": r.get("newToBrandPurchases", 0),
            "ACoS%": _acos(cost, sales), "Ринок": market,
            "Date": r["date"], "CampaignId": str(r.get("campaignId", "")),
        })
    return rows


def build_search_rows(data: list, market: str = "USA") -> list:
    rows = []
    for r in data:
        cost, sales = _num(r.get("cost")), _num(r.get("sales"))
        rows.append({
            "Week": week_label(r["date"]), "Campaign": r.get("campaignName", ""),
            "Ad Group": r.get("adGroupName", ""), "Keyword": r.get("keywordText", ""),
            "Match Type": r.get("matchType", ""), "Search Term": r.get("searchTerm", ""),
            "Impressions": r.get("impressions", 0), "Clicks": r.get("clicks", 0),
            "Cost": round(cost, 2), "Sales": round(sales, 2),
            "Purchases": r.get("purchases", 0), "Units Sold": r.get("unitsSold", 0),
            "ACoS%": _acos(cost, sales), "Ринок": market,
            "Date": r["date"], "CampaignId": str(r.get("campaignId", "")),
            "AdGroupId": str(r.get("adGroupId", "")), "KeywordId": str(r.get("keywordId", "")),
        })
    return rows


def _cell(col: str, v):
    """Значення для запису. ID — як текст (апостроф), щоб не стали 5.57E+14."""
    if v is None:
        return ""
    if col in ID_COLS and str(v).strip() != "":
        return "'" + str(v).lstrip("'")
    return v


def plan_replace(existing: list, headers_wanted: list, new_rows: list,
                 date_from: str, date_to: str, drop_undated: bool, sort_key):
    """
    Чиста функція (тестується офлайн). Повертає (header, table_rows, stats).
    Видаляє рядки з Date у [date_from, date_to] (і без Date, якщо
    drop_undated), додає нові, дописує відсутні колонки праворуч.
    """
    header = list(existing[0]) if existing and existing[0] else []
    for h in headers_wanted:
        if h not in header:
            header.append(h)
    old_header = existing[0] if existing else []
    oi = {h: i for i, h in enumerate(old_header)}
    di = oi.get("Date")

    kept, removed_dated, removed_undated = [], 0, 0
    for r in (existing[1:] if existing else []):
        d = r[di] if di is not None and di < len(r) else ""
        if d:
            if date_from <= d <= date_to:
                removed_dated += 1
                continue
        elif drop_undated:
            removed_undated += 1
            continue
        rec = {h: (r[oi[h]] if oi[h] < len(r) else "") for h in old_header if h in oi}
        kept.append(rec)
    allrecs = kept + list(new_rows)
    allrecs.sort(key=lambda rec: sort_key(rec))
    table = [[_cell(h, rec.get(h, "")) for h in header] for rec in allrecs]
    return header, table, {"removed_dated": removed_dated, "removed_undated": removed_undated,
                           "kept": len(kept), "added": len(new_rows), "total": len(table)}


def _sort_campaign(rec):
    return (str(rec.get("Date", "")), str(rec.get("Campaign", "")))


def _sort_search(rec):
    return (str(rec.get("Date", "")), str(rec.get("Campaign", "")),
            str(rec.get("Ad Group", "")), str(rec.get("Search Term", "")))


def apply_plan(sh, header, table, old_len):
    sh.update([header] + table, "A1", value_input_option="USER_ENTERED")
    new_len = len(table) + 1
    if old_len > new_len:
        sh.batch_clear([f"A{new_len + 1}:Z{old_len}"])


def backup_sheets(tag: str) -> str:
    out = os.path.join("backups", f"{tag}_sb_pre_fix")
    os.makedirs(out, exist_ok=True)
    for name in (SB_CAMPAIGN_SHEET, SB_SEARCH_TERM_SHEET):
        vals = get_sheet(name).get_all_values()
        with open(os.path.join(out, f"{name}.csv"), "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(vals)
        print(f"  💾 Бекап {name}: {len(vals)} рядків → {out}")
    return out


# ── Amazon ───────────────────────────────────────────────────

def get_sb_campaigns_all(token: str, profile_id: str) -> list:
    """Усі SB-кампанії всіх станів, з пагінацією (для перевірки покриття)."""
    ct = "application/vnd.sbcampaignresource.v4+json"
    out, nxt = [], None
    while True:
        body = {"maxResults": 100}
        if nxt:
            body["nextToken"] = nxt
        r = requests.post(f"{ADS_BASE_URL}/sb/v4/campaigns/list",
                          headers=headers(token, profile_id, content_type=ct), json=body)
        if r.status_code != 200:
            print(f"  ⚠️ SB campaigns list: {r.status_code} {r.text[:200]}")
            break
        d = r.json()
        out += d.get("campaigns", [])
        nxt = d.get("nextToken")
        if not nxt:
            break
    return out


def submit_daily(token, profile_id, name, report_type, columns, group_by, start, end) -> str:
    payload = {
        "name": name, "startDate": start, "endDate": end,
        "configuration": {
            "adProduct": "SPONSORED_BRANDS", "groupBy": group_by, "columns": columns,
            "reportTypeId": report_type, "timeUnit": "DAILY", "format": "GZIP_JSON",
        },
    }
    for attempt in range(5):
        r = requests.post(f"{ADS_BASE_URL}/reporting/reports",
                          headers=headers(token, profile_id), json=payload)
        if r.status_code in (200, 202):
            return r.json()["reportId"]
        m = re.search(r"duplicate of\s*:\s*([\w-]+)", r.text)
        if m:
            print(f"  ℹ️ {name}: duplicate, перевикористовуємо {m.group(1)}")
            return m.group(1)
        if r.status_code == 429:
            print(f"  ⏳ 429 — чекаємо 65с (спроба {attempt + 1}/5)")
            time.sleep(65)
            continue
        break
    raise Exception(f"Звіт {name} не створено ({r.status_code}): {r.text[:300]}")


def fetch_range(profile_id: str, start: str, end: str):
    """DAILY Campaign + SearchTerm за [start, end]. Повертає (campaign_data, st_data)."""
    token = get_access_token()
    cid = submit_daily(token, profile_id, f"SB Campaign {start}..{end}", "sbCampaigns",
                       COLS_SB_CAMPAIGN, ["campaign"], start, end)
    time.sleep(65)
    sid = submit_daily(token, profile_id, f"SB SearchTerm {start}..{end}", "sbSearchTerm",
                       COLS_SB_SEARCH_TERM, ["searchTerm"], start, end)
    camp = wait_and_download(get_access_token(), profile_id, cid, max_wait=3300, token_fn=get_access_token)
    st = wait_and_download(get_access_token(), profile_id, sid, max_wait=3300, token_fn=get_access_token)
    return camp, st


def chunks(start: str, end: str):
    s, e = _date.fromisoformat(start), _date.fromisoformat(end)
    while s <= e:
        c_end = min(s + timedelta(days=MAX_CHUNK_DAYS - 1), e)
        yield s.isoformat(), c_end.isoformat()
        s = c_end + timedelta(days=1)


def sanity_check(camp: list, st: list):
    """Джерело має сходитись: Campaign і SearchTerm мають однакові витрати по (date, campaign)."""
    a, b = {}, {}
    for r in camp:
        a[(r["date"], str(r["campaignId"]))] = a.get((r["date"], str(r["campaignId"])), 0) + _num(r.get("cost"))
    for r in st:
        b[(r["date"], str(r["campaignId"]))] = b.get((r["date"], str(r["campaignId"])), 0) + _num(r.get("cost"))
    bad = [(k, round(a.get(k, 0), 2), round(b.get(k, 0), 2))
           for k in set(a) | set(b) if abs(a.get(k, 0) - b.get(k, 0)) > 0.011]
    print(f"  🔎 Звірка Campaign↔SearchTerm по (дата, кампанія): розбіжностей {len(bad)}")
    for x in bad[:10]:
        print("     ", x)
    return bad


def write_range(camp: list, st: list, start: str, end: str, drop_undated: bool):
    pairs = (
        (SB_CAMPAIGN_SHEET, CAMPAIGN_HEADERS, build_campaign_rows(camp), _sort_campaign),
        (SB_SEARCH_TERM_SHEET, SEARCH_HEADERS, build_search_rows(st), _sort_search),
    )
    for sheet_name, hdrs, rows, skey in pairs:
        sh = get_sheet(sheet_name)
        existing = sh.get_all_values()
        header, table, stats = plan_replace(existing, hdrs, rows, start, end, drop_undated, skey)
        apply_plan(sh, header, table, len(existing))
        print(f"  ✅ {sheet_name}: {stats}")
        time.sleep(3)


# ── Режими ───────────────────────────────────────────────────

def run_daily():
    from config import ADS_PROFILE_ID_USA
    if not ADS_PROFILE_ID_USA:
        print("⏭️  profile_id USA не задано")
        return
    today = datetime.utcnow().date()
    end = (today - timedelta(days=1)).isoformat()
    start = (today - timedelta(days=REFRESH_DAYS)).isoformat()
    print(f"📢 SB daily: перезбір {start}..{end}")
    token = get_access_token()
    camps = get_sb_campaigns_all(token, ADS_PROFILE_ID_USA)
    print(f"  ✅ SB кампанії (усі стани): {len(camps)}")
    camp, st = fetch_range(ADS_PROFILE_ID_USA, start, end)
    if not camp:
        print("  ⚠️ порожній Campaign-звіт — нічого не пишемо")
        return
    if sanity_check(camp, st):
        print("  ❌ Campaign і SearchTerm не сходяться — не пишемо")
        return
    write_range(camp, st, start, end, drop_undated=False)


def run_backfill(start: str, end: str):
    from config import ADS_PROFILE_ID_USA
    backup_dir = "(зроблено окремим кроком workflow)"
    if not os.environ.get("SB_BACKUP_DONE"):
        backup_dir = backup_sheets(datetime.utcnow().strftime("%Y-%m-%d_%H%M%S"))
    camp_all, st_all = [], []
    for s, e in chunks(start, end):
        print(f"📥 Backfill {s}..{e}")
        c, t = fetch_range(ADS_PROFILE_ID_USA, s, e)
        camp_all += c
        st_all += t
        time.sleep(65)
    if not camp_all or sanity_check(camp_all, st_all):
        print("❌ Джерело неповне або не сходиться — вкладки НЕ змінено, бекап лишається")
        sys.exit(1)
    # Усі старі рядки без Date відомо хибні (мітка тижня зсунута, затирання
    # по ключу) і повністю перекриті backfill-діапазоном → замінюємо.
    write_range(camp_all, st_all, start, end, drop_undated=True)
    print(f"✅ Backfill завершено. Бекап старих вкладок: {backup_dir}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--backup-only":
        backup_sheets(datetime.utcnow().strftime("%Y-%m-%d_%H%M%S"))
    elif len(sys.argv) >= 4 and sys.argv[1] == "--backfill":
        run_backfill(sys.argv[2], sys.argv[3])
    else:
        run_daily()
