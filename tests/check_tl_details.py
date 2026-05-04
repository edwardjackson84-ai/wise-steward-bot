import requests, json
from dotenv import dotenv_values

vals = dotenv_values(".env.atlasdemo")
api_url = vals.get("TRADELOCKER_API_URL")
acc_id = vals.get("TRADELOCKER_ACCOUNT_ID")

resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
token = resp.json().get("accessToken")
headers = {"Authorization": f"Bearer {token}", "accNum": "6"}

r1 = requests.get(f"{api_url}/trade/accounts/{acc_id}/instruments/16337", headers=headers)
print("r1", r1.status_code, r1.text)

r2 = requests.get(f"{api_url}/trade/instruments/16337", headers=headers)
print("r2", r2.status_code, r2.text)

