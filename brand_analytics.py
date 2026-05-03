# ============================================================
# BRAND ANALYTICS — пошукові запити через SP-API
# ============================================================
import requests
import json
import time
import gzip
import io
from datetime import datetime, timedelta
from config import (
    AMAZON_CLIENT_ID, AMAZON_CLIENT_SECRET,
    AMAZON_REFRESH_TOKEN_USA, AMAZON_REFRESH_TOKEN_CA,
    MARKETPLACE_IDS
)

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

SP_API_ENDPOINTS = {
    "USA": "https://sellingpartnerapi-na.amazon.com",
    "CA":  "https://sellingpartnerapi-na.amazon.com",
}

def get_access_token(market: str) -> str:
    """Отримати access token для SP-API."""
    refresh_token = (
        AMAZON_REFRESH_TOKEN_USA if market == "USA"
        else AMAZON_REFRESH_TOKEN_CA
    )
    resp = requests.post(LWA_TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "client_id":     AMAZON_CLIENT_ID,
        "client_secret": AMAZON_CLIENT_SECRET,
    })
    resp.raise_for_status()
    return resp.json()["access_token"]


def request_search_terms_report(market: str, token: str, weeks_back: int = 1) -> str:
    """Створити запит на звіт по пошуковим запитам. Повертає reportId."""
    base = SP_API_ENDPOINTS[market]
    marketplace_id = MARKETPLACE_IDS[market]

    # Brand Analytics вимагає точний Monday→Sunday тиждень
    today = datetime.utcnow()
    # Brand Analytics має затримку ~2 тижні
    # Запитуємо тиждень який точно вже оброблений
    days_since_monday = today.weekday()  # 0=Monday
    last_monday = today - timedelta(days=days_since_monday + 14)
    last_sunday = last_monday + timedelta(days=6)
    print(f"📅 Brand Analytics період: {last_monday.strftime('%Y-%m-%d')} → {last_sunday.strftime('%Y-%m-%d')}")

    payload = {
        "reportType": "GET_BRAND_ANALYTICS_SEARCH_TERMS_REPORT",
        "dataStartTime": last_monday.strftime("%Y-%m-%dT00:00:00Z"),
        "dataEndTime":   last_sunday.strftime("%Y-%m-%dT23:59:59Z"),
        "reportOptions": {
            "reportPeriod": "WEEK"
        },
        "marketplaceIds": [marketplace_id],
    }

    resp = requests.post(
        f"{base}/reports/2021-06-30/reports",
        headers={
            "x-amz-access-token": token,
            "Content-Type": "application/json",
        },
        json=payload,
    )

    if resp.status_code != 202:
        print(f"❌ Помилка створення звіту [{market}]: {resp.status_code} {resp.text}")
        return None

    report_id = resp.json().get("reportId")
    print(f"📋 Звіт запрошено [{market}]: {report_id}")
    return report_id


def wait_for_report(market: str, token: str, report_id: str, max_wait: int = 120) -> str:
    """Чекати поки звіт готовий. Повертає documentId."""
    base = SP_API_ENDPOINTS[market]

    for attempt in range(max_wait // 10):
        time.sleep(10)
        resp = requests.get(
            f"{base}/reports/2021-06-30/reports/{report_id}",
            headers={"x-amz-access-token": token},
        )
        data = resp.json()
        status = data.get("processingStatus")
        print(f"⏳ Статус звіту [{market}]: {status} (спроба {attempt+1})")

        if status == "DONE":
            return data.get("reportDocumentId")
        elif status == "FATAL":
            doc_id = data.get("reportDocumentId")
            print(f"❌ Звіт [{market}] завершився з помилкою: {status}")
            print(f"❌ Деталі: {json.dumps(data, indent=2)}")
            if doc_id:
                print(f"⚠️ Спробуємо завантажити документ попри FATAL...")
                return doc_id
            return None
        elif status == "CANCELLED":
            print(f"❌ Звіт [{market}] скасовано")
            return None

    print(f"❌ Звіт [{market}] не готовий за {max_wait}с")
    return None


def download_report(market: str, token: str, document_id: str) -> list[dict]:
    """Завантажити і розпарсити звіт."""
    base = SP_API_ENDPOINTS[market]

    # Отримати URL для завантаження
    resp = requests.get(
        f"{base}/reports/2021-06-30/documents/{document_id}",
        headers={"x-amz-access-token": token},
    )
    resp.raise_for_status()
    doc_data = resp.json()
    download_url = doc_data.get("url")
    compression   = doc_data.get("compressionAlgorithm", "")

    # Завантажити файл
    file_resp = requests.get(download_url)
    file_resp.raise_for_status()

    # Розпакувати якщо gzip
    if compression == "GZIP":
        content = gzip.decompress(file_resp.content).decode("utf-8")
    else:
        content = file_resp.text

    # Парсимо JSON
    try:
        data = json.loads(content)
        print(f"🔍 Тип даних: {type(data).__name__}, preview: {str(data)[:300]}")
        
        # Brand Analytics може повертати різні структури
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Шукаємо список в різних полях
            records = (data.get("dataByAsin") or 
                      data.get("searchTerms") or
                      data.get("data") or
                      data.get("records") or
                      [data])
        else:
            records = [data]
            
        print(f"✅ Завантажено {len(records)} записів [{market}]")
        return records
    except Exception as e:
        print(f"❌ Помилка парсингу звіту [{market}]: {e}")
        print(f"🔍 Raw content preview: {content[:500]}")
        return []


def get_brand_analytics(market: str) -> list[dict]:
    """
    Головна функція — отримати Brand Analytics дані.
    Повертає список пошукових запитів з метриками.
    """
    print(f"\n🔍 Brand Analytics [{market}]...")

    try:
        token     = get_access_token(market)
        report_id = request_search_terms_report(market, token)
        if not report_id:
            return []

        doc_id = wait_for_report(market, token, report_id)
        if not doc_id:
            return []

        records = download_report(market, token, doc_id)
        return records

    except Exception as e:
        print(f"❌ Brand Analytics [{market}] помилка: {e}")
        return []


def format_for_sheets(records: list[dict], market: str) -> tuple[list, list]:
    """
    Форматувати дані для Google Sheets.
    Повертає (headers, rows).
    """
    headers = [
        "Тиждень", "Search Term", "Search Frequency Rank",
        "#1 ASIN", "#1 Click Share", "#1 Conversion Share",
        "#2 ASIN", "#2 Click Share", "#2 Conversion Share",
        "#3 ASIN", "#3 Click Share", "#3 Conversion Share",
        "Ринок"
    ]

    week = datetime.utcnow().strftime("%Y-%W")
    rows = []

    for r in records:
        # SP-API повертає різні формати — обробляємо обидва
        search_term = r.get("searchTerm") or r.get("query") or ""
        rank        = r.get("searchFrequencyRank") or r.get("rank") or ""

        top_asins = r.get("topClickedAsins", r.get("topAsins", []))

        def get_asin_data(idx):
            if idx < len(top_asins):
                a = top_asins[idx]
                return (
                    a.get("clickedAsin") or a.get("asin") or "",
                    a.get("clickSharePercentage") or a.get("clickShare") or "",
                    a.get("conversionSharePercentage") or a.get("conversionShare") or "",
                )
            return ("", "", "")

        a1 = get_asin_data(0)
        a2 = get_asin_data(1)
        a3 = get_asin_data(2)

        rows.append([
            week, search_term, rank,
            a1[0], a1[1], a1[2],
            a2[0], a2[1], a2[2],
            a3[0], a3[1], a3[2],
            market
        ])

    # Сортуємо по Search Frequency Rank (чим менше — тим популярніший запит)
    rows.sort(key=lambda x: int(x[2]) if str(x[2]).isdigit() else 999999)

    return headers, rows
