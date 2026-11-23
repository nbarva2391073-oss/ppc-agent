# ============================================================
# ASIN COCKPIT USA — Етап 2. Вкладка "ASIN Cockpit USA": рядок на (Тиждень Пн–Нд, ASIN).
# Джерела (лише читання вкладок): Business_Report_USA (сесії, продажі, одиниці), TACoS_USA (реклама),
# BA_SQP_USA (головний запит), Ad SKU Status USA (активні кампанії), Advertised Product USA (запасне джерело).
# Колонки «Рішення» і «Дата перевірки» НЕ заповнюються і НЕ перезаписуються (їх веде AI/Nataly).
# Upsert за (Week, ASIN): оновлюються лише розраховані колонки.
# SQP Impression Share у BA_SQP вже у відсотках (не множимо на 100).
# Env: ASINS="B0GYSB85SH" (список через кому або CORE), WEEKS=1 (скільки останніх повних тижнів), DRY_RUN=1
# ============================================================
import json, os
from datetime import datetime, timedelta
from collections import defaultdict
from ba_asins import ASIN_CLASS
from sheet_util import ss, ensure_tab, retry

TAB = "ASIN Cockpit USA"
HDR = ["Week", "ASIN", "Class", "Sessions", "PageViews", "Units", "Sales", "CR%",
       "AdSpend", "AdSales", "TACoS%", "ACoS%",
       "SQP Period", "SQP TopQuery", "SQP QueryVolume", "SQP ASIN Impressions", "SQP ASIN Clicks", "SQP CTR%",
       "SQP Impression Share%", "ActiveCampaigns", "ActiveCampaignList",
       "Fresh BR (MAX Date)", "Fresh TACoS (MAX Date)", "Fresh SQP (Period)", "Fresh AdStatus (Date)",
       "Рішення", "Дата перевірки"]
NCALC = HDR.index("Рішення")          # розраховані колонки: 0..NCALC-1
DRY = os.getenv("DRY_RUN", "") in ("1", "true", "True")
OUT = "diag/signals"; os.makedirs(OUT, exist_ok=True)


def num(v):
    try:
        return float(str(v).replace(" ", "").replace(" ", "").replace(",", "."))
    except ValueError:
        return 0.0


def rd(name):
    try:
        v = retry(ss().worksheet(name).get_all_values)
    except Exception as e:
        print(f"  ⚠️ {name}: {e}"); return [], []
    return (v[0], v[1:]) if v else ([], [])


def last_weeks(n):
    t = datetime.utcnow().date()
    mon = t - timedelta(days=t.weekday())           # понеділок поточного тижня
    return [(mon - timedelta(days=7 * k), mon - timedelta(days=7 * k) + timedelta(days=6)) for k in range(n, 0, -1)]


def wl(a, b):
    return f"{a.strftime('%d.%m')}-{b.strftime('%d.%m.%Y')}"


def pdate(s):
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def main():
    asins_env = os.getenv("ASINS", "B0GYSB85SH")
    asins = [a for a, c in ASIN_CLASS.items() if c == "core"] if asins_env.upper() == "CORE" else \
        [a.strip() for a in asins_env.split(",") if a.strip()]
    weeks = last_weeks(int(os.getenv("WEEKS", "1")))
    print(f"ASIN: {asins}; тижні: {[wl(a, b) for a, b in weeks]}")

    bh, br = rd("Business_Report_USA"); bi = {n: i for i, n in enumerate(bh)}
    th, tc = rd("TACoS_USA"); ti = {n: i for i, n in enumerate(th)}
    sh_, sq = rd("BA_SQP_USA"); si = {n: i for i, n in enumerate(sh_)}
    ah, ad = rd("Ad SKU Status USA"); ai = {n: i for i, n in enumerate(ah)}

    br_by = defaultdict(list); tc_by = defaultdict(list); sq_by = defaultdict(list)
    for r in br:
        if len(r) > 1: br_by[r[bi["ASIN"]]].append(r)
    for r in tc:
        if len(r) > 1: tc_by[r[ti["ASIN"]]].append(r)
    for r in sq:
        if len(r) > 2: sq_by[r[si["ASIN"]]].append(r)
    # активні кампанії за останньою датою вкладки Ad SKU Status
    act = defaultdict(set); status_date = ""
    if ad and "Date" in ai:
        status_date = max((r[ai["Date"]][:10] for r in ad if len(r) > ai["Date"]), default="")
        for r in ad:
            if len(r) > ai["AdState"] and r[ai["Date"]][:10] == status_date and all(
                    str(r[ai[k]]).upper() == "ENABLED" for k in ("CampaignState", "AdGroupState", "AdState")):
                act[r[ai["ASIN"]]].add(r[ai["Campaign"]])

    out = []
    for a, b in weeks:
        wlabel = wl(a, b); days = {(a + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
        for asin in asins:
            brw = [r for r in br_by[asin] if r[bi["Дата"]][:10] in days]
            tcw = [r for r in tc_by[asin] if r[ti["Date"]][:10] in days]
            sess = sum(num(r[bi["Sessions"]]) for r in brw); pv = sum(num(r[bi["Page Views"]]) for r in brw)
            units = sum(num(r[bi["Units Ordered"]]) for r in brw); sales = sum(num(r[bi["Ordered Product Sales"]]) for r in brw)
            spend = sum(num(r[ti["Ad_Spend"]]) for r in tcw); asales = sum(num(r[ti["Ad_Sales"]]) for r in tcw)
            tsales = sum(num(r[ti["Total_Sales"]]) for r in tcw) or sales
            # SQP: період, що найточніше накриває тиждень; інакше найсвіжіший тижневий; топ-запит = макс. ASIN Impressions
            per_rows = defaultdict(list)
            for r in sq_by[asin]:
                per_rows[r[si["Період"]]].append(r)
            chosen = wlabel if wlabel in per_rows else ""
            if not chosen:
                cands = [(pdate(p.split("-")[1]), p) for p in per_rows if "-" in p and pdate(p.split("-")[1])
                         and (pdate(p.split("-")[1]) - pdate(p.split("-")[0])).days == 6]
                chosen = max(cands)[1] if cands else ""
            top = max(per_rows[chosen], key=lambda r: num(r[si["ASIN Impressions"]])) if chosen else None
            imp = num(top[si["ASIN Impressions"]]) if top else ""; clk = num(top[si["ASIN Clicks"]]) if top else ""
            fresh_br = max((r[bi["Дата"]][:10] for r in br_by[asin]), default="")
            fresh_tc = max((r[ti["Date"]][:10] for r in tc_by[asin]), default="")
            fresh_sqp = max((p for p in per_rows if "-" in p and pdate(p.split("-")[1])),
                            key=lambda p: pdate(p.split("-")[1]), default="")
            camps = sorted(act.get(asin, set()))
            out.append([
                wlabel, asin, ASIN_CLASS.get(asin, ""), sess, pv, units, round(sales, 2),
                round(units / sess * 100, 2) if sess else "",
                round(spend, 2), round(asales, 2),
                round(spend / tsales * 100, 2) if tsales else "", round(spend / asales * 100, 2) if asales else "",
                chosen, top[si["Search Query"]] if top else "", num(top[si["Query Volume"]]) if top else "",
                imp, clk, round(clk / imp * 100, 2) if imp else "",
                round(num(top[si["ASIN Impression Share"]]), 2) if top else "",
                len(camps), "; ".join(camps), fresh_br, fresh_tc, fresh_sqp, status_date])
    json.dump(out, open(f"{OUT}/cockpit_preview.json", "w"), ensure_ascii=False, indent=1)
    for r in out:
        print(dict(zip(HDR, r)))
    if DRY:
        return
    ws = ensure_tab(TAB, HDR)
    vals = retry(ws.get_all_values)
    hdr = vals[0] if vals else HDR
    if hdr[:NCALC] != HDR[:NCALC]:
        raise SystemExit(f"Заголовок {TAB} не збігається — зупиняюсь, нічого не пишу")
    idx = {(r[0], r[1]): i for i, r in enumerate(vals[1:], start=2) if len(r) > 1}
    upd, new = [], []
    for r in out:
        k = (r[0], r[1])
        if k in idx:
            upd.append({"range": f"A{idx[k]}:{chr(64 + NCALC)}{idx[k]}", "values": [r[:NCALC]]})
        else:
            new.append(r)
    if upd:
        retry(ws.batch_update, upd, value_input_option="RAW")
    if new:
        need = len(vals) + len(new) + 5
        if need > ws.row_count:
            retry(ws.resize, rows=need)
        retry(ws.append_rows, new, value_input_option="RAW", table_range="A1")
    print(f"✍️ {TAB}: оновлено {len(upd)}, додано {len(new)}")


if __name__ == "__main__":
    main()
