# ============================================================
# TEMP: одноразовий backfill для рядків TACoS з порожнім Total_Sales
# (наслідок бага в tacos_date_missing(), виправленого в tacos.py).
# Знаходить усі (market, date) з порожнім Total_Sales і перераховує
# через calculate_tacos() — спрацює там, де Business Report вже
# встиг отримати дані Amazon.
# ============================================================
from sheets import calculate_tacos, get_sheet

def run_backfill():
    for market in ["USA", "CA"]:
        sheet_name = f"TACoS_{market}"
        sh = get_sheet(sheet_name)
        rows = sh.get_all_values()
        if not rows or len(rows) < 2:
            print(f"{market}: порожньо, пропуск")
            continue
        header = rows[0]
        gap_dates = sorted(set(
            r[0] for r in rows[1:]
            if len(r) > 4 and r[0] and r[4] == ""
        ))
        print(f"\n🌎 {market}: знайдено {len(gap_dates)} дат з дірками: {gap_dates}")
        for date in gap_dates:
            print(f"  🔁 перераховую {market} {date}...")
            try:
                calculate_tacos(market, date)
            except Exception as e:
                import traceback
                print(f"  ❌ {market} {date} помилка: {e}")
                traceback.print_exc()
    print("\n✅ BACKFILL TACoS ЗАВЕРШЕНО")

if __name__ == "__main__":
    run_backfill()
