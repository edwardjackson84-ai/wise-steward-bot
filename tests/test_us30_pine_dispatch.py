import sys, asyncio
sys.path.insert(0, '.')
from hankox_executor import (
    get_active_configs, authenticate_tradelocker,
    execute_trade_rest, _ROUTE_CACHE,
    _get_asset_class, resolve_offset, SYMBOL_MAP
)

# Exact Pine Script payload as built by f_json() in wise_steward_master.pine
# sl_points and tp_points are pre-computed by Pine: abs(price - sl)
PINE_PAYLOAD = {
    "action":    "entry",
    "strategy":  "King David Multi-TF",
    "symbol":    "US30",
    "tf":        "15",
    "side":      "sell",
    "price":     40000,
    "sl":        40300,     # absolute SL price level
    "tp":        39870,     # absolute TP price level
    "sl_points": 300.0,     # pre-computed by Pine
    "tp_points": 130.0,     # pre-computed by Pine
}

async def test():
    _ROUTE_CACHE.clear()
    configs = get_active_configs()
    
    data = dict(PINE_PAYLOAD)
    symbol = SYMBOL_MAP.get(data.get("symbol", "UNKNOWN").upper(), data.get("symbol", "UNKNOWN").upper())
    side   = data.get("side", "sell").lower()
    price_val = float(data.get("price", 0))

    sl = resolve_offset(symbol, side, 'sl', data, price_val)
    tp = resolve_offset(symbol, side, 'tp', data, price_val)

    print(f"\n[RESOLVED] symbol={symbol} side={side} sl_distance={sl} tp_distance={tp}")
    print(f"           Expected:  sl=300.0, tp=130.0\n")

    assert abs(sl - 300.0) < 0.001, f"SL wrong: {sl}"
    assert abs(tp - 130.0) < 0.001, f"TP wrong: {tp}"
    print("Resolution assertions passed! Now dispatching to brokers...\n")

    for cfg in configs:
        if "atlas" in cfg["name"] or "e8" in cfg["name"]:
            token, acc_id, acc_num = authenticate_tradelocker(cfg)
            print(f"Dispatching to {cfg['name']}...")
            try:
                result = await execute_trade_rest(
                    token, acc_id, acc_num, symbol, side,
                    0.01, cfg["api_url"], cfg["name"],
                    sl=sl, tp=tp
                )
                print(f"[{cfg['name']}] SUCCESS: {result}")
            except Exception as e:
                print(f"[{cfg['name']}] ERROR: {e}")

asyncio.run(test())
