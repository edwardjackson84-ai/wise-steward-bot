import sys
from hankox_executor import resolve_offset

symbol = "US30"

print("--- Test 1: Legacy Absolute (Buy SL) ---")
# Price 48800, SL sent as 48500 (Legacy)
try:
    data = {"sl": "48500", "sl_type": "absolute"}
    dist = resolve_offset(symbol, "buy", "sl", data, 48800)
    print("Test 1 Passed: Dist =", dist)
except Exception as e:
    print("Test 1 Failed:", e)

print("\n--- Test 2: Directional Validation Bug (Buy SL above price) ---")
# User says buy at 48800, but sends SL at 49000
try:
    data = {"sl": "49000", "sl_type": "absolute"}
    dist = resolve_offset(symbol, "buy", "sl", data, 48800)
    print("Test 2 FAILED (Should have raised ValueError): Dist =", dist)
except Exception as e:
    print("Test 2 Passed (Expected Exception):", type(e).__name__, e)

print("\n--- Test 3: Heuristic Absolute (Wide Stop) ---")
# Price 48800, SL sent as 25000 with NO TYPE.
try:
    data = {"sl": "25000"}
    dist = resolve_offset(symbol, "buy", "sl", data, 48800)
    print("Test 3 Passed: Dist =", dist)
except Exception as e:
    print("Test 3 Failed:", e)

print("\n--- Test 4: Explicit Offset with explicit keyword ---")
try:
    data = {"sl_offset": "200"}
    dist = resolve_offset(symbol, "buy", "sl", data, 48800)
    print("Test 4 Passed: Dist =", dist)
except Exception as e:
    print("Test 4 Failed:", e)

print("\n--- Test 5: Explicit Price without Entry Price ---")
try:
    data = {"sl_price": "48500"}
    dist = resolve_offset(symbol, "buy", "sl", data, 0)
    print("Test 5 FAILED (Should have raised ValueError): Dist =", dist)
except Exception as e:
    print("Test 5 Passed (Expected Exception):", type(e).__name__, e)

