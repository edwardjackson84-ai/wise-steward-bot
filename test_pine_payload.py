import sys; sys.path.insert(0, '.')
from hankox_executor import resolve_offset, _get_asset_class, SYMBOL_MAP

PASS = "\033[92m PASS\033[0m"
FAIL = "\033[91m FAIL\033[0m"

def check(label, got, expected, tol=1e-9):
    if abs(got - expected) <= tol:
        print(f"{PASS} {label}: {got}")
    else:
        print(f"{FAIL} {label}: expected {expected}, got {got}")

# Simulate what webhook() does before calling resolve_offset
def simulate(raw_data, symbol, side, price):
    data = dict(raw_data)
    if "stopLoss" in data and "sl" not in data:
        data["sl"] = data["stopLoss"]
    if "takeProfit" in data and "tp" not in data:
        data["tp"] = data["takeProfit"]
    if "stopLossType" in data and "sl_type" not in data:
        data["sl_type"] = data["stopLossType"]
    if "takeProfitType" in data and "tp_type" not in data:
        data["tp_type"] = data["takeProfitType"]
    ac = _get_asset_class(symbol)
    if "sl_unit" not in data:
        if ac == "forex":   data["sl_unit"] = "pips"
        elif ac == "index": data["sl_unit"] = "points"
    if "tp_unit" not in data:
        if ac == "forex":   data["tp_unit"] = "pips"
        elif ac == "index": data["tp_unit"] = "points"
    sl = resolve_offset(symbol, side, 'sl', data, price)
    tp = resolve_offset(symbol, side, 'tp', data, price)
    return sl, tp

print("\n--- USDCAD Pine payload (stopLoss=200, takeProfit=20) ---")
sl, tp = simulate({"stopLoss": 200, "takeProfit": 20, "takeProfitType": "offset"}, "USDCAD", "buy", 1.3850)
check("USDCAD SL = 200 pips = 0.0200", sl, 200 * 0.0001, tol=1e-7)
check("USDCAD TP = 20 pips = 0.0020",  tp, 20 * 0.0001,  tol=1e-8)

print("\n--- US30 Pine payload (stopLoss=300, takeProfit=130) ---")
sl, tp = simulate({"stopLoss": 300, "takeProfit": 130}, "US30", "sell", 40000)
check("US30 SL = 300 points", sl, 300.0)
check("US30 TP = 130 points", tp, 130.0)

print("\n--- GBPUSD Pine payload (stopLoss=23, takeProfit=82) ---")
sl, tp = simulate({"stopLoss": 23, "takeProfit": 82}, "GBPUSD", "sell", 1.2700)
check("GBPUSD SL = 23 pips = 0.0023", sl, 23 * 0.0001, tol=1e-8)
check("GBPUSD TP = 82 pips = 0.0082", tp, 82 * 0.0001, tol=1e-8)

print()
