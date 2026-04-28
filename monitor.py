# ============================================================
# ЩОДЕННИЙ МОНІТОРИНГ — Рівень 2
# ============================================================

import json
import anthropic
from datetime import datetime, timedelta
from config import (ANTHROPIC_API_KEY, CLAUDE_MODEL,
                    MARGIN, ALERTS,
                    ADS_PROFILE_ID_USA, ADS_PROFILE_ID_CA)
from amazon_ads import (get_access_token, get_campaigns,
                         get_campaign_report)
from sheets import get_full_history, log_alert
from telegram_bot import send_alert, send_daily_ok


def _spend_val(r: dict) -> float:
    """ВИПРАВЛЕНО: reporting API повертає 'cost', не 'spend'."""
    return float(r.get("cost") or r.get("spend") or 0)


def run_daily_monitor():
    print("=" * 60)
    print(f"📱 ЩОДЕННИЙ МОНІТОРИНГ: {datetime.now()}")
    print("=" * 60)

    token = get_access_token()
    today = datetime.now()
    start = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    end   = today.strftime("%Y-%m-%d")

    any_alerts = False

    for market, profile_id in [
        ("USA", ADS_PROFILE_ID_USA),
        ("CA",  ADS_PROFILE_ID_CA),
    ]:
        if not profile_id:
            continue

        print(f"\n🔍 Перевіряємо {market}...")
        alerts, today_data = check_market(
            token, profile_id, market, start, end)

        if alerts:
            any_alerts = True
            for alert in alerts:
                send_alert(**alert, market=market)
                log_alert(
                    market=market,
                    level=alert["level"],
                    problem=alert["problem"],
                    diagnosis=alert["diagnosis"],
                    action=alert["action"],
                )
        else:
            margin = MARGIN.get(market, 0.25)
            send_daily_ok(market, today_data, margin * 100)

    if not any_alerts:
        print("✅ Все в нормі")


def check_market(token, profile_id, market, start, end):
    """Повертає (alerts, today_data)."""
    alerts  = []
    margin  = MARGIN.get(market, 0.25)
    breakeven = margin * 100

    try:
        today_data = get_campaign_report(token, profile_id, start, end)
    except Exception as e:
        print(f"  ⚠️ Не вдалось завантажити дані: {e}")
        return [], []

    history   = get_full_history(market)
    prev_week = _get_previous_week_data(history, market)

    try:
        campaigns = get_campaigns(token, profile_id)
    except Exception as e:
        print(f"  ⚠️ Кампанії не завантажились: {e}")
        campaigns = []

    impr_alerts   = check_impressions(today_data, prev_week, market, campaigns)
    acos_alerts   = check_acos(today_data, breakeven, market)
    budget_alerts = check_budget_pacing(today_data, campaigns)
    tacos_alerts  = check_tacos_trend(history, market)

    alerts.extend(impr_alerts)
    alerts.extend(acos_alerts)
    alerts.extend(budget_alerts)
    alerts.extend(tacos_alerts)

    return alerts, today_data


def check_impressions(today_data, prev_week, market, campaigns):
    alerts = []
    today_by_camp = {}
    for r in today_data:
        name = r.get("campaignName", "")
        if name not in today_by_camp:
            today_by_camp[name] = 0
        today_by_camp[name] += int(r.get("impressions", 0))

    for camp_name, today_impr in today_by_camp.items():
        prev_impr = prev_week.get(camp_name, {}).get("impressions", 0)
        if prev_impr == 0:
            continue
        drop = (prev_impr - today_impr) / prev_impr
        if drop <= 0:
            continue

        camp_data = next(
            (c for c in campaigns if c.get("name") == camp_name), {})
        bidding = camp_data.get("bidding", {})
        adj     = {a["placement"]: a["percentage"]
                   for a in bidding.get("adjustments", [])}
        tos_adj = adj.get("PLACEMENT_TOP", 0)

        diagnosis, action, expected = _diagnose_impression_drop(
            camp_name, drop, today_impr, prev_impr, tos_adj)

        if drop >= ALERTS["impressions_drop_critical"]:
            alerts.append({
                "level": "critical",
                "problem": (f"Impressions впали на {drop*100:.0f}%!\n"
                            f"Кампанія: {camp_name}\n"
                            f"Вчора: {prev_impr} → Сьогодні: {today_impr}"),
                "diagnosis":       diagnosis,
                "action":          action,
                "expected_result": expected,
                "risk":            "Тимчасове підвищення ACoS можливе",
            })
        elif drop >= ALERTS["impressions_drop_warning"]:
            alerts.append({
                "level": "warning",
                "problem": (f"Impressions впали на {drop*100:.0f}%\n"
                            f"Кампанія: {camp_name}"),
                "diagnosis":       diagnosis,
                "action":          action,
                "expected_result": expected,
            })
    return alerts


def _diagnose_impression_drop(camp_name, drop, today, prev, tos_adj):
    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt    = (
        f'Ти Amazon PPC експерт. Кампанія "{camp_name}" втратила '
        f'{drop*100:.0f}% impressions (було {prev}, стало {today}). '
        f'ToS adj: {tos_adj}%. Down Only. '
        f'Відповідь ТІЛЬКИ JSON без markdown: '
        f'{{"diagnosis":"...","action":"...","expected":"..."}}'
    )
    try:
        r    = ai_client.messages.create(
            model=CLAUDE_MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}])
        data = json.loads(r.content[0].text)
        return data["diagnosis"], data["action"], data["expected"]
    except Exception:
        if tos_adj >= 100 and today < 50:
            return (
                "Базовий bid занадто низький для ToS",
                "1. Підвищ базовий bid на 30-50%\n2. Або знизь ToS adj",
                "Impressions відновляться за 24-48 год",
            )
        return (
            "Можливе підвищення ставок конкурентів",
            "1. Перевір конкурентів\n2. Підвищ bid на 15-20%",
            "Результат через 1-2 дні",
        )


def check_acos(today_data, breakeven, market):
    alerts   = []
    by_camp  = {}
    for r in today_data:
        name = r.get("campaignName", "")
        if name not in by_camp:
            by_camp[name] = {"spend": 0, "sales": 0}
        by_camp[name]["spend"] += _spend_val(r)
        by_camp[name]["sales"] += float(r.get("sales7d", 0))

    for camp_name, vals in by_camp.items():
        spend = vals["spend"]
        sales = vals["sales"]
        if spend < 1:
            continue
        acos = spend / sales * 100 if sales > 0 else 999

        if acos > breakeven * ALERTS["acos_critical_multiplier"]:
            loss = spend - (sales * breakeven / 100 if sales > 0 else 0)
            alerts.append({
                "level": "critical",
                "problem": (f"🔴 ACoS критично високий!\n"
                            f"Кампанія: {camp_name}\n"
                            f"ACoS: {acos:.1f}% | Break-even: {breakeven:.1f}%\n"
                            f"Витрачено: ${spend:.2f} | Продажів: ${sales:.2f}\n"
                            f"Збиток: ~${loss:.2f}"),
                "diagnosis":       f"ACoS перевищує break-even на {acos-breakeven:.1f}%",
                "action":          ("1. Знайди ключові слова з 0 продажів → негативні\n"
                                    "2. Знизь bid на 20%\n"
                                    "3. Перевір Search Term Report"),
                "expected_result": f"ACoS повернеться до {breakeven:.0f}% за 1-2 тижні",
                "risk":            "Можливе зниження обсягу продажів",
            })
        elif acos > breakeven * ALERTS["acos_warning_multiplier"]:
            alerts.append({
                "level": "warning",
                "problem": (f"🟡 ACoS вище норми\n"
                            f"Кампанія: {camp_name}\n"
                            f"ACoS: {acos:.1f}% | Break-even: {breakeven:.1f}%\n"
                            f"Витрачено: ${spend:.2f} | Продажів: ${sales:.2f}"),
                "diagnosis":       f"ACoS перевищує break-even на {acos-breakeven:.1f}%",
                "action":          "Перевір ключові слова з низькою конверсією",
                "expected_result": "Моніторити 3 дні",
            })
    return alerts


def check_budget_pacing(today_data, campaigns):
    alerts        = []
    current_hour  = datetime.now().hour
    budget_by_camp = {
        c.get("name"): float(c.get("budget", {}).get("budget", 0))
        for c in campaigns
    }

    by_camp = {}
    for r in today_data:
        name = r.get("campaignName", "")
        if name not in by_camp:
            by_camp[name] = 0
        by_camp[name] += _spend_val(r)

    for camp_name, spend in by_camp.items():
        budget = budget_by_camp.get(camp_name, 0)
        if budget <= 0:
            continue
        pct_used = spend / budget * 100
        if current_hour < 14 and pct_used > 80:
            alerts.append({
                "level": "warning",
                "problem": (f"Бюджет майже вичерпано о {current_hour}:00!\n"
                            f"{camp_name}: ${spend:.2f} з ${budget:.2f} "
                            f"({pct_used:.0f}%)"),
                "diagnosis":       "Бюджет закінчиться до обіду. Втратиш вечірній трафік.",
                "action":          "1. Підвищ бюджет на 30-50%\n   АБО\n2. Знизь ставки",
                "expected_result": "Рівномірний розподіл витрат",
            })
    return alerts


def check_tacos_trend(history, market):
    weekly      = history.get("weekly_summary", [])
    market_rows = [r for r in weekly[1:]
                   if len(r) > 8 and r[1] == market]
    if len(market_rows) < 3:
        return []
    try:
        tacos_values = [float(r[8]) for r in market_rows[-3:] if r[8]]
    except (ValueError, IndexError):
        return []
    if len(tacos_values) < 3:
        return []

    if (tacos_values[2] > tacos_values[1] > tacos_values[0]
            and tacos_values[2] > ALERTS["tacos_warning"] * 100):
        trend           = tacos_values[2] - tacos_values[0]
        weeks_to_crisis = int(
            (15 - tacos_values[2]) / (trend / 2)) if trend > 0 else 99
        return [{
            "level": ("warning" if tacos_values[2] < ALERTS["tacos_critical"] * 100
                      else "critical"),
            "problem": (f"TACoS росте 3 тижні!\n"
                        f"{tacos_values[0]:.1f}% → {tacos_values[1]:.1f}%"
                        f" → {tacos_values[2]:.1f}%"),
            "diagnosis":       (f"При тренді +{trend/2:.1f}%/тиждень TACoS "
                                f"досягне 15% через ~{weeks_to_crisis} тижнів"),
            "action":          ("1. Аудит кампаній з ACoS > break-even\n"
                                "2. Зупини збиткові кампанії\n"
                                "3. Додай негативні ключові слова"),
            "expected_result": "TACoS стабілізується за 2-3 тижні",
            "risk":            "Без дій маржа може впасти до критичного рівня",
        }]
    return []


def _get_previous_week_data(history, market):
    campaign_hist = history.get("campaign_analysis", [])
    market_rows   = [r for r in campaign_hist[1:] if len(r) > 1]
    if not market_rows:
        return {}
    last_week_label = market_rows[-1][0]
    last_week       = {}
    for r in market_rows:
        if r[0] == last_week_label and len(r) > 8:
            camp_name = r[1]
            try:
                impressions = int(r[8]) if r[8] else 0
            except ValueError:
                impressions = 0
            last_week[camp_name] = {"impressions": impressions}
    return last_week
