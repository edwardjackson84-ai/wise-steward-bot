import requests
import json

TRADELOCKER_API_URL = "https://demo.tradelocker.com/backend-api"
email = "edward.jackson84@gmail.com"
password = "v&LA2LWmN5kG"
server = "CRUC"

auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
resp = requests.post(auth_url, json={"email": email, "password": password, "server": server}, headers={"Content-Type": "application/json"})

token = resp.json().get("accessToken")

# Try to get all accounts available for this email/server
endpoints_to_try = [
    f"{TRADELOCKER_API_URL}/auth/jwt/all-accounts",
    f"{TRADELOCKER_API_URL}/auth/jwt/accounts",
    f"{TRADELOCKER_API_URL}/trade/all-accounts",
    f"{TRADELOCKER_API_URL}/auth/jwt/token/accounts",
    f"{TRADELOCKER_API_URL}/trade/accounts?all=true"
]

print("Trying endpoints to find accounts...")
for endpoint in endpoints_to_try:
    print(f"\n--- Trying {endpoint} ---")
    req_resp = requests.get(endpoint, headers={"Authorization": f"Bearer {token}"})
    print(f"Status: {req_resp.status_code}")
    if req_resp.ok:
        try:
            print(json.dumps(req_resp.json(), indent=2))
        except:
            print(req_resp.text)
