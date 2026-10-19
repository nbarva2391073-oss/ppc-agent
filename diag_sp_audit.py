# ОДНОРАЗОВИЙ read-only аудит Sponsored Products USA (нічого не пише в Sheets).
# Мета: (1) чи вікно start=вчора,end=сьогодні дає 2 дні; (2) істинні денні суми
# для звірки з Raw Data / Campaign Analysis / Advertised Product.
import json, os, re, time
from datetime import date, timedelta
import requests
from config import ADS_PROFILE_ID_USA
from amazon_ads import get_access_token, headers, ADS_BASE_URL, wait_and_download

MARKET = os.environ.get("MARKET", "USA")
SFX = "" if MARKET == "USA" else "_" + MARKET
OUT = "diag/sp_audit" + SFX; os.makedirs(OUT, exist_ok=True)
import config
PID = config.ADS_PROFILE_ID_CA if MARKET == "CA" else config.ADS_PROFILE_ID_USA
today = date.today()
D_END = (today - timedelta(days=1)).isoformat()
D_START = (today - timedelta(days=31)).isoformat()
y, t = (today - timedelta(days=1)).isoformat(), today.isoformat()

def dump(n, o):
    json.dump(o, open(os.path.join(OUT, n), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def submit(name, rtype, cols, group, s, e, unit):
    payload = {"name": name, "startDate": s, "endDate": e,
               "configuration": {"adProduct": "SPONSORED_PRODUCTS", "groupBy": group, "columns": cols,
                                 "reportTypeId": rtype, "timeUnit": unit, "format": "GZIP_JSON"}}
    for a in range(6):
        r = requests.post(f"{ADS_BASE_URL}/reporting/reports", headers=headers(get_access_token(), PID), json=payload)
        if r.status_code in (200, 202): return r.json()["reportId"]
        m = re.search(r"duplicate of\s*:\s*([\w-]+)", r.text)
        if m: return m.group(1)
        if r.status_code == 429: time.sleep(65); continue
        raise Exception(f"{name}: {r.status_code} {r.text[:300]}")
    raise Exception(name)

CAMP = ["campaignName", "campaignId", "impressions", "clicks", "cost", "sales7d", "purchases7d"]
ADV = ["campaignName", "adGroupName", "advertisedAsin", "impressions", "clicks", "cost", "purchases14d", "sales14d"]
status = {"window_today": t, "daily_range": [D_START, D_END]}
ids = {}
ids["camp_daily"] = submit("SP camp daily", "spCampaigns", CAMP + ["date"], ["campaign"], D_START, D_END, "DAILY"); time.sleep(65)
ids["camp_two_days"] = submit("SP camp y..t", "spCampaigns", CAMP, ["campaign"], y, t, "SUMMARY"); time.sleep(65)
ids["camp_one_day"] = submit("SP camp y..y", "spCampaigns", CAMP, ["campaign"], y, y, "SUMMARY"); time.sleep(65)
ids["adv_daily"] = submit("SP adv daily", "spAdvertisedProduct", ADV + ["date"], ["advertiser"], D_START, D_END, "DAILY")
status["ids"] = ids; dump("STATUS.json", status)
tot = lambda rows, k: round(sum(float(r.get(k) or 0) for r in rows), 2)
for name, rid in ids.items():
    try:
        rows = wait_and_download(get_access_token(), PID, rid, max_wait=5400, token_fn=get_access_token)
        dump(f"{name}.json", rows)
        status[name] = {"rows": len(rows), "cost": tot(rows, "cost"),
                        "sales": tot(rows, "sales7d") if "adv" not in name else tot(rows, "sales14d")}
        if "daily" in name:
            by = {}
            for r in rows:
                d = r["date"]; by.setdefault(d, [0.0, 0.0, 0, 0])
                by[d][0] += float(r.get("cost") or 0)
                by[d][1] += float(r.get("sales7d") or r.get("sales14d") or 0)
                by[d][2] += int(r.get("clicks") or 0); by[d][3] += int(r.get("impressions") or 0)
            status[name]["by_date"] = {d: [round(v[0], 2), round(v[1], 2), v[2], v[3]] for d, v in sorted(by.items())}
    except Exception as e:
        status[name] = {"error": str(e)[:300]}
    dump("STATUS.json", status)
print(json.dumps(status, ensure_ascii=False, indent=1)[:3000])
