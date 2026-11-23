# Діагностика ролей SP-API токена (лише читання): які ендпоінти відповідають 200, а які 403.
import json, os, requests
from config import MARKETPLACE_IDS
from business_report import get_access_token, SP_API_BASE
M = os.getenv("MARKET", "USA"); mp = MARKETPLACE_IDS[M]
t = get_access_token(M); h = {"x-amz-access-token": t}
tests = {
 "sellers/marketplaceParticipations": ("/sellers/v1/marketplaceParticipations", {}),
 "catalog/2022 (salesRanks)": ("/catalog/2022-04-01/items/B0GYSB85SH", {"marketplaceIds": mp, "includedData": "salesRanks"}),
 "catalog/2022 (summaries)": ("/catalog/2022-04-01/items/B0GYSB85SH", {"marketplaceIds": mp, "includedData": "summaries"}),
 "fba/inventory summaries": ("/fba/inventory/v1/summaries", {"granularityType": "Marketplace", "granularityId": mp, "marketplaceIds": mp, "details": "true"}),
 "reports (list)": ("/reports/2021-06-30/reports", {"reportTypes": "GET_SALES_AND_TRAFFIC_REPORT", "pageSize": 1}),
 "orders v0": ("/orders/v0/orders", {"MarketplaceIds": mp, "CreatedAfter": "2026-11-20T00:00:00Z", "MaxResultsPerPage": 1}),
}
res = {}
for k, (p, q) in tests.items():
    r = requests.get(SP_API_BASE + p, params=q, headers=h, timeout=60)
    res[k] = f"{r.status_code} {r.text[:160].replace(chr(10), ' ')}"
    print(k, "->", res[k])
os.makedirs("diag/signals", exist_ok=True)
json.dump(res, open("diag/signals/sp_roles_diag.json", "w"), ensure_ascii=False, indent=1)
