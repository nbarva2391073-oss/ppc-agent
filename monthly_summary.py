# ============================================================
# Monthly Summary (USA) — місячний підсумок із ПЕРЕВІРЕНИХ джерел.
# PPC: Amazon Ads spCampaigns DAILY за весь місяць (джерело правди) +
#      звірка добових витрат/кліків/показів з Advertised Product USA.
# Seller: Business_Report_USA (Sessions, Page Views, Units, Ordered Product Sales);
#         якщо за якийсь день BR відсутній — це фіксується, НЕ нулі.
# Запис: аркуш "Monthly Summary", upsert за (Month, Market). Нічого іншого не змінює.
# Запуск: MONTH=2026-09 (за замовчуванням — попередній місяць).
# ============================================================
import calendar, json, os, re, time
from datetime import date, datetime, timedelta
import requests
from config import ADS_PROFILE_ID_USA
from amazon_ads import get_access_token, headers, ADS_BASE_URL, wait_and_download
from sheets import get_sheet

MARKET = os.environ.get("MARKET", "USA")
SFX = "" if MARKET == "USA" else "_" + MARKET
PID = __import__("config").ADS_PROFILE_ID_CA if MARKET == "CA" else __import__("config").ADS_PROFILE_ID_USA
OUT = "diag/monthly_summary" + SFX; os.makedirs(OUT, exist_ok=True)
HEAD = ["Month", "Market", "Impressions", "Clicks", "CTR%", "Spend", "CPC", "Ad Sales (7d)", "Orders (7d)", "ACoS%", "ROAS",
        "Sessions", "Page Views", "Units Ordered", "Ordered Product Sales", "Unit Session %", "TACoS%",
        "PPC days", "BR days", "Source check", "Generated (UTC)"]

def num(x):
    try: return float(str(x).replace(",", "."))
    except Exception: return 0.0

def month_range():
    m = os.environ.get("MONTH") or (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    y, mo = map(int, m.split("-")); last = calendar.monthrange(y, mo)[1]
    return m, f"{m}-01", f"{m}-{last:02d}", last

def submit(s, e):
    cols = ["campaignName", "campaignId", "impressions", "clicks", "cost", "sales7d", "purchases7d", "date"]
    payload = {"name": f"SP campaign DAILY {s}..{e}", "startDate": s, "endDate": e,
               "configuration": {"adProduct": "SPONSORED_PRODUCTS", "groupBy": ["campaign"], "columns": cols,
                                 "reportTypeId": "spCampaigns", "timeUnit": "DAILY", "format": "GZIP_JSON"}}
    for _ in range(6):
        r = requests.post(f"{ADS_BASE_URL}/reporting/reports", headers=headers(get_access_token(), PID), json=payload)
        if r.status_code in (200, 202): return r.json()["reportId"]
        mm = re.search(r"duplicate of\s*:\s*([\w-]+)", r.text)
        if mm: return mm.group(1)
        if r.status_code == 429: time.sleep(65); continue
        raise Exception(f"{r.status_code} {r.text[:300]}")
    raise Exception("submit failed")

def main():
    month, s, e, ndays = month_range()
    status = {"month": month, "from": s, "to": e}
    rid = submit(s, e); status["report_id"] = rid
    json.dump(status, open(f"{OUT}/STATUS.json", "w"), indent=1)
    rows = wait_and_download(get_access_token(), PID, rid, max_wait=5400, token_fn=get_access_token)
    by = {}
    for r in rows:
        d = by.setdefault(r["date"], [0, 0, 0.0, 0.0, 0])
        d[0] += int(r.get("impressions") or 0); d[1] += int(r.get("clicks") or 0)
        d[2] += float(r.get("cost") or 0); d[3] += float(r.get("sales7d") or 0); d[4] += int(r.get("purchases7d") or 0)
    imp = sum(v[0] for v in by.values()); clk = sum(v[1] for v in by.values())
    spend = round(sum(v[2] for v in by.values()), 2); sales = round(sum(v[3] for v in by.values()), 2)
    orders = sum(v[4] for v in by.values())
    # звірка з Advertised Product
    adv = get_sheet(f"Advertised Product {MARKET}").get_all_values()
    h = adv[0]; cd, ci, ck, cs = h.index("Date"), h.index("Impressions"), h.index("Clicks"), h.index("Spend")
    A = {}
    for r in adv[1:]:
        if len(r) > cs and s <= r[cd] <= e:
            v = A.setdefault(r[cd], [0, 0, 0.0]); v[0] += int(num(r[ci])); v[1] += int(num(r[ck])); v[2] += num(r[cs])
    diffs = {d: {"campaign": round(by[d][2], 2), "adv": round(A.get(d, [0, 0, None])[2], 2) if d in A else None}
             for d in sorted(by) if d not in A or abs(by[d][2] - A[d][2]) > 0.05}
    # Business Report
    br = get_sheet(f"Business_Report_{MARKET}").get_all_values(); hb = br[0]
    bd, bs, bp, bu, bo = (hb.index(x) for x in ("Дата", "Sessions", "Page Views", "Units Ordered", "Ordered Product Sales"))
    B = {"s": 0.0, "p": 0.0, "u": 0.0, "o": 0.0}; bdays = set()
    for r in br[1:]:
        if len(r) > bo and s <= r[bd] <= e:
            bdays.add(r[bd]); B["s"] += num(r[bs]); B["p"] += num(r[bp]); B["u"] += num(r[bu]); B["o"] += num(r[bo])
    ok = (len(by) == ndays and not diffs and len(bdays) == ndays)
    check = "OK" if ok else f"INCOMPLETE: ppc_days={len(by)}/{ndays}, adv_mismatch_days={len(diffs)}, br_days={len(bdays)}/{ndays}"
    full_br = len(bdays) == ndays
    row = [month, MARKET, imp, clk, round(clk / imp * 100, 2) if imp else "", spend, round(spend / clk, 2) if clk else "",
           sales, orders, round(spend / sales * 100, 1) if sales else "", round(sales / spend, 2) if spend else "",
           round(B["s"]) if bdays else "", round(B["p"]) if bdays else "", round(B["u"]) if bdays else "",
           round(B["o"], 2) if bdays else "",
           round(B["u"] / B["s"] * 100, 2) if bdays and B["s"] else "",
           round(spend / B["o"] * 100, 1) if full_br and B["o"] else "",
           len(by), len(bdays), check, datetime.utcnow().strftime("%Y-%m-%d %H:%M")]
    sh = get_sheet("Monthly Summary")
    ex = sh.get_all_values()
    if not ex or ex[0][:2] != HEAD[:2]:
        final = [HEAD, row]
    else:
        final = [HEAD] + [r for r in ex[1:] if not (r and r[0] == month and len(r) > 1 and r[1] == MARKET)] + [row]
    sh.clear(); sh.update(final, "A1")
    status.update({"row": row, "adv_mismatch": diffs, "ppc_by_date": {d: [v[0], v[1], round(v[2], 2), round(v[3], 2), v[4]] for d, v in sorted(by.items())},
                   "br_days": sorted(bdays), "check": check})
    json.dump(status, open(f"{OUT}/STATUS.json", "w"), ensure_ascii=False, indent=1)
    print(check, row)

if __name__ == "__main__":
    main()
