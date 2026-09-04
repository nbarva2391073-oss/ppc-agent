import requests
from config import (
    ADS_CLIENT_ID, ADS_CLIENT_SECRET, ADS_REFRESH_TOKEN,
    ADS_PROFILE_ID_USA,
)

ADS_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
ADS_BASE_URL  = "https://advertising-api.amazon.com"

OLD_REPORT_IDS = [
    "a21035b1-1045-4dad-9a00-6f713e62772f",  # SB Campaign, перший тест
    "aaec1410-d234-431e-aadb-83df84dd00a9",  # SB Search Term, перший тест
    "3bb78c36-6f3a-4ada-b90c-a413ac9c59f1",  # SB Campaign, останній тест
]


def get_token():
    r = requests.post(ADS_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": ADS_REFRESH_TOKEN,
        "client_id": ADS_CLIENT_ID,
        "client_secret": ADS_CLIENT_SECRET,
    })
    return r.json()["access_token"]


token = get_token()
print("✅ Токен отримано\n")

for rid in OLD_REPORT_IDS:
    resp = requests.get(
        f"{ADS_BASE_URL}/reporting/reports/{rid}",
        headers={
            "Authorization": f"Bearer {token}",
            "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
            "Amazon-Advertising-API-Scope": str(ADS_PROFILE_ID_USA),
        },
    )
    print(f"report_id={rid}")
    print(f"  status_code={resp.status_code}")
    print(f"  body={resp.text[:400]}")
    print()
