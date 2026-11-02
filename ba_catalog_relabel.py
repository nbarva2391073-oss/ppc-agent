# Одноразово: рядки з періодом "2026-26" у BA_SearchCatalog_<USA|CA> → дд.мм.рррр-дд.мм.рррр.
# Період визначаємо ЗА ДАНИМИ: тижневий Search Catalog Amazon за 14.06–20.06 і 21.06–27.06 порівнюється з рядками аркуша
# (Impressions, Clicks по ASIN). Перейменовуємо лише якщо ВСІ рядки збіглись з одним тижнем. Рядки не видаляються.
import csv, gzip, json, os, time, requests
from brand_analytics import get_access_token, SP_API_BASE
from config import MARKETPLACE_IDS
from sheets import get_sheet
_g, _p = requests.get, requests.post
requests.get = lambda *a, **k: _g(*a, timeout=k.pop('timeout', 90), **k)
requests.post = lambda *a, **k: _p(*a, timeout=k.pop('timeout', 90), **k)
OUT = "diag/ba_catalog_relabel"; os.makedirs(OUT, exist_ok=True); BK = "backups/ba_pre/catalog"; os.makedirs(BK, exist_ok=True)
CANDIDATES = [("2026-06-14", "2026-06-20"), ("2026-06-21", "2026-06-27"), ("2026-06-07", "2026-06-13")]
res = {}
def dump(): json.dump(res, open(f"{OUT}/RESULT.json", "w"), ensure_ascii=False, indent=1)
def rget(tok, url):
    for i in range(10):
        r = requests.get(url, headers={"x-amz-access-token": tok})
        if r.status_code == 429: time.sleep(30 + 15 * i); continue
        return r
    return r
for market in ("USA", "CA"):
    sheet = f"BA_SearchCatalog_{market}"; sh = get_sheet(sheet); vals = sh.get_all_values()
    csv.writer(open(f"{BK}/{sheet}.csv", "w", newline="", encoding="utf-8")).writerows(vals)
    hdr = vals[0]; ia, ii, ic = hdr.index("ASIN"), hdr.index("Impressions"), hdr.index("Clicks")
    bad = [(n, r) for n, r in enumerate(vals[1:], start=2) if r and r[0].strip() == "2026-26"]
    res[market] = {"rows_2026_26": len(bad)}
    if not bad: dump(); continue
    tok = get_access_token(market); found = {}
    for s, e in CANDIDATES:
        body = {"reportType": "GET_BRAND_ANALYTICS_SEARCH_CATALOG_PERFORMANCE_REPORT", "dataStartTime": s + "T00:00:00Z", "dataEndTime": e + "T23:59:59Z",
                "reportOptions": {"reportPeriod": "WEEK"}, "marketplaceIds": [MARKETPLACE_IDS[market]]}
        if market == "USA": body["reportOptions"]["asins"] = " ".join(sorted({r[ia] for _, r in bad}))
        rid = None
        for a in range(6):
            r = requests.post(f"{SP_API_BASE}/reports/2021-06-30/reports", headers={"x-amz-access-token": tok, "Content-Type": "application/json"}, json=body)
            if r.status_code == 202: rid = r.json()["reportId"]; break
            time.sleep(30)
        if not rid: continue
        for _ in range(60):
            time.sleep(20); st = rget(tok, f"{SP_API_BASE}/reports/2021-06-30/reports/{rid}").json()
            if st.get("processingStatus") in ("DONE", "FATAL", "CANCELLED"): break
        if not st.get("reportDocumentId"): continue
        d = rget(tok, f"{SP_API_BASE}/reports/2021-06-30/documents/{st['reportDocumentId']}").json()
        f = requests.get(d["url"]); txt = gzip.decompress(f.content).decode() if d.get("compressionAlgorithm") == "GZIP" else f.text
        recs = json.loads(txt).get("dataByAsin") or []
        found[(s, e)] = {r["asin"]: (int((r.get("impressionData") or {}).get("impressionCount") or 0), int((r.get("clickData") or {}).get("clickCount") or 0)) for r in recs}
        sheet_map = {r[ia]: (int(float(r[ii] or 0)), int(float(r[ic] or 0))) for _, r in bad}
        match = sum(1 for a, v in sheet_map.items() if found[(s, e)].get(a) == v)
        res[market][f"{s}..{e}"] = {"matched": match, "of": len(sheet_map)}; dump()
        if match == len(sheet_map):
            label = f"{s[8:]}.{s[5:7]}.{s[:4]}-{e[8:]}.{e[5:7]}.{e[:4]}"
            ups = [{"range": f"A{n}", "values": [[label]]} for n, _ in bad]
            sh.batch_update(ups, value_input_option="RAW"); res[market]["relabelled_to"] = label; res[market]["rows_relabelled"] = len(ups); dump(); break
    else:
        pass
    if "relabelled_to" not in res[market]: res[market]["note"] = "жоден тиждень не збігся повністю — НЕ змінено"
dump(); print(json.dumps(res, ensure_ascii=False))
