import requests, json
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


def main():
    token = get_token()
    print("✅ Токен отримано")

    url = f"{ADS_BASE_URL}/sb/v4/campaigns/list"
    headers = {
        "Authorization": f"Bearer {token}",
        "Amazon-Advertising-API-ClientId": ADS_CLIENT_ID,
        "Amazon-Advertising-API-Scope": str(ADS_PROFILE_ID_USA),
        "Content-Type": "application/vnd.sbcampaignresource.v4+json",
        "Accept": "application/vnd.sbcampaignresource.v4+json",
    }
    payload = {"stateFilter": {"include": ["ENABLED", "PAUSED"]}}

    resp = requests.post(url, headers=headers, json=payload)
    print(f"\n📥 Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"❌ Тіло відповіді: {resp.text}")
        return

    data = resp.json()
    campaigns = data.get("campaigns", [])
    print(f"\n✅ Знайдено {len(campaigns)} SB кампаній:\n")

    for c in campaigns:
        name = c.get("name", "")
        multi = c.get("isMultiAdGroupsEnabled", "невідомо")
        state = c.get("state", "")
        cid = c.get("campaignId", "")
        print(f"  '{name}' | state={state} | isMultiAdGroupsEnabled={multi} | id={cid}")


if __name__ == "__main__":
    main()
