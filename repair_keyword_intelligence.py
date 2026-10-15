# ============================================================
# РЕМОНТ Keyword Intelligence USA: тижневі рядки з Spend=0
# Причина: keywords.analyze_keywords читав r["spend"], а Amazon Reporting
# API повертає "cost" → Spend=0, ACoS=0, статус «Норма/Збитково» хибні.
# Скрипт перебирає тижні (пн–нд), тягне ПЕРВИННІ звіти Amazon
# (search term + targeting), перераховує з виправленою логікою,
# записує upsert-ом (ключ Week/Keyword/Match/Campaign/Run Date) і
# складає diag/ki_repair/RESULT.json зі звіркою сум з Amazon.
# Нічого не видаляє з інших рядків, ставки/кампанії не чіпає.
# ============================================================
import json, os, sys
from datetime import date, timedelta

from config import ADS_PROFILE_ID_USA, SHEETS_USA
from amazon_ads import get_access_token, get_search_term_report, get_targeting_report
from keywords import analyze_keywords
from sheets import read_all, write_keyword_intelligence

MARKET = "USA"
WEEK_STARTS = ["2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28", "2026-10-05"]


def cost(r):
    return float(r.get("cost") or r.get("spend") or 0)


def main():
    out = {"weeks": []}
    pending = []
    os.makedirs("diag/ki_repair", exist_ok=True)
    history = {"raw_data": read_all(SHEETS_USA["raw_data"])}
    for ws in WEEK_STARTS:
        s = date.fromisoformat(ws); e = s + timedelta(days=6)
        label = f"{s.strftime('%d.%m')}-{e.strftime('%d.%m.%Y')}"
        run_date = (e + timedelta(days=1)).isoformat()   # як у weekly: понеділок
        token = get_access_token()
        st = get_search_term_report(token, ADS_PROFILE_ID_USA, s.isoformat(), e.isoformat())
        tg = get_targeting_report(get_access_token(), ADS_PROFILE_ID_USA, s.isoformat(), e.isoformat())
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
        json.dump(out, open("diag/ki_repair/RESULT.json", "w"), ensure_ascii=False, indent=2)
        print(rec)
    # Усі звіти вже отримано → записуємо швидко одним проходом (мінімум
    # вікна гонки з monitor.py, який теж переписує цей аркуш).
    for rows, label, run_date, rec in pending:
        if rec["cost_match"] and rec["sales_match"]:
            write_keyword_intelligence(rows, label, MARKET, run_date=run_date)
            rec["written"] = True
    out["all_ok"] = all(w["written"] for w in out["weeks"])
    json.dump(out, open("diag/ki_repair/RESULT.json", "w"), ensure_ascii=False, indent=2)
    if not out["all_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
