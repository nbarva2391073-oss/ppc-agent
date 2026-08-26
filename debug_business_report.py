import requests, json, gzip, time
from config import (
    AMAZON_CLIENT_ID, AMAZON_CLIENT_SECRET,
    AMAZON_REFRESH_TOKEN_USA, MARKETPLACE_IDS,
)

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SP_API_BASE   = "https://sellingpartnerapi-na.amazon.com"

def get_token():
    r = requests.post(LWA_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": AMAZON_REFRESH_TOKEN_USA,
        "client_id": AMAZON_CLIENT_ID,
        "client_secret": AMAZON_CLIENT_SECRET,
    })
    return r.json()["access_token"]

def test_date(date, token):
    print(f"\n{'='*50}\n📅 Тестуємо дату: {date}\n{'='*50}")
    payload = {
        "reportType": "GET_SALES_AND_TRAFFIC_REPORT",
        "dataStartTime": f"{date}T00:00:00Z",
        "dataEndTime":   f"{date}T23:59:59Z",
        "reportOptions": {"dateGranularity": "DAY", "asinGranularity": "CHILD"},
        "marketplaceIds": [MARKETPLACE_IDS["USA"]],
    }
    resp = requests.post(
        f"{SP_API_BASE}/reports/2021-06-30/reports",
        headers={"x-amz-access-token": token, "Content-Type": "application/json"},
        json=payload,
    )
    if resp.status_code != 202:
        print(f"❌ Запит не пройшов: {resp.status_code} {resp.text}")
        return
    report_id = resp.json()["reportId"]
    print(f"✅ report_id={report_id}")

    for i in range(10):
        time.sleep(15)
        r = requests.get(
            f"{SP_API_BASE}/reports/2021-06-30/reports/{report_id}",
            headers={"x-amz-access-token": token},
        )
        data = r.json()
        status = data.get("processingStatus")
        print(f"  ⏳ статус: {status}")
        if status == "DONE":
            doc_id = data["reportDocumentId"]
            break
        if status in ("FATAL", "CANCELLED"):
            print(f"❌ {json.dumps(data, indent=2)}")
            return
    else:
        print("❌ timeout")
        return

    doc_resp = requests.get(
        f"{SP_API_BASE}/reports/2021-06-30/documents/{doc_id}",
        headers={"x-amz-access-token": token},
    )
    doc_data = doc_resp.json()
    file_resp = requests.get(doc_data["url"])
    content = (
        gzip.decompress(file_resp.content).decode("utf-8")
        if doc_data.get("compressionAlgorithm") == "GZIP"
        else file_resp.text
    )
    parsed = json.loads(content)
    print(f"🔍 Ключі верхнього рівня: {list(parsed.keys())}")
    print(f"🔍 Повний JSON (перші 2000 символів):\n{json.dumps(parsed, indent=2)[:2000]}")


if __name__ == "__main__":
    token = get_token()
    test_date("2026-07-06", token)  # день коли точно були дані
    test_date("2026-08-25", token)  # вчора, де 0 записів
