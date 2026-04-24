import requests
import json

TRADELOCKER_API_URL = "https://demo.tradelocker.com/backend-api"
email = "edward.jackson84@gmail.com"
password = "BfA6c{#USpng"
server = "ATLAS"

auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
payload = {"email": email, "password": password, "server": server}
headers = {"Content-Type": "application/json"}

resp = requests.post(auth_url, json=payload, headers=headers)
if resp.ok:
    token = resp.json().get("accessToken")
    acc_id = "1900606"
    acc_num = "7"
    inst_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/instruments"
    inst_resp = requests.get(inst_url, headers={"Authorization": f"Bearer {token}", "accNum": str(acc_num)})
    
    if inst_resp.ok:
        data = inst_resp.json()
        instruments = data.get("d", []) if isinstance(data, dict) else data
        if isinstance(instruments, dict) and "instruments" in instruments:
            instruments = instruments["instruments"]
        
        print(f"Atlas Account 1900606 ALL Mappings:")
        for inst in instruments:
            name = inst.get("name", "").upper()
            sym = inst.get("symbol", "").upper()
            iid = inst.get("tradableInstrumentId")
            print(f"   - {name} / {sym}: {iid}")
