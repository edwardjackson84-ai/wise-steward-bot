import requests
from dotenv import dotenv_values

def debug_tradelocker(env_file):
    vals = dotenv_values(env_file)
    api_url = vals.get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api")
    email = vals.get("TRADELOCKER_EMAIL")
    password = vals.get("TRADELOCKER_PASSWORD")
    server = vals.get("TRADELOCKER_SERVER")
    
    print(f"Testing {env_file}...")
    print(f"URL: {api_url}/auth/jwt/token")
    print(f"Email: {email}")
    print(f"Server: {server}")
    
    resp = requests.post(
        f"{api_url}/auth/jwt/token",
        json={"email": email, "password": password, "server": server},
        headers={"accept": "application/json", "Content-Type": "application/json"}
    )
    
    print(f"Status Code: {resp.status_code}")
    print(f"Response: {resp.text}\n")

if __name__ == "__main__":
    debug_tradelocker("/Users/edwardjackson/.gemini/antigravity/scratch/.agent/skills/wise_steward/.env.atlasdemo")
    debug_tradelocker("/Users/edwardjackson/.gemini/antigravity/scratch/.agent/skills/wise_steward/.env.e8tradelocker")
