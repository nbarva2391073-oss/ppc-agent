# ============================================================
# BRAND ANALYTICS — окремий запуск
# ============================================================
import sys
from datetime import datetime
from brand_analytics import get_brand_analytics, format_for_sheets
from sheets import append, SHEETS_USA, SHEETS_CA
from telegram_bot import send_message

def run_brand_analytics():
    print("=" * 60)
    print(f"🔍 BRAND ANALYTICS ЗАПУСК")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    results = {}

    for market, sheets in [("USA", SHEETS_USA), ("CA", SHEETS_CA)]:
        print(f"\n🌎 {market}...")
        try:
            records = get_brand_analytics(market)
            if records:
                headers, rows = format_for_sheets(records, market)
                append(sheets["keyword_intelligence"], rows, headers)
                results[market] = len(rows)
                print(f"✅ {market}: {len(rows)} записів збережено")
            else:
                results[market] = 0
                print(f"⚠️ {market}: даних немає")
        except Exception as e:
            print(f"❌ {market} помилка: {e}")
            results[market] = 0

    # Telegram повідомлення
    usa = results.get("USA", 0)
    ca  = results.get("CA", 0)

    if usa > 0 or ca > 0:
        send_message(
            f"🔍 <b>Brand Analytics оновлено!</b>\n"
            f"🇺🇸 USA: {usa} пошукових запитів\n"
            f"🇨🇦 CA: {ca} пошукових запитів\n"
            f"Деталі → Google Sheets (Keyword Intelligence)"
        )
    else:
        send_message("⚠️ <b>Brand Analytics:</b> даних немає цього тижня")

    print("\n✅ BRAND ANALYTICS ЗАВЕРШЕНО")

if __name__ == "__main__":
    run_brand_analytics()
