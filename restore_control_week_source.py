# ============================================================
# ОДНОРАЗОВИЙ скрипт: відновлення джерельних (per-day) даних
# Campaign report за контрольний тиждень 21-27.09.2026 USA.
#
# Мета — НЕ перезаписати Campaign Analysis / Weekly Summary, а
# отримати справжні щоденні цифри напряму з Amazon Ads Reporting API
# (джерело), агрегувати їх у правильну суму за тиждень і зберегти
# результат для звірки з Sellerise, ПЕРЕД тим як щось писати назад
# у Sheets. Нічого в Google Sheets не змінюється.
# ============================================================

import csv
import os
import time
from datetime import date, timedelta

from config import ADS_PROFILE_ID_USA
from amazon_ads import get_access_token, get_campaign_report

DAYS = [date(2026, 9, 21) + timedelta(days=i) for i in range(7)]
OUT_DIR = os.path.join("backups", "control_week_2109_2709_usa_source")
os.makedirs(OUT_DIR, exist_ok=True)

token = get_access_token()
profile_id = ADS_PROFILE_ID_USA

all_daily = {}
for i, d in enumerate(DAYS):
    ds = d.isoformat()
    print(f"→ Campaign report за {ds}...")
    if i > 0 and i % 5 == 0:
        token = get_access_token()
    try:
        data = get_campaign_report(token, profile_id, ds, ds)
    except Exception as e:
        print(f"  ❌ Помилка за {ds}: {e}")
        data = []
    all_daily[ds] = data

    csv_path = os.path.join(OUT_DIR, f"campaign_{ds}.csv")
    if data:
        keys = sorted({k for row in data for k in row.keys()})
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(data)
    else:
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("(немає даних)\n")
    print(f"  ✅ {len(data)} рядків")
    time.sleep(5)

# ── Агрегація по кампанії за весь контрольний тиждень ───────────
agg = {}
for ds, rows in all_daily.items():
    for r in rows:
        name = r.get("campaignName", "")
        spend = float(r.get("cost") or 0)
        sales = float(r.get("sales7d") or 0)
        orders = int(r.get("purchases7d") or 0)
        impr = int(r.get("impressions") or 0)
        clicks = int(r.get("clicks") or 0)
        if name not in agg:
            agg[name] = {"spend": 0.0, "sales": 0.0, "orders": 0,
                         "impressions": 0, "clicks": 0, "days": 0}
        agg[name]["spend"]       += spend
        agg[name]["sales"]       += sales
        agg[name]["orders"]      += orders
        agg[name]["impressions"] += impr
        agg[name]["clicks"]      += clicks
        agg[name]["days"]        += 1

summary_path = os.path.join(OUT_DIR, "WEEK_AGGREGATE.md")
lines = [
    "# Реконструйована сума з джерела (Amazon Ads API, по днях): 21.09-27.09.2026 USA",
    "",
    f"Дні: {[d.isoformat() for d in DAYS]}",
    "",
    "| Campaign | Spend | Sales | Orders | Impressions | Clicks | Днів з даними |",
    "|---|---|---|---|---|---|---|",
]
for name, v in sorted(agg.items(), key=lambda kv: -kv[1]["spend"]):
    lines.append(
        f"| {name} | {v['spend']:.2f} | {v['sales']:.2f} | {v['orders']} | "
        f"{v['impressions']} | {v['clicks']} | {v['days']} |"
    )

flame_total_spend = sum(v["spend"] for k, v in agg.items() if "Flame" in k)
flame_total_sales = sum(v["sales"] for k, v in agg.items() if "Flame" in k)
lines.append("")
lines.append(f"**Сума Spend по всіх кампаніях 'Flame*': {flame_total_spend:.2f}**")
lines.append(f"**Сума Sales по всіх кампаніях 'Flame*': {flame_total_sales:.2f}**")
lines.append("(для звірки з Sellerise live: Spend $42,75)")
lines.append("")
lines.append(f"Поточний (баговий) запис у Campaign Analysis USA для "
             f"'Flame new phrase 2' за 21.09-27.09.2026: Spend 10,04")

with open(summary_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print("\n".join(lines))
print(f"\n✅ Джерельні дані збережено у {OUT_DIR}/ (Sheets НЕ змінювались)")
