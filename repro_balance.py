import os
import requests
import json
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_auth_token():
    api_url  = os.environ.get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api")
    email    = os.environ.get("TRADELOCKER_EMAIL")
    password = os.environ.get("TRADELOCKER_PASSWORD")
    server   = os.environ.get("TRADELOCKER_SERVER")
    print(f"DEBUG AUTH: api_url={api_url}, email={email}, server={server}")
    if not email or not password or not server:
        return None, None
    try:
        url = f"{api_url}/auth/jwt/token"
        resp = requests.post(url, json={"email": email, "password": password, "server": server},
                             headers={"accept": "application/json", "Content-Type": "application/json"}, timeout=8)
        if resp.ok:
            return resp.json().get("accessToken"), api_url
        else:
            print(f"DEBUG AUTH FAIL: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"DEBUG AUTH ERROR: {e}")
    return None, None

def test_metrics(env_file):
    print(f"\n--- Testing env file: {env_file} ---")
    # Clear relevant env vars
    vars_to_clear = [
        "HANKOX_EMAIL", "HANKOX_PASSWORD", "HANKOX_SERVER",
        "TRADELOCKER_API_URL", "TRADELOCKER_EMAIL", "TRADELOCKER_PASSWORD", "TRADELOCKER_SERVER", "TRADELOCKER_ACCOUNT_ID"
    ]
    for v in vars_to_clear:
        if v in os.environ:
            del os.environ[v]
            
    load_dotenv(os.path.join(BASE_DIR, env_file), override=True)
    
    target_id = os.environ.get("TRADELOCKER_ACCOUNT_ID")
    token, api_url = get_auth_token()
    if not token:
        print("Failed to get token")
        return

    try:
        url = f"{api_url}/auth/jwt/all-accounts"
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.ok:
            accounts = resp.json().get("accounts", [])
            found = False
            for acct in accounts:
                if str(acct.get("id")) == str(target_id):
                    balance = acct.get("accountBalance")
                    print(f"SUCCESS: Found account {target_id}, Balance: {balance}")
                    found = True
                    break
            if not found:
                print(f"FAILED: Account {target_id} not found in {len(accounts)} accounts")
                for a in accounts:
                    print(f" - Found ID: {a.get('id')} Name: {a.get('name')}")
        else:
            print(f"FAILED: all-accounts request failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_metrics(".env.atlasdemo")
    test_metrics(".env.crucialdemo")
