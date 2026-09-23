# ============================================================
# CLAUDE DAILY REVIEW — незалежний щоденний тактичний аналіз
# ------------------------------------------------------------
# Що це: другий, незалежний погляд поруч з ChatGPT, яким Nataly вже
# користується для щоранкових рекомендацій (зміна ставок, вимкнення
# таргетів). Claude тут:
#   - НЕ читає жодних рекомендацій ChatGPT (немає до них доступу) —
#     тому висновок дійсно незалежний, а не підтвердження чужого;
#   - працює з тими самими сирими даними, що вже пише ppc-agent
#     (Bid History / Campaign Analysis / Placement / Keyword
#     Intelligence / Advertised Product) — тобто дивиться в ту саму
#     таблицю, з якої бере дані ChatGPT;
#   - пише результат в окрему вкладку "Claude Daily Review {market}",
#     щоб порівнювати з ChatGPT можна було вручну, без автоматичного
#     злиття висновків.
# Запускається щодня з monitor.py, одразу після збору даних за день.
# ============================================================

from datetime import datetime

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MARGIN, SHEETS_USA, SHEETS_CA
from sheets import read_all, write_claude_daily_review
from telegram_bot import send_claude_daily_review


# ── Допоміжне форматування ──────────────────────────────────────

def _rows_for_value(rows: list, col_name: str, value: str) -> list:
    """Заголовок + рядки, де колонка col_name == value (порівняння за назвою
    колонки, не за індексом — стійко до зміни порядку колонок)."""
    if not rows:
        return []
    header = rows[0]
    if col_name not in header:
        return [header]
    idx = header.index(col_name)
    matched = [r for r in rows[1:] if len(r) > idx and r[idx] == value]
    return [header] + matched


def _tail(rows: list, n: int) -> list:
    """Заголовок + останні n рядків."""
    if not rows:
        return []
    if len(rows) <= n + 1:
        return rows
    return [rows[0]] + rows[-n:]


def _format_table(rows: list, max_rows: int = 40) -> str:
    if not rows or len(rows) <= 1:
        return "(немає даних за сьогодні)"
    header, body = rows[0], rows[1:]
    if len(body) > max_rows:
        body = body[-max_rows:]
    lines = [" | ".join(str(c) for c in header)]
    for r in body:
        lines.append(" | ".join(str(c) for c in r))
    return "\n".join(lines)


# ── Збір контексту ───────────────────────────────────────────────

def build_daily_context(market: str, today: str) -> dict:
    sheets = SHEETS_USA if market == "USA" else SHEETS_CA

    bid_history = read_all(sheets["bid_history"])
    bid_today = _rows_for_value(bid_history, "Date", today)

    # Campaign Analysis — це живий знімок поточного тижня (upsert щодня),
    # не історія по днях, тому беремо весь аркуш як є.
    campaign_analysis = read_all(sheets["campaign_analysis"])

    placement_tail = _tail(read_all(sheets["placement_analysis"]), 40)

    keyword_intel = read_all(sheets["keyword_intelligence"])
    kw_today = _rows_for_value(keyword_intel, "Run Date", today)

    advertised = read_all(sheets["advertised_product"])
    advertised_today = _rows_for_value(advertised, "Date", today)

    prev_reviews_tail = _tail(read_all(sheets["claude_daily_review"]), 3)

    return {
        "bid_today":         bid_today,
        "campaign_analysis": campaign_analysis,
        "placement_tail":    placement_tail,
        "kw_today":          kw_today,
        "advertised_today":  advertised_today,
        "prev_tail":         prev_reviews_tail,
    }


# ── AI аналіз ─────────────────────────────────────────────────────

def deep_daily_review(market: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    ctx = build_daily_context(market, today)
    margin = MARGIN.get(market, 0.25)
    breakeven = margin * 100

    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Ти — незалежний PPC-аналітик. Поруч є інший інструмент аналізу
(окремо від тебе, ти його висновків не бачиш і не повинен вгадувати чи
підтверджувати). Твоя роль — самостійна друга думка, а не звірка з кимось.

Проаналізуй сьогоднішні дані Amazon Ads по бренду ALFAMARKER ({market}),
{today}, і дай конкретні тактичні дії — рівня ранкового брифу: що саме
змінилось у ставках, які таргети вимкнути чи знизити, де перерозподілити
бюджет. Не давай загальних порад — тільки те, що підтверджено цифрами
нижче.

Break-even ACoS: {breakeven:.1f}%

{'='*60}
ЗМІНИ СТАВОК СЬОГОДНІ (Bid History, {today})
{'='*60}
{_format_table(ctx['bid_today'])}

{'='*60}
СТАН КАМПАНІЙ (поточний тиждень, оновлюється щодня)
{'='*60}
{_format_table(ctx['campaign_analysis'])}

{'='*60}
PLACEMENT — ОСТАННІ ЗАПИСИ
{'='*60}
{_format_table(ctx['placement_tail'])}

{'='*60}
KEYWORD INTELLIGENCE СЬОГОДНІ
{'='*60}
{_format_table(ctx['kw_today'])}

{'='*60}
ADVERTISED PRODUCT СЬОГОДНІ (продажі по ASIN через рекламу)
{'='*60}
{_format_table(ctx['advertised_today'])}

{'='*60}
ТВОЇ ОСТАННІ 3 ЩОДЕННІ ОГЛЯДИ (контекст тренду — не повторюй дослівно)
{'='*60}
{_format_table(ctx['prev_tail'])}

{'='*60}
ФОРМАТ ВІДПОВІДІ
{'='*60}

## 🔴 Негайні дії сьогодні
Конкретно: яку ставку на яке ключове слово/кампанію змінити (до
скількох $), яке вимкнути, де перерозподілити бюджет.

## 🟡 Спостерігати (ще не дія)
Що виглядає підозріло, але вибірка замала для рішення.

## ✅ Без змін
Коротко, що працює в нормі.

## 🎯 Головний висновок дня
Одне речення.

Якщо даних за сьогодні немає (звіт ще не готовий, вихідний Amazon Ads)
— прямо напиши, що аналізувати нічого, а не імітуй висновок з порожніх
таблиць. Не вигадуй цифр, яких немає у наведених даних."""

    response = ai_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Запуск ─────────────────────────────────────────────────────────

def run_daily_review(market: str):
    if not ANTHROPIC_API_KEY:
        print(f"  ⏭️ Claude Daily Review {market}: ANTHROPIC_API_KEY не задано, пропускаємо")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n🧠 Claude Daily Review {market}...")
    try:
        text = deep_daily_review(market)
        write_claude_daily_review(text, today, market)
        send_claude_daily_review(market, today, text)
        print(f"  ✅ Claude Daily Review {market}: збережено та відправлено")
    except Exception as e:
        print(f"  ❌ Claude Daily Review {market}: {e}")


if __name__ == "__main__":
    import sys
    market_arg = sys.argv[1] if len(sys.argv) > 1 else "USA"
    run_daily_review(market_arg)
