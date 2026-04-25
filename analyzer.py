# ============================================================
# CLAUDE AI ANALYZER — експертний аналіз з повною историєю
# ============================================================

import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MARGIN, ALERTS


def deep_analyze(
    market: str,
    week_label: str,
    campaign_data: list[dict],
    search_term_data: list[dict],
    placement_data: list[dict],
    campaigns: list[dict],
    metrics: dict,
    keyword_analysis: list[dict],
    placement_issues: list[dict],
    history: dict,
) -> str:
    """
    Експертний AI аналіз з урахуванням ВСІЄЇ историї.
    Діагностує проблеми самостійно без гіпотез користувача.
    """
    ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    margin = MARGIN.get(market, 0.25)
    breakeven = margin * 100

    prompt = f"""Ти — провідний експерт з Amazon PPC з 10+ роками досвіду.
Твоя задача — зробити ГЛИБОКИЙ аналіз рекламних кампаній 
бренду ALFAMARKER ({market}) за тиждень {week_label}.

ВАЖЛИВИЙ КОНТЕКСТ:
- Ніша: парфуми з феромонами (конкурентна ніша)
- Break-even ACoS: {breakeven:.1f}%
- Ціль: наздогнати конкурентів → стати №1 в ніші
- Стратегія бідингу: ТІЛЬКИ Down Only (ніколи Up&Down)
- Структура: окремі кампанії для ToS, RoS і PP
- Маржа зараз під тиском (падала з 28.5% до 18.9% за 3 місяці)

{'='*60}
ПОТОЧНІ МЕТРИКИ ({week_label})
{'='*60}
{_format_metrics(metrics, breakeven)}

{'='*60}
КАМПАНІЇ — ДЕТАЛЬНО
{'='*60}
{_format_campaigns(campaign_data, campaigns, breakeven)}

{'='*60}
PLACEMENT ПРОБЛЕМИ
{'='*60}
{_format_placement_issues(placement_issues)}

{'='*60}
КЛЮЧОВІ СЛОВА — ТОП ПРОБЛЕМНІ
{'='*60}
{_format_keywords(keyword_analysis[:30])}

{'='*60}
ВСЯ ИСТОРИЯ ДАНИХ
{'='*60}
{_format_history(history, market)}

{'='*60}
ТВОЄ ЗАВДАННЯ
{'='*60}

Зроби ПОВНИЙ експертний аналіз за такою структурою:

## 🚨 КРИТИЧНІ ПРОБЛЕМИ (потребують дій сьогодні)
Перерахуй проблеми які виявив САМОСТІЙНО аналізуючи дані.
По кожній: що відбувається → чому → що зробити зараз.

## 📊 СТАТУС КОНКУРЕНТНОЇ БОРОТЬБИ
- Чи наближаємось до конкурентів?
- Тренд частки ринку (якщо є дані)
- Що заважає наздогнати

## 📈 АНАЛІЗ КОЖНОЇ КАМПАНІЇ
По кожній кампанії:
- Поточний стан (ACoS vs Break-even)
- Тренд за последні тижні (з историї)
- Проблеми з placement (ToS vs PP)
- Ефективність bid adjustments
- Конкретна рекомендація

## 🔑 КЛЮЧОВІ СЛОВА
### Негайно прибрати (негативні):
### Перенести в Exact Match:
### Підвищити bid:
### Знизити bid:
### Нові перспективні слова для тестування:

## 📦 PLACEMENT СТРАТЕГІЯ
- Де є витік бюджету на PP в ToS кампаніях?
- Рекомендований базовий bid для кожного типу placement

## 📱 ЛІСТИНГ РЕКОМЕНДАЦІЇ
- Які ключові слова додати в заголовок/bullets
- Що покращити для підвищення CVR

## 🎯 ТОП-3 ДІЇ ЦЬОГО ТИЖНЯ
Пріоритизовані дії з найбільшим впливом:

🎯 ДІЯ 1: [конкретна дія]
ЧОМУ: [пояснення на основі даних]
ЯК ЗРОБИТИ: [покрокова інструкція]
ОЧІКУВАНИЙ РЕЗУЛЬТАТ: [прогноз з цифрами]
РИЗИК: [що може піти не так]
ТЕРМІН: [коли побачиш результат]

🎯 ДІЯ 2: ...
🎯 ДІЯ 3: ...

## 📅 ПРОГНОЗ НА НАСТУПНИЙ ТИЖДЕНЬ
На основі трендів і сезонності.

## ⚠️ ПОПЕРЕДЖЕННЯ
Будь-які ознаки що можуть призвести до збитків
(як це було в грудні-січні коли маржа впала до 1-2.6%).

Відповідай конкретно, з цифрами. 
Пояснюй ЧОМУ на основі реальних даних і историї.
НЕ давай загальних порад — тільки конкретику."""

    response = ai_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _format_metrics(metrics: dict, breakeven: float) -> str:
    spend  = metrics.get("total_spend", 0)
    sales  = metrics.get("total_sales", 0)
    acos   = metrics.get("overall_acos", 0)
    tacos  = metrics.get("tacos", 0) * 100
    profit = metrics.get("net_profit", 0)
    roas   = metrics.get("overall_roas", 0)
    budget_issues = metrics.get("budget_issues", [])

    status = "✅" if acos <= breakeven else "🔴"
    tacos_status = "✅" if tacos <= 12 else "🔴"

    lines = [
        f"Spend: ${spend:.2f} | Sales: ${sales:.2f}",
        f"Net Profit: ${profit:.2f}",
        f"{status} ACoS: {acos:.1f}% (Break-even: {breakeven:.1f}%)",
        f"{tacos_status} TACoS: {tacos:.1f}% (ціль: <12%)",
        f"ROAS: {roas:.2f}",
    ]
    if budget_issues:
        lines.append(f"⚠️ Бюджет вичерпано: {', '.join(budget_issues)}")
    return "\n".join(lines)


def _format_campaigns(campaign_data: list[dict],
                       campaigns: list[dict],
                       breakeven: float) -> str:
    by_camp = {}
    for r in campaign_data:
        name = r.get("campaignName", "")
        if name not in by_camp:
            by_camp[name] = {"spend": 0, "sales": 0,
                               "impressions": 0, "clicks": 0, "orders": 0}
        by_camp[name]["spend"]       += float(r.get("spend", 0))
        by_camp[name]["sales"]       += float(r.get("sales7d", 0))
        by_camp[name]["impressions"] += int(r.get("impressions", 0))
        by_camp[name]["clicks"]      += int(r.get("clicks", 0))
        by_camp[name]["orders"]      += int(r.get("purchases7d", 0))

    # Bid adjustments
    bid_info = {}
    for c in campaigns:
        adj = {a["placement"]: a["percentage"]
               for a in c.get("bidding", {}).get("adjustments", [])}
        bid_info[c.get("name", "")] = {
            "strategy": c.get("bidding", {}).get("strategy", ""),
            "tos":      adj.get("PLACEMENT_TOP", 0),
            "pp":       adj.get("PLACEMENT_PRODUCT_PAGE", 0),
            "budget":   c.get("budget", {}).get("budget", 0),
        }

    lines = []
    for name, v in by_camp.items():
        spend = v["spend"]
        sales = v["sales"]
        acos  = spend / sales * 100 if sales > 0 else 999
        roas  = sales / spend if spend > 0 else 0
        bi    = bid_info.get(name, {})
        status = "✅" if acos <= breakeven else "🔴"
        lines.append(
            f"{status} {name}\n"
            f"  Spend=${spend:.2f} Sales=${sales:.2f} "
            f"ACoS={acos:.1f}% ROAS={roas:.2f}\n"
            f"  Impressions={v['impressions']} "
            f"Clicks={v['clicks']} Orders={v['orders']}\n"
            f"  Bid strategy={bi.get('strategy','')} "
            f"ToS adj={bi.get('tos',0)}% "
            f"PP adj={bi.get('pp',0)}% "
            f"Budget=${bi.get('budget',0)}"
        )
    return "\n".join(lines) if lines else "Немає даних"


def _format_placement_issues(issues: list[dict]) -> str:
    if not issues:
        return "Критичних placement проблем не виявлено ✅"
    lines = []
    for i in issues:
        lines.append(
            f"⚠️ {i['campaign']}\n"
            f"  ToS показів: {i['tos_pct']}% (має бути >50%)\n"
            f"  PP показів: {i['pp_pct']}% (має бути <20%)\n"
            f"  ToS adjustment: {i['tos_adj']}%\n"
            f"  PP витрати: ${i['pp_spend']:.2f} "
            f"ACoS на PP: {i['pp_acos']:.1f}%"
        )
    return "\n".join(lines)


def _format_keywords(keywords: list[dict]) -> str:
    lines = []
    for kw in keywords:
        lines.append(
            f"{kw.get('status', '')} [{kw.get('match_type', '')}] "
            f"{kw.get('keyword', '')}\n"
            f"  {kw.get('recommendation', '')} → {kw.get('action', '')}"
        )
    return "\n".join(lines) if lines else "Немає даних"


def _format_history(history: dict, market: str) -> str:
    lines = []

    # Weekly summary history
    weekly = history.get("weekly_summary", [])
    market_rows = [r for r in weekly[1:] if len(r) > 1
                   and r[1] == market]
    if market_rows:
        lines.append("📅 ТИЖНЕВА ИСТОРИЯ:")
        for r in market_rows[-12:]:
            lines.append(
                f"  {r[0]}: Spend=${r[2]} Sales=${r[3]} "
                f"Profit=${r[4]} ACoS={r[6]}% TACoS={r[8]}%"
            )

    # Bid history
    bids = history.get("bid_history", [])
    if len(bids) > 1:
        lines.append("\n💰 ОСТАННЯ ИСТОРИЯ БІДІВ:")
        for r in bids[1:][-15:]:
            if len(r) >= 9:
                lines.append(
                    f"  {r[0]} | {r[1]}: ToS={r[4]}% PP={r[5]}% "
                    f"| KW: {r[8]} bid={r[9]}"
                )

    # Previous recommendations
    recs = history.get("ai_recommendations", [])
    market_recs = [r for r in recs[1:] if len(r) > 2
                   and r[2] == market]
    if market_recs:
        lines.append("\n🤖 ПОПЕРЕДНІ РЕКОМЕНДАЦІЇ:")
        for r in market_recs[-3:]:
            preview = r[3][:800] + "..." if len(r[3]) > 800 else r[3]
            lines.append(f"\n  Тиждень {r[0]}:\n  {preview}")

    # Placement history
    placements = history.get("placement_analysis", [])
    if len(placements) > 1:
        lines.append("\n📍 PLACEMENT ИСТОРИЯ:")
        for r in placements[1:][-20:]:
            if len(r) >= 9:
                lines.append(
                    f"  {r[0]} | {r[1]} | {r[2]}: "
                    f"Imp={r[3]} Spend=${r[6]} ACoS={r[8]}%"
                )

    return "\n".join(lines) if lines else "Перший тиждень — история накопичується"
