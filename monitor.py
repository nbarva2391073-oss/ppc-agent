# ============================================================
# ЩОДЕННИЙ ЗБІР ДАНИХ — тільки збираємо і записуємо в Sheets
# Без Claude API. Без алертів. Без порівнянь.
# ============================================================

from datetime import datetime, timedelta
from config import (
    MARGIN,
    ADS_PROFILE_ID_USA, ADS_PROFILE_ID_CA,
)
from amazon_ads import (
    get_access_token,
    get_campaigns, get_keywords,
    get_campaign_report,
    get_search_term_report,
    get_placement_report,
    get_targeting_report,
    calculate_metrics,
    analyze_placement_issues,
)
from sheets import (
    write_raw_data,
    write_campaign_analysis,
    write_bid_snapshot,
    write_placement_analysis,
    write_keyword_intelligence,
    write_weekly_summary,
)


def run_daily_monitor():
    print("=" * 60)
    print(f"📦 ЗБІР ДАНИХ: {datetime.now()}")
    print("=" * 60)

    token = get_access_token()
    today = datetime.now()
    # Збираємо дані за вчора (Amazon не дає сьогоднішній день в повному обсязі)
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
        metrics = collect_market(token, profile_id, market, date, week)
        all_metrics[market] = metrics

    # Weekly Summary — записуємо після збору обох маркетплейсів
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
    """Збирає всі звіти для одного маркетплейсу і пише в Sheets."""
    margin = MARGIN.get(market, 0.25)
    campaigns = []
    metrics   = {}

    # ── 1. Campaign Report ────────────────────────────────────
    try:
        print(f"  → Campaign Report...")
        campaign_data = get_campaign_report(token, profile_id, date, date)
        metrics       = calculate_metrics(campaign_data, margin)
        write_campaign_analysis(metrics, week, market)
    except Exception as e:
        print(f"  ❌ Campaign report: {e}")
        campaign_data = []

    # ── 2. Search Term Report → Raw Data ──────────────────────
    try:
        print(f"  → Search Term Report...")
        search_data = get_search_term_report(token, profile_id, date, date)
        write_raw_data(search_data, week, market)
    except Exception as e:
        print(f"  ❌ Search Term report: {e}")

    # ── 3. Placement Report ───────────────────────────────────
    try:
        print(f"  → Placement Report...")
        placement_data = get_placement_report(token, profile_id, date, date)
        if not campaigns:
            campaigns = get_campaigns(token, profile_id)
        issues = analyze_placement_issues(placement_data, campaigns)
        write_placement_analysis(placement_data, issues, week, market)
    except Exception as e:
        print(f"  ❌ Placement report: {e}")

    # ── 4. Bid Snapshot (кампанії + ключові слова) ────────────
    try:
        print(f"  → Bid Snapshot...")
        if not campaigns:
            campaigns = get_campaigns(token, profile_id)
        keywords = get_keywords(token, profile_id)
        write_bid_snapshot(campaigns, keywords, week, market)
    except Exception as e:
        print(f"  ❌ Bid snapshot: {e}")

    # ── 5. Targeting Report → Keyword Intelligence ────────────
    try:
        print(f"  → Targeting Report...")
        targeting_data = get_targeting_report(token, profile_id, date, date)
        kw_analysis    = _build_keyword_rows(targeting_data)
        write_keyword_intelligence(kw_analysis, week, market)
    except Exception as e:
        print(f"  ❌ Targeting report: {e}")

    return metrics


def _build_keyword_rows(targeting_data: list) -> list:
    """
    Групуємо targeting report по (keyword, match_type, campaign).
    Повертаємо список словників для write_keyword_intelligence.
    """
    by_kw = {}
    for r in targeting_data:
        key = (
            r.get("keyword") or r.get("targetingExpression", ""),
            r.get("matchType", ""),
            r.get("campaignName", ""),
        )
        if key not in by_kw:
            by_kw[key] = {
                "keyword":    key[0],
                "match_type": key[1],
                "campaign":   key[2],
                "impressions":     0,
                "clicks":          0,
                "orders":          0,
                "spend":           0.0,
                "sales":           0.0,
                "lifetime_sales":  0.0,
                "weeks_active":    1,
                "status":          "",
                "recommendation":  "",
                "listing_indexed": "",
                "action":          "",
            }
        e = by_kw[key]
        e["impressions"] += int(r.get("impressions", 0))
        e["clicks"]      += int(r.get("clicks", 0))
        e["orders"]      += int(r.get("purchases7d", 0))
        spend = float(r.get("cost") or r.get("spend") or 0)
        sales = float(r.get("sales7d", 0))
        e["spend"] += spend
        e["sales"] += sales
        e["lifetime_sales"] += sales

    result = []
    for e in by_kw.values():
        spend = e["spend"]
        sales = e["sales"]
        e["acos"] = round(spend / sales * 100 if sales > 0 else 0, 1)
        e["roas"] = round(sales / spend       if spend > 0 else 0, 2)
        result.append(e)
    return result
