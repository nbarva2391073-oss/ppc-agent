# Вкладка "BA Data Freshness": для кожної BA_* вкладки — останній період, дата оновлення, кількість ASIN в ньому.
# Тільки читає BA_* вкладки; пише лише у "BA Data Freshness" (повний перезапис цієї вкладки).
import re, time
from datetime import datetime
import gspread
from sheets import client, SPREADSHEET_ID, get_sheet
TABS = ["BA_SQP_USA", "BA_SQP_CA", "BA_SearchCatalog_USA", "BA_SearchCatalog_CA", "BA_RepeatPurchase_USA", "BA_RepeatPurchase_CA",
        "BA_MarketBasket_USA", "BA_MarketBasket_CA", "BA_Demographics_USA", "BA_Demographics_CA",
        "BA_TopSearchTerms_USA", "BA_TopSearchTerms_CA", "BA_Trends_USA", "BA_Journey_USA"]
MONTHS = {m: i for i, m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"], 1)}
def start_of(label):
    s = str(label).strip()
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})", s)
    if m: return datetime(int(m[3]), int(m[2]), int(m[1])).date(), s
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m: return datetime(int(m[1]), int(m[2]), int(m[3])).date(), s
    m = re.fullmatch(r"([A-Za-z]+) (\d{1,2}), (\d{4})", s)
    if m and m[1] in MONTHS: return datetime(int(m[3]), MONTHS[m[1]], int(m[2])).date(), s
    return None, s
# Контрольні значення з експортів Amazon (Nataly, 02.11.2026): Loyalty і Journey за серпень/вересень 2026
CONTROL = {
 "BA_Trends_USA": {
  "August 31, 2026": {"Total Customers": 267, "Total Sales": 8192.20, "Total Orders": 289, "New to Brand Customers": 180, "New to Brand Customer Sales": 5004.97,
     "New to Brand Customer Orders": 188, "Repeat Customers": 15, "Repeat Sales": 697.52, "Repeat Orders": 22, "Repeat Purchase Rate": 0.0562,
     "Average Repeat Purchase Interval": 5.27, "Potential New Customers": 604},
  "September 30, 2026": {"Total Customers": 300, "Total Sales": 8941.75, "Total Orders": 325, "New to Brand Customers": 221, "New to Brand Customer Sales": 5893.15,
     "New to Brand Customer Orders": 229, "Repeat Customers": 16, "Repeat Sales": 678.67, "Repeat Orders": 25, "Repeat Purchase Rate": 0.0533,
     "Average Repeat Purchase Interval": 5.68, "Potential New Customers": 603}},
 "BA_Journey_USA": {
  "August 31, 2026": {"Customers in Awareness": 10026, "Customers in Consideration": 36058, "Customers in Intent": 1019, "Customers Viewed Detail Page": 35929,
     "Customers Visited Brand Store": 53, "High Potential Consideration Customers": 713, "Branded Search Customers": 29, "Branded Search Ratio": 0.0029,
     "Customers Added to Cart": 658, "Customers Added to Wish List": 376, "Customers Saved for Later": 154, "New to Brand Customers": 172, "Repeat Customers": 6},
  "September 30, 2026": {"Customers in Awareness": 10139, "Customers in Consideration": 8922, "Customers in Intent": 899, "Customers Viewed Detail Page": 8795,
     "Customers Visited Brand Store": 46, "High Potential Consideration Customers": 1059, "Branded Search Customers": 25, "Branded Search Ratio": 0.0025,
     "Customers Added to Cart": 735, "Customers Added to Wish List": 163, "Customers Saved for Later": 194, "New to Brand Customers": 214, "Repeat Customers": 5}}}
def check(tab, hdr, body):
    ctl = CONTROL.get(tab)
    if not ctl: return ""
    res = []
    for date, exp in ctl.items():
        rows = [r for r in body if r and r[0].strip() == date]
        if not rows: res.append(f"{date[:3]}: немає рядка"); continue
        r = rows[0]; bad = []
        for c, v in exp.items():
            try: got = float(str(r[hdr.index(c)]).replace(",", ".")) if c in hdr and hdr.index(c) < len(r) and r[hdr.index(c)] != "" else None
            except ValueError: got = None
            if got is None: bad.append(f"{c}=порожньо")
            elif abs(got - v) > 0.0006 + 1e-9 * abs(v): bad.append(f"{c}: {got}≠{v}")
        res.append(f"{date.split()[0][:3]}: " + ("перевірено, збігається з експортом Amazon" if not bad else "РОЗБІЖНОСТІ " + "; ".join(bad[:4]) + (f" (+{len(bad)-4})" if len(bad) > 4 else "")))
    return " | ".join(res)
ss = client().open_by_key(SPREADSHEET_ID); out = [["Вкладка", "Останній період", "Рядків у останньому періоді", "ASIN у останньому періоді", "Рядків усього", "Перший період", "Оновлено (UTC)", "Примітка", "Перевірка"]]
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
for t in TABS:
    try: ws = ss.worksheet(t)
    except gspread.WorksheetNotFound:
        out.append([t, "", "", "", 0, "", now, "вкладки немає", ""]); continue
    vals = ws.get_all_values(); time.sleep(2)
    if len(vals) < 2: out.append([t, "", "", "", 0, "", now, "порожня", ""]); continue
    hdr, body = vals[0], [r for r in vals[1:] if any(c.strip() for c in r)]
    parsed = [(start_of(r[0]), r) for r in body]
    dated = [(d, lab, r) for (d, lab), r in parsed if d]
    undated = len(body) - len(dated)
    note = f"{undated} рядків з нерозпізнаним періодом" if undated else ""
    if not dated: out.append([t, "", "", "", len(body), "", now, note or "немає дат", ""]); continue
    last = max(d for d, _, _ in dated); first = min(d for d, _, _ in dated)
    lastrows = [(lab, r) for d, lab, r in dated if d == last]
    ai = hdr.index("ASIN") if "ASIN" in hdr else None
    n_asin = len({r[ai] for _, r in lastrows if len(r) > ai and r[ai]}) if ai is not None else ""
    out.append([t, lastrows[0][0], len(lastrows), n_asin, len(body), first.isoformat(), now, note, check(t, hdr, body)])
# SQP: розріз по періодах (щоб одразу бачити, які ASIN є в кожному періоді)
out.append([]); out.append(["SQP за періодами", "Період", "Рядків", "ASIN (кількість)", "ASIN"])
for t in ("BA_SQP_USA", "BA_SQP_CA"):
    try: vals = ss.worksheet(t).get_all_values()
    except gspread.WorksheetNotFound: continue
    if len(vals) < 2: continue
    h = vals[0]; ai, pi = h.index("ASIN"), h.index("Період")
    per = {}
    for r in vals[1:]:
        if len(r) > ai and r[pi]: per.setdefault(r[pi], []).append(r[ai])
    for p in sorted(per, key=lambda x: (start_of(x)[0] or datetime(1970, 1, 1).date())):
        a = sorted(set(per[p])); out.append([t, p, len(per[p]), len(a), " ".join(a)])
sh = get_sheet("BA Data Freshness"); sh.clear(); sh.update(out, "A1")
for r in out: print(r)
