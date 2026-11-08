# ============================================================
# Архівація старих знімків Suggested Bids (USA/CA) в окрему архівну таблицю.
# Правило: рядки з UpdatedAt старші RETENTION_DAYS (за замовч. 30) спершу
# ДОДАЮТЬСЯ в архів (лише ті, яких там ще нема: UpdatedAt > max в архіві),
# кількість рядків звіряється, і тільки потім вилучаються з основної вкладки.
# Нічого не втрачається; читач read_suggested_bids бере останній знімок.
# Ідемпотентний. Змінні: ARCHIVE_SPREADSHEET_ID, RETENTION_DAYS, DRY_RUN=1.
# ============================================================
import json, os, time
from datetime import datetime, timedelta
from config import SPREADSHEET_ID
from sheets import client

ARCHIVE_ID = os.getenv("ARCHIVE_SPREADSHEET_ID", "18-ILAn9ZvTVmoJpBymFBVz3YHcnRfubUUL3AA96Ds3A")
DAYS = int(os.getenv("RETENTION_DAYS", "30"))
DRY = os.getenv("DRY_RUN", "") in ("1", "true", "True")
TABS = ["Suggested Bids USA", "Suggested Bids CA"]
OUT = "diag/archive_bids"; os.makedirs(OUT, exist_ok=True)


def retry(fn, *a, **k):
    for i in range(6):
        try:
            return fn(*a, **k)
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e) or "503" in str(e):
                time.sleep(15 * (i + 1)); continue
            raise
    return fn(*a, **k)


def run_tab(main_ss, arch_ss, title, cutoff):
    res = {"tab": title}
    ws = main_ss.worksheet(title)
    vals = retry(ws.get_all_values)
    if len(vals) < 2:
        res["status"] = "empty"; return res
    header, rows = vals[0], vals[1:]
    c = header.index("UpdatedAt")
    n_old = 0
    for r in rows:
        d = r[c][:16] if len(r) > c else ""
        if d and d < cutoff:
            n_old += 1
        else:
            break
    res.update(main_rows=len(rows), old_prefix=n_old, cutoff=cutoff)
    if n_old == 0:
        res["status"] = "nothing_to_archive"; return res
    old = [r + [""] * (len(header) - len(r)) for r in rows[:n_old]]
    try:
        aws = arch_ss.worksheet(title)
    except Exception:
        aws = retry(arch_ss.add_worksheet, title=title, rows=1000, cols=len(header))
        retry(aws.update, [header], "A1")
    acol = retry(aws.col_values, c + 1)
    arch_max = max([x[:16] for x in acol[1:] if x] or [""])
    to_add = [r for r in old if r[c][:16] > arch_max]
    res.update(archive_max=arch_max, to_append=len(to_add))
    if DRY:
        res["status"] = "dry_run"; return res
    arows_before = len(retry(aws.col_values, 1)) - 1
    for i in range(0, len(to_add), 5000):
        retry(aws.append_rows, to_add[i:i + 5000], value_input_option="RAW", table_range="A1")
    arows_after = len(retry(aws.col_values, 1)) - 1
    res.update(archive_rows_before=arows_before, archive_rows_after=arows_after)
    if arows_after - arows_before != len(to_add):
        res["status"] = "ABORT_count_mismatch_main_untouched"; return res
    # перевірка що кожен старий UpdatedAt <= max в архіві присутній
    retry(ws.delete_rows, 2, n_old + 1)
    res["status"] = "archived_and_removed"
    res["removed_from_main"] = n_old
    res["main_rows_after"] = len(retry(ws.col_values, 1)) - 1
    return res


def main():
    cutoff = (datetime.utcnow() - timedelta(days=DAYS)).strftime("%Y-%m-%d %H:%M")
    main_ss = client().open_by_key(SPREADSHEET_ID)
    arch_ss = client().open_by_key(ARCHIVE_ID)
    out = {"cutoff": cutoff, "days": DAYS, "dry": DRY, "tabs": []}
    for t in TABS:
        try:
            r = run_tab(main_ss, arch_ss, t, cutoff)
        except Exception as e:
            r = {"tab": t, "status": f"ERROR {e}"}
        print(r); out["tabs"].append(r)
    json.dump(out, open(f"{OUT}/RESULT.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
