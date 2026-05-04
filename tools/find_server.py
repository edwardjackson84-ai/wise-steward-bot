import requests

TRADELOCKER_API_URL = "https://api.tradelocker.com"

# Let's try to find the server name if CRUC doesn't work.
servers = ["CRUC", "CrucialMarkets", "Crucial-Demo", "CrucialMarkets-Demo", "CrucialMarkets-Live", "Crucial-Live"]
email = "user@example.com"
password = "REDACTED"

for s in servers:
    print(f"Trying server: {s}")
    auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
    resp = requests.post(auth_url, json={"email": email, "password": password, "server": s}, headers={"Content-Type": "application/json"})
    
    if resp.ok:
        print(f"SUCCESS with server: {s}")
        break
    else:
        print(f"Failed: {resp.text}")
