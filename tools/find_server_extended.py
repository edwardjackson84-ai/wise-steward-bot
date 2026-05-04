import requests

TRADELOCKER_API_URL = "https://api.tradelocker.com"

servers = [
    "CRUC-Demo", "CRUC-Live", "CRUC Demo", "CRUC Live", 
    "CrucialMarkets-Demo", "CrucialMarkets-Live", "Crucial-Markets-Demo", "Crucial-Markets-Live",
    "Crucial Markets-Demo", "Crucial Markets-Live",
    "CrucialMarkets", "Crucial Markets", "crucial-demo", "crucial-live",
    "CRUC", "cruc"
]
email = "user@example.com"
password = "REDACTED"

found = False
for s in servers:
    print(f"Trying server: {s}")
    auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
    resp = requests.post(auth_url, json={"email": email, "password": password, "server": s}, headers={"Content-Type": "application/json"})
    
    if resp.ok:
        print(f"SUCCESS with server: {s}")
        found = True
        break
    else:
        # print(f"Failed: {resp.text}")
        pass

if not found:
    print("Could not find server string.")
