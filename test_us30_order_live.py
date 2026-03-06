import requests
import json

TRADELOCKER_API_URL = "https://api.tradelocker.com"
email = "edward.jackson84@gmail.com"
password = "v&LA2LWmN5kG"
server = "Hankotrade-Demo"

def test():
    auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
    resp = requests.post(auth_url, json={"email": email, "password": password, "server": server}, headers={"Content-Type": "application/json"})
    
    if not resp.ok:
        print("Auth failed.")
        return
        
    token = resp.json().get("accessToken")
    acc_url = f"{TRADELOCKER_API_URL}/trade/accounts"
    acc_resp = requests.get(acc_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    
    accounts = acc_resp.json().get("accounts", [])
    if not accounts:
        print("No accounts")
        return
        
    acc_id = accounts[0].get("id")
    acc_num = accounts[0].get("accNum", "1")
    
    order_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/orders"
    headers = {
        "Authorization": f"Bearer {token}", 
        "accNum": str(acc_num), 
        "Content-Type": "application/json"
    }
    
    # 49000.0 price is just for show, let's use a real payload similar to what TV sends
    # e.g., market buy of 0.01 lot of US30 with SL 10 points below and TP 20 points above
    # Current US30 is around 49450
    sl = 49440.0
    tp = 49480.0
    
    payload = {
        "tradableInstrumentId": 17028, # US30 ID for Hankotrade Live
        "qty": 0.01,
        "side": "buy",
        "type": "market",
        "validity": "IOC",
        "stopLoss": sl,
        "stopLossType": "absolute",
        "takeProfit": tp,
        "takeProfitType": "absolute"
    }
    print("Sending payload:", json.dumps(payload, indent=2))
    order_resp = requests.post(order_url, json=payload, headers=headers)
    
    print("\n--- Response ---")
    print("Status Code:", order_resp.status_code)
    try:
        print(json.dumps(order_resp.json(), indent=2))
    except:
        print(order_resp.text)

if __name__ == "__main__":
    test()
