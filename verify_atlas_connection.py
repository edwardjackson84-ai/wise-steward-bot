import requests
import json

# Atlas Demo Configuration
TRADELOCKER_API_URL = "https://demo.tradelocker.com/backend-api"
email = "edward.jackson84@gmail.com"
password = "BfA6c{#USpng"
server = "ATLAS"

print(f"Testing connection to Atlas Demo ({server})...")

auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
payload = {"email": email, "password": password, "server": server}
headers = {"Content-Type": "application/json"}

try:
    resp = requests.post(auth_url, json=payload, headers=headers)
    if resp.ok:
        token = resp.json().get("accessToken")
        print("✅ Auth Success! Token retrieved.")
        
        acc_url = f"{TRADELOCKER_API_URL}/auth/jwt/all-accounts"
        acc_resp = requests.get(acc_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        
        if acc_resp.ok:
            accounts = acc_resp.json().get("accounts", [])
            print(f"Found {len(accounts)} accounts.")
            for acc in accounts:
                print(f" - Account ID: {acc.get('id')} | Acc Num: {acc.get('accNum')} | Name: {acc.get('name')}")
                
            if accounts:
                acc_id = accounts[0].get("id")
                acc_num = accounts[0].get("accNum")
                inst_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/instruments"
                inst_resp = requests.get(inst_url, headers={
                    "Authorization": f"Bearer {token}",
                    "accNum": str(acc_num),
                    "Content-Type": "application/json"
                })
                
                if inst_resp.ok:
                    data = inst_resp.json()
                    instruments = data.get("d", []) if isinstance(data, dict) else data
                    if isinstance(instruments, dict) and "instruments" in instruments:
                        instruments = instruments["instruments"]
                    
                    print(f"Successfully fetched {len(instruments)} instruments.")
                    # Let's list a few key ones
                    targets = ["US30", "XAUUSD", "BTCUSD", "GBPUSD"]
                    for inst in instruments:
                        if isinstance(inst, dict):
                            sym = inst.get("symbol", "").upper()
                            if any(t in sym for t in targets):
                                print(f"   - {sym}: {inst.get('tradableInstrumentId')}")
                else:
                    print(f"❌ Failed to fetch instruments: {inst_resp.text}")
        else:
            print(f"❌ Failed to fetch accounts: {acc_resp.text}")
    else:
        print(f"❌ Auth Failed: {resp.status_code} - {resp.text}")

except Exception as e:
    print(f"❌ Connection Error: {e}")
