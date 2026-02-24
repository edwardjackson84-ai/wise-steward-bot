import requests
from tradelocker_executor import authenticate, TRADELOCKER_API_URL

try:
    token, account_id, acc_num = authenticate()
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
    pos_id = "7277816997856580381"
    
    # 1. Try deleting /trade/positions/{pos_id}
    u1 = f"{TRADELOCKER_API_URL}/trade/positions/{pos_id}"
    print(f"DELETE {u1}")
    print(requests.delete(u1, headers=headers).text)

    # 2. Try deleting /trade/accounts/{account_id}/positions/{pos_id}
    u2 = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/positions/{pos_id}"
    print(f"DELETE {u2}")
    print(requests.delete(u2, headers=headers).text)

    # 3. Try with PATCH
    print(f"PATCH {u1}")
    print(requests.patch(u1, headers=headers, json={"qty": 0}).text)

except Exception as e:
    print(e)
