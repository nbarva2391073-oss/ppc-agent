# ============================================================
# РЕМОНТ денних SP-даних USA (одноразово).
# Причина: monitor.py брав вікно start=вчора,end=сьогодні (endDate включний →
# 2 дні, з неповним «сьогодні») під міткою «вчора». Це завищувало
# Raw Data / Advertised Product / Keyword Intelligence (daily) / TACoS.
# Рішення: перезавантажити DAILY-звіти Amazon (timeUnit=DAILY) і замінити
# рядки за дату (upsert) — вихідні звіти є джерелом правди.
# Межі: Raw Data і KI (daily) — з 2026-09-30 (з цієї дати мітки тижнів
# коректні; старіші мітки не чіпаємо). Advertised Product — з першої дати
# в аркуші. TACoS перераховується для тих самих дат.
# Кампанії, ставки, бюджети не змінюються.
# ============================================================
import json, os, re, sys, time
from datetime import date, timedelta

from config import ADS_PROFILE_ID_USA
from amazon_ads import get_access_token, submit_report, wait_and_download
from sheets import (get_sheet, write_raw_data, write_advertised_product,
                    write_keyword_intelligence, calculate_tacos)
from monitor import (COLS_SEARCH_TERM, COLS_TARGETING, COLS_ADVERTISED_PRODUCT,
                     _split_by_date, _week_label_for, _build_keyword_rows)

MARKET = os.environ.get("MARKET", "USA")
SFX = "" if MARKET == "USA" else "_" + MARKET
PID = __import__("config").ADS_PROFILE_ID_CA if MARKET == "CA" else __import__("config").ADS_PROFILE_ID_USA
LAST = (date.today() - timedelta(days=1)).isoformat()      # останній повний день
RAW_KI_FROM = "2026-09-30"
OUT = "diag/sp_repair" + SFX; os.makedirs(OUT, exist_ok=True)


def dump(n, o):
    json.dump(o, open(os.path.join(OUT, n), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def adv_first_date():
    rows = get_sheet(f"Advertised Product {MARKET}").get_all_values()
    ds = sorted({r[0] for r in rows[1:] if r and r[0][:2] == "20"})
    return max(ds[0], (date.today() - timedelta(days=58)).isoformat())


def chunks(a, b, n=31):
    s, e = date.fromisoformat(a), date.fromisoformat(b)
    while s <= e:
        ce = min(s + timedelta(days=n - 1), e)
        yield s.isoformat(), ce.isoformat()
        s = ce + timedelta(days=1)


def main():
    status = {"last": LAST, "steps": []}
    adv_from = adv_first_date()
    status["adv_from"] = adv_from
    token = get_access_token()
    jobs = []   # (kind, from, to, report_id)
    plan = [("search_term", "spSearchTerm", COLS_SEARCH_TERM, ["searchTerm"], RAW_KI_FROM, LAST),
            ("targeting", "spTargeting", COLS_TARGETING, ["targeting"], RAW_KI_FROM, LAST),
            ("advertised", "spAdvertisedProduct", COLS_ADVERTISED_PRODUCT, ["advertiser"], adv_from, LAST)]
    if os.environ.get("ONLY_RAW_KI") == "1":      # Advertised/TACoS вже перевірені → тільки Raw Data і KI
        plan = plan[:2]
    for kind, rtype, cols, grp, a, b in plan:
        for cs, ce in chunks(a, b):
            for attempt in range(6):
                try:
                    rid = submit_report(get_access_token(), PID, f"{kind} {cs}..{ce}", rtype,
                                        cols + ["date"], grp, cs, ce, time_unit="DAILY")
                    break
                except Exception as e:
                    m = re.search(r"duplicate of\s*:\s*([\w-]+)", str(e))
                    if m:
                        rid = m.group(1); break
                    if "429" in str(e): time.sleep(65); continue
                    raise
            jobs.append({"kind": kind, "from": cs, "to": ce, "id": rid})
            status["steps"].append({"submitted": jobs[-1]}); dump("STATUS.json", status)
            time.sleep(65)

    data = {"search_term": [], "targeting": [], "advertised": []}
    for j in jobs:
        rows = wait_and_download(get_access_token(), PID, j["id"], max_wait=5400, token_fn=get_access_token)
        data[j["kind"]] += rows
        status["steps"].append({"downloaded": {**j, "rows": len(rows)}}); dump("STATUS.json", status)

    # Звірка джерела: денні витрати Advertised Product ↔ Search Term (мають збігатись із campaign daily з diag/sp_audit)
    def per_date(rows):
        d = {}
        for r in rows: d[r["date"]] = round(d.get(r["date"], 0) + float(r.get("cost") or 0), 2)
        return d
    adv_d, st_d, tg_d = per_date(data["advertised"]), per_date(data["search_term"]), per_date(data["targeting"])
    truth = {}
    try:
        truth = json.load(open(f"diag/sp_audit{SFX}/STATUS.json"))["camp_daily"]["by_date"]
    except Exception:
        pass
    check = {d: {"adv": adv_d.get(d), "st": st_d.get(d), "tg": tg_d.get(d),
                 "campaign_daily": (truth.get(d) or [None])[0]} for d in sorted(adv_d)}
    status["source_check"] = check; dump("STATUS.json", status)

    # Запис (upsert за датою). Кожен запис — з повторами (квоти Sheets API) і журналом помилок.
    import traceback
    status["write_errors"] = []

    def safe(label, fn, *a, **kw):
        for attempt in range(1, 7):
            try:
                fn(*a, **kw); status.setdefault("write_ok", []).append(label); return True
            except Exception as e:
                status["write_errors"].append({"op": label, "try": attempt, "err": str(e)[:300],
                                               "tb": traceback.format_exc()[-600:]})
                dump("STATUS.json", status)
                time.sleep(20 * attempt)
        return False

    for d, rows in sorted(_split_by_date(data["advertised"]).items()):
        if os.environ.get("ONLY_RAW_KI") == "1": break
        safe(f"adv {d}", write_advertised_product, rows, d, MARKET); time.sleep(2)
    for d, rows in sorted(_split_by_date(data["search_term"]).items()):
        safe(f"raw {d}", write_raw_data, rows, _week_label_for(date.fromisoformat(d)), MARKET, date=d); time.sleep(2)
    for d, rows in sorted(_split_by_date(data["targeting"]).items()):
        safe(f"ki {d}", write_keyword_intelligence, _build_keyword_rows(rows),
             _week_label_for(date.fromisoformat(d)), MARKET, run_date=d); time.sleep(2)
    status["written"] = True; dump("STATUS.json", status)

    # TACoS для дат, що мають Business Report (останні 2 дні ще можуть бути без BR → порожньо, не нуль)
    for d in ([] if os.environ.get("ONLY_RAW_KI") == "1" else sorted(adv_d)):
        try:
            calculate_tacos(MARKET, d)
        except Exception as e:
            status.setdefault("tacos_errors", {})[d] = str(e)[:200]
    status["tacos_done"] = True; dump("STATUS.json", status)
    print("done")


if __name__ == "__main__":
    main()
