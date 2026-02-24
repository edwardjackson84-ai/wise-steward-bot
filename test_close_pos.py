import requests
from tradelocker_executor import authenticate, TRADELOCKER_API_URL

try:
    token, account_id, acc_num = authenticate()
    pos_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/positions"
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
    
    # 1. Get positions
    resp = requests.get(pos_url, headers=headers)
    print(f"GET Positions Status: {resp.status_code}")
    
    data = resp.json()
    positions = []
    if isinstance(data, dict) and "d" in data:
        d = data["d"]
        positions = d.get("positions", []) if isinstance(d, dict) else d
    elif isinstance(data, list):
        positions = data

    print(f"Found {len(positions)} open positions.")
    
    # Let's look at the first position
    if positions:
        pos = positions[0]
        pos_id = pos.get("id")
        print(f"Attempting to close position ID: {pos_id} / Symbol: {pos.get('tradableInstrumentId')} / Side: {pos.get('side')}")
        
        close_url = f"{pos_url}/{pos_id}"
        print(f"DELETE URL: {close_url}")
        del_resp = requests.delete(close_url, headers=headers)
        print(f"DELETE Status: {del_resp.status_code}")
        print(f"DELETE Response: {del_resp.text}")
except Exception as e:
    print(f"Error: {e}")
