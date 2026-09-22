# ============================================================
# TELEGRAM — сповіщення з діагнозом і кроками
# ============================================================

import requests
from datetime import datetime
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS


def send_message(text: str, parse_mode: str = "HTML"):
    if not TELEGRAM_BOT_TOKEN:
        print(f"[TELEGRAM] {text}")
        return
    for chat_id in TELEGRAM_CHAT_IDS:
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            r = requests.post(url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }, timeout=10)
            r.raise_for_status()
        except Exception as e:
            print(f"❌ Telegram помилка для {chat_id}: {e}")


def send_alert(level, market, problem, diagnosis,
               action, expected_result, risk=""):
    icons = {"critical": "🔴", "warning": "🟡", "info": "🟢"}
    icon = icons.get(level, "⚪")
    urgency = {
        "critical": "Реагуй протягом 2 годин!",
        "warning":  "Реагуй сьогодні",
        "info":     "Інформаційно",
    }
    text = (f"{icon} <b>ALFAMARKER — {market}</b>\n"
            f"{urgency.get(level, '')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📉 <b>ПРОБЛЕМА:</b>\n{problem}\n\n"
            f"🔍 <b>ДІАГНОЗ:</b>\n{diagnosis}\n\n"
            f"✅ <b>ЩО ЗРОБИТИ ЗАРАЗ:</b>\n{action}\n\n"
            f"⏱ <b>ОЧІКУВАНИЙ РЕЗУЛЬТАТ:</b>\n{expected_result}")
    if risk:
        text += f"\n\n💰 <b>РИЗИК:</b>\n{risk}"
    text += f"\n\n🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    send_message(text)


def send_weekly_summary(market: str, summary: dict):
    acos   = summary.get("overall_acos", 0)
    tacos  = summary.get("tacos", 0) * 100
    spend  = summary.get("total_spend", 0)
    sales  = summary.get("total_sales", 0)
    profit = summary.get("net_profit", 0)
    roas   = summary.get("overall_roas", 0)

    acos_status  = "✅" if acos < 20 else ("🟡" if acos < 30 else "🔴")
    tacos_status = "✅" if tacos < 10 else ("🟡" if tacos < 12 else "🔴")

    text = (f"📊 <b>ТИЖНЕВИЙ ЗВІТ — {market}</b>\n"
            f"{summary.get('week_label', '')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Spend: <b>${spend:.2f}</b>\n"
            f"📈 Sales: <b>${sales:.2f}</b>\n"
            f"💵 Net Profit: <b>${profit:.2f}</b>\n"
            f"📦 Units: <b>{summary.get('total_orders', 0)}</b>\n\n"
            f"{acos_status} ACoS: <b>{acos:.1f}%</b>\n"
            f"{tacos_status} TACoS: <b>{tacos:.1f}%</b>\n"
            f"⚡ ROAS: <b>{roas:.2f}</b>\n\n"
            f"🏆 Найкраща: {summary.get('top_campaign', '—')}\n"
            f"⚠️ Найгірша: {summary.get('worst_campaign', '—')}\n\n"
            f"📋 Детальний аналіз → Google Sheets")
    send_message(text)


def send_claude_daily_review(market: str, date: str, text: str):
    """
    Окреме повідомлення — незалежний щоденний тактичний огляд Claude.
    Навмисно відділене від send_daily_ok (сирий моніторинг без AI) і
    від тижневого send_weekly_summary, щоб було видно, що це саме
    Claude-думка, а не ChatGPT чи звичайний збір даних.
    """
    MAX_LEN = 3500
    body = text if len(text) <= MAX_LEN else (
        text[:MAX_LEN] + "\n\n…(повний текст → Google Sheets, "
        "вкладка Claude Daily Review)")
    header = (f"🧠 <b>CLAUDE — незалежний огляд, {market}</b> {date}\n"
              f"(окремо від інших звітів)\n"
              f"━━━━━━━━━━━━━━━━━━━━\n\n")
    send_message(header + body) 


def send_claude_weekly_x2_review(market: str, date: str, text: str):
    """
    Окреме повідомлення — незалежний щотижневий стратегічний X2-огляд
    Claude. Відділене і від send_claude_daily_review (щоденна тактика
    ставок), і від send_weekly_summary (цифри тижневого ChatGPT-звіту),
    щоб було видно, що це саме окремий, самостійний X2-погляд раз на
    7 днів.
    """
    MAX_LEN = 3500
    body = text if len(text) <= MAX_LEN else (
        text[:MAX_LEN] + "\n\n…(повний текст → Google Sheets, "
        "вкладка Claude Weekly X2 Review)")
    header = (f"🧠🎯 <b>CLAUDE — WEEKLY X2 REVIEW, {market}</b> {date}\n"
              f"(окремо від ChatGPT і від щоденного тактичного огляду)\n"
              f"━━━━━━━━━━━━━━━━━━━━\n\n")
    send_message(header + body)


def send_daily_ok(market: str, campaign_data: list = None,
                  breakeven: float = 25):
    """
    БАГ ВИПРАВЛЕНО: тепер показує деталі по кожній кампанії
    замість загального 'все в нормі'.
    """
    date_str = datetime.now().strftime('%d.%m.%Y')

    if not campaign_data:
        text = (f"🟢 <b>МОНІТОРИНГ — {market}</b> {date_str}\n"
                f"Аномалій не виявлено. Даних поки немає.")
        send_message(text)
        return

    # Групуємо по кампаніях
    by_camp = {}
    for r in campaign_data:
        name = r.get("campaignName", "")
        if name not in by_camp:
            by_camp[name] = {"spend": 0, "sales": 0,
                             "orders": 0, "impressions": 0}
        by_camp[name]["spend"]       += float(r.get("spend", 0))
        by_camp[name]["sales"]       += float(r.get("sales7d", 0))
        by_camp[name]["orders"]      += int(r.get("purchases7d", 0))
        by_camp[name]["impressions"] += int(r.get("impressions", 0))

    total_spend = sum(v["spend"] for v in by_camp.values())
    total_sales = sum(v["sales"] for v in by_camp.values())
    total_acos  = (total_spend / total_sales * 100
                   if total_sales > 0 else 0)

    overall_status = "✅" if total_acos <= breakeven else "🔴"

    lines = [
        f"{overall_status} <b>МОНІТОРИНГ — {market}</b> {date_str}",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"💰 Витрачено: <b>${total_spend:.2f}</b>",
        f"📈 Продажів: <b>${total_sales:.2f}</b>",
        f"📊 Загальний ACoS: <b>{total_acos:.1f}%</b> "
        f"(break-even: {breakeven:.0f}%)",
        f"",
        f"<b>По кампаніях:</b>",
    ]

    for name, v in by_camp.items():
        spend  = v["spend"]
        sales  = v["sales"]
        orders = v["orders"]
        acos   = spend / sales * 100 if sales > 0 else 0
        roas   = sales / spend if spend > 0 else 0

        if sales == 0 and spend > 0:
            status = "🔴"
            note = "0 продажів!"
        elif acos > breakeven * 1.5:
            status = "🔴"
            note = f"ACoS {acos:.0f}% >> break-even"
        elif acos > breakeven:
            status = "🟡"
            note = f"ACoS {acos:.0f}% > break-even"
        else:
            status = "✅"
            note = f"ACoS {acos:.0f}%"

        # Скорочуємо назву кампанії
        short_name = name[:30] + "..." if len(name) > 30 else name

        lines.append(
            f"{status} {short_name}\n"
            f"   💵 ${spend:.2f} → 📈 ${sales:.2f} "
            f"({orders} зам.) | {note}"
        )

    send_message("\n".join(lines))
