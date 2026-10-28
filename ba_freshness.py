# Вкладка "BA Data Freshness": для кожної BA_* вкладки — останній період, дата оновлення, кількість ASIN в ньому.
# Тільки читає BA_* вкладки; пише лише у "BA Data Freshness" (повний перезапис цієї вкладки).
import re, time
from datetime import datetime
import gspread
from sheets import client, SPREADSHEET_ID, get_sheet
TABS = ["BA_SQP_USA", "BA_SQP_CA", "BA_SearchCatalog_USA", "BA_SearchCatalog_CA", "BA_RepeatPurchase_USA", "BA_RepeatPurchase_CA",
        "BA_MarketBasket_USA", "BA_MarketBasket_CA", "BA_Demographics_USA", "BA_Demographics_CA",
        "BA_TopSearchTerms_USA", "BA_TopSearchTerms_CA", "BA_Trends_USA", "BA_Trends_CA"]
MONTHS = {m: i for i, m in enumerate(["January","February","March","April","May","June","July","August","September","October","November","December"], 1)}
def start_of(label):
    s = str(label).strip()
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})\s*-\s*(\d{2})\.(\d{2})\.(\d{4})", s)
    if m: return datetime(int(m[3]), int(m[2]), int(m[1])).date(), s
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m: return datetime(int(m[1]), int(m[2]), int(m[3])).date(), s
    m = re.match(r"([A-Za-z]+) (\d{1,2}), (\d{4})", s)
    if m and m[1] in MONTHS: return datetime(int(m[3]), MONTHS[m[1]], int(m[2])).date(), s
    return None, s
ss = client().open_by_key(SPREADSHEET_ID); out = [["Вкладка", "Останній період", "Рядків у останньому періоді", "ASIN у останньому періоді", "Рядків усього", "Перший період", "Оновлено (UTC)", "Примітка"]]
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
for t in TABS:
    try: ws = ss.worksheet(t)
    except gspread.WorksheetNotFound:
        out.append([t, "", "", "", 0, "", now, "вкладки немає"]); continue
    vals = ws.get_all_values(); time.sleep(2)
    if len(vals) < 2: out.append([t, "", "", "", 0, "", now, "порожня"]); continue
    hdr, body = vals[0], [r for r in vals[1:] if any(c.strip() for c in r)]
    parsed = [(start_of(r[0]), r) for r in body]
    dated = [(d, lab, r) for (d, lab), r in parsed if d]
    undated = len(body) - len(dated)
    note = f"{undated} рядків з нерозпізнаним періодом" if undated else ""
    if not dated: out.append([t, "", "", "", len(body), "", now, note or "немає дат"]); continue
    last = max(d for d, _, _ in dated); first = min(d for d, _, _ in dated)
    lastrows = [(lab, r) for d, lab, r in dated if d == last]
    ai = hdr.index("ASIN") if "ASIN" in hdr else None
    n_asin = len({r[ai] for _, r in lastrows if len(r) > ai and r[ai]}) if ai is not None else ""
    out.append([t, lastrows[0][0], len(lastrows), n_asin, len(body), first.isoformat(), now, note])
sh = get_sheet("BA Data Freshness"); sh.clear(); sh.update(out, "A1")
for r in out: print(r)
