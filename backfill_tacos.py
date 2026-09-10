import sys
from sheets import calculate_tacos, cleanup_tacos

MARKET = sys.argv[1]
DATES = sys.argv[2:]

for date in DATES:
    print(f"\n📅 TACoS {MARKET} за {date}")
    try:
        calculate_tacos(MARKET, date)
    except Exception as e:
        import traceback
        print(f"❌ {date}: {e}")
        traceback.print_exc()

cleanup_tacos(MARKET)
print("\n✅ Backfill завершено")
