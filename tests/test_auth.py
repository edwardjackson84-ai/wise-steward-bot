import requests
from dotenv import dotenv_values

vals = dotenv_values(".env.e8tradelocker")
auth_url = f"{vals.get('TRADELOCKER_API_URL')}/auth/jwt/token"
payload = {"email": vals.get("TRADELOCKER_EMAIL"), "password": vals.get("TRADELOCKER_PASSWORD"), "server": vals.get("TRADELOCKER_SERVER")}
resp = requests.post(auth_url, json=payload, headers={"Content-Type": "application/json"})
print(resp.json())
