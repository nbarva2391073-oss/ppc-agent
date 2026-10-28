# Read-only: (1) схема і обсяг Top Search Terms (report 652423020754) + рядки з "pheromone";
# (2) що означає період "2026-26" у BA_SearchCatalog_USA: тижневий Search Catalog 21–27.06.2026 і порівняння з рядками аркуша.
import json, os, time, gzip, requests
from brand_analytics import get_access_token, SP_API_BASE
from config import MARKETPLACE_IDS
_g, _p = requests.get, requests.post
requests.get = lambda *a, **k: _g(*a, timeout=k.pop('timeout', 90), **k)
requests.post = lambda *a, **k: _p(*a, timeout=k.pop('timeout', 90), **k)
OUT = "diag/ba_diag3"; os.makedirs(OUT, exist_ok=True); res = {}
def dump(): json.dump(res, open(f"{OUT}/RESULT.json", "w"), ensure_ascii=False, indent=1)
tok = get_access_token("USA"); H = lambda: {"x-amz-access-token": tok, "Content-Type": "application/json"}
def get(url, **kw):
    for i in range(10):
        r = requests.get(url, headers=H(), **kw)
        if r.status_code == 429: time.sleep(30 + 15 * i); continue
        return r
    return r
def doc(doc_id):
    d = get(f"{SP_API_BASE}/reports/2021-06-30/documents/{doc_id}").json()
    f = requests.get(d["url"]); txt = gzip.decompress(f.content).decode() if d.get("compressionAlgorithm") == "GZIP" else f.text
    return len(txt), json.loads(txt)
weeks = [("2026-06-07","2026-06-13"),("2026-06-14","2026-06-20"),("2026-06-28","2026-07-04")]
res["weeks"] = {}
for ws_, we_ in weeks:
    r = requests.post(f"{SP_API_BASE}/reports/2021-06-30/reports", headers=H(), json={
        "reportType": "GET_BRAND_ANALYTICS_SEARCH_CATALOG_PERFORMANCE_REPORT", "dataStartTime": ws_+"T00:00:00Z",
        "dataEndTime": we_+"T23:59:59Z", "reportOptions": {"reportPeriod": "WEEK", "asins": "B0G5QB4W6N B09NBB4QP7 B07TJW4Y94"},
        "marketplaceIds": [MARKETPLACE_IDS["USA"]]})
    res["weeks"][ws_] = {"http": r.status_code, "id": (r.json().get("reportId") if r.status_code == 202 else r.text[:200])}; dump(); time.sleep(8)
for ws_, v in res["weeks"].items():
    if not str(v["id"]).isdigit(): continue
    for _ in range(45):
        time.sleep(20); st = get(f"{SP_API_BASE}/reports/2021-06-30/reports/{v['id']}").json()
        if st.get("processingStatus") in ("DONE", "FATAL", "CANCELLED"): break
    v["status"] = st.get("processingStatus")
    if st.get("reportDocumentId"):
        _, j = doc(st["reportDocumentId"]); recs = j.get("dataByAsin") or []
        v["rows"] = [[r.get("asin"), (r.get("impressionData") or {}).get("impressionCount"), (r.get("clickData") or {}).get("clickCount")] for r in recs]
    dump()
res["sheet_2026_26_expected"] = {"B0G5QB4W6N": [6878, 37], "B09NBB4QP7": [1688, 16], "B07TJW4Y94": [1652, 2]}
dump(); print("ok")
