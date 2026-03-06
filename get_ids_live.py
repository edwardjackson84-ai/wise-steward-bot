import requests

TRADELOCKER_API_URL = "https://api.tradelocker.com"
email = "edward.jackson84@gmail.com"
password = "v&LA2LWmN5kG"
server = "Hankotrade-Live"

auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
resp = requests.post(auth_url, json={"email": email, "password": password, "server": server}, headers={"Content-Type": "application/json"})

if resp.ok:
    token = resp.json().get("accessToken")
    acc_url = f"{TRADELOCKER_API_URL}/trade/accounts"
    acc_resp = requests.get(acc_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    
    if acc_resp.ok:
        accounts = acc_resp.json().get("accounts", [])
        if accounts:
            acc_id = accounts[0].get("id")
            acc_num = accounts[0].get("accNum", "1")
            inst_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/instruments"
            inst_resp = requests.get(inst_url, headers={"Authorization": f"Bearer {token}", "accNum": str(acc_num), "Content-Type": "application/json"})
            
            if inst_resp.ok:
                data = inst_resp.json()
                instruments = data.get("d", []) if isinstance(data, dict) else data
                if isinstance(instruments, dict) and "instruments" in instruments:
                    instruments = instruments["instruments"]
                
                targets = ["US30", "NAS100", "SPX", "EURUSD", "GBPUSD", "XAUUSD", "BTCUSD"]
                for inst in instruments:
                    if isinstance(inst, dict):
                        name = inst.get("name", "").upper()
                        sym = inst.get("symbol", "").upper()
                        inst_id = inst.get("tradableInstrumentId")
                        if any(t in name or t in sym for t in targets):
                            print(f"{name} ({sym}): {inst_id}")
            else:
                print("Failed to fetch instruments:", inst_resp.text)
        else:
            print("No accounts found.")
    else:
        print("Failed to fetch accounts:", acc_resp.text)
else:
    print("Auth failed:", resp.text)
