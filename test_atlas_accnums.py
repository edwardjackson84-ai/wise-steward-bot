import requests, json
from dotenv import dotenv_values
vals = dotenv_values(".env.atlasdemo")
api_url = vals.get("TRADELOCKER_API_URL")
resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
token = resp.json().get("accessToken")

for i in range(10):
    headers = {"Authorization": f"Bearer {token}", "accNum": str(i)}
    acc_resp = requests.get(f"{api_url}/trade/accounts", headers=headers)
    print(f"accNum={i}: {acc_resp.status_code} {acc_resp.text}")
