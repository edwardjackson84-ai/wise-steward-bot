import sys, requests
sys.path.append('.')
from hankox_executor import get_active_configs, authenticate_tradelocker

configs = get_active_configs()

for cfg in configs:
    if "e8" in cfg["name"]:
        token, acc_id, acc_num = authenticate_tradelocker(cfg)
        headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
        
        url = f"{cfg['api_url']}/trade/accounts/{acc_id}/instruments"
        resp = requests.get(url, headers=headers)
        data = resp.json().get("d", {}).get("instruments", [])
        for inst in data:
            name = str(inst.get("name")).upper()
            if "USD" in name and "CAD" in name:
                print(f"[{cfg['name']}] Found possible match: {inst.get('name')} (ID: {inst.get('tradableInstrumentId')})")
