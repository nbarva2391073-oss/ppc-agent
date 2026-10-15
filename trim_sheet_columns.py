# ============================================================
# Звільнення комірок у Google Sheets (ліміт книги — 10 000 000 комірок).
# Автоматичні вкладки створено через add_worksheet(rows=2000, cols=60), але
# реально використовують 8-20 колонок; порожні колонки (60 × тисячі рядків)
# з'їли ~97% ліміту (≈9.7M) — і найближчий append (Suggested Bids ≈ +2800
# рядків/2 доби) упирається в ліміт. Скрипт обрізає ЛИШЕ порожні колонки
# праворуч від останньої заповненої (+3 запас). Дані не змінюються.
# НЕ чіпає: Sellerise*, ручні/контрольні вкладки (≤40 колонок вже малі).
# ============================================================
import json, os, sys, time
import gspread
from config import SPREADSHEET_ID
from sheets import client

SKIP_PREFIX = ("Sellerise",)
OUT = "diag/trim"; os.makedirs(OUT, exist_ok=True)


def total_cells(ss):
    return sum(w.row_count * w.col_count for w in ss.worksheets())


def main():
    ss = client().open_by_key(SPREADSHEET_ID)
    res = {"before_total": total_cells(ss), "tabs": []}
    for ws in ss.worksheets():
        if ws.title.startswith(SKIP_PREFIX) or ws.col_count < 40:
            continue
        try:
            vals = ws.get_all_values()
            used = max((len(r) for r in vals), default=1)
            # остання непорожня колонка (get_all_values повертає рядки до останньої непорожньої)
            last = 0
            for r in vals:
                for i in range(len(r) - 1, -1, -1):
                    if r[i] != "":
                        last = max(last, i + 1); break
            target = max(last + 3, 8)
            entry = {"tab": ws.title, "rows": ws.row_count, "cols_before": ws.col_count,
                     "last_used_col": last, "cols_after": target}
            if target < ws.col_count:
                ws.resize(cols=target)
            else:
                entry["cols_after"] = ws.col_count
            res["tabs"].append(entry)
        except Exception as e:
            res["tabs"].append({"tab": ws.title, "error": str(e)[:200]})
        time.sleep(2.5)
    res["after_total"] = total_cells(client().open_by_key(SPREADSHEET_ID))
    json.dump(res, open(os.path.join(OUT, "RESULT.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "tabs"}))


if __name__ == "__main__":
    main()
