import sys, asyncio, json, traceback
sys.path.append('.')
from dotenv import dotenv_values
from hankox_executor import get_active_configs, authenticate_tradelocker, execute_trade_rest, _ROUTE_CACHE

async def test_cold_cache():
    _ROUTE_CACHE.clear()  # Ensure cold cache
    configs = get_active_configs()
    tasks = []
    for cfg in configs:
        if "atlas" in cfg["name"] or "e8" in cfg["name"]:
            token, acc_id, acc_num = authenticate_tradelocker(cfg)
            print(f"Testing {cfg['name']} - accId: {acc_id}, accNum: {acc_num}")
            # Mock US30 sell order
            try:
                res = await execute_trade_rest(token, acc_id, acc_num, "US30", "sell", 0.01, cfg["api_url"], cfg["name"], sl=200, tp=400)
                print(f"[{cfg['name']}] SUCCESS: {res}")
            except Exception as e:
                print(f"[{cfg['name']}] EXCEPTION: {e}")
                traceback.print_exc()

asyncio.run(test_cold_cache())
