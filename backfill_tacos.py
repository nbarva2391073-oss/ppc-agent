# ============================================================
# ОДНОРАЗОВИЙ BACKFILL — TACoS за дні, де дані вже є в Business Report
# і Advertised Product, але tacos.yml їх пропустив
# ============================================================

from sheets import calculate_tacos, cleanup_tacos

BACKFILL_DATES = [
    "2026-08-26",
    "2026-08-27",
    "2026-08-28",
    "2026-08-29",
    "2026-08-30",
]

for date in BACKFILL_DATES:
    print(f"\n{'='*50}")
    print(f"📅 Backfill TACoS за {date}")
    print(f"{'='*50}")
    try:
        calculate_tacos("USA", date)
    except Exception as e:
        import traceback
        print(f"❌ Помилка за {date}: {e}")
        traceback.print_exc()

cleanup_tacos("USA")
print("\n✅ Backfill завершено")
