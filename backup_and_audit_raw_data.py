# ============================================================
# ОДНОРАЗОВИЙ скрипт: бекап + аудит перед відновленням історії.
# Знімає CSV-знімок 4 аркушів (Raw Data USA, Advertised Product USA,
# Campaign Analysis USA, Weekly Summary) і будує текстовий звіт по
# контрольному тижню 21-27.09 USA: скільки рядків, які точні дублікати,
# які week-мітки фактично присутні. Нічого не видаляє і не змінює.
# ============================================================

import csv
import os
from datetime import datetime, date

from sheets import get_sheet
from config import SHEETS_USA, SHEETS_COMMON

STAMP = datetime.now().strftime("%Y-%m-%d_%H%M%S")
OUT_DIR = os.path.join("backups", f"{STAMP}_control_week_2109_2709_usa")
os.makedirs(OUT_DIR, exist_ok=True)

TARGETS = {
    "raw_data":          SHEETS_USA["raw_data"],
    "advertised_product": SHEETS_USA["advertised_product"],
    "campaign_analysis": SHEETS_USA["campaign_analysis"],
    "weekly_summary":    SHEETS_COMMON["weekly_summary"],
}

snapshots = {}

for key, sheet_name in TARGETS.items():
    print(f"→ Читаю '{sheet_name}'...")
    sh = get_sheet(sheet_name)
    values = sh.get_all_values()
    snapshots[key] = values
    csv_path = os.path.join(OUT_DIR, f"{sheet_name.replace(' ', '_')}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(values)
    print(f"  ✅ {len(values)} рядків збережено у {csv_path}")

CONTROL_WEEK_LABEL = "21.09-27.09.2026"
CONTROL_START = date(2026, 9, 21)
CONTROL_END   = date(2026, 9, 27)


def _idx(header, name):
    try:
        return header.index(name)
    except ValueError:
        return None


def _parse_date(s):
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


lines = []
lines.append(f"# Аудит control week {CONTROL_WEEK_LABEL} — USA")
lines.append(f"Знято: {datetime.now().isoformat()}")
lines.append("")

# ── Raw Data USA ──────────────────────────────────────────────
rd = snapshots["raw_data"]
lines.append(f"## Raw Data USA")
lines.append(f"- Всього рядків (без заголовка): {max(len(rd)-1, 0)}")
if rd:
    header = rd[0]
    date_i = _idx(header, "Date")
    week_i = _idx(header, "Week")
    with_date  = sum(1 for r in rd[1:] if date_i is not None and len(r) > date_i and r[date_i])
    without_date = max(len(rd)-1, 0) - with_date
    lines.append(f"- З заповненим Date: {with_date}")
    lines.append(f"- Без Date (старі weekly-рядки): {without_date}")

    # рядки, що стосуються контрольного тижня (за Week або за Date)
    control_rows = []
    for r in rd[1:]:
        w = r[week_i] if week_i is not None and len(r) > week_i else ""
        d_raw = r[date_i] if date_i is not None and len(r) > date_i else ""
        d = _parse_date(d_raw) if d_raw else None
        in_week = (w == CONTROL_WEEK_LABEL) or (d and CONTROL_START <= d <= CONTROL_END)
        if in_week:
            control_rows.append(r)
    lines.append(f"- Рядків, що належать до {CONTROL_WEEK_LABEL} (за Week або Date): {len(control_rows)}")

    # точні дублікати (повний збіг рядка)
    seen = {}
    exact_dupes = 0
    for r in rd[1:]:
        key = tuple(r)
        seen[key] = seen.get(key, 0) + 1
    for key, cnt in seen.items():
        if cnt > 1:
            exact_dupes += (cnt - 1)
    lines.append(f"- Точних дублікатів рядків (всього надлишкових копій): {exact_dupes}")
lines.append("")

# ── Advertised Product USA ───────────────────────────────────
ap = snapshots["advertised_product"]
lines.append(f"## Advertised Product USA")
lines.append(f"- Всього рядків (без заголовка): {max(len(ap)-1, 0)}")
if ap:
    header = ap[0]
    date_i = _idx(header, "Date")
    control_rows = []
    for r in ap[1:]:
        d_raw = r[date_i] if date_i is not None and len(r) > date_i else ""
        d = _parse_date(d_raw) if d_raw else None
        if d and CONTROL_START <= d <= CONTROL_END:
            control_rows.append(r)
    lines.append(f"- Рядків у діапазоні {CONTROL_START}..{CONTROL_END}: {len(control_rows)}")

    seen = {}
    for r in ap[1:]:
        key = tuple(r)
        seen[key] = seen.get(key, 0) + 1
    exact_dupes = sum(cnt - 1 for cnt in seen.values() if cnt > 1)
    lines.append(f"- Точних дублікатів рядків (всього надлишкових копій): {exact_dupes}")

    # дублікати саме в контрольному тижні
    seen_cw = {}
    for r in control_rows:
        key = tuple(r)
        seen_cw[key] = seen_cw.get(key, 0) + 1
    cw_dupes = sum(cnt - 1 for cnt in seen_cw.values() if cnt > 1)
    lines.append(f"- З них точних дублікатів у контрольному тижні: {cw_dupes}")

    # дні контрольного тижня, яких взагалі немає
    present_days = set()
    for r in control_rows:
        d_raw = r[date_i] if date_i is not None and len(r) > date_i else ""
        d = _parse_date(d_raw) if d_raw else None
        if d:
            present_days.add(d.isoformat())
    from datetime import timedelta as _td
    all_days = [(CONTROL_START + _td(days=i)).isoformat() for i in range(7)]
    missing_days = [d for d in all_days if d not in present_days]
    lines.append(f"- Дні контрольного тижня без жодного рядка: {missing_days if missing_days else '(немає)'}")
lines.append("")

# ── Campaign Analysis USA (Flame) ────────────────────────────
ca = snapshots["campaign_analysis"]
lines.append(f"## Campaign Analysis USA — рядки Flame навколо контрольного тижня")
if ca:
    header = ca[0]
    week_i = _idx(header, "Week")
    camp_i = _idx(header, "Campaign")
    flame_rows = []
    for r in ca[1:]:
        camp = r[camp_i] if camp_i is not None and len(r) > camp_i else ""
        if "Flame" in camp:
            flame_rows.append(r)
    lines.append(f"- Всього рядків Flame у таблиці: {len(flame_rows)}")
    lines.append(f"- Заголовок: {header}")
    for r in flame_rows:
        w = r[week_i] if week_i is not None and len(r) > week_i else ""
        if "21.09" in w or "27.09" in w or "28.09" in w or "20.09" in w:
            lines.append(f"  · {r}")
lines.append("")

# ── Weekly Summary ────────────────────────────────────────────
ws = snapshots["weekly_summary"]
lines.append(f"## Weekly Summary — записи USA навколо контрольного тижня")
if ws:
    header = ws[0]
    lines.append(f"- Заголовок: {header}")
    week_i = _idx(header, "Week")
    market_i = _idx(header, "Market")
    for r in ws[1:]:
        w = r[week_i] if week_i is not None and len(r) > week_i else ""
        m = r[market_i] if market_i is not None and len(r) > market_i else ""
        if ("USA" in m or market_i is None) and ("21.09" in w or "27.09" in w or "28.09" in w or "20.09" in w):
            lines.append(f"  · {r}")

summary_path = os.path.join(OUT_DIR, "AUDIT_SUMMARY.md")
with open(summary_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print(f"\n✅ Бекап і аудит збережено у {OUT_DIR}/")
