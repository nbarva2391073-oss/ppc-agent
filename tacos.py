# ============================================================
# TACoS — розрахунок Total ACoS та Organic Share по ASIN
# Зводить Advertised Product + Business Report.
# Business Report має затримку консолідації ~1-2 доби (див.
# business_report.py), тому TACoS теж рахує "позавчора" як основну
# дату, плюс catch-up по попередніх днях, які ще не порахувались
# (Business Report тоді ще не мав для них даних).
# Запускається о 23:00 UTC.
# ============================================================

from datetime import datetime, timedelta
from sheets import calculate_tacos, cleanup_tacos, get_sheet


def get_target_date() -> str:
    return (datetime.utcnow() - timedelta(days=2)).strftime("%Y-%m-%d")


def get_catchup_dates(days_back: int = 2) -> list:
    today = datetime.utcnow()
    return [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(2, days_back + 2)]


def tacos_date_missing(market: str, date: str) -> bool:
    sheet_name = f"TACoS_{market}"
    try:
        sh = get_sheet(sheet_name)
        rows = sh.get_all_values()
    except Exception:
        return True
    return not any(r and r[0] == date for r in rows[1:])


def run_tacos():
    print("=" * 60)
    print(f"📊 TACoS — РОЗРАХУНОК ОРГАНІКА VS РЕКЛАМА")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    target_date = get_target_date()
    print(f"📅 Основна дата (позавчора): {target_date}")

    for market in ["USA", "CA"]:
        print(f"\n🌎 {market}...")
        try:
            calculate_tacos(market, target_date)
        except Exception as e:
            import traceback
            print(f"  ❌ {market} помилка: {e}")
            traceback.print_exc()

    print("\n🔄 Catch-up: перевіряємо попередні дні на відсутність...")
    for market in ["USA", "CA"]:
        for date in get_catchup_dates():
            if date == target_date:
                continue
            if tacos_date_missing(market, date):
                print(f"\n  🔁 [{market}] {date}: відсутній, пробуємо порахувати")
                try:
                    calculate_tacos(market, date)
                except Exception as e:
                    import traceback
                    print(f"  ❌ {market} {date} помилка: {e}")
                    traceback.print_exc()

    for market in ["USA", "CA"]:
        try:
            cleanup_tacos(market)
        except Exception as e:
            print(f"  ⚠️ cleanup_tacos {market}: {e}")

    print("\n✅ TACoS ЗАВЕРШЕНО")


if __name__ == "__main__":
    run_tacos()
