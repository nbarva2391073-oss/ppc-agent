import requests
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


token = get_token()
rid = "3bb78c36-6f3a-4ada-b90c-a413ac9c59f1"

resp = requests.get(
    f"{ADS_BASE_URL}/reporting/reports/{rid}",
    headers={
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
        "Amazon-Advertising-API-Scope": str(ADS_PROFILE_ID_USA),
    },
)
data = resp.json()
print(f"status={data.get('status')}")
print(f"url={'є' if data.get('url') else 'немає'}")
print(f"fileSize={data.get('fileSize')}")
