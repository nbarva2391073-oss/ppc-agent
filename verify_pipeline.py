# Read-only аудит аркушів (нічого не змінює): останні дати, дублікати, рядки без дати, добові суми Spend.
import json, os, collections, time
from sheets import read_all_optional
OUT = "diag/verify"; os.makedirs(OUT, exist_ok=True)
TABS = ["Raw Data USA", "Campaign Analysis USA", "Bid History USA", "Placement Analysis USA",
        "Keyword Intelligence USA", "Advertised Product USA", "Suggested Bids USA", "SB_Campaign_USA",
        "SB_SearchTerm_USA", "Business_Report_USA", "TACoS_USA", "BA_Pending_Reports", "BA_SearchCatalog_USA",
        "BA_RepeatPurchase_USA", "BA_MarketBasket_USA", "BA_Demographics_USA", "BA_TopSearchTerms_USA",
        "BA_Trends_USA", "BA_SQP_USA", "Weekly Summary", "Monthly Summary USA", "Monthly Summary"]
DATE_NAMES = ("date", "дата", "run date", "snapshot date", "report date")
SPEND = ("spend", "cost", "ad_spend")
def num(x):
    try: return float(str(x).replace(",", "."))
    except Exception: return 0.0
res = {}
for t in TABS:
    for i in range(4):
        try: rows = read_all_optional(t); break
        except Exception: time.sleep(20)
    if not rows:
        res[t] = {"exists_or_nonempty": False}; continue
    h = rows[0]; hl = [str(x).strip().lower() for x in h]
    r = {"rows": len(rows) - 1, "header": h[:24]}
    dcols = [i for i, x in enumerate(hl) if x in DATE_NAMES]
    scol = next((i for i, x in enumerate(hl) if x in SPEND), None)
    r["date_cols"] = [h[i] for i in dcols]
    if dcols:
        di = dcols[0]
        ds = [x[di] for x in rows[1:] if len(x) > di and x[di][:2] == "20"]
        r["undated_rows"] = len(rows) - 1 - len(ds)
        r["first_date"] = min(ds) if ds else None; r["last_date"] = max(ds) if ds else None
        r["distinct_dates"] = len(set(ds))
        if scol is not None:
            per = collections.defaultdict(float)
            for x in rows[1:]:
                if len(x) > max(di, scol) and x[di][:2] == "20": per[x[di]] += num(x[scol])
            r["spend_per_date"] = {k: round(v, 2) for k, v in sorted(per.items())[-40:]}
        # якщо дата + набір перших колонок задають запис: дублі повних рядків
    full = collections.Counter(tuple(x) for x in rows[1:])
    r["exact_duplicate_rows"] = sum(v - 1 for v in full.values() if v > 1)
    dups = [(k, v) for k, v in full.items() if v > 1]
    r["dup_samples"] = [{"count": v, "row": list(k)[:14]} for k, v in dups[:4]]
    r["dup_by_first_col"] = dict(collections.Counter(k[0] for k, v in dups).most_common(12))
    r["dup_samples_recent"] = [{"count": v, "row": list(k)[:14]} for k, v in dups if str(k[0]).endswith(".10.2026")][:6]
    if t in ("BA_Pending_Reports", "BA_Trends_USA", "BA_SQP_USA", "Weekly Summary"):
        r["last_rows"] = [x[:10] for x in rows[-14:]]
    r["tail"] = rows[-1][:12]
    res[t] = r
    json.dump(res, open(os.path.join(OUT, "RESULT.json"), "w"), ensure_ascii=False, indent=1)
print("done")


# ── Звірка тижневих вкладок з істиною Amazon (diag/sp_audit/camp_daily.json, DAILY по кампаніях) ──
try:
    from datetime import date as _d, timedelta as _td
    truth = json.load(open("diag/sp_audit/camp_daily.json"))
    def wlabel(ds):
        d = _d.fromisoformat(ds); s = d - _td(days=d.weekday()); e = s + _td(days=6)
        return f"{s.strftime('%d.%m')}-{e.strftime('%d.%m.%Y')}"
    T = collections.defaultdict(float); days = collections.defaultdict(set)
    for r in truth:
        T[(wlabel(r["date"]), r["campaignName"])] += float(r.get("cost") or 0); days[wlabel(r["date"])].add(r["date"])
    comp = {}
    ca = read_all_optional("Campaign Analysis USA"); hc = ca[0]; iw, ic, isp = hc.index("Week"), hc.index("Campaign"), hc.index("Spend")
    CA = collections.defaultdict(float)
    for r in ca[1:]:
        if len(r) > isp: CA[(r[iw], r[ic])] += num(r[isp])
    pl = read_all_optional("Placement Analysis USA"); hp = pl[0]; pw, pc, ps = hp.index("Week"), hp.index("Campaign"), hp.index("Spend")
    PL = collections.defaultdict(float)
    for r in pl[1:]:
        if len(r) > ps: PL[(r[pw], r[pc])] += num(r[ps])
    for wk in sorted(days, key=lambda x: x[6:10] + x[3:5] + x[:2]):
        tw = round(sum(v for (w, c), v in T.items() if w == wk), 2)
        cw = round(sum(v for (w, c), v in CA.items() if w == wk), 2)
        pw_ = round(sum(v for (w, c), v in PL.items() if w == wk), 2)
        comp[wk] = {"days_in_truth": len(days[wk]), "amazon_cost": tw, "campaign_analysis": cw, "placement": pw_}
    res["_week_vs_amazon"] = comp
    json.dump(res, open(os.path.join(OUT, "RESULT.json"), "w"), ensure_ascii=False, indent=1)
except Exception as ex:
    res["_week_vs_amazon_error"] = str(ex)[:300]
    json.dump(res, open(os.path.join(OUT, "RESULT.json"), "w"), ensure_ascii=False, indent=1)
