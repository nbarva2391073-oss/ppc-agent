# ============================================================
# РЕМОНТ тижневих вкладок Campaign Analysis USA і Placement Analysis USA.
# Причина: історичні тижні записувались з хибних вікон (2 дні / накопичення append):
#   Campaign Analysis 14.09 і 21.09 мали лише частину тижня, Placement мав ~2× витрат.
# Рішення: для кожного тижня (пн–нд, а поточний — до вчора) беремо ПЕРВИННІ звіти
# Amazon (SUMMARY за тиждень, spCampaigns: campaign і campaignPlacement) і замінюємо
# рядки цього тижня (upsert за Week). Перед записом: звірка суми cost з Amazon.
# Статуси/Issue Placement не вигадуємо: переносимо існуючі за (Week, Campaign),
# інакше "✅". Ставки, бюджети, кампанії не змінюються.
# ============================================================
import json, os, re, time
from datetime import date, timedelta

from config import ADS_PROFILE_ID_USA, MARGIN
from amazon_ads import get_access_token, submit_report, wait_and_download, calculate_metrics
from monitor import COLS_CAMPAIGN, COLS_PLACEMENT
from sheets import get_sheet, write_campaign_analysis

MARKET = "USA"; PID = ADS_PROFILE_ID_USA
OUT = "diag/weekly_repair"; os.makedirs(OUT, exist_ok=True); BK = "backups/weekly_pre_repair"; os.makedirs(BK, exist_ok=True)
FIRST_MONDAY = date(2026, 8, 17)
LAST = date.today() - timedelta(days=1)


def label(s, e): return f"{s.strftime('%d.%m')}-{e.strftime('%d.%m.%Y')}"
def dump(o): json.dump(o, open(f"{OUT}/STATUS.json", "w"), ensure_ascii=False, indent=1)


def submit(kind, rtype, cols, grp, s, e):
    for _ in range(8):
        try:
            return submit_report(get_access_token(), PID, f"{kind} {s}..{e}", rtype, cols, grp, s, e)
        except Exception as ex:
            m = re.search(r"duplicate of\s*:\s*([\w-]+)", str(ex))
            if m: return m.group(1)
            if "429" in str(ex): time.sleep(65); continue
            raise
    raise RuntimeError("submit")


def main():
    import csv
    for n in ("Campaign Analysis USA", "Placement Analysis USA"):
        v = get_sheet(n).get_all_values()
        csv.writer(open(f"{BK}/{n.replace(' ', '_')}.csv", "w", newline="", encoding="utf-8")).writerows(v)
        time.sleep(3)
    weeks = []
    m = FIRST_MONDAY
    while m <= LAST:
        weeks.append((m, min(m + timedelta(days=6), LAST))); m += timedelta(days=7)
    status = {"weeks": [], "last": LAST.isoformat()}
    jobs = []
    for s, e in weeks:
        c = submit("camp", "spCampaigns", COLS_CAMPAIGN, ["campaign"], s.isoformat(), e.isoformat()); time.sleep(65)
        p = submit("plc", "spCampaigns", COLS_PLACEMENT, ["campaignPlacement"], s.isoformat(), e.isoformat()); time.sleep(65)
        jobs.append((s, e, c, p)); status["submitted"] = [(label(a, b), c_, p_) for a, b, c_, p_ in jobs]; dump(status)

    pending = []
    for s, e, c, p in jobs:
        camp = wait_and_download(get_access_token(), PID, c, max_wait=5400, token_fn=get_access_token)
        plc = wait_and_download(get_access_token(), PID, p, max_wait=5400, token_fn=get_access_token)
        cost = lambda rows: round(sum(float(r.get("cost") or 0) for r in rows), 2)
        rec = {"week": label(s, e), "campaign_rows": len(camp), "placement_rows": len(plc),
               "camp_cost": cost(camp), "plc_cost": cost(plc),
               "match": abs(cost(camp) - cost(plc)) < 0.05, "written": False}
        status["weeks"].append(rec); dump(status)
        pending.append((s, e, camp, plc, rec))

    # Існуючі статуси Placement → переносимо
    plsh = get_sheet("Placement Analysis USA"); ex = plsh.get_all_values()
    hdr = ex[0]; iw, ic, ip = hdr.index("Week"), hdr.index("Campaign"), hdr.index("Placement")
    ist, iis = hdr.index("Status"), hdr.index("Issue")
    keep_status = {}
    for r in ex[1:]:
        if len(r) > iis and r[ist]: keep_status[(r[iw], r[ic])] = (r[ist], r[iis])

    for s, e, camp, plc, rec in pending:
        if not rec["match"] or not camp:
            continue
        lab = label(s, e)
        write_campaign_analysis(calculate_metrics(camp, MARGIN.get(MARKET, 0.25)), lab, MARKET)
        rec["written"] = True; dump(status); time.sleep(5)

    # Placement — один запис: прибираємо всі рядки ремонтованих тижнів і дописуємо нові
    labels = {label(s, e) for s, e, camp, plc, rec in pending if rec["match"] and plc}
    ex = plsh.get_all_values()
    kept = [r for r in ex if r and (r[0] == "Week" or r[0] not in labels)]
    new = []
    for s, e, camp, plc, rec in pending:
        lab = label(s, e)
        if lab not in labels: continue
        for r in plc:
            camp_n = r.get("campaignName", ""); sp = round(float(r.get("cost") or 0), 2); sl = round(float(r.get("sales7d") or 0), 2)
            st, iss = keep_status.get((lab, camp_n), ("✅", ""))
            ctr = round(float(r.get("clicks") or 0) / float(r["impressions"]) * 100, 2) if float(r.get("impressions") or 0) else 0
            new.append([lab, camp_n, r.get("placementClassification") or r.get("placement") or r.get("campaignPlacement") or "missing",
                        r.get("impressions", 0), r.get("clicks", 0), ctr, sp, sl, round(sp / sl * 100 if sl > 0 else 0, 1), st, iss])
    plsh.clear(); plsh.update(kept + new, "A1")
    status["placement_written_rows"] = len(new); status["placement_weeks"] = sorted(labels); dump(status)
    print("done")


if __name__ == "__main__":
    main()
