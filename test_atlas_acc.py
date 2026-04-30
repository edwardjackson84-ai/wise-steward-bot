import requests, json
from dotenv import dotenv_values
vals = dotenv_values(".env.atlasdemo")
api_url = vals.get("TRADELOCKER_API_URL")
resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
token = resp.json().get("accessToken")
headers = {"Authorization": f"Bearer {token}"}
acc_resp = requests.get(f"{api_url}/trade/accounts", headers=headers)
print(acc_resp.text)
