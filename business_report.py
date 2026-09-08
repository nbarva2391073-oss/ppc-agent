# ============================================================
# BUSINESS REPORT — GET_SALES_AND_TRAFFIC_REPORT через SP-API
# Збір щоденних даних по кожному ASIN (CHILD) для USA і CA
# ============================================================

import requests
import json
import gzip
from datetime import datetime, timedelta
from config import (
    AMAZON_CLIENT_ID, AMAZON_CLIENT_SECRET,
    AMAZON_REFRESH_TOKEN_USA, AMAZON_REFRESH_TOKEN_CA,
    MARKETPLACE_IDS
)
from sheets import append, get_sheet

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SP_API_BASE   = "https://sellingpartnerapi-na.amazon.com"

BUSINESS_REPORT_SHEETS = {
    "USA": "Business_Report_USA",
    "CA":  "Business_Report_CA",
}

HEADERS_BR = [
    "Дата", "ASIN",
    "Sessions", "Page Views",
    "Buy Box %", "Units Ordered",
    "Ordered Product Sales", "Conversion Rate",
    "Ринок",
]


def get_access_token(market: str) -> str:
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


def get_yesterday() -> str:
    return (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")


def request_business_report(market: str, token: str, date: str) -> str:
    """Запросити Business Report за конкретний день. Повертає reportId."""
    marketplace_id = MARKETPLACE_IDS[market]

    payload = {
        "reportType": "GET_SALES_AND_TRAFFIC_REPORT",
        "dataStartTime": f"{date}T00:00:00Z",
        "dataEndTime":   f"{date}T23:59:59Z",
        "reportOptions": {
            "dateGranularity": "DAY",
            "asinGranularity": "CHILD",
        },
        "marketplaceIds": [marketplace_id],
    }

    resp = requests.post(
        f"{SP_API_BASE}/reports/2021-06-30/reports",
        headers={
            "x-amz-access-token": token,
            "Content-Type": "application/json",
        },
        json=payload,
    )

    if resp.status_code != 202:
        print(f"❌ Помилка запиту [{market}]: {resp.status_code} {resp.text}")
        return None

    report_id = resp.json().get("reportId")
    print(f"📋 Business Report запрошено [{market}] за {date}: {report_id}")
    return report_id


def wait_for_report(market: str, token: str, report_id: str,
                    max_attempts: int = 30) -> str:
    """Чекати готовності звіту (до 5 хвилин). Повертає documentId."""
    import time
    for attempt in range(max_attempts):
        time.sleep(10)
        resp = requests.get(
            f"{SP_API_BASE}/reports/2021-06-30/reports/{report_id}",
            headers={"x-amz-access-token": token},
        )
        data   = resp.json()
        status = data.get("processingStatus")
        print(f"  ⏳ [{market}] статус: {status} (спроба {attempt + 1})")

        if status == "DONE":
            return data.get("reportDocumentId")
        elif status in ("FATAL", "CANCELLED"):
            print(f"  ❌ [{market}] звіт завершився: {status}")
            print(f"  ❌ Деталі: {json.dumps(data, indent=2)}")
            return None

    print(f"  ❌ [{market}] звіт не готовий за {max_attempts * 10}с")
    return None


def download_and_parse(market: str, token: str, document_id: str) -> list:
    """Завантажити і розпарсити Business Report."""
    resp = requests.get(
        f"{SP_API_BASE}/reports/2021-06-30/documents/{document_id}",
        headers={"x-amz-access-token": token},
    )
    resp.raise_for_status()
    doc = resp.json()

    url         = doc.get("url")
    compression = doc.get("compressionAlgorithm", "")

    file_resp = requests.get(url)
    file_resp.raise_for_status()

    content = (
        gzip.decompress(file_resp.content).decode("utf-8")
        if compression == "GZIP"
        else file_resp.text
    )

    try:
        data = json.loads(content)
        # Звіт повертає {"salesAndTrafficByAsin": [...]}
        # НЕ фолбечимо на salesAndTrafficByDate — це інша структура
        # (без ASIN/traffic/sales по товару), яка ламає format_rows()
        records = data.get("salesAndTrafficByAsin")
        if records is None:
            print(f"  ⚠️ [{market}] Немає ключа 'salesAndTrafficByAsin' в відповіді")
            print(f"  🔍 Ключі відповіді: {list(data.keys())}")
            return []
        print(f"  ✅ Завантажено {len(records)} записів [{market}]")
        return records
    except Exception as e:
        print(f"  ❌ Помилка парсингу [{market}]: {e}")
        print(f"  🔍 Preview: {content[:300]}")
        return []


def format_rows(records: list, market: str, date: str) -> list:
    """Форматувати записи для Google Sheets."""
    rows = []
    for r in records:
        if not isinstance(r, dict):
            continue

        # childAsin — реальний товар з конкретною ціною (те що в ASIN_PRICE_CONFIG).
        # parentAsin — "парасолька" для варіацій, ним ніхто не торгує напряму.
        asin         = r.get("childAsin") or r.get("parentAsin") or ""
        traffic      = r.get("trafficByAsin") or {}
        sales        = r.get("salesByAsin") or {}

        sessions     = traffic.get("sessions", "")
        page_views   = traffic.get("pageViews", "")
        buy_box_pct  = traffic.get("buyBoxPercentage", "")
        units        = sales.get("unitsOrdered", "")
        revenue      = sales.get("orderedProductSales", {})
        revenue_val  = revenue.get("amount", "") if isinstance(revenue, dict) else revenue
        conv_rate    = traffic.get("unitSessionPercentage", "")

        rows.append([
            date, asin,
            sessions, page_views,
            buy_box_pct, units,
            revenue_val, conv_rate,
            market,
        ])

    return rows


def ensure_headers(sheet_name: str, headers: list):
    """Гарантовано додає заголовки в перший рядок, якщо їх нема."""
    sh = get_sheet(sheet_name)
    first_row = sh.row_values(1)
    if not first_row or first_row[0] != headers[0]:
        sh.update([headers], "A1")
        print(f"  📝 Заголовки додано в '{sheet_name}'")


def run_business_report():
    """Головна функція — запускається з GitHub Actions щодня."""
    print("=" * 60)
    print(f"📊 BUSINESS REPORT — ЗБІР ДАНИХ")
    print(f"   {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 60)

    date = get_yesterday()
    print(f"📅 Дата: {date}")

    for market in ["USA", "CA"]:
        print(f"\n🌎 {market}...")

        # До 2 повторних спроб, якщо Amazon повертає DONE з 0 записів
        # (транзієнтна поведінка Amazon API — не наш баг, підтверджено
        # спостереженнями за 25.08 і 28.08: перша спроба 0 записів,
        # повторна — реальні дані)
        max_attempts = 3
        records = []
        for attempt in range(1, max_attempts + 1):
            try:
                token     = get_access_token(market)
                report_id = request_business_report(market, token, date)
                if not report_id:
                    break

                document_id = wait_for_report(market, token, report_id)
                if not document_id:
                    break

                token   = get_access_token(market)
                records = download_and_parse(market, token, document_id)

                # Перевіряємо чи звіт "неповний": є записи (продажі вже
                # консолідовані), але трафік (Sessions) ще не встиг
                # обробитись на боці Amazon — це той самий клас транзієнтної
                # проблеми, що й "0 записів", просто виявляється пізніше
                # в циклі. Умова навмисно сувора: ВСІ рядки одночасно
                # мають Sessions=0 — один ASIN з натуральним 0 сесій
                # (є не рідкість) не повинен тригерити retry.
                traffic_incomplete = False
                if records:
                    sessions_values = [
                        r.get("trafficByAsin", {}).get("sessions", 0)
                        for r in records
                    ]
                    if sessions_values and all(v == 0 for v in sessions_values):
                        traffic_incomplete = True

                if records and not traffic_incomplete:
                    break

                if attempt < max_attempts:
                    if not records:
                        print(f"  ⚠️ [{market}] спроба {attempt}/{max_attempts}: 0 записів, повторюємо через 2 хв...")
                    else:
                        print(f"  ⚠️ [{market}] спроба {attempt}/{max_attempts}: всі Sessions=0 (трафік ще не консолідовано), повторюємо через 2 хв...")
                    import time
                    time.sleep(120)
                    records = []
                else:
                    if not records:
                        print(f"  ⚠️ [{market}] всі {max_attempts} спроби дали 0 записів — даних дійсно немає")
                    else:
                        print(f"  ⚠️ [{market}] всі {max_attempts} спроби мають Sessions=0 — зберігаємо як є (можливо реальний день без трафіку)")

            except Exception as e:
                import traceback
                print(f"  ❌ {market} помилка (спроба {attempt}): {e}")
                traceback.print_exc()

        if not records:
            continue

        rows        = format_rows(records, market, date)
        sheet_name  = BUSINESS_REPORT_SHEETS[market]
        ensure_headers(sheet_name, HEADERS_BR)
        append(sheet_name, rows, HEADERS_BR)
        print(f"  ✅ {market}: {len(rows)} записів збережено в '{sheet_name}'")

    print("\n✅ BUSINESS REPORT ЗАВЕРШЕНО")


if __name__ == "__main__":
    run_business_report()
