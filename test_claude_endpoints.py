import requests, json
from dotenv import dotenv_values

def test_api(env_file, symbol_id, route_id):
    print(f"\n--- Testing {env_file} (Inst {symbol_id}) ---")
    vals = dotenv_values(env_file)
    api_url = vals.get("TRADELOCKER_API_URL")
    acc_id = vals.get("TRADELOCKER_ACCOUNT_ID")
    acc_num = vals.get("TRADELOCKER_ACCNUM", "1" if "e8" in env_file.lower() else "1")

    resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
    token = resp.json().get("accessToken")
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}

    # 1. Detail endpoint with routeId query param
    r1 = requests.get(f"{api_url}/trade/instruments/{symbol_id}?routeId={route_id}", headers=headers)
    print("1. /trade/instruments/{id}?routeId :", r1.status_code, r1.text[:100])

    r1a = requests.get(f"{api_url}/trade/accounts/{acc_id}/instruments/{symbol_id}?routeId={route_id}", headers=headers)
    print("1a. /trade/accounts/{id}/instruments/{id}?routeId :", r1a.status_code, r1a.text[:100])

    # 2. Detail and Info endpoints
    r2 = requests.get(f"{api_url}/trade/instruments/{symbol_id}/details", headers=headers)
    print("2. /trade/instruments/{id}/details :", r2.status_code, r2.text[:100])
    
    r3 = requests.get(f"{api_url}/trade/instruments/{symbol_id}/info", headers=headers)
    print("3. /trade/instruments/{id}/info :", r3.status_code, r3.text[:100])

    # 3. Fetch quotes (if available in REST API, usually TradeLocker uses WebSockets for quotes but let's try)
    r4 = requests.get(f"{api_url}/trade/accounts/{acc_id}/quotes", headers=headers)
    print("4. /trade/accounts/{id}/quotes :", r4.status_code, r4.text[:100])
    
    r5 = requests.get(f"{api_url}/trade/quotes?tradableInstrumentIds={symbol_id}", headers=headers)
    print("5. /trade/quotes?ids={id} :", r5.status_code, r5.text[:100])

test_api(".env.atlasdemo", 16337, 1402944)
test_api(".env.e8tradelocker", 6107, 948735)

