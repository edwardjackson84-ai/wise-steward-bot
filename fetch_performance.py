import os
import json
import requests
from datetime import datetime

# Import authentication helper from executor to reuse credentials
from tradelocker_executor import authenticate, get_config

def get_strategy_performance():
    """
    Fetches TradeLocker account history, matches orders to strategies via the local
    order_strategy_map.json, and calculates win/loss ratio and PnL per strategy.
    
    Returns:
        list: A list of dicts containing performance metrics per strategy.
    """
    try:
        # 1. Authenticate with TradeLocker
        token, account_id, acc_num = authenticate()
        
        # 2. Get the local strategy mapping
        mapping = {}
        journal_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal")
        map_file = os.path.join(journal_dir, "order_strategy_map.json")
        if os.path.exists(map_file):
            with open(map_file, "r") as f:
                mapping = json.load(f)
                
        # 3. Fetch Historical Trades from TradeLocker
        # Limit to last 1000 orders. Using ordersHistory as it contains the 22-column PnL array.
        config = get_config()
        history_url = f"{config['API_URL']}/trade/accounts/{account_id}/ordersHistory?limit=1000"
        headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
        resp = requests.get(history_url, headers=headers)
        
        if not resp.ok:
            print(f"Failed to fetch history: {resp.text}")
            return []
            
        history_data = resp.json()
        orders = []
        if isinstance(history_data, dict) and "d" in history_data:
            d = history_data["d"]
            orders = d.get("ordersHistory", []) if isinstance(d, dict) else d
        elif isinstance(history_data, list):
            orders = history_data
            
        # 4. Aggregate Performance
        stats = {}
        
        for order in orders:
            # TradeLocker ordersHistory format (22 columns):
            # [0: id, 1: instrument, 2: account, 3: qty, 4: side, 5: type, 6: status, 
            #  ... 10: realizedPnl, 13: created, 14: executed/closed ...]
            
            if isinstance(order, list) and len(order) >= 22:
                order_id = str(order[0])
                status = str(order[6]).lower()
                
                # Index 10 is Realized PnL based on the API inspection
                try:
                    pnl = float(order[10]) if order[10] is not None else 0.0
                except (ValueError, TypeError):
                    pnl = 0.0
                    
                # We only want orders that are Fully Executed or Closed and have mapped strategies
                if status in ['filled', 'closed', 'fully executed', 'executed'] and order_id in mapping:
                    strat_name = mapping[order_id].get("strategy", "Unknown")
                    sym = mapping[order_id].get("symbol", "Unknown")
                    
                    key = f"{strat_name} ({sym})"
                    if key not in stats:
                        stats[key] = {"wins": 0, "losses": 0, "pnl": 0.0, "trades": 0}
                        
                    stats[key]["trades"] += 1
                    stats[key]["pnl"] += pnl
                    if pnl > 0:
                        stats[key]["wins"] += 1
                    elif pnl < 0:
                        stats[key]["losses"] += 1
                        
        # Restructure for DataFrame rendering
        result = []
        for name, data in stats.items():
            win_rate = (data["wins"] / data["trades"]) * 100 if data["trades"] > 0 else 0
            result.append({
                "Strategy & Asset": name,
                "Total Trades": data["trades"],
                "Wins": data["wins"],
                "Losses": data["losses"],
                "Win Rate (%)": round(win_rate, 2),
                "Total PnL ($)": round(data["pnl"], 2)
            })
            
        # Sort by PnL
        result.sort(key=lambda x: x["Total PnL ($)"], reverse=True)
        return result
        
    except Exception as e:
        print(f"Error computing performance metrics: {e}")
        return []

if __name__ == "__main__":
    print(json.dumps(get_strategy_performance(), indent=2))
