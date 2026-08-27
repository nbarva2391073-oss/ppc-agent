# ============================================================
# CUSTOMER JOURNEY — читання вручну завантажених CSV з Google Drive
# Обробляє тільки ті типи звітів, яких немає через SP-API:
#   Trends_...            -> BA_Trends_USA
#   US_Demographics_...   -> BA_Demographics_USA
#   US_Top_Search_Terms_..._-> BA_TopSearchTerms_USA
# Ігнорує (вже збирається через API):
#   Search_Query_Performance_, Market_Basket_,
#   Repeat_Purchase_, Search_Catalog_Performance_
# ============================================================

import csv
import io
import re
import json
import requests
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import google.auth.transport.requests as google_requests

from config import GOOGLE_CREDENTIALS_JSON
from sheets import get_sheet, append

DRIVE_FOLDER_ID = "1RAxh0_LIkrKTEECfW8_D2oObFuft6LNe"
DRIVE_API = "https://www.googleapis.com/drive/v3"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

IGNORED_PREFIXES = [
    "Search_Query_Performance_",
    "Market_Basket_",
    "Repeat_Purchase_",
    "Search_Catalog_Performance_",
]

TRENDS_SHEET = "BA_Trends_USA"
DEMOGRAPHICS_SHEET = "BA_Demographics_USA"
TOP_SEARCH_TERMS_SHEET = "BA_TopSearchTerms_USA"


def get_drive_token() -> str:
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    creds.refresh(google_requests.Request())
    return creds.token


def list_files_recursive(folder_id: str, token: str) -> list:
    """Рекурсивно збирає всі файли в папці і підпапках Drive."""
    headers = {"Authorization": f"Bearer {token}"}
    files = []

    resp = requests.get(
        f"{DRIVE_API}/files",
        headers=headers,
        params={
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "files(id,name,mimeType)",
            "pageSize": 200,
        },
    )
    resp.raise_for_status()
    entries = resp.json().get("files", [])

    for e in entries:
        if e["mimeType"] == "application/vnd.google-apps.folder":
            files.extend(list_files_recursive(e["id"], token))
        elif e["name"].lower().endswith(".csv"):
            files.append(e)

    return files


def download_csv(file_id: str, token: str) -> str:
    resp = requests.get(
        f"{DRIVE_API}/files/{file_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"alt": "media"},
    )
    resp.raise_for_status()
    return resp.content.decode("utf-8-sig")


def classify_file(name: str) -> str:
    """Визначає тип файлу за префіксом назви. None = ігноруємо."""
    for prefix in IGNORED_PREFIXES:
        if name.startswith(prefix):
            return None

    if name.startswith("Trends_"):
        return "TRENDS"
    if name.startswith("US_Demographics_"):
        return "DEMOGRAPHICS"
    if name.startswith("US_Top_Search_Terms_"):
        return "TOP_SEARCH_TERMS"
    return None


def extract_period_from_filename(name: str) -> str:
    """
    Витягує дату з назви файлу, напр.
    US_Demographics_Simple_Month_2026_01_31.csv -> 2026-01-31
    """
    m = re.search(r"(\d{4})_(\d{2})_(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def extract_keyword_from_filename(name: str) -> str:
    """
    US_Top_Search_Terms_pheromone_Month_2026_01_31.csv -> pheromone
    """
    m = re.match(r"US_Top_Search_Terms_(.+?)_Month_", name)
    return m.group(1) if m else ""


def parse_csv_skip_meta(content: str) -> tuple:
    """
    Amazon CSV: рядок 1 = мета-фільтри запиту, рядок 2 = реальні заголовки,
    рядок 3+ = дані. Повертає (headers, rows).
    """
    reader = list(csv.reader(io.StringIO(content)))
    if len(reader) < 3:
        return [], []
    headers = reader[1]
    rows = reader[2:]
    return headers, rows


def upsert_rows(sheet_name: str, headers: list, rows: list, key_cols: list):
    """
    Видаляє старі рядки з таким самим значенням key_cols
    і записує нові — уникає дублікатів при повторній обробці файлу.
    """
    sh = get_sheet(sheet_name)
    existing = sh.get_all_values()

    if not existing or not existing[0] or existing[0][0] != headers[0]:
        sh.clear()
        sh.update([headers] + rows, "A1")
        print(f"  📝 '{sheet_name}': заголовки + {len(rows)} рядків записано")
        return

    header_row = existing[0]
    key_idx = [header_row.index(c) for c in key_cols if c in header_row]

    new_keys = set()
    for r in rows:
        key = tuple(r[i] if i < len(r) else "" for i in key_idx)
        new_keys.add(key)

    kept = [header_row]
    removed = 0
    for row in existing[1:]:
        key = tuple(row[i] if i < len(row) else "" for i in key_idx)
        if key in new_keys:
            removed += 1
            continue
        kept.append(row)

    final_rows = kept + rows
    sh.clear()
    sh.update(final_rows, "A1")
    print(f"  🔄 '{sheet_name}': замінено {removed} старих рядків, додано {len(rows)} нових")


def process_trends(name: str, content: str):
    headers, rows = parse_csv_skip_meta(content)
    if not headers or not rows:
        print(f"  ⚠️ '{name}': порожній файл")
        return
    upsert_rows(TRENDS_SHEET, headers, rows, key_cols=["Date"])


def process_demographics(name: str, content: str):
    headers, rows = parse_csv_skip_meta(content)
    if not headers or not rows:
        print(f"  ⚠️ '{name}': порожній файл")
        return

    period = extract_period_from_filename(name)
    headers_with_period = ["Period"] + headers
    rows_with_period = [[period] + row for row in rows]

    upsert_rows(
        DEMOGRAPHICS_SHEET, headers_with_period, rows_with_period,
        key_cols=["Period", "Demographic Type", "Demographic"],
    )


def process_top_search_terms(name: str, content: str):
    headers, rows = parse_csv_skip_meta(content)
    if not headers or not rows:
        print(f"  ⚠️ '{name}': порожній файл")
        return

    period = extract_period_from_filename(name)
    keyword = extract_keyword_from_filename(name)
    headers_full = ["Period", "Keyword"] + headers
    rows_full = [[period, keyword] + row for row in rows]

    upsert_rows(
        TOP_SEARCH_TERMS_SHEET, headers_full, rows_full,
        key_cols=["Period", "Keyword", "Search Term"],
    )


def run_customer_journey():
    print("=" * 60)
    print(f"📁 CUSTOMER JOURNEY — ЧИТАННЯ CSV З GOOGLE DRIVE")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    token = get_drive_token()
    files = list_files_recursive(DRIVE_FOLDER_ID, token)
    print(f"📂 Знайдено {len(files)} CSV файлів у папці (з підпапками)")

    processed = {"TRENDS": 0, "DEMOGRAPHICS": 0, "TOP_SEARCH_TERMS": 0}
    skipped = 0

    for f in files:
        name = f["name"]
        file_type = classify_file(name)

        if file_type is None:
            skipped += 1
            continue

        print(f"\n🔍 Обробляю: {name} ({file_type})")
        try:
            content = download_csv(f["id"], token)

            if file_type == "TRENDS":
                process_trends(name, content)
            elif file_type == "DEMOGRAPHICS":
                process_demographics(name, content)
            elif file_type == "TOP_SEARCH_TERMS":
                process_top_search_terms(name, content)

            processed[file_type] += 1
        except Exception as e:
            import traceback
            print(f"  ❌ Помилка обробки '{name}': {e}")
            traceback.print_exc()

    print(f"\n📊 Підсумок:")
    for t, count in processed.items():
        print(f"   {t}: {count} файлів оброблено")
    print(f"   Проігноровано (вже через API або невідомий тип): {skipped}")

    print("\n✅ CUSTOMER JOURNEY ЗАВЕРШЕНО")


if __name__ == "__main__":
    run_customer_journey()
