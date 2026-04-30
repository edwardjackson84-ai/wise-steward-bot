import sys, asyncio, requests
sys.path.append('.')
from hankox_executor import get_active_configs, authenticate_tradelocker

configs = get_active_configs()

for cfg in configs:
    if "atlas" in cfg["name"] or "e8" in cfg["name"]:
        token, acc_id, acc_num = authenticate_tradelocker(cfg)
        headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
        
        # 1. Fetch instruments
        url = f"{cfg['api_url']}/trade/accounts/{acc_id}/instruments"
        resp = requests.get(url, headers=headers)
        if not resp.ok:
            print(f"[{cfg['name']}] Failed to fetch instruments: {resp.status_code}")
            continue
            
        data = resp.json().get("d", {}).get("instruments", [])
        found = False
        for inst in data:
            if inst.get("name") == "USDCAD":
                found = True
                inst_id = inst.get("tradableInstrumentId")
                routes = inst.get("routes", [])
                print(f"[{cfg['name']}] Found USDCAD. ID: {inst_id}. Routes: {len(routes)}")
                for r in routes:
                    if r.get("type") == "TRADE":
                        route_id = r.get("id")
                        detail_url = f"{cfg['api_url']}/trade/instruments/{inst_id}?routeId={route_id}"
                        det_resp = requests.get(detail_url, headers=headers)
                        schedule = det_resp.json().get("d", {}).get("tickSize", [])
                        print(f"  -> Route {route_id} Schedule: {schedule}")
        if not found:
            print(f"[{cfg['name']}] USDCAD NOT FOUND")
