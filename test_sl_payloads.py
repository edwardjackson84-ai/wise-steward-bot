import requests, os, time
from tradelocker_executor import authenticate, TRADELOCKER_API_URL

def get_auth_from_env():
    env_file = ".env"
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k] = v

btc_id = 16720
price = 100000.0  # Safe high values for BTC
sl_price = 95000.0
tp_price = 110000.0

get_auth_from_env()
token, acc_id, acc_num = authenticate()
if not token:
    exit(1)

order_url = f"{TRADELOCKER_API_URL}/trade/accounts/{acc_id}/orders"
headers = {
    "Authorization": f"Bearer {token}",
    "accNum": str(acc_num),
    "Content-Type": "application/json"
}

def place(test_name, extra_payload):
    payload = {
        "tradableInstrumentId": btc_id,
        "qty": 0.01,
        "side": "buy",
        "type": "market",
        "validity": "IOC",
        "routeId": 1555930
    }
    payload.update(extra_payload)
    print(f"\n--- Testing: {test_name} ---")
    resp = requests.post(order_url, json=payload, headers=headers)
    if resp.ok:
        data = resp.json()
        print("Success! Response:")
        print(data)
        # Try to see if SL was saved by fetching positions immediately
        pos_id = data.get("positionId")
        if pos_id:
            pass # We could check but let's just dump
    else:
        print("Failed:", resp.text)
    time.sleep(1)

# Test 1: Current
place("Test 1: stopLoss & stopLossType", {
    "stopLoss": sl_price, "stopLossType": "absolute",
    "takeProfit": tp_price, "takeProfitType": "absolute"
})

# Test 2: Just stopLoss
place("Test 2: stopLoss only", {
    "stopLoss": sl_price, 
    "takeProfit": tp_price
})

# Test 3: stopLossPrice
place("Test 3: stopLossPrice", {
    "stopLossPrice": sl_price, 
    "takeProfitPrice": tp_price
})

# Test 4: nested value
place("Test 4: Nested Object", {
    "stopLoss": {"type": "absolute", "value": sl_price},
    "takeProfit": {"type": "absolute", "value": tp_price}
})
