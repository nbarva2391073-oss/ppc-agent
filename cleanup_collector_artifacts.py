# ============================================================
# Одноразове прибирання артефактів ЗБОРУ (технічний сміття, не аналітика):
#  1) Keyword Intelligence USA: 185 порожніх рядків «01.09.2026-30.09.2026»
#     (SQP писався в KI з хибним розбором → лише мітка періоду і «USA», без даних).
#  2) BA_SearchCatalog_USA / BA_RepeatPurchase_USA: точні дублікати рядків
#     (повторне завантаження того самого звіту).
# Перед змінами — повна копія аркуша в backups/cleanup_pre/. Видаляються ЛИШЕ
# рядки, що повністю порожні (крім мітки) або є точною копією попереднього.
# ============================================================
import csv, json, os
from sheets import get_sheet
BK = "backups/cleanup_pre"; OUT = "diag/cleanup"; os.makedirs(BK, exist_ok=True); os.makedirs(OUT, exist_ok=True)
res = {}

def backup(name, rows):
    with open(os.path.join(BK, name.replace(" ", "_") + ".csv"), "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

def rewrite(sh, rows):
    sh.clear(); sh.update(rows, "A1")

# 1) KI
sh = get_sheet("Keyword Intelligence USA"); rows = sh.get_all_values(); backup("Keyword Intelligence USA", rows)
keep = [rows[0]]; drop = 0
for r in rows[1:]:
    if r and r[0] == "01.09.2026-30.09.2026" and not any((c or "").strip() for c in r[1:18]):
        drop += 1; continue
    keep.append(r)
res["ki_blank_rows_removed"] = drop
if drop: rewrite(sh, keep)

# 2) BA exact duplicates
for t in ("BA_SearchCatalog_USA", "BA_RepeatPurchase_USA", "BA_MarketBasket_USA"):
    sh = get_sheet(t); rows = sh.get_all_values(); backup(t, rows)
    seen = set(); keep = [rows[0]]; drop = 0
    for r in rows[1:]:
        k = tuple(r)
        if k in seen: drop += 1; continue
        seen.add(k); keep.append(r)
    res[t] = {"before": len(rows) - 1, "duplicates_removed": drop}
    if drop: rewrite(sh, keep)
json.dump(res, open(os.path.join(OUT, "RESULT.json"), "w"), ensure_ascii=False, indent=1)
print(res)
