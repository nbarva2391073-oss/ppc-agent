import requests, json, time
from config import (
    ADS_CLIENT_ID, ADS_CLIENT_SECRET, ADS_REFRESH_TOKEN,
    ADS_PROFILE_ID_USA,
)

ADS_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
ADS_BASE_URL  = "https://advertising-api.amazon.com"


def get_token():
    r = requests.post(ADS_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": ADS_REFRESH_TOKEN,
        "client_id": ADS_CLIENT_ID,
        "client_secret": ADS_CLIENT_SECRET,
    })
    return r.json()["access_token"]


def test_report(name, report_type_id, columns, group_by, token):
    print(f"\n{'='*50}")
    print(f"🔍 Тестуємо {report_type_id}")
    print(f"{'='*50}")

    payload = {
        "name": name,
        "startDate": "2026-08-25",
        "endDate": "2026-08-30",
        "configuration": {
            "adProduct": "SPONSORED_BRANDS",
            "groupBy": group_by,
            "columns": columns,
            "reportTypeId": report_type_id,
            "timeUnit": "SUMMARY",
            "format": "GZIP_JSON",
        },
    }

    resp = requests.post(
        f"{ADS_BASE_URL}/reporting/reports",
        headers={
            "Authorization": f"Bearer {token}",
            "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
            "Amazon-Advertising-API-Scope": str(ADS_PROFILE_ID_USA),
            "Content-Type": "application/json",
        },
        json=payload,
    )
    print(f"📥 Submit status: {resp.status_code}")
    print(f"   Body: {resp.text}")

    if resp.status_code != 202:
        return None
    return resp.json().get("reportId")


def check_status(report_id, token):
    for i in range(10):
        time.sleep(15)
        resp = requests.get(
            f"{ADS_BASE_URL}/reporting/reports/{report_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
                "Amazon-Advertising-API-Scope": str(ADS_PROFILE_ID_USA),
            },
        )
        data = resp.json()
        status = data.get("status")
        print(f"  ⏳ статус: {status}")
        if status in ("COMPLETED", "FAILED"):
            print(f"  Деталі: {json.dumps(data, indent=2)[:500]}")
            return
    print("  ⌛ timeout")


if __name__ == "__main__":
    token = get_token()
    print("✅ Токен отримано")

    rid1 = test_report(
        "SB Campaign Test", "sbCampaigns",
        ["campaignId", "campaignName", "campaignStatus", "impressions", "clicks", "cost", "sales", "purchases", "unitsSold", "newToBrandSales", "newToBrandPurchases"],
        ["campaign"], token,
    )
    if rid1:
        check_status(rid1, token)

    rid2 = test_report(
        "SB Search Term Test", "sbSearchTerm",
        ["campaignId", "campaignName", "adGroupName", "keywordText", "matchType", "searchTerm", "impressions", "clicks", "cost", "sales", "purchases", "unitsSold"],
        ["searchTerm"], token,
    )
    if rid2:
        check_status(rid2, token)
