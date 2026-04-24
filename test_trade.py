import sys
import os
import time

# Append the current directory so we can import hankox_executor
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from hankox_executor import get_active_configs, place_market_orders_sync

def main():
    payload = {
      "ticker": "EURUSD",
      "action": "buy",
      "qty": 0.01,
      "stopLoss": 20.0,
      "stopLossType": "trailingOffset",
      "trStopOffset": 20.0,
      "takeProfit": 40.0,
      "takeProfitType": "offset",
      "comment": "9/20 BUY Trail 20pip Test",
      "bypass_sabbath": True # Force bypass just in case
    }
    
    print(f"--- TradingView JSON Payload ---\n{payload}\n")
    
    configs = get_active_configs()
    active_envs = [c['name'] for c in configs]
    print(f"Active Accounts Found: {active_envs}\n")
    
    print("Dispatching trades...")
    # Emulate the webhook parsing
    symbol = payload.get("symbol") or payload.get("ticker", "UNKNOWN")
    action = payload.get("action", "").lower()
    qty = payload.get("qty", 0.01)
    sl = payload.get("sl") or payload.get("stopLoss", 0)
    tp = payload.get("tp") or payload.get("takeProfit", 0)
    
    kwargs = {}
    if "stopLossType" in payload: kwargs["stopLossType"] = payload["stopLossType"]
    if "trailTrigger" in payload: kwargs["trailTrigger"] = payload["trailTrigger"]
    if "trailStep" in payload: kwargs["trailStep"] = payload["trailStep"]
    if "trStopOffset" in payload: kwargs["trStopOffset"] = payload["trStopOffset"]
    if "takeProfitType" in payload: kwargs["takeProfitType"] = payload["takeProfitType"]

    result = place_market_orders_sync(configs, symbol, action, qty, sl, tp, **kwargs)
    print(f"Dispatch Result: {result}")
    
    # Wait for the async background thread to complete
    print("Waiting 5 seconds for trades to execute...")
    time.sleep(5)
    print("Done!")

if __name__ == "__main__":
    main()
