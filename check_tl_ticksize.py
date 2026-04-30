import requests, json
from dotenv import dotenv_values

vals = dotenv_values(".env.atlasdemo")
api_url = vals.get("TRADELOCKER_API_URL")
acc_id = vals.get("TRADELOCKER_ACCOUNT_ID")

resp = requests.post(f"{api_url}/auth/jwt/token", json={"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}, headers={"Content-Type": "application/json"})
token = resp.json().get("accessToken")
headers = {"Authorization": f"Bearer {token}", "accNum": "6"}

# Let's check /instruments
inst_resp = requests.get(f"{api_url}/trade/instruments", headers=headers)
print("trade/instruments:", inst_resp.status_code)
if inst_resp.ok:
    data = inst_resp.json()
    print("Keys:", data.keys())
    # find 16337
    for inst in data.get("d", {}).get("instruments", []):
        if inst.get("tradableInstrumentId") == 16337 or inst.get("id") == 16337:
            print(json.dumps(inst, indent=2))
            break
