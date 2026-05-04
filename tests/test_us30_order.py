import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

from tradelocker_executor import authenticate, TRADELOCKER_API_URL

def test():
    print("Authenticating...")
    token, acc_id, acc_num = authenticate()
    order_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/orders"
    headers = {
        "Authorization": f"Bearer {token}", 
        "accNum": str(acc_num), 
        "Content-Type": "application/json"
    }
    
    payload = {
        "tradableInstrumentId": 17028, # US30 ID
        "qty": 0.01,
        "side": "buy",
        "type": "market",
        "validity": "IOC"
    }
    print("Sending payload:", json.dumps(payload, indent=2))
    resp = requests.post(order_url, json=payload, headers=headers)
    
    print("\n--- Response ---")
    print("Status Code:", resp.status_code)
    try:
        print(json.dumps(resp.json(), indent=2))
    except:
        print(resp.text)

if __name__ == "__main__":
    test()
