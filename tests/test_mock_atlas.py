import requests
import json
import time

# Target the local Hanko X Executor
WEBHOOK_URL = "http://localhost:5001/webhook"

mock_payload = {
    "symbol": "US30",
    "action": "buy",
    "contracts": 0.01,
    "sl": 38000,
    "tp": 40000,
    "bypass_sabbath": "true",
    "comment": "Verification Test for Atlas Demo"
}

print(f"Sending mock signal to {WEBHOOK_URL}...")
try:
    # Ensure Atlas Demo is marked as active in its .env for the executor to pick it up
    # (The executor reads env files on each webhook hit if it's coded that way or we restart it)
    
    resp = requests.post(WEBHOOK_URL, json=mock_payload, headers={"Content-Type": "application/json"}, timeout=5)
    print(f"Response Status: {resp.status_code}")
    print(f"Response Body: {resp.text}")
except Exception as e:
    print(f"Error sending webhook: {e}")
