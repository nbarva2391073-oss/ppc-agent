# ОДНОРАЗОВИЙ read-only аудит Sponsored Brands USA.
# Нічого не пише в Sheets, не змінює кампанії. Лише GET/POST звітів і list.
# Зберігає сирі відповіді Amazon Ads API у diag/sb_audit/.
import gzip, io, json, os, re, time
from datetime import datetime
import requests
from config import ADS_PROFILE_ID_USA
from amazon_ads import get_access_token, headers, ADS_BASE_URL

OUT = os.path.join("diag", "sb_audit")
os.makedirs(OUT, exist_ok=True)
PID = ADS_PROFILE_ID_USA
START, END = "2026-09-14", "2026-10-08"      # DAILY-період аудиту
SUM_END = "2026-10-04"                       # кінець тижня 28.09–04.10

def dump(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)

token = get_access_token()

# 1. SB-кампанії: усі стани, з пагінацією
camps, tok = [], None
ct = "application/vnd.sbcampaignresource.v4+json"
while True:
    body = {"maxResults": 100}
    if tok: body["nextToken"] = tok
    r = requests.post(f"{ADS_BASE_URL}/sb/v4/campaigns/list",
                      headers=headers(token, PID, content_type=ct), json=body)
    if r.status_code != 200:
        dump("campaigns_error.json", {"status": r.status_code, "body": r.text[:800]}); break
    d = r.json(); camps += d.get("campaigns", []); tok = d.get("nextToken")
    if not tok: break
dump("sb_campaigns_all_states.json", camps)
print("SB campaigns (all states):", len(camps),
      [(c.get("campaignId"), c.get("name"), c.get("state")) for c in camps])

CAMP = ["date","campaignId","campaignName","campaignStatus","impressions","clicks","cost","sales","purchases","unitsSold"]
CAMP_COLLECTOR = ["campaignId","campaignName","campaignStatus","impressions","clicks","cost","sales","purchases","unitsSold","newToBrandSales","newToBrandPurchases"]
ST_COLLECTOR = ["campaignId","campaignName","adGroupName","keywordText","matchType","searchTerm","impressions","clicks","cost","sales","purchases","unitsSold"]
ST_A = ["date","campaignId","campaignName","adGroupId","adGroupName","keywordId","keywordText","matchType","searchTerm","impressions","clicks","cost","sales","purchases","unitsSold"]
ST_B = ["date"] + ST_COLLECTOR
TG_A = ["date","campaignId","campaignName","adGroupId","adGroupName","keywordId","keywordText","matchType","targetingText","targetingType","impressions","clicks","cost","sales","purchases","unitsSold"]
TG_B = ["date","campaignId","campaignName","adGroupId","adGroupName","targetId","targetingText","targetingType","matchType","impressions","clicks","cost","sales","purchases","unitsSold"]
TG_C = ["date","campaignId","campaignName","adGroupName","targetingText","matchType","impressions","clicks","cost","sales","purchases"]

PLAN = [  # label, reportTypeId, groupBy, timeUnit, columns, start, end
 ("camp_daily",          "sbCampaigns",  ["campaign"],    "DAILY",   CAMP,           START, END),
 ("camp_summary_collector_window", "sbCampaigns", ["campaign"], "SUMMARY", CAMP_COLLECTOR, "2026-10-05", "2026-10-06"),
 ("camp_summary_single_day",       "sbCampaigns", ["campaign"], "SUMMARY", CAMP_COLLECTOR, "2026-10-05", "2026-10-05"),
 ("st_daily_A",          "sbSearchTerm", ["searchTerm"],  "DAILY",   ST_A,           START, END),
 ("st_daily_B",          "sbSearchTerm", ["searchTerm"],  "DAILY",   ST_B,           START, END),
 ("st_summary_period",   "sbSearchTerm", ["searchTerm"],  "SUMMARY", ST_COLLECTOR,   "2026-09-14", SUM_END),
 ("tg_daily_A",          "sbTargeting",  ["targeting"],   "DAILY",   TG_A,           START, END),
 ("tg_daily_B",          "sbTargeting",  ["targeting"],   "DAILY",   TG_B,           START, END),
 ("tg_daily_C",          "sbTargeting",  ["targeting"],   "DAILY",   TG_C,           START, END),
]

pending, status = {}, {}
for label, rtype, grp, unit, cols, s, e in PLAN:
    payload = {"name": f"SBaudit {label}", "startDate": s, "endDate": e,
               "configuration": {"adProduct": "SPONSORED_BRANDS", "groupBy": grp, "columns": cols,
                                 "reportTypeId": rtype, "timeUnit": unit, "format": "GZIP_JSON"}}
    rid = None
    for attempt in range(5):
        r = requests.post(f"{ADS_BASE_URL}/reporting/reports", headers=headers(token, PID), json=payload)
        if r.status_code in (200, 202):
            rid = r.json()["reportId"]; break
        m = re.search(r"duplicate of\s*:\s*([\w-]+)", r.text)
        if m: rid = m.group(1); break
        if r.status_code == 429:
            time.sleep(65); continue
        break
    status[label] = {"submit_http": r.status_code, "submit_body": None if rid else r.text[:600],
                     "report_id": rid, "window": [s, e], "timeUnit": unit}
    print(label, r.status_code, rid)
    if rid: pending[label] = rid
    time.sleep(65)

deadline = time.time() + 80 * 60
while pending and time.time() < deadline:
    token = get_access_token()
    for label, rid in list(pending.items()):
        r = requests.get(f"{ADS_BASE_URL}/reporting/reports/{rid}", headers=headers(token, PID))
        d = r.json() if r.status_code == 200 else {"status": f"HTTP {r.status_code}", "body": r.text[:300]}
        st = d.get("status")
        if st == "COMPLETED":
            raw = requests.get(d.get("url") or d.get("location")).content
            data = json.loads(gzip.GzipFile(fileobj=io.BytesIO(raw)).read().decode("utf-8"))
            dump(f"report_{label}.json", data)
            status[label].update({"final": "COMPLETED", "rows": len(data)})
            print("done", label, len(data)); pending.pop(label)
        elif st == "FAILED":
            status[label].update({"final": "FAILED", "reason": d.get("failureReason")})
            print("FAILED", label, d.get("failureReason")); pending.pop(label)
    if pending: time.sleep(60)
for label in pending:
    status[label]["final"] = "TIMEOUT/IN_PROGRESS"
dump("STATUS.json", status)
print(json.dumps(status, ensure_ascii=False, indent=1)[:3000])
