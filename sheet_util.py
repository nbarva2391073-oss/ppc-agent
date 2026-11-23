# Допоміжне для нових вкладок «сигналів»: створення вкладки, заміна рядків за датою (upsert).
import time
from config import SPREADSHEET_ID
from sheets import client


def retry(fn, *a, **k):
    for i in range(6):
        try:
            return fn(*a, **k)
        except Exception as e:
            s = str(e)
            if "429" in s or "Quota" in s or "503" in s or "500" in s:
                time.sleep(15 * (i + 1)); continue
            raise
    return fn(*a, **k)


_SS = None


def ss():
    global _SS
    if _SS is None:
        _SS = client().open_by_key(SPREADSHEET_ID)
    return _SS


def ensure_tab(name, header):
    """Повертає worksheet; створює з заголовком, якщо нема. Заголовок не перезаписує."""
    try:
        ws = ss().worksheet(name)
    except Exception:
        ws = retry(ss().add_worksheet, title=name, rows=500, cols=max(len(header), 8))
        retry(ws.update, [header], "A1")
        retry(ws.freeze, rows=1)
    return ws


def replace_dates(name, header, rows, date_col, dates):
    """Видаляє з вкладки наші рядки за вказані дати (date_col = індекс колонки з датою)
    і дописує нові. Рядки інших дат не чіпає. Ідемпотентно."""
    ws = ensure_tab(name, header)
    vals = retry(ws.get_all_values)
    dates = set(dates)
    first = None
    tail_only = True
    for i, r in enumerate(vals[1:], start=2):
        d = r[date_col][:10] if len(r) > date_col else ""
        if d in dates:
            if first is None:
                first = i
        elif first is not None:
            tail_only = False
    removed = 0
    if first is not None:
        if tail_only:
            removed = len(vals) - first + 1
            retry(ws.delete_rows, first, len(vals))
        else:
            keep = [r for r in vals[1:] if not (len(r) > date_col and r[date_col][:10] in dates)]
            removed = len(vals) - 1 - len(keep)
            retry(ws.batch_clear, [f"A2:{_col(len(header))}{len(vals)}"])
            if keep:
                keep = [r + [""] * (len(header) - len(r)) for r in keep]
                retry(ws.update, keep, "A2", value_input_option="RAW")
    if rows:
        have = len(retry(ws.col_values, 1))
        need = have + len(rows) + 5
        if need > ws.row_count:
            retry(ws.resize, rows=need)
        for i in range(0, len(rows), 3000):
            retry(ws.append_rows, rows[i:i + 3000], value_input_option="RAW", table_range="A1")
    return removed, len(rows)


def _col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s
