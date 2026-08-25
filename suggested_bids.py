# ============================================================
# SUGGESTED BIDS — збір рекомендованих ставок через SP Ads API
# Запускається окремо раз на 2 дні, пише в Sheets
# monitor.py читає з Sheets — без live запитів до Amazon
# ============================================================

import requests
import time
import json
from datetime import datetime
from config import (
    ADS_CLIENT_ID, ADS_CLIENT_SECRET, ADS_REFRESH_TOKEN,
    ADS_PROFILE_ID_USA, ADS_PROFILE_ID_CA,
)
from amazon_ads import get_access_token, get_campaigns, get_keywords
from sheets import get_sheet

ADS_BASE_URL = "https://advertising-api.amazon.com"

SUGGESTED_BID_SHEETS = {
    "USA": "Suggested Bids USA",
    "CA":  "Suggested Bids CA",
}

HEADERS = [
    "CampaignId", "CampaignName", "AdGroupId", "AdGroupName",
    "Keyword", "MatchType",
    "SuggestedBid", "BidRangeMin", "BidRangeMax",
    "UpdatedAt",
]


def fetch_bid_recommendations(token: str, profile_id: str,
                               keywords: list, campaigns: list) -> list:
    """
    Збирає suggested bids для всіх ENABLED keywords.
    Повертає список рядків для запису в Sheets.
    Захист: якщо 0 результатів або помилка — повертає порожній список,
    старі дані в Sheets залишаються нетронутими.
    """
    # Маппінг campaignId → campaignName
    camp_names = {str(c.get("campaignId", "")): c.get("name", "")
                  for c in campaigns}

    # Групуємо ENABLED keywords по (adGroupId, campaignId)
    by_adgroup = {}
    for kw in keywords:
        if str(kw.get("state", "")).upper() != "ENABLED":
            continue
        adgroup_id   = str(kw.get("adGroupId", ""))
        campaign_id  = str(kw.get("campaignId", ""))
        adgroup_name = kw.get("adGroupName", "")
        kw_text      = kw.get("keywordText", "")
        match_type   = str(kw.get("matchType", "EXACT")).upper()
        kw_id        = str(kw.get("keywordId", ""))

        if not adgroup_id or not kw_text or not kw_id:
            continue

        type_map = {
            "EXACT":  "KEYWORD_EXACT_MATCH",
            "PHRASE": "KEYWORD_PHRASE_MATCH",
            "BROAD":  "KEYWORD_BROAD_MATCH",
        }
        key = (adgroup_id, campaign_id)
        by_adgroup.setdefault(key, {
            "adgroup_name": adgroup_name,
            "keywords": [],
        })["keywords"].append({
            "kw_text":    kw_text,
            "match_type": match_type,
            "expr_type":  type_map.get(match_type, "KEYWORD_EXACT_MATCH"),
            "keyword_id": kw_id,
        })

    total = len(by_adgroup)
    print(f"  📊 {total} активних ad groups для обробки")

    if total == 0:
        return []

    url = f"{ADS_BASE_URL}/sp/targets/bid/recommendations"
    h = {
        "Authorization":                   f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
        "Amazon-Advertising-API-Scope":    str(profile_id),
        "Content-Type":                    "application/json",
        "Accept":                          "application/json",
    }

    reverse_map = {
        "KEYWORD_EXACT_MATCH":  "EXACT",
        "KEYWORD_PHRASE_MATCH": "PHRASE",
        "KEYWORD_BROAD_MATCH":  "BROAD",
    }

    rows = []
    processed = 0
    updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    for (adgroup_id, campaign_id), ag_data in by_adgroup.items():
        adgroup_name = ag_data["adgroup_name"]
        camp_name    = camp_names.get(campaign_id, "")
        kw_list      = ag_data["keywords"]

        for i in range(0, len(kw_list), 100):
            chunk = kw_list[i:i + 100]
            payload = {
                "campaignId":           campaign_id,
                "adGroupId":            adgroup_id,
                "recommendationType":   "BIDS_FOR_EXISTING_AD_GROUP",
                "targetingExpressions": [
                    {"type": kw["expr_type"], "value": kw["kw_text"]}
                    for kw in chunk
                ],
            }

            for attempt in range(3):
                try:
                    r = requests.post(url, headers=h, json=payload)

                    if r.status_code == 200:
                        data = r.json()

                        # Debug першої успішної відповіді
                        if len(rows) == 0:
                            print(f"  🔍 Структура відповіді: {list(data.keys())}")
                            if data:
                                first_val = str(list(data.values())[0])[:200]
                                print(f"  🔍 Перше значення: {first_val}")

                        # Правильна структура відповіді:
                        # bidRecommendations → [{bidRecommendationsForTargetingExpressions: [{
                        #   targetingExpression: {type, value},
                        #   bidValues: [{suggestedBid, rangeStart, rangeEnd}]
                        # }]}]
                        for theme_rec in data.get("bidRecommendations", []):
                            for target_rec in theme_rec.get("bidRecommendationsForTargetingExpressions", []):
                                expr       = target_rec.get("targetingExpression", {})
                                kw_text    = expr.get("value", "")
                                expr_type  = expr.get("type", "")
                                match_type = reverse_map.get(expr_type, "")

                                bid_values = target_rec.get("bidValues", [{}])
                                first_bid  = bid_values[0] if bid_values else {}
                                suggested  = float(first_bid.get("suggestedBid", 0) or 0)
                                bid_min    = float(first_bid.get("rangeStart", 0) or 0)
                                bid_max    = float(first_bid.get("rangeEnd", 0) or 0)

                                if suggested == 0:
                                    continue

                                for kw in chunk:
                                    if (kw["kw_text"] == kw_text and
                                            kw["match_type"] == match_type):
                                        rows.append([
                                            campaign_id, camp_name,
                                            adgroup_id, adgroup_name,
                                            kw_text, match_type,
                                            round(suggested, 2),
                                            round(bid_min, 2),
                                            round(bid_max, 2),
                                            updated_at,
                                        ])
                                        break
                        break  # успіх — виходимо з retry

                    elif r.status_code == 429:
                        wait = 30
                        print(f"  ⏳ Rate limit [{adgroup_id}] — {wait}s (спроба {attempt+1}/3)")
                        time.sleep(wait)

                    elif r.status_code == 404:
                        break  # нова кампанія без даних

                    else:
                        if processed < 3:
                            print(f"  ⚠️ [{adgroup_id}]: {r.status_code} {r.text[:150]}")
                        break

                except Exception as e:
                    print(f"  ⚠️ exception [{adgroup_id}]: {e}")
                    break

            time.sleep(5.0)

        processed += 1
        if processed % 5 == 0:
            print(f"  ⏳ Прогрес: {processed}/{total} ad groups, {len(rows)} рядків зібрано")

    return rows


def write_suggested_bids(market: str, rows: list):
    """
    Безпечний запис: очищає і записує ТІЛЬКИ якщо rows > 0.
    Якщо 0 результатів — залишає старі дані нетронутими.
    """
    sheet_name = SUGGESTED_BID_SHEETS[market]
    sh = get_sheet(sheet_name)

    if not rows:
        # Читаємо дату останнього оновлення з поточних даних
        existing = sh.get_all_values()
        last_date = ""
        if len(existing) > 1:
            try:
                col_updated = existing[0].index("UpdatedAt")
                last_date = existing[1][col_updated] if len(existing[1]) > col_updated else ""
            except ValueError:
                pass
        print(f"  ⚠️ {market}: 0 результатів — залишаємо старі дані (від {last_date})")
        return

    # Є дані — очищаємо і записуємо
    sh.clear()
    sh.update([HEADERS] + rows, "A1")
    print(f"  ✅ {market}: {len(rows)} рядків записано в '{sheet_name}'")


def run_suggested_bids():
    print("=" * 60)
    print(f"💡 SUGGESTED BIDS — ЗБІР РЕКОМЕНДОВАНИХ СТАВОК")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    markets = [
        ("USA", ADS_PROFILE_ID_USA),
        ("CA",  ADS_PROFILE_ID_CA),
    ]

    for market, profile_id in markets:
        if not profile_id:
            print(f"⏭️  {market}: profile_id не задано")
            continue

        print(f"\n🌎 {market}...")
        try:
            token     = get_access_token()
            campaigns = get_campaigns(token, profile_id)
            keywords  = get_keywords(token, profile_id)
            print(f"  ✅ Кампанії: {len(campaigns)}, Keywords: {len(keywords)}")

            rows = fetch_bid_recommendations(token, profile_id, keywords, campaigns)
            write_suggested_bids(market, rows)

        except Exception as e:
            import traceback
            print(f"  ❌ {market} помилка: {e}")
            traceback.print_exc()

    print("\n✅ SUGGESTED BIDS ЗАВЕРШЕНО")


if __name__ == "__main__":
    run_suggested_bids()
