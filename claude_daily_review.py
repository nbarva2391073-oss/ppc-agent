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

from config import (ANTHROPIC_API_KEY, CLAUDE_MODEL, SHEETS_USA, SHEETS_CA,
                    EXCLUDED_CAMPAIGN_IDS, EXCLUDED_CAMPAIGN_NAMES)
from sheets import read_all, read_all_optional, write_claude_daily_review
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


def _drop_excluded(rows: list) -> list:
    """Прибирає рядки виключених кампаній (за CampaignId або назвою) з вхідних даних огляду."""
    if not rows or len(rows) <= 1:
        return rows
    h = rows[0]
    i_id = h.index("CampaignId") if "CampaignId" in h else None
    i_nm = next((h.index(c) for c in ("Campaign", "CampaignName", "Campaign Name") if c in h), None)
    out = [h]
    for r in rows[1:]:
        cid = str(r[i_id]).strip().lstrip("'") if i_id is not None and len(r) > i_id else ""
        nm = str(r[i_nm]).strip().lower() if i_nm is not None and len(r) > i_nm else ""
        if cid in EXCLUDED_CAMPAIGN_IDS or nm in EXCLUDED_CAMPAIGN_NAMES:
            continue
        out.append(r)
    return out


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
    bid_today = _drop_excluded(_rows_for_value(bid_history, "Date", today))

    # Campaign Analysis — це живий знімок поточного тижня (upsert щодня),
    # не історія по днях, тому беремо весь аркуш як є.
    campaign_analysis = _drop_excluded(read_all(sheets["campaign_analysis"]))

    placement_tail = _tail(_drop_excluded(read_all(sheets["placement_analysis"])), 40)

    keyword_intel = read_all(sheets["keyword_intelligence"])
    kw_today = _drop_excluded(_rows_for_value(keyword_intel, "Run Date", today))

    advertised = read_all(sheets["advertised_product"])
    advertised_today = _rows_for_value(advertised, "Date", today)

    prev_reviews_tail = _tail(read_all(sheets["claude_daily_review"]), 3)

    # Ручні аркуші Nataly: захищені тести / дати review. Лише читання,
    # аркуш не створюється, якщо його немає.
    control = _drop_excluded(read_all_optional(sheets.get("campaign_control", "Campaign Control USA")))
    review_queue = _drop_excluded(read_all_optional(sheets.get("review_queue", "Review Queue USA")))

    return {
        "bid_today":         bid_today,
        "campaign_analysis": campaign_analysis,
        "placement_tail":    placement_tail,
        "kw_today":          kw_today,
        "advertised_today":  advertised_today,
        "prev_tail":         prev_reviews_tail,
        "control":           control,
        "review_queue":      review_queue,
        "has_today_data":    len(kw_today) > 1 or len(advertised_today) > 1,
    }


# ── AI аналіз ─────────────────────────────────────────────────────

def deep_daily_review(market: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    ctx = build_daily_context(market, today)

    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Ти — незалежний PPC-аналітик. Поруч є інший інструмент аналізу
(окремо від тебе, ти його висновків не бачиш і не повинен вгадувати чи
підтверджувати). Твоя роль — самостійна друга думка, а не звірка з кимось.

Проаналізуй сьогоднішні дані Amazon Ads по бренду ALFAMARKER ({market}),
{today}, і дай конкретні тактичні дії — рівня ранкового брифу: що саме
змінилось у ставках, які таргети вимкнути чи знизити, де перерозподілити
бюджет. Не давай загальних порад — тільки те, що підтверджено цифрами
нижче.

ЕКОНОМІКА (використовуй саме ці пороги, інших не вигадуй):
- Беззбитковий ACoS одиниці товару ≈ 50% при ціні ~$25 (беззбитковий CPA ≈ $13).
- Червона лінія для акаунта в цілому: ACoS 35–40%. Комфортна зона: 25–30%.
- ACoS вище 30%, але нижче 50% по окремому таргету — «вище комфортної зони», а НЕ збитковість.
  Збитковість — лише при ACoS > 50% (або CPA > $13) на достатній вибірці кліків.
- Колонка above_comfort_cpc у Bid History — груба евристика (Suggested > max CPC по ASIN),
  не беззбитковість.

ПРАВИЛА ПОВЕДІНКИ:
1. Не радь паузу чи зміну ставки там, де в Campaign Control / Review Queue є захищений тест
   із датою review, яка ще не настала. Натомість напиши «захищений тест до <дата>, спостерігати».
2. Не повторюй ту саму пораду (особливо паузу) кілька днів поспіль без НОВИХ даних.
   Якщо порада вже була в попередніх оглядах, а нових даних немає — не повторюй.
   Якщо повторюєш — поясни, що саме нового.
3. Порівнюй ефективні ставки: база × (1 + TopAdj%/100) для Top of Search і
   база × (1 + RestAdj%/100) для Rest of Search (колонки TopAdj%/RestAdj% у Bid History,
   якщо порожні — корекцій невідомо, не припускай їх), а не лише базову ставку проти Suggested.
4. Suggested bid — НЕ ціль. Це орієнтир; джерела розходяться (напр., «pheromone oil»:
   $0.53 / $1.01 / $1.16 у Bid History проти $3.81 у Bid Monitor). Завжди вказуй
   джерело числа і не радь підняти ставку лише тому, що вона нижча за Suggested.
5. Рядки з reason, що починається з «DATA ISSUE», — проблема даних, не зміна ставки:
   не роби з них висновків про ставки, лише згадай як проблему даних.
6. Кампанії зі списку виключень у даних відсутні; не згадуй їх і не пропонуй для них дій.
{"7. СЬОГОДНІ ДАНИХ НЕМАЄ (Keyword Intelligence і Advertised Product порожні): розділ «Негайні дії» має містити лише «Немає — даних за сьогодні немає», усі спостереження — тільки в «Спостерігати»." if not ctx['has_today_data'] else ""}

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
CAMPAIGN CONTROL (ручний аркуш Nataly — захищені тести, статуси)
{'='*60}
{_format_table(ctx['control'], max_rows=60)}

{'='*60}
REVIEW QUEUE (ручний аркуш Nataly — дати review)
{'='*60}
{_format_table(ctx['review_queue'], max_rows=60)}

{'='*60}
ТВОЇ ОСТАННІ 3 ЩОДЕННІ ОГЛЯДИ (контекст тренду — не повторюй дослівно і не повторюй поради без нових даних)
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

    # 2000 токенів обривали бриф посеред речення (≈4 400 символів, 09.10).
    response = ai_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    if getattr(response, "stop_reason", "") == "max_tokens":
        text += "\n\n⚠️ Огляд обрізано за ліміту довжини (max_tokens) — частину висновків може бракувати."
        print("  ⚠️ Claude Daily Review: stop_reason=max_tokens")
    return text


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
