# ============================================================
# TEMP: одноразовий аудит + дедуплікація Business_Report_USA/CA.
# Дублікати — наслідок старої логіки запису (до коміту d541587,
# 09.09.2026), яка не мала upsert і просто дописувала рядки.
# Поточний fetch_and_store_day() вже коректно робить upsert по
# (Дата) — це стосується лише історичних "хвостів" з ДО фіксу.
#
# Дедуп-ключ: (Дата, ASIN). З кожної групи дублікатів лишаємо один
# рядок — з пріоритетом на "має реальні дані" (Sessions/Units/Sales
# > 0) над "нульовим" snapshot-рядком; серед кількох "реальних" —
# з найбільшими показниками (тобто фінальний/повний, а не проміжний).
# ============================================================
from sheets import get_sheet

SHEETS = ["Business_Report_USA", "Business_Report_CA"]


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _score(row):
    sessions = _num(row[2]) if len(row) > 2 else 0.0
    units    = _num(row[5]) if len(row) > 5 else 0.0
    sales    = _num(row[6]) if len(row) > 6 else 0.0
    has_data = 1 if (sessions > 0 or units > 0 or sales > 0) else 0
    return (has_data, sessions, units, sales)


def cleanup(sheet_name: str):
    sh = get_sheet(sheet_name)
    rows = sh.get_all_values()
    if not rows or len(rows) < 2:
        print(f"{sheet_name}: порожньо, пропуск")
        return
    header, data = rows[0], rows[1:]

    groups = {}
    order = []  # зберігаємо порядок появи ключів
    for r in data:
        if len(r) < 2 or not r[0] or not r[1]:
            continue
        key = (r[0], r[1])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    dup_keys = {k: v for k, v in groups.items() if len(v) > 1}
    extra_rows = sum(len(v) - 1 for v in dup_keys.values())
    print(f"\n📋 {sheet_name}: {len(data)} рядків, {len(groups)} унікальних (Дата,ASIN)")
    print(f"   Дублікованих ключів: {len(dup_keys)}, зайвих рядків: {extra_rows}")

    if extra_rows == 0:
        print(f"   ✅ дублікатів немає, без змін")
        return

    final_rows = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            final_rows.append(group[0])
        else:
            best = max(group, key=_score)
            final_rows.append(best)

    sh.clear()
    sh.update([header] + final_rows, "A1")
    print(f"   🧹 Очищено: {len(data)} → {len(final_rows)} рядків (видалено {len(data) - len(final_rows)})")


def run():
    for name in SHEETS:
        try:
            cleanup(name)
        except Exception as e:
            import traceback
            print(f"❌ {name} помилка: {e}")
            traceback.print_exc()
    print("\n✅ ЗАВЕРШЕНО")


if __name__ == "__main__":
    run()
