import requests, json
from dotenv import dotenv_values

def get_ticks(env_file, symbol_id, route_id):
    vals = dotenv_values(env_file)
    api_url = vals.get("TRADELOCKER_API_URL")
    acc_num = vals.get("TRADELOCKER_ACCNUM", "1" if "e8" in env_file.lower() else "1")

    resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
    token = resp.json().get("accessToken")
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}

    r1 = requests.get(f"{api_url}/trade/instruments/{symbol_id}?routeId={route_id}", headers=headers)
    if r1.ok:
        data = r1.json().get("d", {})
        print(f"[{env_file}] {data.get('name')} tickSize:")
        print(json.dumps(data.get("tickSize", []), indent=2))
    else:
        print(f"[{env_file}] Failed to get inst {symbol_id}: {r1.status_code}")

# Atlas US30 (16337, 1402944)
get_ticks(".env.atlasdemo", 16337, 1402944)
# E8 US30 (6107, 948735)
get_ticks(".env.e8tradelocker", 6107, 948735)
# E8 EURUSD (6051)
get_ticks(".env.e8tradelocker", 6051, 948735) # guessing routeId, let's just get routeId first
