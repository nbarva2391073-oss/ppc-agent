# ============================================================
# KEYWORD INTELLIGENCE — глибокий аналіз ключових слів
# ============================================================

from config import MARGIN


def analyze_keywords(search_term_data: list[dict],
                     targeting_data: list[dict],
                     history: dict,
                     market: str) -> list[dict]:
    """
    Повний аналіз ключових слів:
    - Поточна ефективність
    - Lifetime value
    - Match type стратегія
    - Канібалізація
    - Негативні кандидати
    - Рекомендації
    """
    margin = MARGIN.get(market, 0.25)
    breakeven = margin * 100

    # Збираємо поточні дані по словах
    kw_data = {}
    for r in search_term_data:
        term = r.get("searchTerm") or r.get("keyword", "")
        if not term:
            continue
        if term not in kw_data:
            kw_data[term] = {
                "keyword": term,
                "match_type": r.get("matchType", ""),
                "campaign": r.get("campaignName", ""),
                "impressions": 0, "clicks": 0,
                "spend": 0, "sales": 0, "orders": 0,
                "campaigns_list": [],
            }
        kw = kw_data[term]
        kw["impressions"] += int(r.get("impressions", 0))
        kw["clicks"]      += int(r.get("clicks", 0))
        kw["spend"]       += float(r.get("spend", 0))
        kw["sales"]       += float(r.get("sales7d", 0))
        kw["orders"]      += int(r.get("purchases7d", 0))
        camp = r.get("campaignName", "")
        if camp and camp not in kw["campaigns_list"]:
            kw["campaigns_list"].append(camp)

    # Додаємо дані з targeting report
    for r in targeting_data:
        term = r.get("targetingText", "")
        if not term or term in ("auto", "close-match", "loose-match"):
            continue
        if term not in kw_data:
            kw_data[term] = {
                "keyword": term,
                "match_type": r.get("matchType", ""),
                "campaign": r.get("campaignName", ""),
                "impressions": 0, "clicks": 0,
                "spend": 0, "sales": 0, "orders": 0,
                "campaigns_list": [r.get("campaignName", "")],
            }

    # Розраховуємо lifetime value з историї
    lifetime = _get_lifetime_values(history)

    # Знаходимо канібалізацію
    cannibalization = _find_cannibalization(kw_data)

    # Аналізуємо кожне слово
    results = []
    for term, kw in kw_data.items():
        spend  = kw["spend"]
        sales  = kw["sales"]
        orders = kw["orders"]
        clicks = kw["clicks"]
        impressions = kw["impressions"]

        acos = spend / sales * 100 if sales > 0 else 999
        roas = sales / spend if spend > 0 else 0
        ctr  = clicks / impressions * 100 if impressions > 0 else 0
        cvr  = orders / clicks * 100 if clicks > 0 else 0

        lifetime_sales  = lifetime.get(term, {}).get("sales", sales)
        lifetime_spend  = lifetime.get(term, {}).get("spend", spend)
        weeks_active    = lifetime.get(term, {}).get("weeks", 1)
        lifetime_acos   = (lifetime_spend / lifetime_sales * 100
                           if lifetime_sales > 0 else 999)

        # Визначаємо статус
        status, recommendation, action = _classify_keyword(
            term, acos, lifetime_acos, breakeven,
            clicks, orders, impressions, ctr, cvr,
            kw["match_type"], kw["campaigns_list"],
            cannibalization,
        )

        results.append({
            **kw,
            "acos":           round(acos if acos < 999 else 0, 1),
            "roas":           round(roas, 2),
            "ctr":            round(ctr, 2),
            "cvr":            round(cvr, 2),
            "lifetime_sales": round(lifetime_sales, 2),
            "lifetime_acos":  round(lifetime_acos if
                                     lifetime_acos < 999 else 0, 1),
            "weeks_active":   weeks_active,
            "status":         status,
            "recommendation": recommendation,
            "action":         action,
            "is_cannibal":    term in cannibalization,
            "listing_indexed": "",  # Заповнить Brand Analytics
        })

    # Сортуємо: спочатку проблемні
    results.sort(key=lambda x: (
        0 if "🔴" in x["status"] else
        1 if "🟡" in x["status"] else 2
    ))

    return results


def _classify_keyword(term, acos, lifetime_acos, breakeven,
                       clicks, orders, impressions, ctr, cvr,
                       match_type, campaigns_list, cannibalization):
    """Класифікувати ключове слово і дати рекомендацію."""

    # 🔴 Негативне — зливає бюджет
    if clicks >= 10 and orders == 0:
        return (
            "🔴 Негативне",
            f"Витрачено бюджет ({clicks} кліків, 0 продажів)",
            f"ДОДАТИ як негативне слово. "
            f"Зекономить бюджет на цьому слові.",
        )

    # 🔴 Хронічно збитково (більше 4 тижнів)
    if lifetime_acos > breakeven * 1.5 and clicks >= 20:
        return (
            "🔴 Збитково (хронічно)",
            f"Lifetime ACoS {lifetime_acos:.1f}% >> "
            f"Break-even {breakeven:.1f}%",
            f"Знизити bid на 30% або додати як негативне.",
        )

    # 🟡 Збитково цього тижня
    if acos > breakeven * 1.2:
        return (
            "🟡 Збитково (цього тижня)",
            f"ACoS {acos:.1f}% > Break-even {breakeven:.1f}%",
            f"Знизити bid на 15-20%. Перевірити через 2 тижні.",
        )

    # 🟡 Канібалізація
    if term in cannibalization:
        camps = ", ".join(cannibalization[term])
        return (
            "🟡 Канібалізація",
            f"Слово присутнє в {len(cannibalization[term])} кампаніях: "
            f"{camps}",
            f"Залишити тільки в одній кампанії. "
            f"В інших додати як негативне.",
        )

    # 🟡 Низький CTR
    if impressions >= 100 and ctr < 0.3:
        return (
            "🟡 Низький CTR",
            f"CTR {ctr:.2f}% < 0.3% при {impressions} показах",
            f"Перевірити релевантність слова. "
            f"Можливо потрібно оновити фото або заголовок лістингу.",
        )

    # ✅ Топ перформер — просувати в Exact
    if acos < breakeven * 0.7 and orders >= 3:
        if match_type in ("broad", "phrase", "auto"):
            return (
                "✅ Топ переможець",
                f"ACoS {acos:.1f}% << Break-even {breakeven:.1f}%",
                f"ПЕРЕНЕСТИ в Exact Match кампанію з bid +20%. "
                f"Додати як негативне в поточній кампанії.",
            )
        else:
            return (
                "✅ Топ (Exact)",
                f"ACoS {acos:.1f}% — відмінно",
                f"Розглянути підвищення bid на 10-15% "
                f"для збільшення обсягу.",
            )

    # 🟢 Норма
    if acos <= breakeven:
        return (
            "🟢 Норма",
            f"ACoS {acos:.1f}% в межах цілі",
            "Підтримувати поточний bid. Моніторити щотижня.",
        )

    # ⚪ Мало даних
    return (
        "⚪ Мало даних",
        f"Лише {clicks} кліків — недостатньо для висновків",
        "Почекати 2-3 тижні для накопичення даних.",
    )


def _find_cannibalization(kw_data: dict) -> dict:
    """Знайти ключові слова що присутні в кількох кампаніях."""
    result = {}
    for term, data in kw_data.items():
        if len(data["campaigns_list"]) > 1:
            result[term] = data["campaigns_list"]
    return result


def _get_lifetime_values(history: dict) -> dict:
    """Розрахувати lifetime value ключових слів з историї."""
    raw_history = history.get("raw_data", [])
    if len(raw_history) <= 1:
        return {}

    lifetime = {}
    for row in raw_history[1:]:
        if len(row) < 12:
            continue
        term = row[4] if len(row) > 4 else ""  # Search Term колонка
        if not term:
            term = row[5] if len(row) > 5 else ""  # Keyword колонка
        if not term:
            continue
        try:
            spend = float(row[10]) if row[10] else 0
            sales = float(row[11]) if row[11] else 0
        except (ValueError, IndexError):
            continue

        if term not in lifetime:
            lifetime[term] = {"spend": 0, "sales": 0, "weeks": 0}
        lifetime[term]["spend"] += spend
        lifetime[term]["sales"] += sales
        lifetime[term]["weeks"] += 1

    return lifetime


def find_negative_candidates(search_term_data: list[dict],
                              breakeven: float) -> list[dict]:
    """Знайти кандидатів для негативних ключових слів."""
    candidates = []
    term_stats = {}

    for r in search_term_data:
        term  = r.get("searchTerm", "")
        if not term:
            continue
        if term not in term_stats:
            term_stats[term] = {"clicks": 0, "orders": 0,
                                  "spend": 0, "sales": 0,
                                  "campaign": r.get("campaignName", "")}
        term_stats[term]["clicks"] += int(r.get("clicks", 0))
        term_stats[term]["orders"] += int(r.get("purchases7d", 0))
        term_stats[term]["spend"]  += float(r.get("spend", 0))
        term_stats[term]["sales"]  += float(r.get("sales7d", 0))

    for term, s in term_stats.items():
        acos = s["spend"] / s["sales"] * 100 if s["sales"] > 0 else 999
        if s["clicks"] >= 5 and s["orders"] == 0:
            candidates.append({
                "term": term,
                "reason": f"{s['clicks']} кліків, 0 продажів",
                "waste": round(s["spend"], 2),
                "campaign": s["campaign"],
            })
        elif acos > breakeven * 2 and s["clicks"] >= 10:
            candidates.append({
                "term": term,
                "reason": f"ACoS {acos:.1f}% >> Break-even {breakeven:.1f}%",
                "waste": round(s["spend"] - s["sales"] * breakeven / 100, 2),
                "campaign": s["campaign"],
            })

    candidates.sort(key=lambda x: x["waste"], reverse=True)
    return candidates[:20]
