import sys
import os
from dotenv import dotenv_values
import requests
import json

def fetch_config():
    vals = dotenv_values("/Users/edwardjackson/.gemini/antigravity/scratch/.agent/skills/wise_steward/.env.atlasdemo")
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
    
    config_url = f"{api_url}/trade/config"
    resp = requests.get(config_url, headers={"Authorization": f"Bearer {token}", "accNum": "1"})
    if resp.ok:
        data = resp.json()
        print("TradeLocker Config:\n")
        print(json.dumps(data, indent=2))
    else:
        print("Failed to fetch config:", resp.text)

if __name__ == "__main__":
    fetch_config()
