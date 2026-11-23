# Діагностика ролей SP-API токена (лише читання): які ендпоінти відповідають 200, а які 403.
import json, os, requests
from config import MARKETPLACE_IDS
from business_report import get_access_token, SP_API_BASE
M = os.getenv("MARKET", "USA"); mp = MARKETPLACE_IDS[M]
res = {}
os.makedirs("diag/signals", exist_ok=True)
def _save(): json.dump(res, open("diag/signals/sp_roles_diag.json", "w"), ensure_ascii=False, indent=1)
try:
    t = get_access_token(M)
except Exception as e:
    res["TOKEN_ERROR"] = repr(e)[:400]; _save(); print(res); raise SystemExit(0)
h = {"x-amz-access-token": t}
for _m in ("CA",):
    try: get_access_token(_m); res["token CA"] = "ok"
    except Exception as e: res["token CA"] = repr(e)[:300]
tests = {
 "sellers/marketplaceParticipations": ("/sellers/v1/marketplaceParticipations", {}),
 "catalog/2022 (salesRanks)": ("/catalog/2022-04-01/items/B0GYSB85SH", {"marketplaceIds": mp, "includedData": "salesRanks"}),
 "catalog/2022 (summaries)": ("/catalog/2022-04-01/items/B0GYSB85SH", {"marketplaceIds": mp, "includedData": "summaries"}),
 "fba/inventory summaries": ("/fba/inventory/v1/summaries", {"granularityType": "Marketplace", "granularityId": mp, "marketplaceIds": mp, "details": "true"}),
 "reports (list)": ("/reports/2021-06-30/reports", {"reportTypes": "GET_SALES_AND_TRAFFIC_REPORT", "pageSize": 1}),
 "pricing v0 competitivePrice (SalesRankings)": ("/products/pricing/v0/competitivePrice", {"MarketplaceId": mp, "Asins": "B0GYSB85SH", "ItemType": "Asin"}),
 "pricing v0 price": ("/products/pricing/v0/price", {"MarketplaceId": mp, "Asins": "B0GYSB85SH", "ItemType": "Asin"}),
 "catalog v0 item": ("/catalog/v0/items/B0GYSB85SH", {"MarketplaceId": mp}),
 "orders v0": ("/orders/v0/orders", {"MarketplaceIds": mp, "CreatedAfter": "2026-11-20T00:00:00Z", "MaxResultsPerPage": 1}),
}
for k, (p, q) in tests.items():
    try:
        r = requests.get(SP_API_BASE + p, params=q, headers=h, timeout=60)
        res[k] = f"{r.status_code} {r.text[:160].replace(chr(10), ' ')}"
    except Exception as e:
        res[k] = repr(e)[:200]
    print(k, "->", res[k])
for rt in ("GET_AFN_INVENTORY_DATA", "GET_FBA_MYI_UNSUPPRESSED_INVENTORY_DATA", "GET_FBA_INVENTORY_PLANNING_DATA"):
    try:
        r = requests.post(SP_API_BASE + "/reports/2021-06-30/reports", json={"reportType": rt, "marketplaceIds": [mp]}, headers=h, timeout=60)
        res["createReport " + rt] = f"{r.status_code} {r.text[:140].replace(chr(10), ' ')}"
    except Exception as e:
        res["createReport " + rt] = repr(e)[:200]
_save()
