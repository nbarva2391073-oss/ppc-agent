# ============================================================
# Перерахунок TACoS_USA для діапазону дат ОДНИМ проходом (без звітів Amazon).
# Джерела: Advertised Product USA (Spend, Sales (Ad)) + Business_Report_USA
# (Ordered Product Sales). Відсутній Business Report → порожньо (не 0).
# Читає аркуші один раз, пише один раз (без квот Sheets API).
# Бекап: backups/tacos_pre_recalc/TACoS_USA.csv. Результат: diag/tacos_recalc/STATUS.json
# ============================================================
import csv, json, os, time
from datetime import date, timedelta

from config import SHEETS_USA
from sheets import get_sheet
from amazon_ads import ASIN_PRICE_CONFIG

MARKET = os.environ.get("MARKET", "USA")
SFX = "" if MARKET == "USA" else "_" + MARKET
FROM = os.environ.get("TACOS_FROM", "2026-08-25")
TO = os.environ.get("TACOS_TO") or (date.today() - timedelta(days=1)).isoformat()
OUT = "diag/tacos_recalc" + SFX; os.makedirs(OUT, exist_ok=True)
BK = "backups/tacos_pre_recalc" + SFX; os.makedirs(BK, exist_ok=True)


def num(x):
    try: return float(str(x).replace(",", "."))
    except Exception: return None


def retry(fn, *a):
    for i in range(1, 7):
        try: return fn(*a)
        except Exception as e:
            print("retry", i, str(e)[:120]); time.sleep(20 * i)
    raise RuntimeError("retry exhausted")


def main():
    adv = retry(lambda: get_sheet(f"Advertised Product {MARKET}").get_all_values())
    br = retry(lambda: get_sheet(f"Business_Report_{MARKET}").get_all_values())
    tc_sh = get_sheet(f"TACoS_{MARKET}")
    tc = retry(lambda: tc_sh.get_all_values())
    with open(os.path.join(BK, f"TACoS_{MARKET}.csv"), "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(tc)

    h = adv[0]; cd, ca, cs, csl = h.index("Date"), h.index("ASIN"), h.index("Spend"), h.index("Sales (Ad)")
    A = {}
    for r in adv[1:]:
        if len(r) <= max(cd, ca, cs, csl) or not r[ca] or not (FROM <= r[cd] <= TO): continue
        d = A.setdefault((r[cd], r[ca]), [0.0, 0.0])
        d[0] += num(r[cs]) or 0.0; d[1] += num(r[csl]) or 0.0
    hb = br[0]; bd, ba, bs = hb.index("Дата"), hb.index("ASIN"), hb.index("Ordered Product Sales")
    B = {}; br_dates = set()
    for r in br[1:]:
        if len(r) <= max(bd, ba, bs) or not r[ba] or not (FROM <= r[bd] <= TO): continue
        B[(r[bd], r[ba])] = B.get((r[bd], r[ba]), 0.0) + (num(r[bs]) or 0.0); br_dates.add(r[bd])

    ours = set(ASIN_PRICE_CONFIG.keys())
    dates = sorted({k[0] for k in A} | br_dates)
    new = []
    for d in dates:
        asins = sorted(({k[1] for k in A if k[0] == d} | {k[1] for k in B if k[0] == d}) & ours)
        for a in asins:
            sp, sl = (A.get((d, a)) or [0.0, 0.0]); sp, sl = round(sp, 2), round(sl, 2)
            tot = B.get((d, a))
            if tot is None:
                tv = org = tp = osh = ""
            else:
                tv = round(tot, 2); org = round(tot - sl, 2)
                tp = round(sp / tot * 100, 1) if tot > 0 else ""
                osh = round(org / tot * 100, 1) if tot > 0 else ""
            new.append([d, a, sp, sl, tv, org, tp, round(sp / sl * 100, 1) if sl > 0 else "", osh])
    header = ["Date", "ASIN", "Ad_Spend", "Ad_Sales", "Total_Sales", "Organic_Sales", "TACoS%", "ACoS%", "Organic_Share%"]
    keep = [r for r in tc[1:] if r and not (FROM <= r[0] <= TO)]
    final = [header] + sorted(keep + new, key=lambda r: (r[0], r[1]))
    retry(lambda: (tc_sh.clear(), tc_sh.update(final, "A1")))
    per_day = {}
    for r in new: per_day[r[0]] = round(per_day.get(r[0], 0) + (r[2] or 0), 2)
    json.dump({"from": FROM, "to": TO, "rows_written": len(new), "dates": len(dates),
               "br_dates": sorted(br_dates), "adv_spend_per_day": per_day,
               "dates_without_br": [d for d in dates if d not in br_dates]},
              open(os.path.join(OUT, "STATUS.json"), "w"), ensure_ascii=False, indent=1)
    print("done", len(new))


if __name__ == "__main__":
    main()
