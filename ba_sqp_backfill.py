# Одноразово: запит історичних SQP (USA) для ядра і решти ASIN: місяці липень/серпень + тижні нд–сб з 23.08 по 24.10.
# Записує рядки "очікує" в BA_Pending_Reports; завантаження робить звичайний ba-fetch (python main_brand_analytics.py --fetch).
import time, json, os
from datetime import date, timedelta, datetime
import brand_analytics as ba
from sheets import append
OUT = "diag/ba_backfill"; os.makedirs(OUT, exist_ok=True)
MARKET = os.environ.get("MARKET", "USA")
plan = [("2026-07-01", "2026-07-31", "MONTH"), ("2026-08-01", "2026-08-31", "MONTH")]
d = date(2026, 8, 23)
while d + timedelta(days=6) <= date(2026, 10, 24):
    plan.append((d.isoformat(), (d + timedelta(days=6)).isoformat(), "WEEK")); d += timedelta(days=7)
log = []
tok = ba.get_access_token(MARKET); t0 = time.time(); rows = []
for s, e, per in plan:
    for group, rtype in (("CORE", "SQP" if per == "MONTH" else "SQP_WEEK"), ("OTHER", "SQP_OTHER" if per == "MONTH" else "SQP_WEEK_OTHER")):
        if time.time() - t0 > 45 * 60: tok = ba.get_access_token(MARKET); t0 = time.time()
        ba.SQP_OVERRIDE = (s, e, per)
        rid = None
        for attempt in range(6):
            rid = ba.request_sqp(MARKET, tok, group, per)
            if rid: break
            time.sleep(65)
        log.append({"period": f"{s}..{e}", "per": per, "group": group, "type": rtype, "report_id": rid})
        if rid: rows.append([datetime.utcnow().strftime("%Y-%m-%d %H:%M"), rid, MARKET, "очікує", "", rtype])
        json.dump(log, open(f"{OUT}/RESULT.json", "w"), indent=1); time.sleep(65)
ba.SQP_OVERRIDE = None
if rows:
    append("BA_Pending_Reports", rows, ["Дата запиту", "Report ID", "Ринок", "Статус", "Дата виконання", "Тип звіту"])
print(f"requested {len(rows)} of {len(log)}")
