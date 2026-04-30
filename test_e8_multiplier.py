import sys, asyncio
sys.path.append('.')
from hankox_executor import get_active_configs, authenticate_tradelocker, execute_trade_rest

async def main():
    configs = get_active_configs()
    e8_cfg = next((c for c in configs if "e8tradelocker" in c["name"].lower()), None)
    if e8_cfg:
        token, acc_id, acc_num = authenticate_tradelocker(e8_cfg)
        res = await execute_trade_rest(token, acc_id, acc_num, "DOW+", "sell", 0.01, e8_cfg["api_url"], e8_cfg["name"], sl=200, tp=400)
        print(f"Trade result: {res}")

asyncio.run(main())
