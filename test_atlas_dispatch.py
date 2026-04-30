import sys, asyncio
sys.path.append('.')
from hankox_executor import get_active_configs, place_market_orders_sync
configs = get_active_configs()
atlas_cfgs = [c for c in configs if "atlas" in c["name"].lower()]
print(f"Atlas configs: {[c['name'] for c in atlas_cfgs]}")
if atlas_cfgs:
    results = place_market_orders_sync(atlas_cfgs, "DOW+", "sell", 0.01, sl=200, tp=400, trade_id="TEST_ATLAS")
    print(f"Dispatch results: {results}")
