import requests
from dotenv import dotenv_values

def debug_atlas_accounts():
    env_file = "/Users/edwardjackson/.gemini/antigravity/scratch/.agent/skills/wise_steward/.env.atlasdemo"
    vals = dotenv_values(env_file)
    api_url = vals.get("TRADELOCKER_API_URL")
    email = vals.get("TRADELOCKER_EMAIL")
    password = vals.get("TRADELOCKER_PASSWORD")
    server = vals.get("TRADELOCKER_SERVER")
    target_id = vals.get("TRADELOCKER_ACCOUNT_ID")
    
    resp = requests.post(
        f"{api_url}/auth/jwt/token",
        json={"email": email, "password": password, "server": server},
        headers={"accept": "application/json", "Content-Type": "application/json"}
    )
    token = resp.json().get("accessToken")
    
    url = f"{api_url}/auth/jwt/all-accounts"
    headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
    acc_resp = requests.get(url, headers=headers)
    
    print(f"Target ID: {target_id}")
    for a in acc_resp.json().get("accounts", []):
        print(f"Account returned: ID={a.get('id')}, name={a.get('name')}")

if __name__ == "__main__":
    debug_atlas_accounts()
