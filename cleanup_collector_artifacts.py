# Одноразово: вирівнювання мітки поточного тижня після ремонту.
# Ремонт записав поточний тиждень як "12.10-14.10.2026", а monitor використовує "12.10-18.10.2026".
#  - Campaign Analysis: рядки "12.10-14.10.2026" видаляємо (правильні "12.10-18.10.2026" вже є, збігаються з Amazon).
#  - Placement: старі (задубльовані) рядки "12.10-18.10.2026" замінюємо відремонтованими "12.10-14.10.2026" з новою міткою.
import csv, json, os
from sheets import get_sheet
BK = "backups/cleanup_pre"; OUT = "diag/cleanup"; os.makedirs(BK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
OLD, NEW = "12.10-14.10.2026", "12.10-18.10.2026"
res = {}
for t in ("Campaign Analysis USA", "Placement Analysis USA"):
    sh = get_sheet(t); rows = sh.get_all_values()
    csv.writer(open(f"{BK}/{t.replace(' ', '_')}_labelfix.csv", "w", newline="", encoding="utf-8")).writerows(rows)
    if t.startswith("Campaign"):
        out = [r for r in rows if not (r and r[0] == OLD)]
    else:
        out = [r for r in rows if not (r and r[0] == NEW)]
        out = [([NEW] + r[1:]) if (r and r[0] == OLD) else r for r in out]
    res[t] = {"before": len(rows), "after": len(out)}
    sh.clear(); sh.update(out, "A1")
json.dump(res, open(f"{OUT}/RESULT.json", "w"), indent=1); print(res)
