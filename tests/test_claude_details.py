import requests, json
from dotenv import dotenv_values

def get_detail(env_file, symbol_id, route_id):
    vals = dotenv_values(env_file)
    api_url = vals.get("TRADELOCKER_API_URL")
    acc_num = vals.get("TRADELOCKER_ACCNUM", "1" if "e8" in env_file.lower() else "1")

    resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
    token = resp.json().get("accessToken")
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}

    r1 = requests.get(f"{api_url}/trade/instruments/{symbol_id}?routeId={route_id}", headers=headers)
    print(f"\n--- {env_file} ---")
    print(json.dumps(r1.json(), indent=2))

get_detail(".env.atlasdemo", 16337, 1402944)
get_detail(".env.e8tradelocker", 6107, 948735)
