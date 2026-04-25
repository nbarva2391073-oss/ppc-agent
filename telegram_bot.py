# ============================================================
# TELEGRAM — сповіщення з діагнозом і кроками
# ============================================================

import requests
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS


def send_message(text: str, parse_mode: str = "HTML"):
    """Надіслати повідомлення всім отримувачам."""
    if not TELEGRAM_BOT_TOKEN:
        print(f"[TELEGRAM] {text}")
        return

    for chat_id in TELEGRAM_CHAT_IDS:
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as e:
            print(f"❌ Telegram помилка для {chat_id}: {e}")


def send_alert(
    level: str,           # "critical", "warning", "info"
    market: str,          # "USA" або "CA"
    problem: str,         # Що сталось
    diagnosis: str,       # Чому це сталось
    action: str,          # Що зробити
    expected_result: str, # Очікуваний результат
    risk: str = "",       # Ризики
):
    """Надіслати структуроване сповіщення з діагнозом."""

    icons = {
        "critical": "🔴",
        "warning":  "🟡",
        "info":     "🟢",
    }
    icon = icons.get(level, "⚪")

    urgency = {
        "critical": "Реагуй протягом 2 годин!",
        "warning":  "Реагуй сьогодні",
        "info":     "Інформаційно",
    }

    text = f"""{icon} <b>ALFAMARKER — {market}</b>
{urgency.get(level, '')}
━━━━━━━━━━━━━━━━━━━━

📉 <b>ПРОБЛЕМА:</b>
{problem}

🔍 <b>ДІАГНОЗ:</b>
{diagnosis}

✅ <b>ЩО ЗРОБИТИ ЗАРАЗ:</b>
{action}

⏱ <b>ОЧІКУВАНИЙ РЕЗУЛЬТАТ:</b>
{expected_result}"""

    if risk:
        text += f"\n\n💰 <b>РИЗИК:</b>\n{risk}"

    text += f"\n\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"

    send_message(text)


def send_weekly_summary(market: str, summary: dict):
    """Надіслати тижневий звіт в Telegram."""
    acos = summary.get("overall_acos", 0)
    tacos = summary.get("tacos", 0) * 100
    spend = summary.get("total_spend", 0)
    sales = summary.get("total_sales", 0)
    profit = summary.get("net_profit", 0)
    roas = summary.get("overall_roas", 0)

    # Визначаємо статус
    if acos < 20:
        acos_status = "✅"
    elif acos < 30:
        acos_status = "🟡"
    else:
        acos_status = "🔴"

    if tacos < 10:
        tacos_status = "✅"
    elif tacos < 12:
        tacos_status = "🟡"
    else:
        tacos_status = "🔴"

    text = f"""📊 <b>ТИЖНЕВИЙ ЗВІТ — {market}</b>
{summary.get('week_label', '')}
━━━━━━━━━━━━━━━━━━━━

💰 Spend: <b>${spend:.2f}</b>
📈 Sales: <b>${sales:.2f}</b>
💵 Net Profit: <b>${profit:.2f}</b>
📦 Units: <b>{summary.get('total_orders', 0)}</b>

{acos_status} ACoS: <b>{acos:.1f}%</b>
{tacos_status} TACoS: <b>{tacos:.1f}%</b>
⚡ ROAS: <b>{roas:.2f}</b>

🏆 Найкраща кампанія: {summary.get('top_campaign', '—')}
⚠️ Найгірша кампанія: {summary.get('worst_campaign', '—')}

📋 Детальний аналіз → Google Sheets"""

    send_message(text)


def send_daily_ok(market: str):
    """Надіслати повідомлення що все добре."""
    text = f"""🟢 <b>ЩОДЕННИЙ МОНІТОРИНГ — {market}</b>
{datetime.now().strftime('%d.%m.%Y')}

Все в нормі. Аномалій не виявлено.
├── Impressions: ✅ норма
├── ACoS: ✅ в межах цілі
├── Запаси: ✅ достатньо
└── Бюджети: ✅ не вичерпані"""

    send_message(text)
