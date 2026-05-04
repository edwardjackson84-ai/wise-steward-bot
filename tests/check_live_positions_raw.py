import sys, asyncio, json, requests
sys.path.append('.')
from dotenv import dotenv_values
from hankox_executor import get_active_configs, authenticate_tradelocker

configs = get_active_configs()

for cfg in configs:
    if "e8tradelocker" in cfg["name"]:
        token, acc_id, acc_num = authenticate_tradelocker(cfg)
        headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
        url = f"{cfg['api_url']}/trade/accounts/{acc_id}/positions"
        resp = requests.get(url, headers=headers)
        if resp.ok:
            data = resp.json()
            print(json.dumps(data.get("d", {}), indent=2))
        break
