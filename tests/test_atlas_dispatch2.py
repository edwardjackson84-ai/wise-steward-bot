import sys, asyncio
sys.path.append('.')
from hankox_executor import get_active_configs, authenticate_tradelocker, execute_trade_rest

async def main():
    configs = get_active_configs()
    atlas_cfg = next((c for c in configs if "atlas" in c["name"].lower()), None)
    if atlas_cfg:
        token, acc_id, acc_num = authenticate_tradelocker(atlas_cfg)
        print(f"Auth: acc_num={acc_num}")
        res = await execute_trade_rest(token, acc_id, acc_num, "DOW+", "sell", 0.01, atlas_cfg["api_url"], atlas_cfg["name"], sl=200, tp=400)
        print(f"Trade result: {res}")

asyncio.run(main())
