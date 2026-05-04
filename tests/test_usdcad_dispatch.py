import sys, asyncio, traceback
sys.path.append('.')
from hankox_executor import get_active_configs, authenticate_tradelocker, execute_trade_rest, _ROUTE_CACHE

async def test_dispatch():
    _ROUTE_CACHE.clear()
    configs = get_active_configs()
    for cfg in configs:
        if "atlas" in cfg["name"] or "e8" in cfg["name"]:
            token, acc_id, acc_num = authenticate_tradelocker(cfg)
            print(f"Testing {cfg['name']} - accId: {acc_id}, accNum: {acc_num}")
            try:
                res = await execute_trade_rest(token, acc_id, acc_num, "USDCAD", "sell", 0.01, cfg["api_url"], cfg["name"], sl=200, tp=400)
                print(f"[{cfg['name']}] SUCCESS: {res}")
            except Exception as e:
                print(f"[{cfg['name']}] EXCEPTION: {e}")

asyncio.run(test_dispatch())
