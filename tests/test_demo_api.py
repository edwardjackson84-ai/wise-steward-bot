import requests
import json

TRADELOCKER_API_URL = "https://demo.tradelocker.com/backend-api"
email = "user@example.com"
password = "REDACTED"
server = "CRUC"

auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
resp = requests.post(auth_url, json={"email": email, "password": password, "server": server}, headers={"Content-Type": "application/json"})

print(f"Status: {resp.status_code}")
try:
    print(json.dumps(resp.json(), indent=2))
except:
    print(resp.text)
