# ============================================================
# Щоденна історія BSR (SP-API Catalog Items 2022-04-01, includedData=salesRanks).
# Вкладка "BSR History USA": Дата | ASIN | Категорія | Ранг | Час знімка UTC.
# Лише додаємо рядки; ключ Дата+ASIN+Категорія (існуючі ключі не перезаписуємо).
# Для кожної категорії, яку повертає API: displayGroupRanks (головна, напр. Beauty & Personal Care)
# і classificationRanks (підкатегорії). Env: MARKET=USA, DRY_RUN=1
# ============================================================
import json, os, time
from datetime import datetime
import requests
from config import MARKETPLACE_IDS
from business_report import get_access_token, SP_API_BASE
from sheet_util import ensure_tab, retry

MARKET = os.getenv("MARKET", "USA")
DRY = os.getenv("DRY_RUN", "") in ("1", "true", "True")
TAB = f"BSR History {MARKET}"
HDR = ["Дата", "ASIN", "Категорія", "Ранг", "Час знімка UTC"]
CORE = ["B0G5QB4W6N", "B0GYSB85SH", "B081T6QGD9", "B07TJW4Y94", "B09NBB4QP7",
        "B0G6VRGTPR", "B0GYSJC1PM", "B0GCBCW8RK", "B07PTQKZ82", "B07ZTJM5WJ"]
OUT = "diag/bsr"; os.makedirs(OUT, exist_ok=True)


def get_ranks(token, asin):
    mp = MARKETPLACE_IDS[MARKET]
    for att in range(6):
        r = requests.get(f"{SP_API_BASE}/catalog/2022-04-01/items/{asin}",
                         params={"marketplaceIds": mp, "includedData": "salesRanks"},
                         headers={"x-amz-access-token": token}, timeout=60)
        if r.status_code in (429, 500, 503):
            time.sleep(5 * (att + 1)); continue
        break
    if r.status_code != 200:
        return None, f"{r.status_code} {r.text[:200]}"
    out, seen = [], set()
    for blk in r.json().get("salesRanks", []):
        if blk.get("marketplaceId") not in (None, mp):
            continue
        for x in blk.get("displayGroupRanks", []) or []:
            t = x.get("title") or x.get("websiteDisplayGroup")
            if t and t not in seen and x.get("rank") is not None:
                seen.add(t); out.append((t, x["rank"]))
        for x in blk.get("classificationRanks", []) or []:
            t = x.get("title") or x.get("classificationId")
            if t and t not in seen and x.get("rank") is not None:
                seen.add(t); out.append((t, x["rank"]))
    return out, None


def main():
    now = datetime.utcnow(); today = now.strftime("%Y-%m-%d"); ts = now.strftime("%Y-%m-%d %H:%M:%S")
    token = get_access_token(MARKET)
    rows, errors = [], {}
    for asin in CORE:
        ranks, err = get_ranks(token, asin)
        if err:
            errors[asin] = err; print(f"  ❌ {asin}: {err}")
        else:
            print(f"  ✅ {asin}: {ranks}")
            rows += [[today, asin, cat, rk, ts] for cat, rk in ranks]
        time.sleep(1.0)
    json.dump({"date": today, "rows": rows, "errors": errors}, open(f"{OUT}/bsr_{today}.json", "w"),
              ensure_ascii=False, indent=1)
    if DRY:
        print(f"DRY: {len(rows)} рядків"); return
    ws = ensure_tab(TAB, HDR)
    vals = retry(ws.get_all_values)
    have = {(r[0], r[1], r[2]) for r in vals[1:] if len(r) > 2}
    new = [r for r in rows if (r[0], r[1], r[2]) not in have]
    if new:
        need = len(vals) + len(new) + 5
        if need > ws.row_count:
            retry(ws.resize, rows=need)
        retry(ws.append_rows, new, value_input_option="RAW", table_range="A1")
    print(f"✍️ {TAB}: додано {len(new)}, вже було {len(rows) - len(new)}, помилок ASIN: {len(errors)}")
    if errors and len(errors) == len(CORE):
        raise SystemExit("Усі ASIN повернули помилку")


if __name__ == "__main__":
    main()
