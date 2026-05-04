import requests, json
from dotenv import dotenv_values
vals = dotenv_values(".env.e8tradelocker")
api_url = vals.get("TRADELOCKER_API_URL")
acc_id = vals.get("TRADELOCKER_ACCOUNT_ID")
resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
token = resp.json().get("accessToken")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "accNum": "1"}

order_payload = {
    "price": 0, "qty": 0.01, "side": "sell", "type": "market", "tradableInstrumentId": 6107, "routeId": 948735, 
    "validity": "IOC", "stopLossType": "offset", "takeProfitType": "offset",
    "stopLoss": 200, "takeProfit": 400
}
resp = requests.post(f"{api_url}/trade/accounts/{acc_id}/orders", json=order_payload, headers=headers)
print(resp.status_code, resp.text)
