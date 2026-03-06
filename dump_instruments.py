import requests
import os
import getpass
from tradelocker_executor import TRADELOCKER_API_URL

def get_auth_from_env():
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v
    
    email = os.environ.get("TRADELOCKER_EMAIL")
    password = os.environ.get("TRADELOCKER_PASSWORD")
    server = os.environ.get("TRADELOCKER_SERVER", "Hankotrade-Live")
    return email, password, server

def authenticate_local():
    email, password, server = get_auth_from_env()
    if not email or not password:
        print("Missing credentials.")
        return None, None, None

    auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
    payload = {"email": email, "password": password, "server": server}
    headers = {"Content-Type": "application/json"}
    auth_response = requests.post(auth_url, json=payload, headers=headers)
    if not auth_response.ok:
        print("Auth failed.")
        return None, None, None

    token = auth_response.json().get("accessToken")
    acc_url = f"{TRADELOCKER_API_URL}/trade/accounts"
    acc_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    acc_response = requests.get(acc_url, headers=acc_headers)
    if not acc_response.ok:
        print("Account fetch failed.")
        return None, None, None
        
    accounts = acc_response.json().get("accounts", [])
    if not accounts:
        print("No accounts found.")
        return None, None, None
        
    acc = accounts[0]
    return token, acc.get("id"), acc.get("accNum", "1")

token, acc_id, acc_num = authenticate_local()
if not token:
    exit(1)

instruments_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/instruments"
headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num), "Content-Type": "application/json"}
response = requests.get(instruments_url, headers=headers)

if response.ok:
    data = response.json()
    instruments = data.get("d", []) if isinstance(data, dict) else data
    if isinstance(instruments, dict) and "instruments" in instruments:
        instruments = instruments["instruments"]
    
    matches = []
    for inst in instruments:
        if isinstance(inst, dict):
            name = inst.get("name", "")
            id_ = inst.get("tradableInstrumentId", "")
            matches.append(f"{name}: {id_}")
    
    with open("all_instruments.txt", "w") as f:
        f.write("\n".join(matches))
    print(f"Total instruments found: {len(matches)}")
else:
    print("Failed to fetch instruments:", response.text)
