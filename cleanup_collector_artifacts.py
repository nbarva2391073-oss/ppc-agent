# Затверджене користувачем (19.10) очищення: точні дублі + недатовані тижневі рядки, що дублюють датовані дні.
# Бекап кожного аркуша в backups/cleanup_pre/ ПЕРЕД змінами. Результат: diag/cleanup/RESULT.json
import csv, json, os, re, time
from sheets import get_sheet
BK = "backups/cleanup_pre"; OUT = "diag/cleanup"; os.makedirs(BK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
DEDUPE = ["Bid History USA", "Placement Analysis USA", "Weekly Summary", "Campaign Analysis CA",
          "Bid History CA", "Raw Data USA", "Raw Data CA", "Advertised Product USA"]
# недатовані тижні, що перекриваються датованими днями (подвійний підрахунок) -> видаляємо
OVERLAP_WEEKS = ("28.09", "05.10")
RAW = ("Raw Data USA", "Raw Data CA")
res = {}
def retry(fn, n=6):
    for a in range(1, n + 1):
        try: return fn()
        except Exception as e:
            print("retry", a, e); time.sleep(20 * a)
    raise RuntimeError("failed")
for t in DEDUPE:
    sh = retry(lambda: get_sheet(t)); rows = retry(lambda: sh.get_all_values())
    csv.writer(open(f"{BK}/{t.replace(' ', '_')}_final.csv", "w", newline="", encoding="utf-8")).writerows(rows)
    if not rows: res[t] = {"before": 0}; continue
    hdr, body = rows[0], rows[1:]
    removed_undated = 0
    if t in RAW and "Date" in hdr:
        di = hdr.index("Date"); keep = []
        for r in body:
            d = r[di].strip() if len(r) > di else ""
            wk = (r[0] if r else "")
            if not d and any(wk.startswith(w) for w in OVERLAP_WEEKS):
                removed_undated += 1; continue
            keep.append(r)
        body = keep
    seen, out, dups = set(), [], 0
    for r in body:
        k = tuple(c.strip() for c in r)
        if not any(k): continue
        if k in seen: dups += 1; continue
        seen.add(k); out.append(r)
    res[t] = {"before": len(rows) - 1, "after": len(out), "dups_removed": dups, "undated_overlap_removed": removed_undated}
    if dups or removed_undated:
        retry(lambda: sh.clear()); retry(lambda: sh.update([hdr] + out, "A1"))
    print(t, res[t]); time.sleep(5)
json.dump(res, open(f"{OUT}/RESULT.json", "w"), indent=1, ensure_ascii=False)
