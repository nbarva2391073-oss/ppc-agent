# ============================================================
# Щоденний залишок FBA по кожному SKU (SP-API FBA Inventory v1 summaries).
# Вкладка "FBA Inventory <M>": Date, SKU, ASIN, FNSKU, Product, Sellable, Inbound (working/shipped/receiving/total),
# Reserved, Unfulfillable, Researching, Total. Рядки за сьогоднішню дату замінюються; історія лишається.
# Env: MARKET=USA, DRY_RUN=1
# ============================================================
import json, os, time
from datetime import datetime
import requests
from config import MARKETPLACE_IDS
from business_report import get_access_token, SP_API_BASE
from sheet_util import replace_dates

MARKET = os.getenv("MARKET", "USA")
DRY = os.getenv("DRY_RUN", "") in ("1", "true", "True")
TAB = f"FBA Inventory {MARKET}"
HDR = ["Date", "SKU", "ASIN", "FNSKU", "Product", "Sellable", "InboundWorking", "InboundShipped", "InboundReceiving",
       "InboundTotal", "Reserved", "Unfulfillable", "Researching", "Total"]
OUT = "diag/signals" + ("" if MARKET == "USA" else f"_{MARKET}"); os.makedirs(OUT, exist_ok=True)


def fetch():
    token = get_access_token(MARKET); mp = MARKETPLACE_IDS[MARKET]
    items, nt = [], None
    while True:
        p = {"granularityType": "Marketplace", "granularityId": mp, "marketplaceIds": mp, "details": "true"}
        if nt:
            p["nextToken"] = nt
        for att in range(5):
            r = requests.get(f"{SP_API_BASE}/fba/inventory/v1/summaries", params=p,
                             headers={"x-amz-access-token": token}, timeout=60)
            if r.status_code in (429, 500, 503):
                time.sleep(10 * (att + 1)); continue
            break
        if r.status_code != 200:
            raise Exception(f"FBA Inventory {r.status_code}: {r.text[:300]}")
        j = r.json()
        items += (j.get("payload") or {}).get("inventorySummaries", [])
        nt = (j.get("pagination") or {}).get("nextToken")
        if not nt:
            return items


def main():
    items = fetch()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows = []
    for s in items:
        d = s.get("inventoryDetails") or {}
        w, sh, rc = (d.get("inboundWorkingQuantity") or 0), (d.get("inboundShippedQuantity") or 0), (d.get("inboundReceivingQuantity") or 0)
        rows.append([today, s.get("sellerSku", ""), s.get("asin", ""), s.get("fnSku", ""), s.get("productName", ""),
                     d.get("fulfillableQuantity", 0), w, sh, rc, w + sh + rc,
                     (d.get("reservedQuantity") or {}).get("totalReservedQuantity", 0),
                     (d.get("unfulfillableQuantity") or {}).get("totalUnfulfillableQuantity", 0),
                     d.get("researchingQuantity", 0) if not isinstance(d.get("researchingQuantity"), dict)
                     else d["researchingQuantity"].get("totalResearchingQuantity", 0),
                     s.get("totalQuantity", 0)])
    rows.sort(key=lambda r: (r[2], r[1]))
    print(f"  ℹ️ FBA {MARKET}: {len(rows)} SKU")
    json.dump(rows, open(f"{OUT}/fba_{today}.json", "w"), ensure_ascii=False, indent=1)
    if DRY:
        return
    print("  ✍️", replace_dates(TAB, HDR, rows, 0, [today]))


if __name__ == "__main__":
    main()
