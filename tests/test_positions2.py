import requests
from tradelocker_executor import authenticate, TRADELOCKER_API_URL

try:
    token, account_id, acc_num = authenticate()
    pos_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/positions"
    pos_resp = requests.get(pos_url, headers={
        "Authorization": f"Bearer {token}",
        "accNum": str(acc_num)
    })
    print(f"Status: {pos_resp.status_code}")
    print(pos_resp.text[:500])
except Exception as e:
    print(e)
