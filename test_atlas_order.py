import requests, json
from dotenv import dotenv_values
vals = dotenv_values(".env.atlasdemo")
api_url = vals.get("TRADELOCKER_API_URL")
acc_id = vals.get("TRADELOCKER_ACCOUNT_ID")
resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
token = resp.json().get("accessToken")

# Try to get instruments
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "accNum": str(acc_id)}
inst_resp = requests.get(f"{api_url}/trade/accounts/{acc_id}/instruments", headers=headers)
if not inst_resp.ok:
    print(f"Inst fetch failed: {inst_resp.text}")
    # Try with accNum: 1
    headers["accNum"] = "1"
    inst_resp = requests.get(f"{api_url}/trade/accounts/{acc_id}/instruments", headers=headers)
    print(f"Inst fetch with accNum=1: {inst_resp.text[:100]}")

route_id = None
for inst in inst_resp.json().get("d", {}).get("instruments", []):
    if str(inst.get("tradableInstrumentId")) == "16337":
        route_id = next((r.get("id") for r in inst.get("routes", []) if r.get("type") == "TRADE"), None)
        break

order_payload = {
    "price": 0, "qty": 0.01, "side": "sell", "type": "market", "tradableInstrumentId": 16337, "routeId": route_id, 
    "validity": "IOC", "stopLossType": "offset", "takeProfitType": "offset",
    "stopLoss": 200, "takeProfit": 400
}
resp = requests.post(f"{api_url}/trade/accounts/{acc_id}/orders", json=order_payload, headers=headers)
print(resp.status_code, resp.text)
