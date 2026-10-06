# ОДНОРАЗОВА діагностика Suggested Bids USA (нічого не пише в Sheets).
# Зберігає сирі відповіді Amazon Ads API у diag/suggested_bids_usa/.
import json, os, requests
from config import ADS_CLIENT_ID, ADS_PROFILE_ID_USA
from amazon_ads import get_access_token, headers, ADS_BASE_URL

OUT = os.path.join("diag", "suggested_bids_usa")
os.makedirs(OUT, exist_ok=True)
TARGET_NAME = "inside x2 exact diagnostic"
KEYS = ["pheromone perfume for woman", "pheromone perfume women", "pheromone perfume"]

def dump(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

token = get_access_token()
pid = ADS_PROFILE_ID_USA

# 1. Профілі: marketplace/country для ADS_PROFILE_ID_USA
r = requests.get(f"{ADS_BASE_URL}/v2/profiles",
                 headers=headers(token, pid))
profiles = r.json() if r.status_code == 200 else {"status": r.status_code, "body": r.text[:500]}
dump("profiles.json", profiles)

def paged(url, ct, payload, field):
    items, tok = [], None
    while True:
        p = dict(payload)
        if tok:
            p["nextToken"] = tok
        r = requests.post(url, headers=headers(token, pid, content_type=ct), json=p)
        if r.status_code != 200:
            return items, {"status": r.status_code, "body": r.text[:500]}
        d = r.json()
        items += d.get(field, [])
        tok = d.get("nextToken")
        if not tok:
            return items, None

# 2. Кампанії: поточний фільтр (ENABLED,PAUSED, без пагінації) vs усі стани з пагінацією
ct_c = "application/vnd.spCampaign.v3+json"
cur = requests.post(f"{ADS_BASE_URL}/sp/campaigns/list",
                    headers=headers(token, pid, content_type=ct_c),
                    json={"stateFilter": {"include": ["ENABLED", "PAUSED"]}, "maxResults": 100}).json()
cur_ids = {str(c["campaignId"]) for c in cur.get("campaigns", [])}
allc, err = paged(f"{ADS_BASE_URL}/sp/campaigns/list", ct_c, {"maxResults": 100}, "campaigns")
dump("campaigns_all.json", allc)
target = [c for c in allc if TARGET_NAME in c.get("name", "").lower()]
summary = {
    "current_code_returns": len(cur_ids), "current_has_nextToken": bool(cur.get("nextToken")),
    "all_states_paginated": len(allc), "error": err,
    "state_counts": {}, "target_campaigns": target,
    "target_in_current_code_result": [str(c["campaignId"]) in cur_ids for c in target],
}
for c in allc:
    summary["state_counts"][c.get("state")] = summary["state_counts"].get(c.get("state"), 0) + 1

# 3. Ключові слова: поточний виклик (ENABLED, maxResults 1000, без пагінації) vs усі з пагінацією
ct_k = "application/vnd.spKeyword.v3+json"
curk = requests.post(f"{ADS_BASE_URL}/sp/keywords/list",
                     headers=headers(token, pid, content_type=ct_k),
                     json={"stateFilter": {"include": ["ENABLED"]}, "maxResults": 1000}).json()
cur_kw_ids = {str(k["keywordId"]) for k in curk.get("keywords", [])}
allk, errk = paged(f"{ADS_BASE_URL}/sp/keywords/list", ct_k, {"maxResults": 1000}, "keywords")
dump("keywords_all.json", allk)
tids = {str(c["campaignId"]) for c in target}
tk = [k for k in allk if str(k.get("campaignId")) in tids]
summary.update({
    "keywords_current_code_returns": len(cur_kw_ids), "keywords_current_has_nextToken": bool(curk.get("nextToken")),
    "keywords_all_paginated": len(allk), "keywords_error": errk,
    "target_keywords": tk,
    "target_keywords_in_current_code_result": sum(str(k["keywordId"]) in cur_kw_ids for k in tk),
})

# 4. Сирі відповіді recommendations: цільова кампанія + «стара» кампанія з тими ж ключами
CTS = {
    "default_json": "application/json",
    "theme_v4": "application/vnd.spthemebasedbidrecommendation.v4+json",
    "theme_v5": "application/vnd.spthemebasedbidrecommendation.v5+json",
}
def recs(label, camp_id, ag_id):
    out = {}
    for tag, ct in CTS.items():
        payload = {"campaignId": str(camp_id), "adGroupId": str(ag_id),
                   "recommendationType": "BIDS_FOR_EXISTING_AD_GROUP",
                   "targetingExpressions": [{"type": "KEYWORD_EXACT_MATCH", "value": k} for k in KEYS]}
        h = headers(token, pid, content_type=ct)
        rr = requests.post(f"{ADS_BASE_URL}/sp/targets/bid/recommendations", headers=h, json=payload)
        try: body = rr.json()
        except Exception: body = rr.text[:1000]
        out[tag] = {"status": rr.status_code, "body": body}
    dump(f"recs_{label}.json", out)

for c in target:
    ags = {str(k["adGroupId"]) for k in tk if str(k["campaignId"]) == str(c["campaignId"])}
    for ag in ags:
        recs(f"target_{c['campaignId']}_{ag}", c["campaignId"], ag)
legacy = [k for k in allk if k.get("keywordText", "").lower() in KEYS
          and str(k.get("campaignId")) not in tids and k.get("matchType") == "EXACT"]
summary["legacy_same_keywords"] = legacy[:20]
seen = set()
for k in legacy:
    key = (k["campaignId"], k["adGroupId"])
    if key in seen or len(seen) >= 2:
        continue
    seen.add(key)
    recs(f"legacy_{k['campaignId']}_{k['adGroupId']}", k["campaignId"], k["adGroupId"])

dump("SUMMARY.json", summary)
print(json.dumps({k: v for k, v in summary.items() if not isinstance(v, list)}, indent=2, ensure_ascii=False))
