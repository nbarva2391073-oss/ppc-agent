# ============================================================
# CLAUDE WEEKLY X2 REVIEW — незалежний щотижневий стратегічний
# огляд ходу до цілі X2 (подвоєння продажів), окремо від:
#   - claude_daily_review.py   (щоденна тактика ставок/таргетів)
#   - analyzer.py/main_weekly.py (тижневий AI Recommendations —
#     той інструмент, яким Nataly вже користується, ChatGPT-подібний
#     аналіз; Claude тут його висновків НЕ читає і не намагається
#     вгадати чи підтвердити — справді незалежна друга думка).
# ------------------------------------------------------------
# Що це:
#   - Стратегічний рівень (ASIN/Brand), не тактика окремого bid'а:
#     чи рухаємось до X2, у яких пріоритетних ASIN цього тижня
#     змінився статус, які живі тести перетнули evidence-поріг.
#   - Читає ту саму таблицю (`1yDQzK8Ep...`), підмножину вкладок з
#     X2-протоколу читання (x2-strategy-working-mode.md): Monthly
#     Sales History, ASIN Control, Business_Report, Advertised
#     Product, TACoS, Campaign Performance History US, Placement
#     Analysis, Brand Event Log. НЕ починає з Search Terms/Keyword
#     Intelligence/raw campaign dumps — той самий принцип, що і в
#     ручному X2-аналізі.
#   - Пише результат в окрему вкладку "Claude Weekly X2 Review
#     {market}" і шле окреме Telegram-повідомлення — так само, як
#     Claude Daily Review відділений від AI Recommendations.
#   - Точні 7-денні вирівняні вікна (поточний тиждень vs попередній
#     vs MTD) навмисно НЕ рахуються тут у Python — це вимагало б
#     відтворити нетривіальні правила дедуплікації з проєктного
#     документа (тижневі rollup-рядки поряд із щоденними, intraday
#     cumulative snapshots). Замість цього моделі передаються сирі
#     хвости таблиць + самі правила текстом у промпті, і вона сама
#     перевіряє фактичну max-дату джерела та вирівнює періоди —
#     той самий підхід, що вже працює в claude_daily_review.py.
#
# Запускається раз на 7 днів через GitHub Actions
# (.github/workflows/weekly_x2_review.yml, понеділок 13:00 UTC —
# це після 14:00 Europe/Sofia і взимку (UTC+2), і влітку (UTC+3)).
# ============================================================

from datetime import datetime

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MARGIN
from sheets import read_all, write_claude_weekly_x2_review
from telegram_bot import send_claude_weekly_x2_review
from claude_daily_review import _format_table, _tail


# ── Точні назви вкладок (звірено з x2-strategy-working-mode.md) ──
# УВАГА: "Campaign Performance History US" — без "A" на кінці, це
# підтверджена в документі назва, не помилка.

X2_TAB_NAMES = {
    "USA": {
        "monthly_sales_history": "Monthly Sales History USA",
        "asin_control":          "ASIN Control USA",
        "business_report":       "Business_Report_USA",
        "advertised_product":    "Advertised Product USA",
        "tacos":                 "TACoS_USA",
        "campaign_perf_history": "Campaign Performance History US",
        "placement_analysis":    "Placement Analysis USA",
        "brand_event_log":       "Brand Event Log",
        "prev_reviews":          "Claude Weekly X2 Review USA",
    },
    "CA": {
        "monthly_sales_history": "Monthly Sales History CA",
        "asin_control":          "ASIN Control CA",
        "business_report":       "Business_Report_CA",
        "advertised_product":    "Advertised Product CA",
        "tacos":                 "TACoS_CA",
        "campaign_perf_history": "Campaign Performance History CA",
        "placement_analysis":    "Placement Analysis CA",
        "brand_event_log":       "Brand Event Log",
        "prev_reviews":          "Claude Weekly X2 Review CA",
    },
}


# ── Збір контексту ───────────────────────────────────────────────

def build_weekly_x2_context(market: str) -> dict:
    tabs = X2_TAB_NAMES.get(market, X2_TAB_NAMES["USA"])

    return {
        "monthly_sales_history": read_all(tabs["monthly_sales_history"]),
        "asin_control":          read_all(tabs["asin_control"]),
        "business_report_tail":  _tail(read_all(tabs["business_report"]), 90),
        "advertised_tail":       _tail(read_all(tabs["advertised_product"]), 90),
        "tacos_tail":            _tail(read_all(tabs["tacos"]), 60),
        "campaign_perf_history": _tail(read_all(tabs["campaign_perf_history"]), 8),
        "placement_tail":        _tail(read_all(tabs["placement_analysis"]), 40),
        "brand_event_log":       _tail(read_all(tabs["brand_event_log"]), 40),
        "prev_review_tail":      _tail(read_all(tabs["prev_reviews"]), 2),
    }


# ── AI аналіз ─────────────────────────────────────────────────────

def deep_weekly_x2_review(market: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    ctx = build_weekly_x2_context(market)
    margin = MARGIN.get(market, 0.25)
    breakeven = margin * 100

    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Ти — незалежний стратегічний аналітик росту для бренду
ALFAMARKER ({market}). Поруч є інший інструмент аналізу (ChatGPT), його
висновків ти не бачиш і не повинен вгадувати чи підтверджувати — твоя
роль повністю самостійна друга думка, так само як для щоденного
тактичного огляду (окремий інструмент, не цей).

Це ЩОТИЖНЕВИЙ СТРАТЕГІЧНИЙ огляд ходу до цілі X2 (подвоєння продажів
бренду) — не тактика ставок на сьогодні (та робиться окремо, щодня).
Питання цього огляду: чи рухаємось до X2, у яких пріоритетних ASIN
цього тижня змінився статус, які живі тести перетнули evidence-поріг
і потребують рішення.

Дата запуску: {today}. Break-even ACoS: {breakeven:.1f}%.

ОБОВ'ЯЗКОВІ ПРАВИЛА (з робочого документа проєкту, застосовувати
завжди, без винятків):
- Перед тим, як вважати період "завершеним тижнем" — знайди фактичну
  останню дату в наведених нижче таблицях. Не припускай, що дані вже
  покривають повний календарний тиждень.
- Порівнюй тільки вирівняні періоди: поточні 7 завершених днів vs
  попередні 7 днів vs MTD. Якщо вирівняти неможливо через неповні
  дані — прямо скажи це і чому, не рахуй наближено "на око".
- У Business Report / Advertised Product можуть траплятися дублікати
  рядків і змішані гранулярності (тижневі rollup-рядки поряд із
  щоденними, intraday cumulative snapshots одного дня). Якщо бачиш
  підозріло однакові чи по-денно зростаючі рядки для одного й того ж
  ключа (дата+кампанія+ASIN) — не підсумовуй їх наосліп, зазнач це як
  застереження в розділі "Застереження щодо даних", а не мовчки
  виправляй.
- Total Business Report CVR (units/sessions) — це НЕ organic CVR,
  навіть коли на ASIN немає власних PPC-кампаній (sessions/units не
  розкладаються Amazon на paid/organic). Не видавай total CVR за
  виміряну organic- чи paid-CVR в жодному напрямку.
- Малі evidence-ladder пороги (напр. 15-20 relevant кліків без order
  на одному таргеті) — це сигнал ЛОКАЛЬНО по цьому таргету, не
  фінальний вердикт по всьому ASIN/тесту. Фінальний негативний
  вердикт — тільки на ~45-50 сукупних ДОЗРІЛИХ relevant кліках без
  жодного order по всьому тесту.
- Один сильний ASIN/таргет серед кількох слабких — не привід закривати
  весь напрямок; виділяй переможця окремо від слабких.
- Не вигадуй цифр, яких немає в даних нижче. Якщо конкретної таблиці
  немає або вона порожня — прямо напиши "даних немає", а не імітуй
  висновок із порожніх рядків.

{'='*60}
MONTHLY SALES HISTORY — продажі по ASIN, помісячно
{'='*60}
{_format_table(ctx['monthly_sales_history'], max_rows=60)}

{'='*60}
ASIN CONTROL — статуси ASIN (блокування реклами, eligibility тощо)
{'='*60}
{_format_table(ctx['asin_control'], max_rows=40)}

{'='*60}
BUSINESS REPORT — останні рядки (sessions/units/sales по ASIN)
{'='*60}
{_format_table(ctx['business_report_tail'], max_rows=90)}

{'='*60}
ADVERTISED PRODUCT — останні рядки (продажі через рекламу по ASIN)
{'='*60}
{_format_table(ctx['advertised_tail'], max_rows=90)}

{'='*60}
TACoS — органіка vs реклама по ASIN, останні рядки
{'='*60}
{_format_table(ctx['tacos_tail'], max_rows=60)}

{'='*60}
CAMPAIGN PERFORMANCE HISTORY US — місячні агрегати по кампаніях
{'='*60}
{_format_table(ctx['campaign_perf_history'], max_rows=8)}

{'='*60}
PLACEMENT ANALYSIS — останні рядки
{'='*60}
{_format_table(ctx['placement_tail'], max_rows=40)}

{'='*60}
BRAND EVENT LOG — структурні події (ціна/rebuild/baseline), останні
{'='*60}
{_format_table(ctx['brand_event_log'], max_rows=40)}

{'='*60}
ТВОЇ ОСТАННІ 2 ЩОТИЖНЕВІ X2-ОГЛЯДИ (контекст тренду — не повторюй
дослівно, згадуй тільки якщо статус реально змінився)
{'='*60}
{_format_table(ctx['prev_review_tail'], max_rows=10)}

{'='*60}
ФОРМАТ ВІДПОВІДІ
{'='*60}

## 🎯 Статус X2 цього тижня
Одне-два речення: рухаємось до цілі чи ні, на основі вирівняних 7д vs
7д vs MTD (або прямо скажи, що вирівняти неможливо, і чому саме).

## 🔴 Потрібне рішення цього тижня
Конкретні ASIN/тести, де evidence-поріг вже перетнутий і справді є що
вирішувати (пауза/масштаб/перегляд ціни) — з посиланням на конкретні
цифри з таблиць вище.

## 🟡 Спостерігати (ще не дозріло)
ASIN/тести, де щось змінюється, але вибірка чи період замалі для дії.

## ✅ Без змін
Коротко — що триває в нормі, без нових рішень цього тижня.

## ⚠️ Застереження щодо даних
Дублікати, неповні періоди, зіпсовані значення, відсутні вкладки —
якщо є, зазнач прямо тут, а не мовчки виправляй чи ігноруй.

Якщо дані за цей тиждень не оновились з минулого огляду або їх немає
— прямо напиши, що аналізувати нічого нового, а не імітуй висновок з
тих самих цифр."""

    response = ai_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Запуск ─────────────────────────────────────────────────────────

def run_weekly_x2_review(market: str):
    if not ANTHROPIC_API_KEY:
        print(f"  ⏭️ Claude Weekly X2 Review {market}: ANTHROPIC_API_KEY не задано, пропускаємо")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n🎯 Claude Weekly X2 Review {market}...")
    try:
        text = deep_weekly_x2_review(market)
        write_claude_weekly_x2_review(text, today, market)
        send_claude_weekly_x2_review(market, today, text)
        print(f"  ✅ Claude Weekly X2 Review {market}: збережено та відправлено")
    except Exception as e:
        print(f"  ❌ Claude Weekly X2 Review {market}: {e}")


if __name__ == "__main__":
    import sys
    market_arg = sys.argv[1] if len(sys.argv) > 1 else "USA"
    run_weekly_x2_review(market_arg)
