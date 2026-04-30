import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hankox_executor import resolve_offset

PASS = "\033[92m PASS\033[0m"
FAIL = "\033[91m FAIL\033[0m"

def check(label, fn, expected=None, raises=False):
    try:
        result = fn()
        if raises:
            print(f"{FAIL} {label}: expected exception, got {result}")
        elif expected is not None and abs(result - expected) > 1e-9:
            print(f"{FAIL} {label}: expected {expected}, got {result}")
        else:
            print(f"{PASS} {label}: {result}")
    except Exception as e:
        if raises:
            print(f"{PASS} {label}: raised {type(e).__name__}: {e}")
        else:
            print(f"{FAIL} {label}: unexpected exception: {e}")

print("\n--- sl_unit authority (V5 key fix) ---")
# sl_unit="pips" with value that WOULD be misclassified as absolute by heuristic
check("sl_unit=pips bypasses heuristic",
      lambda: resolve_offset("USDCAD", "buy", "sl", {"sl": "1.34", "sl_unit": "pips"}, 1.35),
      expected=1.34 * 0.0001)

print("\n--- asset-class unit compatibility ---")
check("pips on index raises",
      lambda: resolve_offset("US30", "buy", "sl", {"sl": "200", "sl_unit": "pips"}, 48800),
      raises=True)
check("points on FX raises",
      lambda: resolve_offset("USDCAD", "buy", "sl", {"sl": "20", "sl_unit": "points"}, 1.35),
      raises=True)

print("\n--- negative distance guard ---")
check("negative sl raises",
      lambda: resolve_offset("USDCAD", "buy", "sl", {"sl_offset": "-5"}, 1.35),
      raises=True)

print("\n--- price==0 guard ---")
check("missing price raises",
      lambda: resolve_offset("USDCAD", "buy", "sl", {"sl": "200"}, 0),
      raises=True)

print("\n--- legacy index (heuristic, no unit) ---")
check("US30 legacy offset (heuristic offset branch)",
      lambda: resolve_offset("US30", "buy", "sl", {"sl": "200"}, 48800),
      expected=200.0)

print("\n--- legacy FX (heuristic + converter fallback) ---")
# value=0.001 < price*0.05 (1.35*0.05=0.0675) → triggers heuristic offset branch → legacy multiplier
check("USDCAD legacy offset (heuristic + legacy multiplier)",
      lambda: resolve_offset("USDCAD", "sell", "sl", {"sl": "0.001"}, 1.35),
      expected=0.001 * 0.0001)

print("\n--- explicit sl_price ---")
check("sl_price=48500 buy at 48800",
      lambda: resolve_offset("US30", "buy", "sl", {"sl_price": "48500"}, 48800),
      expected=300.0)
check("sl_price wrong side raises",
      lambda: resolve_offset("US30", "buy", "sl", {"sl_price": "49000"}, 48800),
      raises=True)

print()
