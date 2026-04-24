import os
import requests
import json
from dotenv import dotenv_values

def get_positions():
    vals = dotenv_values("/Users/edwardjackson/.gemini/antigravity/scratch/.agent/skills/wise_steward/.env.atlasdemo")
    api_url = vals.get("TRADELOCKER_API_URL")
    
    # 1. Auth
    resp = requests.post(
        f"{api_url}/auth/jwt/token",
        json={
            "email": vals.get("TRADELOCKER_EMAIL"),
            "password": vals.get("TRADELOCKER_PASSWORD"),
            "server": vals.get("TRADELOCKER_SERVER")
        },
        headers={"Content-Type": "application/json"}
    )
    
    if not resp.ok:
        print("Auth failed", resp.text)
        return
        
    token = resp.json().get("accessToken")
    acc_id = vals.get("TRADELOCKER_ACCOUNT_ID")
    
    # Get Account Num
    resp = requests.get(f"{api_url}/auth/jwt/all-accounts", headers={"Authorization": f"Bearer {token}"})
    accounts = resp.json().get("accounts", [])
    acc_num = None
    for a in accounts:
        if str(a.get("id")) == str(acc_id):
            acc_num = a.get("accNum")
            break
            
    print("Acc num:", acc_num)
    
    # 2. Get Orders
    pos_url = f"{api_url}/trade/accounts/{acc_id}/orders"
    headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(acc_num)
    }
    
    resp = requests.get(pos_url, headers=headers)
    if resp.ok:
        data = resp.json()
        print("Orders:")
        print(json.dumps(data, indent=2))
    else:
        print("Failed to get orders", resp.text)

if __name__ == "__main__":
    get_positions()
