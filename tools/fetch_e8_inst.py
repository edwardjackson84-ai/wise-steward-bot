import requests
from dotenv import dotenv_values

def fetch_e8_instruments():
    vals = dotenv_values("/Users/edwardjackson/.gemini/antigravity/scratch/.agent/skills/wise_steward/.env.e8tradelocker")
    api_url = vals.get("TRADELOCKER_API_URL")
    
    resp = requests.post(
        f"{api_url}/auth/jwt/token",
        json={
            "email": vals.get("TRADELOCKER_EMAIL"),
            "password": vals.get("TRADELOCKER_PASSWORD"),
            "server": vals.get("TRADELOCKER_SERVER")
        },
        headers={"Content-Type": "application/json"}
    )
    token = resp.json().get("accessToken")
    acc_id = vals.get("TRADELOCKER_ACCOUNT_ID")
    
    inst_url = f"{api_url}/trade/accounts/{acc_id}/instruments"
    inst_resp = requests.get(inst_url, headers={"Authorization": f"Bearer {token}", "accNum": "1"})
    
    if inst_resp.ok:
        data = inst_resp.json()
        instruments = data.get("d", {}).get("instruments", [])
        for i in instruments[:30]:  # print first 30 to see format
            print(f"Name: {i.get('name')}, ID: {i.get('tradableInstrumentId')}, Type: {i.get('type')}")
            routes = i.get('routes', [])
            print(f"  Routes: {routes}")

if __name__ == "__main__":
    fetch_e8_instruments()
