# ============================================================
# SUGGESTED BIDS — збір рекомендованих ставок через SP Ads API
# Запускається окремо раз на 2 дні, пише в Sheets
# monitor.py читає з Sheets — без live запитів до Amazon
#
# Зміни (жовтень 2026):
#  - пагінація кампаній/груп/ключів (nextToken) — раніше брались лише
#    перші 100 кампаній і 1000 ключів, нові кампанії випадали;
#  - назви кампаній/груп беруться за ID з повного списку (усі стани);
#  - v5 theme-based recommendations: bidValues = [low, suggested, high],
#    полів rangeStart/rangeEnd немає (раніше → завжди 0/0, а як
#    suggested бралось bidValues[0], тобто НИЖНЯ межа);
#  - відсутні значення лишаються порожніми, не 0;
#  - історія: нові snapshot-рядки ДОДАЮТЬСЯ, без clear().
# ============================================================

import time
import requests
from datetime import datetime, timezone
from config import (
    ADS_CLIENT_ID, ADS_PROFILE_ID_USA, ADS_PROFILE_ID_CA,
)
from amazon_ads import get_access_token, headers, ADS_BASE_URL
from sheets import get_sheet

SUGGESTED_BID_SHEETS = {
    "USA": "Suggested Bids USA",
    "CA":  "Suggested Bids CA",
}

# Нові колонки лише ДОПИСУЮТЬСЯ праворуч до наявного заголовка (без зсуву).
HEADERS = [
    "CampaignId", "CampaignName", "AdGroupId", "AdGroupName",
    "Keyword", "MatchType",
    "SuggestedBid", "BidRangeMin", "BidRangeMax",
    "UpdatedAt",
    "SnapshotDate", "SnapshotTime", "KeywordId", "CurrentBid", "Status",
]

CT_THEME_V5 = "application/vnd.spthemebasedbidrecommendation.v5+json"
PREFERRED_THEME = "CONVERSION_OPPORTUNITIES"

TYPE_MAP = {
    "EXACT":  "KEYWORD_EXACT_MATCH",
    "PHRASE": "KEYWORD_PHRASE_MATCH",
    "BROAD":  "KEYWORD_BROAD_MATCH",
}
REVERSE_MAP = {v: k for k, v in TYPE_MAP.items()}


def _post(url, token, profile_id, ct, payload, retries=5):
    """POST з retry на 429/5xx. Повертає (status, json|text)."""
    r = None
    for attempt in range(retries):
        r = requests.post(url, headers=headers(token, profile_id, content_type=ct),
                          json=payload)
        if r.status_code == 429 or r.status_code >= 500:
            wait = int(r.headers.get("Retry-After", 0) or 0) or 30 * (attempt + 1)
            print(f"  ⏳ {r.status_code} — чекаємо {wait}s (спроба {attempt+1}/{retries})")
            time.sleep(wait)
            continue
        break
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:300]


def _paged(token, profile_id, url, ct, payload, field):
    """Збирає ВСІ сторінки через nextToken. Кидає виняток при помилці."""
    items, next_token = [], None
    while True:
        body = dict(payload)
        if next_token:
            body["nextToken"] = next_token
        status, data = _post(url, token, profile_id, ct, body)
        if status != 200:
            raise Exception(f"{url}: {status} {str(data)[:200]}")
        items += data.get(field, [])
        next_token = data.get("nextToken")
        if not next_token:
            return items


def log_profile(token, profile_id, market):
    """Підтвердження marketplace/profile для логів."""
    try:
        r = requests.get(f"{ADS_BASE_URL}/v2/profiles",
                         headers=headers(token, profile_id))
        for p in r.json():
            if str(p.get("profileId")) == str(profile_id):
                acc = p.get("accountInfo", {})
                print(f"  🌎 {market}: profile ...{str(profile_id)[-4:]} → "
                      f"{p.get('countryCode')} {p.get('currencyCode')} "
                      f"marketplace={acc.get('marketplaceStringId')} type={acc.get('type')}")
                return
        print(f"  ⚠️ {market}: profile ...{str(profile_id)[-4:]} не знайдено в /v2/profiles")
    except Exception as e:
        print(f"  ⚠️ Не вдалось перевірити profile: {e}")


def parse_bid_values(bid_values):
    """
    v5: bidValues = [{suggestedBid: low}, {suggestedBid: suggested}, {suggestedBid: high}].
    Повертає (low, suggested, high); відсутнє = None (не 0).
    """
    vals = []
    for b in bid_values or []:
        v = b.get("suggestedBid")
        vals.append(float(v) if v not in (None, "") else None)
    if len(vals) == 3 and all(v is not None for v in vals) and vals[0] <= vals[1] <= vals[2]:
        return vals[0], vals[1], vals[2]
    if len(vals) == 1:
        return None, vals[0], None
    if vals:
        print(f"  ⚠️ Несподівана структура bidValues: {vals}")
    return None, None, None


def fetch_bid_recommendations(token, profile_id):
    campaigns = _paged(token, profile_id, f"{ADS_BASE_URL}/sp/campaigns/list",
                       "application/vnd.spCampaign.v3+json", {"maxResults": 100}, "campaigns")
    camp_names = {str(c["campaignId"]): c.get("name", "") for c in campaigns}
    camp_state = {str(c["campaignId"]): str(c.get("state", "")).upper() for c in campaigns}

    adgroups = _paged(token, profile_id, f"{ADS_BASE_URL}/sp/adGroups/list",
                      "application/vnd.spAdGroup.v3+json", {"maxResults": 100}, "adGroups")
    ag_names = {str(a["adGroupId"]): a.get("name", "") for a in adgroups}

    keywords = _paged(token, profile_id, f"{ADS_BASE_URL}/sp/keywords/list",
                      "application/vnd.spKeyword.v3+json",
                      {"stateFilter": {"include": ["ENABLED"]}, "maxResults": 1000}, "keywords")
    print(f"  ✅ Кампаній: {len(campaigns)}, груп: {len(adgroups)}, ENABLED keywords: {len(keywords)}")

    by_adgroup = {}
    for kw in keywords:
        cid = str(kw.get("campaignId", ""))
        if camp_state.get(cid) == "ARCHIVED":
            continue
        key = (str(kw["adGroupId"]), cid)
        by_adgroup.setdefault(key, []).append(kw)

    now = datetime.now(timezone.utc)
    snap_date, snap_time = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
    updated_at = now.strftime("%Y-%m-%d %H:%M")

    rows, processed, no_rec = [], 0, 0
    for (ag_id, cid), kws in by_adgroup.items():
        for i in range(0, len(kws), 100):
            chunk = kws[i:i + 100]
            payload = {
                "campaignId": cid, "adGroupId": ag_id,
                "recommendationType": "BIDS_FOR_EXISTING_AD_GROUP",
                "targetingExpressions": [
                    {"type": TYPE_MAP.get(str(k.get("matchType", "")).upper(), "KEYWORD_EXACT_MATCH"),
                     "value": k.get("keywordText", "")} for k in chunk],
            }
            status, data = _post(f"{ADS_BASE_URL}/sp/targets/bid/recommendations",
                                 token, profile_id, CT_THEME_V5, payload)
            found = {}
            if status == 200 and isinstance(data, dict):
                themes = data.get("bidRecommendations", [])
                theme = next((t for t in themes if t.get("theme") == PREFERRED_THEME),
                             themes[0] if themes else {})
                for tr in theme.get("bidRecommendationsForTargetingExpressions", []):
                    ex = tr.get("targetingExpression", {})
                    found[(ex.get("value", "").lower(), REVERSE_MAP.get(ex.get("type", ""), ""))] = \
                        parse_bid_values(tr.get("bidValues"))
            elif processed < 5:
                print(f"  ⚠️ [{ag_id}] {status}: {str(data)[:160]}")

            for k in chunk:
                mt = str(k.get("matchType", "")).upper()
                low, sug, high = found.get((k.get("keywordText", "").lower(), mt), (None, None, None))
                if sug is None:
                    no_rec += 1
                rows.append({
                    "CampaignId": cid, "CampaignName": camp_names.get(cid, ""),
                    "AdGroupId": ag_id, "AdGroupName": ag_names.get(ag_id, ""),
                    "Keyword": k.get("keywordText", ""), "MatchType": mt,
                    "SuggestedBid": sug, "BidRangeMin": low, "BidRangeMax": high,
                    "UpdatedAt": updated_at,
                    "SnapshotDate": snap_date, "SnapshotTime": snap_time,
                    "KeywordId": str(k.get("keywordId", "")),
                    "CurrentBid": k.get("bid"),
                    "Status": str(k.get("state", "")).upper(),
                })
            time.sleep(3.0)
        processed += 1
        if processed % 5 == 0:
            print(f"  ⏳ {processed}/{len(by_adgroup)} ad groups, {len(rows)} рядків")
    print(f"  ℹ️ Без рекомендації (поля порожні): {no_rec} з {len(rows)}")
    return rows


def write_suggested_bids(market, rows):
    """
    Додає snapshot-рядки в кінець (історія), без clear().
    Запис за НАЗВАМИ колонок; відсутні нові колонки дописуються праворуч.
    None → порожня клітинка (не 0).
    """
    if not rows:
        print(f"  ⚠️ {market}: 0 результатів — нічого не пишемо")
        return
    sh = get_sheet(SUGGESTED_BID_SHEETS[market])
    header = sh.row_values(1)
    if not header:
        header = list(HEADERS)
        sh.update([header], "A1")
    else:
        missing = [h for h in HEADERS if h not in header]
        if missing:
            import gspread
            start = gspread.utils.rowcol_to_a1(1, len(header) + 1)
            sh.update([missing], start)
            header = header + missing
            print(f"  📝 Додано колонки праворуч: {missing}")
    out = [[("" if r.get(h) is None else r.get(h)) for h in header] for r in rows]
    sh.append_rows(out, value_input_option="RAW", table_range="A1")
    print(f"  ✅ {market}: додано {len(out)} рядків snapshot {rows[0]['SnapshotDate']} {rows[0]['SnapshotTime']}")


def run_suggested_bids():
    print("=" * 60)
    print("💡 SUGGESTED BIDS — ЗБІР РЕКОМЕНДОВАНИХ СТАВОК")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)
    for market, profile_id in (("USA", ADS_PROFILE_ID_USA), ("CA", ADS_PROFILE_ID_CA)):
        if not profile_id:
            print(f"⏭️  {market}: profile_id не задано")
            continue
        print(f"\n🌎 {market}...")
        try:
            token = get_access_token()
            log_profile(token, profile_id, market)
            write_suggested_bids(market, fetch_bid_recommendations(token, profile_id))
        except Exception as e:
            import traceback
            print(f"  ❌ {market} помилка: {e}")
            traceback.print_exc()
    print("\n✅ SUGGESTED BIDS ЗАВЕРШЕНО")


if __name__ == "__main__":
    run_suggested_bids()
