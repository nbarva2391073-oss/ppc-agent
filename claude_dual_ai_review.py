# ============================================================
# CLAUDE DUAL-AI REVIEW — Round 1 / Round 2 координації з ChatGPT
# через вкладку "Joint Review Queue" (додано 23.09.2026)
# ------------------------------------------------------------
# Навіщо: для ВАГОМИХ (Material = YES) стратегічних X2/PPC-рішень —
# не для щоденної тактики ставок (та лишається в claude_daily_review.py
# / claude_weekly_x2_review.py без змін) — Nataly хотіла, щоб Claude і
# ChatGPT спочатку незалежно (наосліп) сформулювали висновок, а потім
# один раз звірились — без ручного копіювання повідомлень між двома AI.
#
# Протокол (узгоджено з Nataly + ChatGPT 22-23.09.2026):
#   Round 1 (сліпий): кожна сторона отримує тільки Question + Shared
#     Evidence (нейтральний опис, без нічиєї інтерпретації — його
#     заповнює сама Nataly при створенні рядка) + доступ до сирих даних
#     цієї ж таблиці. Жодна сторона НЕ бачить R1-колонок іншої, навіть
#     якщо вони вже заповнені — код нижче свідомо ніколи не читає
#     "ChatGPT R1 *" під час Round 1.
#   Round 2 (звірка): дозволено тільки коли ОБИДВІ сторони мають
#     R1 Status = DONE. Кожна сторона читає обидва R1-висновки і пише
#     Agree / Partially agree / Disagree + причину + чи змінилась
#     позиція і чому саме (не "бо інший так сказав").
#   Максимум 2 раунди — далі рішення за Nataly (поле "Nataly Decision").
#
# Nataly сама додає новий рядок (Decision ID, Created, Question,
# Shared Evidence, Material) — жоден AI новий рядок не створює, тільки
# заповнює свої колонки для вже існуючого Decision ID.
#
# Запуск:
#   python claude_dual_ai_review.py round1   — тільки Round 1
#   python claude_dual_ai_review.py round2   — тільки Round 2
#   python claude_dual_ai_review.py both     — обидва (типово)
# ============================================================

import sys
from datetime import datetime

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from sheets import (
    get_claude_round1_queue, get_claude_round2_queue,
    write_claude_round1_result, write_claude_round2_result,
)
from telegram_bot import send_message
from claude_weekly_x2_review import build_weekly_x2_context, _format_table


# ── Парсинг структурованої відповіді ────────────────────────────────

def _parse_fields(text: str, field_names: list[str]) -> dict:
    """Витягує CONCLUSION:/EVIDENCE:/... блоки з відповіді моделі.
    Кожне поле триває до наступного розпізнаного маркера або кінця
    тексту. Якщо модель не дотрималась формату — усе падає в перше
    поле, щоб інформація хоча б не загубилась (видно буде в Sheets)."""
    markers = {name: f"{name.upper()}:" for name in field_names}
    positions = []
    for name, marker in markers.items():
        idx = text.upper().find(marker)
        if idx != -1:
            positions.append((idx, name, marker))
    positions.sort()
    result = {name: "" for name in field_names}
    if not positions:
        result[field_names[0]] = text.strip()
        return result
    for i, (idx, name, marker) in enumerate(positions):
        start = idx + len(marker)
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        result[name] = text[start:end].strip()
    return result


# ── Round 1 (сліпий) ─────────────────────────────────────────────────

def _round1_prompt(question: str, shared_evidence: str) -> str:
    # Дані по обох ринках — те саме джерело, що вже читає щотижневий
    # X2-огляд, щоб Round 1 спирався на ту саму сувору дисципліну
    # (max date, дедуплікація, R039, Sellerise vs Amazon), а не вигадував.
    ctx_usa = build_weekly_x2_context("USA")
    ctx_ca = build_weekly_x2_context("CA")

    return f"""Ти — незалежний стратегічний X2-аналітик для бренду ALFAMARKER.
Поруч є інший інструмент аналізу (ChatGPT) — його висновку з цього самого
питання ти НЕ бачиш і не повинен вгадувати чи підтверджувати. Це справжній
Round 1 сліпого протоколу: сформулюй свою позицію самостійно, з нуля.

Це ВАГОМЕ стратегічне рішення (не щоденна тактика ставок) — постав
Nataly, яке вимагає твого чесного, обґрунтованого висновку, а не
узагальненої поради.

ПИТАННЯ:
{question}

SHARED EVIDENCE / DATA SCOPE (нейтральний опис від Nataly, без нічиєї
інтерпретації — тільки факти, дати, ASIN/campaign):
{shared_evidence}

Нижче — сирі дані по обох ринках з тієї самої таблиці, якою користуються
і ти, і ChatGPT. Дотримуйся тих самих правил, що і в щотижневому
X2-огляді: перевіряй фактичну max-дату джерела, не вигадуй цифр, яких
немає в даних, явно зазнач обмеження атрибуції (R039: Advertised SKU vs
blended), не сумуй Sellerise з Amazon за одну дату.

{'='*60}
USA — MONTHLY SALES HISTORY
{'='*60}
{_format_table(ctx_usa['monthly_sales_history'], max_rows=40)}

{'='*60}
USA — BUSINESS REPORT (хвіст)
{'='*60}
{_format_table(ctx_usa['business_report_tail'], max_rows=60)}

{'='*60}
USA — CAMPAIGN PERFORMANCE HISTORY
{'='*60}
{_format_table(ctx_usa['campaign_perf_history'], max_rows=8)}

{'='*60}
CA — MONTHLY SALES HISTORY
{'='*60}
{_format_table(ctx_ca['monthly_sales_history'], max_rows=40)}

{'='*60}
CA — BUSINESS REPORT (хвіст)
{'='*60}
{_format_table(ctx_ca['business_report_tail'], max_rows=60)}

ФОРМАТ ВІДПОВІДІ (обов'язково саме такими маркерами, кожен з нового рядка):

CONCLUSION: одне-два речення — конкретний висновок, не загальна порада.
EVIDENCE: ключові цифри/факти, на яких тримається висновок.
CONFIDENCE: High / Medium / Low — і чому саме такий рівень.
CHANGE_MIND: що конкретно змінило б цю позицію (новий факт, тест, дані).
LIMITATIONS: чого в наявних даних бракує для повнішої впевненості
(незріле attribution, відсутній Business Report, blended замість
same-SKU тощо — конкретно, не загальною фразою)."""


def run_round1():
    queue = get_claude_round1_queue()
    if not queue:
        print("  ⏭️ Claude Dual-AI Round 1: немає нових вагомих питань у черзі")
        return
    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for item in queue:
        decision_id = item["decision_id"]
        print(f"\n🧠 Claude Dual-AI Round 1: {decision_id}...")
        try:
            prompt = _round1_prompt(item["question"], item["shared_evidence"])
            response = ai_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            fields = _parse_fields(
                text, ["CONCLUSION", "EVIDENCE", "CONFIDENCE", "CHANGE_MIND", "LIMITATIONS"])
            write_claude_round1_result(
                decision_id,
                conclusion=fields["CONCLUSION"],
                evidence=fields["EVIDENCE"],
                confidence=fields["CONFIDENCE"],
                change_mind=fields["CHANGE_MIND"],
                limitations=fields["LIMITATIONS"],
            )
            send_message(
                f"🧠 <b>CLAUDE — Dual-AI Round 1</b>\n"
                f"Decision ID: {decision_id}\n"
                f"Висновок: {fields['CONCLUSION'][:400]}\n"
                f"(повний текст → Google Sheets, Joint Review Queue)"
            )
        except Exception as e:
            print(f"  ❌ Claude Dual-AI Round 1 {decision_id}: {e}")


# ── Round 2 (звірка) ─────────────────────────────────────────────────

def _round2_prompt(question: str, shared_evidence: str,
                    own_conclusion: str, own_evidence: str,
                    other_conclusion: str, other_evidence: str,
                    other_confidence: str, other_limitations: str) -> str:
    return f"""Це Round 2 сліпого dual-AI протоколу для ALFAMARKER. У Round 1 ти
(Claude) і ChatGPT незалежно, не бачачи одне одного, відповіли на те
саме питання. Тепер порівняй обидва висновки.

ПИТАННЯ:
{question}

SHARED EVIDENCE:
{shared_evidence}

ТВІЙ ВЛАСНИЙ ВИСНОВОК З ROUND 1:
{own_conclusion}
Докази: {own_evidence}

ВИСНОВОК CHATGPT З ROUND 1 (він так само не бачив твого):
{other_conclusion}
Докази: {other_evidence}
Впевненість ChatGPT: {other_confidence}
Обмеження за ChatGPT: {other_limitations}

Правило: змінюй позицію ТІЛЬКИ якщо ChatGPT навів новий факт чи
аргумент, якого не було у твоєму Round 1 — не "бо інший так сказав".
Якщо нового аргументу немає — лишайся при своїй позиції, навіть якщо
вона відрізняється від ChatGPT. Це останній раунд — далі рішення за
Nataly, тож чесно зафіксуй, у чому саме згода, а у чому ні, замість
штучного компромісу.

ФОРМАТ ВІДПОВІДІ (обов'язково саме такими маркерами):

POSITION: Agree / Partially agree / Disagree.
REASON: чому саме така позиція — конкретно, з посиланням на докази.
CHANGED: Так/Ні — і якщо так, який КОНКРЕТНИЙ новий факт/аргумент від
ChatGPT це змінив (не просто "переконав")."""


def run_round2():
    queue = get_claude_round2_queue()
    if not queue:
        print("  ⏭️ Claude Dual-AI Round 2: немає питань, готових до звірки")
        return
    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    for item in queue:
        decision_id = item["decision_id"]
        print(f"\n🧠 Claude Dual-AI Round 2: {decision_id}...")
        try:
            prompt = _round2_prompt(
                item["question"], item["shared_evidence"],
                item["claude_r1_conclusion"], item["claude_r1_evidence"],
                item["chatgpt_r1_conclusion"], item["chatgpt_r1_evidence"],
                item["chatgpt_r1_confidence"], item["chatgpt_r1_limitations"],
            )
            response = ai_client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text
            fields = _parse_fields(text, ["POSITION", "REASON", "CHANGED"])
            write_claude_round2_result(
                decision_id,
                position=fields["POSITION"],
                reason=fields["REASON"],
                changed=fields["CHANGED"],
            )
            send_message(
                f"🧠 <b>CLAUDE — Dual-AI Round 2</b>\n"
                f"Decision ID: {decision_id}\n"
                f"Позиція: {fields['POSITION']}\n"
                f"{fields['REASON'][:400]}\n"
                f"(повний текст обох сторін → Google Sheets, Joint Review Queue)"
            )
        except Exception as e:
            print(f"  ❌ Claude Dual-AI Round 2 {decision_id}: {e}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if not ANTHROPIC_API_KEY:
        print("  ⏭️ Claude Dual-AI Review: ANTHROPIC_API_KEY не задано, пропускаємо")
        sys.exit(0)
    if mode in ("round1", "both"):
        run_round1()
    if mode in ("round2", "both"):
        run_round2()
