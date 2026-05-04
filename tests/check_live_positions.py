import sys, asyncio, json, requests
sys.path.append('.')
from dotenv import dotenv_values
from hankox_executor import get_active_configs, authenticate_tradelocker

configs = get_active_configs()

for cfg in configs:
    if "e8tradelocker" in cfg["name"] or "atlas" in cfg["name"]:
        try:
            token, acc_id, acc_num = authenticate_tradelocker(cfg)
            headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
            url = f"{cfg['api_url']}/trade/accounts/{acc_id}/positions"
            resp = requests.get(url, headers=headers)
            if resp.ok:
                data = resp.json()
                positions = data.get("d", {}).get("positions", [])
                print(f"--- {cfg['name']} ---")
                print(f"Open Positions: {len(positions)}")
                for p in positions:
                    print(f"  {p.get('tradableInstrumentId')} {p.get('side')} Qty: {p.get('qty')} Price: {p.get('price')} SL: {p.get('stopLoss')} TP: {p.get('takeProfit')}")
            else:
                print(f"--- {cfg['name']} --- Failed to get positions: {resp.status_code}")
        except Exception as e:
            print(f"--- {cfg['name']} --- Exception: {e}")
