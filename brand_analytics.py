# ============================================================
# BRAND ANALYTICS — Search Query Performance через SP-API
# ============================================================
import requests
import json
import time
import gzip
from datetime import datetime, timedelta
from config import (
    AMAZON_CLIENT_ID, AMAZON_CLIENT_SECRET,
    AMAZON_REFRESH_TOKEN_USA, AMAZON_REFRESH_TOKEN_CA,
    MARKETPLACE_IDS
)

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SP_API_BASE = "https://sellingpartnerapi-na.amazon.com"

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


def get_week_dates():
    """Залишено для зворотної сумісності (більше не використовується для запитів)."""
    today = datetime.utcnow()
    days_since_sunday = (today.weekday() + 1) % 7
    last_sunday = today - timedelta(days=days_since_sunday + 14)
    last_saturday = last_sunday + timedelta(days=6)
    return last_sunday, last_saturday


def get_previous_month_dates():
    """Повертає перший і останній день ПОПЕРЕДНЬОГО місяця.
    Наприклад, якщо запуск 10 липня — повертає 1-30 червня."""
    today = datetime.utcnow()
    first_day_this_month = today.replace(day=1)
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    first_day_prev_month = last_day_prev_month.replace(day=1)
    return first_day_prev_month, last_day_prev_month


def request_sqp_report(market: str, token: str) -> str:
    """Запросити Search Query Performance звіт. Повертає reportId."""
    marketplace_id = MARKETPLACE_IDS[market]
    start, end = get_previous_month_dates()

    print(f"📅 SQP період (попередній місяць): {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")

    # Флагманські ASIN для SQP звіту
    FLAGSHIP_ASINS = {
        "USA": "B081T6QGD9 B0G5QB4W6N B09NBB4QP7",
        "CA":  "B081T6QGD9 B0G5QB4W6N B09NBB4QP7",
    }

    payload = {
        "reportType": "GET_BRAND_ANALYTICS_SEARCH_QUERY_PERFORMANCE_REPORT",
        "dataStartTime": start.strftime("%Y-%m-%dT00:00:00Z"),
        "dataEndTime":   end.strftime("%Y-%m-%dT23:59:59Z"),
        "reportOptions": {
            "reportPeriod": "MONTH",
            "asin": FLAGSHIP_ASINS[market],
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
    print(f"📋 Звіт запрошено [{market}]: {report_id}")
    return report_id


def wait_for_report(market: str, token: str, report_id: str, max_wait: int = 600) -> str:
    """Чекати поки звіт готовий. Повертає documentId."""
    for attempt in range(max_wait // 10):
        time.sleep(10)
        resp = requests.get(
            f"{SP_API_BASE}/reports/2021-06-30/reports/{report_id}",
            headers={"x-amz-access-token": token},
        )
        data = resp.json()
        status = data.get("processingStatus")
        print(f"⏳ Статус [{market}]: {status} (спроба {attempt+1})")

        if status == "DONE":
            return data.get("reportDocumentId")
        elif status in ("FATAL", "CANCELLED"):
            print(f"❌ Звіт завершився: {status}")
            print(f"❌ Деталі: {json.dumps(data, indent=2)}")
            return None

    print(f"❌ Звіт не готовий за {max_wait}с")
    return None


def download_report(market: str, token: str, document_id: str) -> list:
    """Завантажити і розпарсити звіт."""
    # Отримати URL
    resp = requests.get(
        f"{SP_API_BASE}/reports/2021-06-30/documents/{document_id}",
        headers={"x-amz-access-token": token},
    )
    resp.raise_for_status()
    doc_data = resp.json()

    download_url = doc_data.get("url")
    compression  = doc_data.get("compressionAlgorithm", "")

    if not download_url:
        print(f"❌ URL не знайдено. Відповідь: {doc_data}")
        return []

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
        print(f"🔍 Структура: {type(data).__name__}, ключі: {list(data.keys()) if isinstance(data, dict) else 'list'}")

        # SQP звіт повертає {"dataByAsin": [...]} або просто список
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = (data.get("dataByAsin") or
                      data.get("searchQueryPerformanceByAsin") or
                      data.get("searchTerms") or
                      data.get("data") or
                      [])
        else:
            records = []

        print(f"✅ Завантажено {len(records)} записів [{market}]")
        if records:
            print(f"🔍 Перший запис (ключі): {list(records[0].keys()) if isinstance(records[0], dict) else records[0]}")
        return records

    except Exception as e:
        print(f"❌ Помилка парсингу: {e}")
        print(f"🔍 Raw preview: {content[:300]}")
        return []


def get_brand_analytics(market: str) -> list:
    """Головна функція — отримати SQP дані."""
    print(f"\n🔍 Brand Analytics (SQP) [{market}]...")
    try:
        token     = get_access_token(market)
        report_id = request_sqp_report(market, token)
        if not report_id:
            return []
        doc_id = wait_for_report(market, token, report_id)
        if not doc_id:
            return []
        return download_report(market, token, doc_id)
    except Exception as e:
        import traceback
        print(f"❌ Brand Analytics [{market}] помилка: {e}")
        traceback.print_exc()
        return []


def format_for_sheets(records: list, market: str) -> tuple:
    """Форматувати для Google Sheets."""
    headers = [
        "Період", "Search Term", "Search Frequency Rank",
        "Impressions", "Clicks", "Cart Adds", "Purchases",
        "Click Rate", "Purchase Rate",
        "#1 ASIN", "#1 Click Share", "#1 Conv Share",
        "#2 ASIN", "#2 Click Share", "#2 Conv Share",
        "#3 ASIN", "#3 Click Share", "#3 Conv Share",
        "Ринок"
    ]

    def format_period(rec):
        start = rec.get("startDate", "")
        end = rec.get("endDate", "")
        try:
            s = datetime.strptime(start, "%Y-%m-%d").strftime("%d.%m.%Y")
            e = datetime.strptime(end, "%Y-%m-%d").strftime("%d.%m.%Y")
            return f"{s}-{e}"
        except Exception:
            return f"{start}-{end}"

    rows = []

    for r in records:
        if not isinstance(r, dict):
            continue

        week = format_period(r)
        search_term = r.get("searchTerm") or r.get("query") or ""
        rank        = r.get("searchFrequencyRank") or r.get("rank") or ""
        impressions = r.get("impressions") or ""
        clicks      = r.get("clicks") or ""
        cart_adds   = r.get("cartAdds") or ""
        purchases   = r.get("purchases") or ""
        click_rate  = r.get("clickRate") or ""
        purch_rate  = r.get("purchaseRate") or ""

        top_asins = (r.get("topClickedAsins") or
                    r.get("topAsins") or
                    r.get("asins") or [])

        def get_asin(idx):
            if idx < len(top_asins) and isinstance(top_asins[idx], dict):
                a = top_asins[idx]
                return (
                    a.get("clickedAsin") or a.get("asin") or "",
                    a.get("clickSharePercentage") or a.get("clickShare") or "",
                    a.get("conversionSharePercentage") or a.get("conversionShare") or "",
                )
            return ("", "", "")

        a1, a2, a3 = get_asin(0), get_asin(1), get_asin(2)

        rows.append([
            week, search_term, rank,
            impressions, clicks, cart_adds, purchases,
            click_rate, purch_rate,
            a1[0], a1[1], a1[2],
            a2[0], a2[1], a2[2],
            a3[0], a3[1], a3[2],
            market
        ])

    rows.sort(key=lambda x: int(x[2]) if str(x[2]).isdigit() else 999999)
    return headers, rows


def check_report_status(market: str, token: str, report_id: str) -> dict:
    """Перевірити статус звіту ОДИН РАЗ (без очікування).
    Повертає {"status": "...", "document_id": "..." or None}
    """
    resp = requests.get(
        f"{SP_API_BASE}/reports/2021-06-30/reports/{report_id}",
        headers={"x-amz-access-token": token},
    )
    if resp.status_code != 200:
        print(f"❌ Помилка перевірки статусу [{market}]: {resp.status_code} {resp.text}")
        return {"status": "ERROR", "document_id": None}

    data = resp.json()
    status = data.get("processingStatus")
    document_id = data.get("reportDocumentId")
    print(f"⏳ Статус [{market}] report_id={report_id}: {status}")
    if status in ("FATAL", "CANCELLED"):
        print(f"🔍 DEBUG повна відповідь Amazon: {json.dumps(data, indent=2)}")
    return {"status": status, "document_id": document_id}


# ASIN для Search Catalog Performance в USA (щоб не тягнути весь каталог)
SEARCH_CATALOG_ASINS_USA = (
    "B0GYSJC1PM B0GYSB85SH B07TJW4Y94 B0G6VRGTPR B09NBB4QP7 "
    "B07ZTJM5WJ B0GCBCW8RK B0G5QB4W6N B0FGJVGNTK B0FGJST2KJ "
    "B0DHCR7D4W B09RBGJYXX B081T6QGD9 B07PTQKZ82"
)


def request_search_catalog_report(market: str, token: str) -> str:
    """Запросити Search Catalog Performance звіт.
    USA — з конкретним списком ASIN, CA — без ASIN (весь каталог).
    Повертає reportId."""
    marketplace_id = MARKETPLACE_IDS[market]
    start, end = get_previous_month_dates()

    print(f"📅 Search Catalog період (попередній місяць): {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")

    report_options = {"reportPeriod": "MONTH"}
    if market == "USA":
        report_options["asins"] = SEARCH_CATALOG_ASINS_USA
        print(f"🎯 USA: запит обмежено {len(SEARCH_CATALOG_ASINS_USA.split())} ASIN")
    else:
        print(f"🌐 {market}: запит без обмеження ASIN (увесь каталог)")

    payload = {
        "reportType": "GET_BRAND_ANALYTICS_SEARCH_CATALOG_PERFORMANCE_REPORT",
        "dataStartTime": start.strftime("%Y-%m-%dT00:00:00Z"),
        "dataEndTime":   end.strftime("%Y-%m-%dT23:59:59Z"),
        "reportOptions": report_options,
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
        print(f"❌ Помилка запиту Search Catalog [{market}]: {resp.status_code} {resp.text}")
        return None

    report_id = resp.json().get("reportId")
    print(f"📋 Search Catalog звіт запрошено [{market}]: {report_id}")
    return report_id


def format_search_catalog_for_sheets(records: list, market: str) -> tuple:
    """Форматувати Search Catalog Performance для Google Sheets."""
    headers = [
        "Період", "ASIN",
        "Impressions", "Clicks", "Click Rate",
        "Cart Adds", "Purchases", "Conversion Rate",
        "Ринок"
    ]

    rows = []

    for r in records:
        if not isinstance(r, dict):
            continue

        start = r.get("startDate", "")
        end = r.get("endDate", "")
        try:
            s = datetime.strptime(start, "%Y-%m-%d").strftime("%d.%m.%Y")
            e = datetime.strptime(end, "%Y-%m-%d").strftime("%d.%m.%Y")
            week = f"{s}-{e}"
        except Exception:
            week = f"{start}-{end}"

        asin = r.get("asin", "")

        impression_data = r.get("impressionData") or {}
        click_data       = r.get("clickData") or {}
        cart_add_data     = r.get("cartAddData") or {}
        purchase_data     = r.get("purchaseData") or {}

        impressions  = impression_data.get("impressionCount", "")
        clicks       = click_data.get("clickCount", "")
        click_rate   = click_data.get("clickRate", "")
        cart_adds    = cart_add_data.get("cartAddCount", "")
        purchases    = purchase_data.get("purchaseCount", "")
        conv_rate    = purchase_data.get("conversionRate", "")

        rows.append([
            week, asin,
            impressions, clicks, click_rate,
            cart_adds, purchases, conv_rate,
            market
        ])

    return headers, rows


# ASIN для Repeat Purchase Report — всі 14 активних товарів (флагмани нестабільні,
# тому беремо повний список замість жорсткого хардкоду 2-3 ASIN)
REPEAT_PURCHASE_ASINS = (
    "B0GYSJC1PM B0GYSB85SH B07TJW4Y94 B0G6VRGTPR B09NBB4QP7 "
    "B07ZTJM5WJ B0GCBCW8RK B0G5QB4W6N B0FGJVGNTK B0FGJST2KJ "
    "B0DHCR7D4W B09RBGJYXX B081T6QGD9 B07PTQKZ82"
)


def request_repeat_purchase_report(market: str, token: str) -> str:
    """Запросити Repeat Purchase Behaviour звіт для всіх 14 активних ASIN.
    reportPeriod=MONTH (порівняння QoQ/YoY робимо розрахунком поверх
    накопичених місячних даних, не окремим API-запитом).
    Повертає reportId."""
    marketplace_id = MARKETPLACE_IDS[market]
    start, end = get_previous_month_dates()

    print(f"📅 Repeat Purchase період (попередній місяць): {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")
    print(f"ℹ️ {market}: звіт по всьому бренду (asin параметр не підтримується цим reportType)")

    payload = {
        "reportType": "GET_BRAND_ANALYTICS_REPEAT_PURCHASE_REPORT",
        "dataStartTime": start.strftime("%Y-%m-%dT00:00:00Z"),
        "dataEndTime":   end.strftime("%Y-%m-%dT23:59:59Z"),
        "reportOptions": {
            "reportPeriod": "MONTH",
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
        print(f"❌ Помилка запиту Repeat Purchase [{market}]: {resp.status_code} {resp.text}")
        return None

    report_id = resp.json().get("reportId")
    print(f"📋 Repeat Purchase звіт запрошено [{market}]: {report_id}")
    return report_id


def format_repeat_purchase_for_sheets(records: list, market: str) -> tuple:
    """Форматувати Repeat Purchase Behaviour для Google Sheets.
    Реальна структура запису (перевірено на живих даних):
    {startDate, endDate, asin, orders, uniqueCustomers,
     repeatCustomersPctTotal, repeatPurchaseRevenue:{amount,currencyCode},
     repeatPurchaseRevenuePctTotal}
    """
    headers = [
        "Період", "ASIN",
        "Orders", "Unique Customers",
        "Repeat Customers %", "Repeat Purchase Revenue",
        "Repeat Purchase Revenue %",
        "Ринок"
    ]

    rows = []

    for r in records:
        if not isinstance(r, dict):
            continue

        start = r.get("startDate", "")
        end = r.get("endDate", "")
        try:
            s = datetime.strptime(start, "%Y-%m-%d").strftime("%d.%m.%Y")
            e = datetime.strptime(end, "%Y-%m-%d").strftime("%d.%m.%Y")
            period = f"{s}-{e}"
        except Exception:
            period = f"{start}-{end}"

        asin = r.get("asin", "")
        orders = r.get("orders", "")
        unique_customers = r.get("uniqueCustomers", "")

        repeat_pct = r.get("repeatCustomersPctTotal", "")
        if isinstance(repeat_pct, (int, float)):
            repeat_pct = round(repeat_pct * 100, 2)  # частка → відсоток

        revenue_data = r.get("repeatPurchaseRevenue") or {}
        revenue = revenue_data.get("amount", "") if isinstance(revenue_data, dict) else ""

        revenue_pct = r.get("repeatPurchaseRevenuePctTotal", "")
        if isinstance(revenue_pct, (int, float)):
            revenue_pct = round(revenue_pct * 100, 2)

        rows.append([
            period, asin,
            orders, unique_customers,
            repeat_pct, revenue, revenue_pct,
            market
        ])

    return headers, rows


def request_market_basket_report(market: str, token: str) -> str:
    """Запросити Market Basket Analysis звіт.
    reportOptions приймає ТІЛЬКИ reportPeriod (без asin/asins —
    Amazon поверне помилку, як і для Repeat Purchase).
    Повертає reportId."""
    marketplace_id = MARKETPLACE_IDS[market]
    start, end = get_previous_month_dates()

    print(f"📅 Market Basket період (попередній місяць): {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}")
    print(f"ℹ️ {market}: звіт по всьому бренду (asin параметр не підтримується цим reportType)")

    payload = {
        "reportType": "GET_BRAND_ANALYTICS_MARKET_BASKET_REPORT",
        "dataStartTime": start.strftime("%Y-%m-%dT00:00:00Z"),
        "dataEndTime":   end.strftime("%Y-%m-%dT23:59:59Z"),
        "reportOptions": {
            "reportPeriod": "MONTH",
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
        print(f"❌ Помилка запиту Market Basket [{market}]: {resp.status_code} {resp.text}")
        return None

    report_id = resp.json().get("reportId")
    print(f"📋 Market Basket звіт запрошено [{market}]: {report_id}")
    return report_id


def format_market_basket_for_sheets(records: list, market: str) -> tuple:
    """Форматувати Market Basket Analysis для Google Sheets.
    Реальна структура запису (з офіційної схеми Amazon):
    {startDate, endDate, asin, purchasedWithAsin, purchasedWithRank, combinationPct}
    По одному рядку на кожну комбінацію товарів (ранг 1-3 на ASIN).
    """
    headers = [
        "Період", "ASIN",
        "Purchased With ASIN", "Rank", "Combination %",
        "Ринок"
    ]

    rows = []

    for r in records:
        if not isinstance(r, dict):
            continue

        start = r.get("startDate", "")
        end = r.get("endDate", "")
        try:
            s = datetime.strptime(start, "%Y-%m-%d").strftime("%d.%m.%Y")
            e = datetime.strptime(end, "%Y-%m-%d").strftime("%d.%m.%Y")
            period = f"{s}-{e}"
        except Exception:
            period = f"{start}-{end}"

        asin = r.get("asin", "")
        purchased_with = r.get("purchasedWithAsin", "")
        rank = r.get("purchasedWithRank", "")

        combo_pct = r.get("combinationPct", "")
        if isinstance(combo_pct, (int, float)):
            combo_pct = round(combo_pct * 100, 2)

        rows.append([
            period, asin,
            purchased_with, rank, combo_pct,
            market
        ])

    return headers, rows
