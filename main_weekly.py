# ============================================================
# ГОЛОВНИЙ ОРКЕСТРАТОР — щотижневий запуск
# ============================================================

import sys
from datetime import datetime, timedelta
from config import (MARGIN, ADS_PROFILE_ID_USA, ADS_PROFILE_ID_CA)
from amazon_ads import (
    get_access_token, get_campaigns, get_keywords,
    get_search_term_report, get_campaign_report,
    get_placement_report, get_targeting_report,
    calculate_metrics, analyze_placement_issues,
)
from analyzer import deep_analyze
from keywords import analyze_keywords, find_negative_candidates
from sheets import (
    write_raw_data, write_bid_snapshot,
    write_placement_analysis, write_campaign_analysis,
    write_keyword_intelligence, write_ai_recommendations,
    write_weekly_summary, get_full_history,
)
from telegram_bot import send_weekly_summary, send_message


def get_week_dates() -> tuple[str, str, str]:
    today = datetime.now()
    end   = today - timedelta(days=1)
    start = end - timedelta(days=6)
    return (
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        f"{start.strftime('%d.%m')}-{end.strftime('%d.%m.%Y')}",
    )


def process_market(token: str, profile_id: str,
                   market: str, start: str, end: str,
                   week_label: str) -> dict:
    """Обробити один маркетплейс повністю."""
    print(f"\n{'='*50}")
    print(f"🌎 ОБРОБЛЯЄМО: {market}")
    print(f"{'='*50}")

    margin = MARGIN.get(market, 0.25)

    # ── 1. Кампанії і ключові слова ──────────────────────────
    print("\n📡 Завантажуємо кампанії...")
    campaigns = get_campaigns(token, profile_id)
    keywords  = get_keywords(token, profile_id)

    # ── 2. Звіти — запускаємо всі, потім чекаємо ────────────
    print("\n📋 Завантажуємо звіти...")
    import time as _time
    from concurrent.futures import ThreadPoolExecutor

    # Спочатку створюємо всі звіти з затримкою
    from amazon_ads import _request_report, wait_and_download
    from datetime import datetime as _dt, timedelta as _td

    def _make_report(fn, *args):
        _time.sleep(5)  # затримка між запитами
        return fn(*args)

    with ThreadPoolExecutor(max_workers=4) as ex:
        f_st = ex.submit(_make_report, get_search_term_report, token, profile_id, start, end)
        _time.sleep(3)
        f_ca = ex.submit(_make_report, get_campaign_report,    token, profile_id, start, end)
        _time.sleep(3)
        f_pl = ex.submit(_make_report, get_placement_report,   token, profile_id, start, end)
        _time.sleep(3)
        f_tg = ex.submit(_make_report, get_targeting_report,   token, profile_id, start, end)
    search_term_data = f_st.result()
    campaign_data    = f_ca.result()
    placement_data   = f_pl.result()
    targeting_data   = f_tg.result()

    # ── 3. Метрики ───────────────────────────────────────────
    print("\n📊 Розраховуємо метрики...")
    metrics = calculate_metrics(campaign_data, margin)
    metrics["week_label"] = week_label

    # ── 4. Placement аналіз ──────────────────────────────────
    print("\n📍 Аналізуємо placements...")
    placement_issues = analyze_placement_issues(
        placement_data, campaigns)
    if placement_issues:
        print(f"  ⚠️ Виявлено {len(placement_issues)} placement проблем")

    # ── 5. Keyword Intelligence ──────────────────────────────
    print("\n🔑 Аналізуємо ключові слова...")
    history = get_full_history(market)
    keyword_analysis = analyze_keywords(
        search_term_data, targeting_data, history, market)
    negative_candidates = find_negative_candidates(
        search_term_data, margin * 100)
    print(f"  ✅ Ключових слів: {len(keyword_analysis)}")
    print(f"  ⚠️ Кандидатів на негативні: {len(negative_candidates)}")

    # ── 6. Записуємо в Google Sheets ─────────────────────────
    print("\n📝 Записуємо в Google Sheets...")
    write_raw_data(search_term_data, week_label, market)
    write_bid_snapshot(campaigns, keywords, week_label, market)
    write_placement_analysis(placement_data, placement_issues,
                              week_label, market)
    write_campaign_analysis(metrics, week_label, market)
    write_keyword_intelligence(keyword_analysis, week_label, market)

    # ── 7. AI Аналіз ─────────────────────────────────────────
    print("\n🧠 Запускаємо AI аналіз...")
    history_updated = get_full_history(market)
    ai_analysis = deep_analyze(
        market=market,
        week_label=week_label,
        campaign_data=campaign_data,
        search_term_data=search_term_data,
        placement_data=placement_data,
        campaigns=campaigns,
        metrics=metrics,
        keyword_analysis=keyword_analysis,
        placement_issues=placement_issues,
        history=history_updated,
    )

    write_ai_recommendations(ai_analysis, week_label, market)
    print("  ✅ AI аналіз збережено")

    # ── 8. Telegram звіт ─────────────────────────────────────
    send_weekly_summary(market, metrics)

    return metrics


def run_weekly():
    """Головна функція щотижневого запуску."""
    print("=" * 60)
    print(f"🚀 PPC AGENT v2 — ТИЖНЕВИЙ ЗАПУСК")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    start, end, week_label = get_week_dates()
    print(f"📅 Тиждень: {week_label}")

    try:
        token = get_access_token()
        print("✅ Amazon Ads токен отримано")

        usa_metrics = {}
        ca_metrics  = {}

        # ── USA ─────────────────────────────────────────────
        if ADS_PROFILE_ID_USA:
            usa_metrics = process_market(
                token, ADS_PROFILE_ID_USA,
                "USA", start, end, week_label)
        else:
            print("⚠️ ADS_PROFILE_ID_USA не налаштовано")

        # ── CANADA ──────────────────────────────────────────
        if ADS_PROFILE_ID_CA:
            ca_metrics = process_market(
                token, ADS_PROFILE_ID_CA,
                "CA", start, end, week_label)
        else:
            print("⚠️ ADS_PROFILE_ID_CA не налаштовано")

        # ── Загальний Summary ────────────────────────────────
        write_weekly_summary(usa_metrics, ca_metrics, week_label)

        # ── Фінальне повідомлення ────────────────────────────
        print("\n" + "=" * 60)
        print("✅ ТИЖНЕВИЙ АГЕНТ ЗАВЕРШИВ РОБОТУ УСПІШНО!")
        print("=" * 60)

        send_message(
            f"✅ <b>Тижневий звіт готовий!</b>\n"
            f"Тиждень: {week_label}\n"
            f"Деталі → Google Sheets"
        )

    except Exception as e:
        print(f"\n❌ КРИТИЧНА ПОМИЛКА: {e}")
        import traceback
        traceback.print_exc()
        send_message(f"❌ <b>PPC Agent помилка!</b>\n{str(e)[:500]}")
        sys.exit(1)


if __name__ == "__main__":
    run_weekly()
