# ============================================================
# РЕМОНТ Keyword Intelligence USA: тижневі рядки з Spend=0
# Причина: keywords.analyze_keywords читав r["spend"], а Amazon Reporting
# API повертає "cost" → Spend=0, ACoS=0, статус «Норма/Збитково» хибні.
# Скрипт перебирає тижні (пн–нд), тягне ПЕРВИННІ звіти Amazon
# (search term + targeting), перераховує з виправленою логікою,
# записує upsert-ом (ключ Week/Keyword/Match/Campaign/Run Date) і
# складає diag/ki_repair" + SFX + "/RESULT.json зі звіркою сум з Amazon.
# Нічого не видаляє з інших рядків, ставки/кампанії не чіпає.
# ============================================================
import json, os, re, sys, time
from datetime import date, timedelta

from config import ADS_PROFILE_ID_USA, SHEETS_USA
from amazon_ads import get_access_token, submit_report, wait_and_download
from keywords import analyze_keywords
from sheets import read_all, write_keyword_intelligence

MARKET = os.environ.get("MARKET", "USA")
SFX = "" if MARKET == "USA" else "_" + MARKET
ADS_PROFILE_ID_USA = __import__("config").ADS_PROFILE_ID_CA if MARKET == "CA" else ADS_PROFILE_ID_USA
WEEK_STARTS = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"]


def cost(r):
    return float(r.get("cost") or r.get("spend") or 0)


def main():
    out = {"weeks": []}
    pending = []
    os.makedirs("diag/ki_repair" + SFX + "", exist_ok=True)
    history = {"raw_data": read_all(f"Raw Data {MARKET}")}
    ST_COLS = ["campaignName", "adGroupName", "keyword", "matchType", "searchTerm", "impressions",
               "clicks", "cost", "sales7d", "purchases7d", "costPerClick"]
    TG_COLS = ["campaignName", "adGroupName", "matchType", "impressions", "clicks",
               "cost", "sales7d", "purchases7d", "costPerClick"]

    def submit(kind, rtype, cols, grp, s_, e_):
        for _ in range(8):
            try:
                return submit_report(get_access_token(), ADS_PROFILE_ID_USA, f"{kind} {s_}..{e_}",
                                     rtype, cols, grp, s_, e_)
            except Exception as ex:
                m = re.search(r"duplicate of\s*:\s*([\w-]+)", str(ex))
                if m: return m.group(1)
                if "429" in str(ex): time.sleep(65); continue
                raise
        raise RuntimeError("submit failed")

    # 1) Одразу ставимо ВСІ звіти в чергу (Amazon генерує паралельно) — послідовно було б >2 год.
    jobs = []
    for ws in WEEK_STARTS:
        s = date.fromisoformat(ws); e = s + timedelta(days=6)
        jobs.append((ws, s, e,
                     submit("st", "spSearchTerm", ST_COLS, ["searchTerm"], s.isoformat(), e.isoformat()),
                     None))
        time.sleep(65)
        jobs[-1] = jobs[-1][:4] + (submit("tg", "spTargeting", TG_COLS, ["targeting"], s.isoformat(), e.isoformat()),)
        time.sleep(65)
    out["submitted"] = [(j[0], j[3], j[4]) for j in jobs]
    json.dump(out, open("diag/ki_repair" + SFX + "/RESULT.json", "w"), ensure_ascii=False, indent=2)

    # 2) Завантажуємо і рахуємо
    for ws, s, e, st_id, tg_id in jobs:
        label = f"{s.strftime('%d.%m')}-{e.strftime('%d.%m.%Y')}"
        run_date = (e + timedelta(days=1)).isoformat()   # як у weekly: понеділок
        st = wait_and_download(get_access_token(), ADS_PROFILE_ID_USA, st_id, max_wait=5400, token_fn=get_access_token)
        tg = wait_and_download(get_access_token(), ADS_PROFILE_ID_USA, tg_id, max_wait=5400, token_fn=get_access_token)
        rows = analyze_keywords(st, tg, history, MARKET)
        amazon_cost = round(sum(cost(r) for r in st), 2)
        amazon_sales = round(sum(float(r.get("sales7d", 0)) for r in st), 2)
        kw_cost = round(sum(r["spend"] for r in rows), 2)
        kw_sales = round(sum(r["sales"] for r in rows), 2)
        rec = {"week": label, "run_date": run_date, "searchterm_rows": len(st),
               "kw_rows": len(rows), "amazon_cost": amazon_cost, "kw_cost": kw_cost,
               "amazon_sales": amazon_sales, "kw_sales": kw_sales,
               "cost_match": abs(amazon_cost - kw_cost) < 0.05,
               "sales_match": abs(amazon_sales - kw_sales) < 0.05}
        goda = [r for r in rows if r["keyword"] == "goda pheromone perfume for women"]
        rec["goda"] = [{k: g[k] for k in ("campaign", "clicks", "spend", "sales", "acos")} for g in goda]
        rec["written"] = False
        pending.append((rows, label, run_date, rec))
        out["weeks"].append(rec)
        json.dump(out, open("diag/ki_repair" + SFX + "/RESULT.json", "w"), ensure_ascii=False, indent=2)
        print(rec)
    # Усі звіти вже отримано → записуємо швидко одним проходом (мінімум
    # вікна гонки з monitor.py, який теж переписує цей аркуш).
    for rows, label, run_date, rec in pending:
        if rec["cost_match"] and rec["sales_match"]:
            write_keyword_intelligence(rows, label, MARKET, run_date=run_date)
            rec["written"] = True
    out["all_ok"] = all(w["written"] for w in out["weeks"])
    json.dump(out, open("diag/ki_repair" + SFX + "/RESULT.json", "w"), ensure_ascii=False, indent=2)
    if not out["all_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
