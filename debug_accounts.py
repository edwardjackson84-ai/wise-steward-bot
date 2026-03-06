import requests
import json

TRADELOCKER_API_URL = "https://demo.tradelocker.com/backend-api"
email = "edward.jackson84@gmail.com"
password = "v&LA2LWmN5kG"
server = "CRUC"

auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
resp = requests.post(auth_url, json={"email": email, "password": password, "server": server}, headers={"Content-Type": "application/json"})

if resp.ok:
    token = resp.json().get("accessToken")
    acc_url = f"{TRADELOCKER_API_URL}/trade/accounts"
    
    # Try getting accounts
    acc_resp = requests.get(acc_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    print("GET /trade/accounts status:", acc_resp.status_code)
    try:
        print(json.dumps(acc_resp.json(), indent=2))
    except:
        print(acc_resp.text)
        
    # Also try the B2B endpoint with the demo web token, just in case
    b2b_url = "https://api.tradelocker.com/trade/accounts"
    b2b_resp = requests.get(b2b_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    print("\nGET api.tradelocker.com/trade/accounts status:", b2b_resp.status_code)
    try:
        print(json.dumps(b2b_resp.json(), indent=2))
    except:
        print(b2b_resp.text)
