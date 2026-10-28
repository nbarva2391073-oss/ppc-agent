# Read-only діагностика Brand Analytics (SP-API). Нічого не пише в Sheets, нічого не змінює в Amazon
# (probe-запити лише створюють звіти для читання). Результат: diag/ba_diag/RESULT.json
import json, os, sys, time, gzip, requests, collections
_g, _p = requests.get, requests.post
requests.get = lambda *a, **k: _g(*a, timeout=k.pop('timeout', 60), **k)
requests.post = lambda *a, **k: _p(*a, timeout=k.pop('timeout', 60), **k)
T0 = time.time()
def log(*a): print(f'[{int(time.time()-T0)}s]', *a, flush=True)
from datetime import datetime, timedelta
from brand_analytics import get_access_token, SP_API_BASE
from config import MARKETPLACE_IDS
OUT = "diag/ba_diag"; os.makedirs(OUT, exist_ok=True)
res = {"reports": {}, "sqp_docs": {}, "probes": {}}
def dump(): json.dump(res, open(f"{OUT}/RESULT.json", "w"), ensure_ascii=False, indent=1)
KNOWN = ["GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT", "GET_BRAND_ANALYTICS_SEARCH_CATALOG_PERFORMANCE_REPORT",
         "GET_BRAND_ANALYTICS_REPEAT_PURCHASE_REPORT", "GET_BRAND_ANALYTICS_MARKET_BASKET_REPORT",
         "GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT"]
def H(tok): return {"x-amz-access-token": tok, "Content-Type": "application/json"}
def doc_records(tok, doc_id):
    d = requests.get(f"{SP_API_BASE}/reports/2021-06-30/documents/{doc_id}", headers=H(tok)); d.raise_for_status(); d = d.json()
    f = requests.get(d["url"]); f.raise_for_status()
    txt = gzip.decompress(f.content).decode() if d.get("compressionAlgorithm") == "GZIP" else f.text
    j = json.loads(txt)
    return j, (j if isinstance(j, list) else (j.get("dataByAsin") or j.get("data") or j.get("dataByDepartmentAndSearchTerm") or []))
for market in ("USA", "CA"):
    tok = get_access_token(market); res["reports"][market] = {}
    for rt in KNOWN:
        log(market, 'list', rt)
        items, nxt = [], None
        since = (datetime.utcnow() - timedelta(days=89)).strftime("%Y-%m-%dT00:00:00Z")
        for _ in range(12):
            params = {"reportTypes": rt, "pageSize": 100, "createdSince": since} if not nxt else {"nextToken": nxt}
            r = requests.get(f"{SP_API_BASE}/reports/2021-06-30/reports", headers=H(tok), params=params)
            log('  http', r.status_code)
            if r.status_code == 429: time.sleep(30); continue
            if r.status_code != 200: items.append({"err": r.status_code, "body": r.text[:200]}); break
            j = r.json(); items += j.get("reports", []); nxt = j.get("nextToken")
            if not nxt: break
            time.sleep(2)
        res["reports"][market][rt] = [{k: i.get(k) for k in ("reportId", "createdTime", "dataStartTime", "dataEndTime", "processingStatus", "reportDocumentId", "reportSpecification", "err", "body")} for i in items]
        dump()
    # документи SQP (всі DONE): склад ASIN по періоду
    if market == "USA":
        for it in res["reports"][market][KNOWN[0]]:
            if it.get("processingStatus") == "DONE" and it.get("reportDocumentId"):
                try:
                    j, recs = doc_records(tok, it["reportDocumentId"])
                    by = collections.Counter((r.get("startDate"), r.get("endDate"), r.get("asin")) for r in recs if isinstance(r, dict))
                    res["sqp_docs"][it["reportId"]] = {"spec": it.get("reportSpecification"), "records": len(recs), "by_period_asin": {f"{k[0]}..{k[1]} {k[2]}": v for k, v in by.items()}}
                except Exception as e:
                    res["sqp_docs"][it["reportId"]] = {"error": str(e)[:200]}
                dump(); time.sleep(1)
    # probes: які типи приймає API
    mp = MARKETPLACE_IDS[market]; ws, we = "2026-10-18T00:00:00Z", "2026-10-24T23:59:59Z"
    core = "B0G5QB4W6N B0GYSB85SH B09NBB4QP7 B0G6VRGTPR B081T6QGD9 B0GYSJC1PM B07TJW4Y94 B07PTQKZ82 B07ZTJM5WJ B0GCBCW8RK"
    probes = {
      "SEARCH_TERMS_WEEK": ("GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT", {"reportPeriod": "WEEK"}, ws, we),
      "SQP_WEEK_10ASIN": ("GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT", {"reportPeriod": "WEEK", "asin": core}, ws, we),
      "DEMOGRAPHICS": ("GET_BRAND_ANALYTICS_DEMOGRAPHICS_REPORT", {"reportPeriod": "MONTH"}, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z"),
      "CUSTOMER_LOYALTY": ("GET_BRAND_ANALYTICS_CUSTOMER_LOYALTY_REPORT", {"reportPeriod": "MONTH"}, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z"),
      "CUSTOMER_JOURNEY": ("GET_BRAND_ANALYTICS_CUSTOMER_JOURNEY_REPORT", {"reportPeriod": "MONTH"}, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z"),
      "SQP_BRAND_VIEW": ("GET_BRAND_ANALYTICS_SQP_BRAND_VIEW_REPORT", {"reportPeriod": "MONTH"}, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z"),
      "SEARCH_FUNNEL_OUTLIERS": ("GET_BRAND_ANALYTICS_SEARCH_FUNNEL_OUTLIERS_REPORT", {"reportPeriod": "MONTH"}, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z"),
      "AMAZONS_CHOICE": ("GET_BRAND_ANALYTICS_AMAZONS_CHOICE_BADGE_REPORT", {"reportPeriod": "MONTH"}, "2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z"),
    }
    if market == "USA":
        res["probes"][market] = {}
        for name, (rt, opts, s, e) in probes.items():
            r = requests.post(f"{SP_API_BASE}/reports/2021-06-30/reports", headers=H(tok),
                              json={"reportType": rt, "dataStartTime": s, "dataEndTime": e, "reportOptions": opts, "marketplaceIds": [mp]})
            res["probes"][market][name] = {"type": rt, "http": r.status_code, "body": r.text[:300]}
            dump(); time.sleep(4)
        # Search Terms: дочекатись і подивитись схему
        sid = (res["probes"][market]["SEARCH_TERMS_WEEK"].get("body") or "")
        try: sid = json.loads(sid).get("reportId")
        except Exception: sid = None
        if sid:
            for _ in range(60):
                time.sleep(20)
                st = requests.get(f"{SP_API_BASE}/reports/2021-06-30/reports/{sid}", headers=H(tok)).json()
                if st.get("processingStatus") in ("DONE", "FATAL", "CANCELLED"): break
            res["probes"][market]["SEARCH_TERMS_WEEK"]["final"] = st.get("processingStatus")
            if st.get("reportDocumentId"):
                try:
                    j, recs = doc_records(tok, st["reportDocumentId"])
                    res["probes"][market]["SEARCH_TERMS_WEEK"]["records"] = len(recs)
                    res["probes"][market]["SEARCH_TERMS_WEEK"]["top_keys"] = list(j.keys()) if isinstance(j, dict) else "list"
                    res["probes"][market]["SEARCH_TERMS_WEEK"]["sample"] = recs[:2]
                    res["probes"][market]["SEARCH_TERMS_WEEK"]["pheromone_rows"] = sum(1 for r in recs if "pheromone" in json.dumps(r).lower())
                except Exception as e:
                    res["probes"][market]["SEARCH_TERMS_WEEK"]["doc_err"] = str(e)[:200]
            dump()
dump(); print("done")
