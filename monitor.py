# ============================================================
# ЩОДЕННИЙ ЗБІР ДАНИХ — тільки збираємо і записуємо в Sheets
# Без Claude API. Без алертів. Без порівнянь.
# ============================================================

from datetime import datetime, timedelta
from config import MARGIN, ADS_PROFILE_ID_USA, ADS_PROFILE_ID_CA
from amazon_ads import (
    get_access_token, get_campaigns, get_keywords,
    submit_report, wait_and_download,
    calculate_metrics, analyze_placement_issues,
)
from sheets import (
    write_raw_data, write_campaign_analysis,
    write_bid_snapshot, write_placement_analysis,
    write_keyword_intelligence, write_weekly_summary,
)

# ── Колонки звітів ────────────────────────────────────────────
COLS_CAMPAIGN = [
    "campaignName", "campaignId",
    "impressions", "clicks",
    "cost", "sales7d", "purchases7d",
]
COLS_SEARCH_TERM = [
    "campaignName", "adGroupName", "keyword", "matchType",
    "searchTerm", "impressions", "clicks",
    "cost", "sales7d", "purchases7d", "costPerClick",
]
COLS_PLACEMENT = [
    "campaignName", "impressions", "clicks",
    "cost", "sales7d", "purchases7d",
]
COLS_TARGETING = [
    "campaignName", "adGroupName", "matchType",
    "impressions", "clicks",
    "cost", "sales7d", "purchases7d", "costPerClick",
]


def run_daily_monitor():
    print("=" * 60)
    print(f"📦 ЗБІР ДАНИХ: {datetime.now()}")
    print("=" * 60)

    today = datetime.now()
    date  = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    week  = today.strftime("%Y-W%W")

    all_metrics = {}

    for market, profile_id in [
        ("USA", ADS_PROFILE_ID_USA),
        ("CA",  ADS_PROFILE_ID_CA),
    ]:
        if not profile_id:
            print(f"⏭️  {market}: profile_id не задано, пропускаємо")
            continue

        print(f"\n📊 Збираємо {market}...")
        # Свіжий токен для кожного маркетплейсу
        token = get_access_token()
        metrics = collect_market(token, profile_id, market, date, week)
        all_metrics[market] = metrics

    # Weekly Summary
    try:
        write_weekly_summary(
            usa_metrics=all_metrics.get("USA", {}),
            ca_metrics=all_metrics.get("CA", {}),
            week=week,
        )
    except Exception as e:
        print(f"  ❌ Weekly Summary: {e}")

    print("\n✅ Збір завершено")


def collect_market(token, profile_id, market, date, week):
    margin = MARGIN.get(market, 0.25)

    # ── Крок 1: Запускаємо ВСІ 4 звіти одночасно ─────────────
    # Так Amazon починає обробку всіх звітів паралельно
    print(f"  → Запускаємо звіти для {date}...")
    report_ids = {}

    for rname, rtype, cols, grp in [
        ("campaign",    "spCampaigns",  COLS_CAMPAIGN,    ["campaign"]),
        ("search_term", "spSearchTerm", COLS_SEARCH_TERM, ["searchTerm"]),
        ("placement",   "spCampaigns",  COLS_PLACEMENT,   ["campaignPlacement"]),
        ("targeting",   "spTargeting",  COLS_TARGETING,   ["targeting"]),
    ]:
        try:
            rid = submit_report(
                token, profile_id,
                f"{rname} {date}", rtype, cols, grp, date,
            )
            report_ids[rname] = rid
            print(f"  📋 {rname}: {rid[:8]}...")
        except Exception as e:
            print(f"  ❌ Submit {rname}: {e}")

    # ── Крок 2: Кампанії та ключові слова (поки звіти готуються) ──
    campaigns = []
    keywords  = []
    try:
        campaigns = get_campaigns(token, profile_id)
        keywords  = get_keywords(token, profile_id)
        print(f"  ✅ Кампанії: {len(campaigns)}, ключові слова: {len(keywords)}")
    except Exception as e:
        print(f"  ⚠️ Кампанії/ключові слова: {e}")

    # ── Крок 3: Завантажуємо кожен звіт зі свіжим токеном ────────
    metrics = {}

    # Campaign
    if "campaign" in report_ids:
        try:
            print(f"  → Чекаємо Campaign report...")
            t = get_access_token()
            data    = wait_and_download(t, profile_id, report_ids["campaign"],
                                        token_fn=get_access_token)
            metrics = calculate_metrics(data, margin)
            write_campaign_analysis(metrics, week, market)
        except Exception as e:
            print(f"  ❌ Campaign: {e}")

    # Bid Snapshot — не потребує звіту, вже маємо дані
    if campaigns:
        try:
            write_bid_snapshot(campaigns, keywords, week, market)
        except Exception as e:
            print(f"  ❌ Bid Snapshot: {e}")

    # Search Term → Raw Data
    if "search_term" in report_ids:
        try:
            print(f"  → Чекаємо Search Term report...")
            t = get_access_token()
            data = wait_and_download(t, profile_id, report_ids["search_term"],
                                     token_fn=get_access_token)
            write_raw_data(data, week, market)
        except Exception as e:
            print(f"  ❌ Search Term: {e}")

    # Placement
    if "placement" in report_ids:
        try:
            print(f"  → Чекаємо Placement report...")
            t = get_access_token()
            data   = wait_and_download(t, profile_id, report_ids["placement"],
                                       token_fn=get_access_token)
            issues = analyze_placement_issues(data, campaigns)
            write_placement_analysis(data, issues, week, market)
        except Exception as e:
            print(f"  ❌ Placement: {e}")

    # Targeting → Keyword Intelligence
    if "targeting" in report_ids:
        try:
            print(f"  → Чекаємо Targeting report...")
            t = get_access_token()
            data        = wait_and_download(t, profile_id, report_ids["targeting"],
                                            token_fn=get_access_token)
            kw_analysis = _build_keyword_rows(data)
            write_keyword_intelligence(kw_analysis, week, market)
        except Exception as e:
            print(f"  ❌ Targeting: {e}")

    return metrics


def _build_keyword_rows(targeting_data: list) -> list:
    """Групуємо targeting report по ключовому слову."""
    by_kw = {}
    for r in targeting_data:
        key = (
            r.get("keyword") or r.get("targetingExpression", ""),
            r.get("matchType", ""),
            r.get("campaignName", ""),
        )
        if key not in by_kw:
            by_kw[key] = {
                "keyword": key[0], "match_type": key[1], "campaign": key[2],
                "impressions": 0, "clicks": 0, "orders": 0,
                "spend": 0.0, "sales": 0.0, "lifetime_sales": 0.0,
                "weeks_active": 1, "status": "", "recommendation": "",
                "listing_indexed": "", "action": "",
            }
        e = by_kw[key]
        e["impressions"] += int(r.get("impressions", 0))
        e["clicks"]      += int(r.get("clicks", 0))
        e["orders"]      += int(r.get("purchases7d", 0))
        spend = float(r.get("cost") or r.get("spend") or 0)
        sales = float(r.get("sales7d", 0))
        e["spend"]         += spend
        e["sales"]         += sales
        e["lifetime_sales"] += sales

    result = []
    for e in by_kw.values():
        e["acos"] = round(e["spend"] / e["sales"] * 100 if e["sales"] > 0 else 0, 1)
        e["roas"] = round(e["sales"] / e["spend"]       if e["spend"] > 0 else 0, 2)
        result.append(e)
    return result
