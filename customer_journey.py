# ============================================================
# BA з ручних CSV (Google Drive) → BA_Trends_USA (Customer Loyalty), BA_Journey_USA (Customer Journey),
# BA_Demographics_USA, BA_TopSearchTerms_USA.
# ПРАВИЛА (виправлення 02.11.2026):
#  * тип звіту визначається за ЗАГОЛОВКОМ колонок, не за іменем файла (Amazon називає Journey і Loyalty однаково);
#  * запис по ключу — оновлення комірок на місці; вкладка НЕ переписується, порядок рядків і сторонні колонки не чіпаються;
#  * рядок Loyalty приймається лише якщо заповнено всі 13 колонок;
#  * рядки, де перша колонка не дата (ручні копії/BACKUP), ігноруються і не видаляються;
#  * DRY_RUN=1 — нічого не пишемо, лише звіт у diag/ba_journey/.
# ============================================================
import csv, io, os, re, json, time
from datetime import datetime
import requests
from google.oauth2.service_account import Credentials
import google.auth.transport.requests as google_requests
from config import GOOGLE_CREDENTIALS_JSON
from sheets import get_sheet

DRIVE_FOLDER_ID = "1RAxh0_LIkrKTEECfW8_D2oObFuft6LNe"
DRIVE_API = "https://www.googleapis.com/drive/v3"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DRY = os.environ.get("DRY_RUN") == "1"
OUT = "diag/ba_journey"; os.makedirs(OUT, exist_ok=True)
IGNORED_PREFIXES = ["Search_Query_Performance_", "Market_Basket_", "Repeat_Purchase_", "Search_Catalog_Performance_"]

TRENDS_SHEET, JOURNEY_SHEET = "BA_Trends_USA", "BA_Journey_USA"
DEMOGRAPHICS_SHEET, TOP_SEARCH_TERMS_SHEET = "BA_Demographics_USA", "BA_TopSearchTerms_USA"

LOYALTY_COLS = ["Date", "Total Customers", "Total Sales", "Total Orders", "New to Brand Customers",
                "New to Brand Customer Sales", "New to Brand Customer Orders", "Repeat Customers", "Repeat Sales",
                "Repeat Orders", "Repeat Purchase Rate", "Average Repeat Purchase Interval", "Potential New Customers"]
JOURNEY_COLS = ["Date", "Customers in Awareness", "Customers in Consideration", "Customers in Intent",
                "Branded Search Customers", "Branded Search Ratio", "Customers Viewed Detail Page",
                "Customers Visited Brand Store", "High Potential Consideration Customers", "New to Brand Customers",
                "Customers Added to Cart", "Customers Added to Wish List", "Customers Saved for Later", "Repeat Customers"]
MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"]
LOG = {"files": [], "actions": [], "warnings": []}

def dump(): json.dump(LOG, open(f"{OUT}/{'DRYRUN' if DRY else 'RESULT'}.json", "w"), ensure_ascii=False, indent=1)
def warn(msg): print("  ⚠️", msg); LOG["warnings"].append(msg)
def retry(fn, n=6):
    for a in range(1, n + 1):
        try: return fn()
        except Exception as e:
            print("  retry", a, str(e)[:120]); time.sleep(20 * a)
    raise RuntimeError("retry exhausted")

def norm_date(s):
    """→ 'August 31, 2026' (формат BA_Trends_USA) або None, якщо це не дата."""
    s = str(s).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            d = datetime.strptime(s, fmt); return f"{MONTHS[d.month-1]} {d.day}, {d.year}"
        except ValueError: pass
    return None

def clean(v):
    """$8,192.20 → 8192.20; 5.62% → 0.0562; решту лишаємо як є."""
    t = str(v).strip()
    if t.endswith("%"):
        try: return str(round(float(t[:-1].replace(",", "")) / 100, 6))
        except ValueError: return t
    t2 = t.replace("$", "").replace(",", "")
    try: float(t2); return t2
    except ValueError: return t

def get_drive_token():
    creds = Credentials.from_service_account_info(json.loads(GOOGLE_CREDENTIALS_JSON), scopes=SCOPES)
    creds.refresh(google_requests.Request()); return creds.token

def list_files_recursive(folder_id, token, path=""):
    h = {"Authorization": f"Bearer {token}"}; files = []
    r = requests.get(f"{DRIVE_API}/files", headers=h, timeout=60, params={
        "q": f"'{folder_id}' in parents and trashed=false", "fields": "files(id,name,mimeType,modifiedTime)", "pageSize": 200})
    r.raise_for_status()
    for e in r.json().get("files", []):
        if e["mimeType"] == "application/vnd.google-apps.folder": files += list_files_recursive(e["id"], token, f"{path}{e['name']}/")
        elif e["name"].lower().endswith(".csv"): e["path"] = f"{path}{e['name']}"; files.append(e)
    return files

def download_csv(fid, token):
    r = requests.get(f"{DRIVE_API}/files/{fid}", headers={"Authorization": f"Bearer {token}"}, params={"alt": "media"}, timeout=120)
    r.raise_for_status(); return r.content.decode("utf-8-sig")

def classify(headers):
    """Тип звіту за заголовками колонок."""
    h = {c.strip() for c in headers}
    if "Date" in h and "Total Customers" in h and "Repeat Purchase Rate" in h: return "LOYALTY"
    if "Date" in h and ({"Top Tier Customers"} & h or any("RFM" in c for c in h)): return "LOYALTY_RFM"
    if "Date" in h and (h & {"Customers in Awareness", "Customers in Consideration", "Customers in Intent"}): return "JOURNEY"
    if "Date" in h and "New to Brand Customers" in h and "Repeat Customers" in h and "Total Customers" not in h: return "JOURNEY"
    if "Demographic Type" in h or "Demographic" in h: return "DEMOGRAPHICS"
    if "Search Term" in h: return "TOP_SEARCH_TERMS"
    return None

def parse(content):
    """Повертає (meta, headers, rows). Якщо перший рядок містить 'Date' — мета-рядка немає; інакше рядок 1 = мета."""
    rd = list(csv.reader(io.StringIO(content)))
    if not rd: return [], [], []
    if "Date" in [c.strip() for c in rd[0]]: return [], rd[0], rd[1:]
    if len(rd) >= 2 and classify(rd[1]): return rd[0], rd[1], rd[2:]
    return [], rd[0], rd[1:]

# ---------- запис на місці ----------
def upsert_inplace(sheet_name, headers, rows, key_cols, required=None):
    """rows — списки у порядку headers. Існуючий рядок з тим самим ключем оновлюється лише в колонках джерела;
    нові рядки додаються в кінець. Нічого не видаляється і не переставляється."""
    sh = retry(lambda: get_sheet(sheet_name)); ex = retry(lambda: sh.get_all_values())
    if not ex or not ex[0]:
        LOG["actions"].append({"sheet": sheet_name, "created_header": headers, "rows": len(rows)})
        if not DRY:
            retry(lambda: sh.update([headers] + rows, "A1"))
        return {"updated": 0, "added": len(rows)}
    hdr = ex[0]
    for c in headers:
        if c not in hdr:   # нова колонка джерела — додаємо в кінець заголовка (без зсуву існуючих)
            hdr = hdr + [c]
            if not DRY: retry(lambda: sh.update([[c]], gspread_a1(1, len(hdr))))
    idx = {c: hdr.index(c) for c in headers}
    ki = [hdr.index(c) for c in key_cols]
    pos = {}
    for n, r in enumerate(ex[1:], start=2):
        k = tuple((r[i] if i < len(r) else "").strip() for i in ki)
        pos.setdefault(k, n)
    updates, appended, upd_rows = [], [], 0
    for r in rows:
        d = dict(zip(headers, r)); k = tuple(str(d.get(c, "")).strip() for c in key_cols)
        if k in pos:
            n = pos[k]; cur = ex[n - 1]; changed = False
            for c in headers:
                if c in key_cols: continue
                val = d.get(c, "")
                if val == "": continue          # порожнє джерело не стирає існуюче
                ci = idx[c]; old = cur[ci] if ci < len(cur) else ""
                if str(old).replace(",", ".") != str(val).replace(",", "."):
                    updates.append({"range": gspread_a1(n, ci + 1), "values": [[val]]}); changed = True
            upd_rows += changed
        else:
            full = [""] * len(hdr)
            for c in headers: full[idx[c]] = d.get(c, "")
            appended.append(full); pos[k] = None
    LOG["actions"].append({"sheet": sheet_name, "cells_updated": len(updates), "rows_updated": upd_rows, "rows_added": len(appended),
                           "sample_updates": updates[:6]})
    if not DRY:
        for i in range(0, len(updates), 200): retry(lambda: sh.batch_update(updates[i:i + 200], value_input_option="USER_ENTERED")); time.sleep(2)
        if appended: retry(lambda: sh.append_rows(appended, value_input_option="USER_ENTERED"))
    return {"updated": upd_rows, "added": len(appended)}

def gspread_a1(row, col):
    s = ""
    while col: col, r = divmod(col - 1, 26); s = chr(65 + r) + s
    return f"{s}{row}"

def main():
    print("=" * 60, "\n📁 BA З ДИСКА (CSV) — header-based\n", "=" * 60, sep="")
    token = get_drive_token(); files = list_files_recursive(DRIVE_FOLDER_ID, token)
    print(f"📂 CSV файлів: {len(files)}")
    loyalty, rfm, journey = {}, {}, {}      # Date -> {col: val}
    for f in sorted(files, key=lambda x: x["path"]):
        name = f["name"]
        if any(name.startswith(p) for p in IGNORED_PREFIXES): continue
        try: content = download_csv(f["id"], token)
        except Exception as e: warn(f"{f['path']}: не завантажено ({e})"); continue
        meta, headers, rows = parse(content)
        typ = classify(headers)
        LOG["files"].append({"path": f["path"], "type": typ, "headers": headers, "rows": len(rows), "meta": meta[:3]}); dump()
        if typ is None: print(f"  ⏭ {f['path']}: тип не розпізнано за заголовками"); continue
        print(f"  🔍 {f['path']}: {typ}, {len(rows)} рядків")
        hi = {c.strip(): i for i, c in enumerate(headers)}
        if typ in ("LOYALTY", "LOYALTY_RFM", "JOURNEY"):
            tgt = {"LOYALTY": loyalty, "LOYALTY_RFM": rfm, "JOURNEY": journey}[typ]
            for r in rows:
                dt = norm_date(r[hi["Date"]]) if len(r) > hi["Date"] else None
                if not dt: continue          # не дата — ігноруємо
                rec = tgt.setdefault(dt, {})
                for c, i in hi.items():
                    if c == "Date" or i >= len(r) or str(r[i]).strip() == "": continue
                    v = clean(r[i])
                    if c in rec and rec[c] != v and typ == "JOURNEY": warn(f"Journey {dt}: '{c}' розбіжність між файлами: {rec[c]} vs {v} ({name})")
                    rec.setdefault(c, v)
        elif typ == "DEMOGRAPHICS":
            m = re.search(r"(\d{4})_(\d{2})_(\d{2})", name); period = f"{m[1]}-{m[2]}-{m[3]}" if m else ""
            if not period: warn(f"{f['path']}: немає дати в імені файла — пропущено"); continue
            upsert_inplace(DEMOGRAPHICS_SHEET, ["Period"] + headers, [[period] + r for r in rows], ["Period", "Demographic Type", "Demographic"])
        elif typ == "TOP_SEARCH_TERMS":
            m = re.search(r"(\d{4})_(\d{2})_(\d{2})", name); period = f"{m[1]}-{m[2]}-{m[3]}" if m else ""
            kw = (re.match(r"US_Top_Search_Terms_(.+?)_Month_", name) or [None, ""])[1]
            if not kw:   # запит із мета-рядка (Search Term / Keyword фільтр)
                mm = re.search(r"(pheromones?)", " ".join(meta), re.I); kw = mm[1].lower() if mm else ""
            if not period or not kw: warn(f"{f['path']}: не визначено період ({period}) або запит ({kw}) — пропущено"); continue
            upsert_inplace(TOP_SEARCH_TERMS_SHEET, ["Period", "Keyword"] + headers, [[period, kw] + r for r in rows], ["Period", "Keyword", "Search Term"])
    # --- Loyalty → BA_Trends_USA (лише повні 13 колонок) ---
    ok_rows = []
    for dt, rec in loyalty.items():
        missing = [c for c in LOYALTY_COLS[1:] if c not in rec]
        if missing: warn(f"Loyalty {dt}: заповнено не всі 13 колонок (немає {missing}) — НЕ записую"); continue
        ok_rows.append([dt] + [rec[c] for c in LOYALTY_COLS[1:]])
    if ok_rows: LOG["trends_result"] = upsert_inplace(TRENDS_SHEET, LOYALTY_COLS, ok_rows, ["Date"])
    # --- RFM-колонки (N–S) для існуючих місяців: лише ті колонки, що є в джерелі ---
    for dt, rec in rfm.items():
        cols = [c for c in rec]
        if cols: upsert_inplace(TRENDS_SHEET, ["Date"] + cols, [[dt] + [rec[c] for c in cols]], ["Date"])
    # --- Journey → BA_Journey_USA ---
    jr = []
    for dt, rec in journey.items():
        jr.append([dt] + [rec.get(c, "") for c in JOURNEY_COLS[1:]])
        miss = [c for c in JOURNEY_COLS[1:] if c not in rec]
        if miss: warn(f"Journey {dt}: немає колонок {miss}")
    if jr: LOG["journey_result"] = upsert_inplace(JOURNEY_SHEET, JOURNEY_COLS, jr, ["Date"])
    LOG["parsed"] = {"loyalty": loyalty, "rfm": rfm, "journey": journey}
    dump(); print("done", "(DRY RUN)" if DRY else "")

if __name__ == "__main__":
    main()
