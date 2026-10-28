# Read-only: (1) схема і обсяг Top Search Terms (report 652423020754) + рядки з "pheromone";
# (2) що означає період "2026-26" у BA_SearchCatalog_USA: тижневий Search Catalog 21–27.06.2026 і порівняння з рядками аркуша.
import json, os, time, gzip, requests
from brand_analytics import get_access_token, SP_API_BASE
from config import MARKETPLACE_IDS
_g, _p = requests.get, requests.post
requests.get = lambda *a, **k: _g(*a, timeout=k.pop('timeout', 90), **k)
requests.post = lambda *a, **k: _p(*a, timeout=k.pop('timeout', 90), **k)
OUT = "diag/ba_diag2"; os.makedirs(OUT, exist_ok=True); res = {}
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
# (2) запит тижневого каталогу
cat = requests.post(f"{SP_API_BASE}/reports/2021-06-30/reports", headers=H(), json={
    "reportType": "GET_BRAND_ANALYTICS_SEARCH_CATALOG_PERFORMANCE_REPORT", "dataStartTime": "2026-06-21T00:00:00Z",
    "dataEndTime": "2026-06-27T23:59:59Z", "reportOptions": {"reportPeriod": "WEEK", "asins": "B0G5QB4W6N B09NBB4QP7 B07TJW4Y94"},
    "marketplaceIds": [MARKETPLACE_IDS["USA"]]})
res["catalog_probe_request"] = {"http": cat.status_code, "body": cat.text[:300]}; dump()
# (1) Search Terms: потоково, без повного завантаження в пам'ять
import zlib, re
try:
    d = get(f"{SP_API_BASE}/reports/2021-06-30/documents/" + get(f"{SP_API_BASE}/reports/2021-06-30/reports/652423020754").json()["reportDocumentId"]).json()
    r = requests.get(d["url"], stream=True)
    total_c = int(r.headers.get("Content-Length") or 0)
    dec = zlib.decompressobj(31) if d.get("compressionAlgorithm") == "GZIP" else None
    head, tail, got, hits, nbytes, t0 = "", "", 0, [], 0, time.time()
    for chunk in r.iter_content(1 << 20):
        got += len(chunk); txt = (dec.decompress(chunk) if dec else chunk).decode("utf-8", "ignore"); nbytes += len(txt)
        if len(head) < 3000: head += txt[: 3000 - len(head)]
        buf = tail + txt
        for m in re.finditer(r'"searchTerm"\s*:\s*"(pheromones?)"', buf, re.I):
            hits.append(buf[max(0, m.start() - 200): m.end() + 400])
        tail = buf[-600:]
        if time.time() - t0 > 480 or nbytes > 1_500_000_000: break
    res["search_terms"] = {"compressed_bytes": total_c, "decompressed_scanned": nbytes, "head": head, "exact_hits": len(hits), "hit_examples": hits[:3], "stopped_early": time.time() - t0 > 480}
except Exception as e:
    res["search_terms"] = {"error": str(e)[:300]}
dump()
# дочекатись тижневого каталогу і порівняти
try:
    rid = cat.json()["reportId"]
    for _ in range(40):
        time.sleep(20); st = get(f"{SP_API_BASE}/reports/2021-06-30/reports/{rid}").json()
        if st.get("processingStatus") in ("DONE", "FATAL", "CANCELLED"): break
    res["catalog_probe_status"] = st.get("processingStatus")
    if st.get("reportDocumentId"):
        _, j = doc(st["reportDocumentId"]); recs = j.get("dataByAsin") or j.get("data") or j
        res["catalog_probe_rows"] = [{"asin": r.get("asin"), "start": r.get("startDate"), "end": r.get("endDate"),
                                      "impr": (r.get("impressionData") or {}).get("impressionCount"),
                                      "clicks": (r.get("clickData") or {}).get("clickCount")} for r in recs]
        res["sheet_2026_26_expected"] = {"B0G5QB4W6N": [6878, 37], "B09NBB4QP7": [1688, 16], "B07TJW4Y94": [1652, 2]}
except Exception as e:
    res["catalog_probe_error"] = str(e)[:300]
dump(); print("ok")
