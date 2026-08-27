# ============================================================
# TACoS — розрахунок Total ACoS та Organic Share по ASIN
# Зводить Advertised Product + Business Report за вчорашній день
# Запускається окремо о 23:00 UTC, коли обидва джерела вже записані
# ============================================================

from datetime import datetime, timedelta
from sheets import calculate_tacos, cleanup_tacos


def get_yesterday() -> str:
    return "2026-08-25"  # TEMP: ручний перерахунок з правильними child ASIN


def run_tacos():
    print("=" * 60)
    print(f"📊 TACoS — РОЗРАХУНОК ОРГАНІКА VS РЕКЛАМА")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    date = get_yesterday()
    print(f"📅 Дата: {date}")

    for market in ["USA", "CA"]:
        print(f"\n🌎 {market}...")
        try:
            calculate_tacos(market, date)
            cleanup_tacos(market)
        except Exception as e:
            import traceback
            print(f"  ❌ {market} помилка: {e}")
            traceback.print_exc()

    print("\n✅ TACoS ЗАВЕРШЕНО")


if __name__ == "__main__":
    run_tacos()
