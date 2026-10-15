# Read-only аудит аркушів (нічого не змінює): останні дати, дублікати, рядки без дати, добові суми Spend.
import json, os, collections, time
from sheets import read_all_optional
OUT = "diag/verify"; os.makedirs(OUT, exist_ok=True)
TABS = ["Raw Data USA", "Campaign Analysis USA", "Bid History USA", "Placement Analysis USA",
        "Keyword Intelligence USA", "Advertised Product USA", "Suggested Bids USA", "SB_Campaign_USA",
        "SB_SearchTerm_USA", "Business_Report_USA", "TACoS_USA", "BA_Pending_Reports", "BA_SearchCatalog_USA",
        "BA_RepeatPurchase_USA", "BA_MarketBasket_USA", "BA_Demographics_USA", "BA_TopSearchTerms_USA",
        "BA_Trends_USA", "Weekly Summary", "Monthly Summary USA", "Monthly Summary"]
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
    r["tail"] = rows[-1][:12]
    res[t] = r
    json.dump(res, open(os.path.join(OUT, "RESULT.json"), "w"), ensure_ascii=False, indent=1)
print("done")
