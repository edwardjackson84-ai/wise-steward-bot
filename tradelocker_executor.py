import os
import json
from datetime import datetime
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory queue to store alerts for the local agent to fetch. 
# (Note: In production, consider Redis or a database, but this works for the bridge).
ALERT_QUEUE = []

# -------------------------------------------------------------------
# Wise Steward Trading Agent - TradeLocker Executor
# -------------------------------------------------------------------

TRADELOCKER_API_URL = os.environ.get("TRADELOCKER_API_URL", "https://api.tradelocker.com")
EMAIL = os.environ.get("TRADELOCKER_EMAIL", "your_email")
PASSWORD = os.environ.get("TRADELOCKER_PASSWORD", "your_password")
SERVER = os.environ.get("TRADELOCKER_SERVER", "Hankotrade-Live")

INSTRUMENT_MAP = {
    "US30": 17028, # Mapped from Hankotrade Demo API
    "BTCUSD": 16720,
    "EURUSD": 16985,
    "GBPUSD": 16977,
    "NAS100": 17035,
    "SPX500": 17034,
    "XAGUSD": 18277,
    "XAUUSD": 18278,
    "CADJPY": 18205,
    "NZDJPY": 18207,
    "USDHKD": 18209,
    "USDCNH": 18210,
    "BRENT": 17930,
    "WTI": 17928
}

def is_sabbath_mode_active():
    """Check if the current time is within the Sabbath blackout period."""
    now = datetime.now()
    if now.weekday() == 4 and now.hour >= 16:
        return True
    if now.weekday() == 5:
        return True
    if now.weekday() == 6 and now.hour < 17:
        return True
    return False

def authenticate():
    """Authenticate with TradeLocker API and return JWT, account ID, and accNum."""
    print("Authenticating with TradeLocker...")
    auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
    payload = {"email": EMAIL, "password": PASSWORD, "server": SERVER}
    headers = {"Content-Type": "application/json"}
    
    auth_response = requests.post(auth_url, json=payload, headers=headers)
    if not auth_response.ok:
        raise Exception(f"Failed to authenticate: {auth_response.text}")
        
    token = auth_response.json().get("accessToken")
    
    accounts_url = f"{TRADELOCKER_API_URL}/auth/jwt/all-accounts"
    acc_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    acc_response = requests.get(accounts_url, headers=acc_headers)
    
    if not acc_response.ok:
        raise Exception(f"Failed to fetch accounts: {acc_response.text}")
        
    accounts = acc_response.json().get("accounts", [])
    if not accounts:
        raise Exception("No TradeLocker accounts found for this user.")
        
    first_account = accounts[0]
    return token, first_account.get("id"), first_account.get("accNum", "1")

def write_journal_entry(signal_data):
    """Write an entry to the Journal of the Sovereign Arbitrator."""
    print("Writing to Journal of the Sovereign Arbitrator...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    symbol = signal_data.get("symbol", "UNKNOWN")
    action = signal_data.get("action", "Unknown")
    
    journal_dir = "journal"
    if not os.path.exists(journal_dir):
        os.makedirs(journal_dir)
        
    filename = os.path.join(journal_dir, f"Alert_{symbol}_{timestamp}.md")
    
    content = f"""# Alert: {symbol}
    
**Date & Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Action:** {action}
**Technical Confluence:** {signal_data.get("strategy", "Unknown")}
**Signal Type:** {signal_data.get("signal_type", signal_data.get("signal", "Unknown"))}
**Price:** {signal_data.get("price", "Market")}
**Biblical Principle:** *Exercising Diligence over Haste.*

### Raw Payload
```json
{json.dumps(signal_data, indent=2)}
```
"""
    with open(filename, "w") as f:
        f.write(content)
        
    print(f"Journal successfully written to {filename}")

def close_position(token, account_id, acc_num, signal_data, target_close_side):
    """Closes all open positions for the given symbol matching the side, or all positions if target is 'all'."""
    symbol = signal_data.get("symbol")
    instrument_id = INSTRUMENT_MAP.get(symbol) if symbol else None
    
    if target_close_side != "all" and not instrument_id:
        print(f"Error: {symbol} is not mapped. Cannot close position.")
        return
        
    if target_close_side == "all":
        print("Attempting to close ALL open positions across the account...")
    else:
        print(f"Attempting to close {target_close_side} position(s) for {symbol}...")
    
    # Fetch open positions
    pos_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/positions"
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
    resp = requests.get(pos_url, headers=headers)
    
    if not resp.ok:
        print(f"Failed to fetch positions: {resp.text}")
        return
        
    positions_data = resp.json()
    print(f"DEBUG FETCH POSITIONS RAW: {json.dumps(positions_data)}")
    positions = []
    
    # TradeLocker API response structure handling
    if isinstance(positions_data, dict) and "d" in positions_data:
        d = positions_data["d"]
        positions = d.get("positions", []) if isinstance(d, dict) else d
    elif isinstance(positions_data, list):
        positions = positions_data
        
    positions_closed = 0
    for pos in positions:
        # TradeLocker positions are arrays: [id, tradableInstrumentId, accountId, side, qty, price, sl, tp, timestamp...]
        # Ex: ["7277816997856580016", "17028", "1555930", "sell", "0.01", "49414", null, ...]
        if isinstance(pos, list) and len(pos) >= 5:
            pos_id = pos[0]
            pos_instrument_id = pos[1]
            pos_side = pos[3].lower()
            
            symbol_match = target_close_side == "all" or (str(pos_instrument_id) == str(instrument_id))
            target_tl_side = "buy" if target_close_side in ["long", "buy"] else "sell"
            side_match = target_close_side == "all" or (pos_side == target_tl_side)
            
            if symbol_match and side_match:
                # Issue Global DELETE request to close the position
                # Hankotrade's wrapper uses /trade/positions/{id} instead of /trade/accounts/
                close_url = f"{TRADELOCKER_API_URL}/trade/positions/{pos_id}"
                del_resp = requests.delete(close_url, headers=headers)
                
                if del_resp.ok:
                    print(f"Successfully closed position ID: {pos_id}")
                    positions_closed += 1
                else:
                    print(f"Failed to close position ID {pos_id}: {del_resp.text}")
                    
    if positions_closed == 0:
        if target_close_side == "all":
            print("No open positions found to close.")
        else:
            print(f"No open {target_close_side} positions found for {symbol} to close.")

def place_order(token, account_id, acc_num, signal_data):
    """Place a market entry order on TradeLocker based on the webhook signal."""
    symbol = signal_data.get("symbol")
    
    # Support both old {"side": "buy"} and new {"action": "buy"}
    action = signal_data.get("action", "").lower()
    side = signal_data.get("side", action).lower()
    
    tl_side = "buy" if side in ["long", "buy"] else "sell"
    
    instrument_id = INSTRUMENT_MAP.get(symbol)
    if not instrument_id:
        print(f"Error: {symbol} is not mapped to an Instrument ID. Cannot place order.")
        return
        
    print(f"Placing {tl_side} order for {symbol} (Instrument ID: {instrument_id})...")
    
    # Fetch dynamic routeId (Required for Hankotrade indices/crypto)
    instruments_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/instruments"
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num), "Content-Type": "application/json"}
    inst_resp = requests.get(instruments_url, headers=headers)
    
    route_id = None
    if inst_resp.ok:
        data = inst_resp.json()
        inst_list = data.get("d", []) if isinstance(data, dict) else data
        if isinstance(inst_list, dict) and "instruments" in inst_list:
            inst_list = inst_list["instruments"]
        
        for inst in inst_list:
            if isinstance(inst, dict) and inst.get("tradableInstrumentId") == instrument_id:
                for r in inst.get("routes", []):
                    if r.get("type") == "TRADE":
                        route_id = r.get("id")
                        break
                        
    order_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/orders"
    
    # Parse generic defaults or Oliver Velez specific fields
    # Use environment variable for base lot size, defaulting to 0.01 if not set
    base_lot_size = float(os.environ.get("BASE_LOT_SIZE", 0.01))
    
    # Check for symbol-specific lot size override
    specific_lot = float(os.environ.get(f"LOT_SIZE_{symbol}", 0.0))
    if specific_lot > 0.0:
        base_lot_size = specific_lot
        
    quantity = signal_data.get("contracts", signal_data.get("qty", base_lot_size))
    sl = signal_data.get("sl", signal_data.get("initial_stop"))
    tp = signal_data.get("tp")
    
    # Safely convert sl and tp to float, ignoring TradingView string artifacts
    try:
        sl_float = float(sl) if sl and str(sl) != "NaN" and "{{" not in str(sl) else None
    except ValueError:
        sl_float = None
        
    try:
        tp_float = float(tp) if tp and str(tp) != "NaN" and "{{" not in str(tp) else None
    except ValueError:
        tp_float = None
        
    payload = {
        "tradableInstrumentId": instrument_id,
        "qty": float(quantity),
        "side": tl_side,
        "type": "market",
        "validity": "IOC"  # Required immediate-or-cancel for market
    }
    
    if sl_float:
        payload["stopLoss"] = sl_float
        payload["stopLossType"] = "absolute"
        
    if tp_float:
        payload["takeProfit"] = tp_float
        payload["takeProfitType"] = "absolute"
        
    if route_id:
        payload["routeId"] = route_id
        
    response = requests.post(order_url, json=payload, headers=headers)
    if response.ok:
        print(f"Trade successfully placed! Order ID: {response.json().get('orderId', 'Unknown')}")
    else:
        print(f"Failed to place trade: {response.text}")

@app.route('/ping', methods=['GET'])
def ping():
    """Heartbeat endpoint to keep Render alive."""
    return jsonify({"status": "alive", "timestamp": datetime.now().isoformat()}), 200

@app.route('/check-alerts', methods=['GET'])
def check_alerts():
    """Endpoint for the local agent to poll for new alerts."""
    global ALERT_QUEUE
    if not ALERT_QUEUE:
        return jsonify({"alerts": []}), 200
        
    # Return all alerts and clear the queue
    alerts_to_return = list(ALERT_QUEUE)
    ALERT_QUEUE.clear()
    return jsonify({"alerts": alerts_to_return}), 200

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    print("\n--- Received Webhook Signal ---")
    
    if is_sabbath_mode_active():
        print("Rejecting trade signal: Sabbath Mode Active")
        return jsonify({"status": "rejected", "reason": "Sabbath Mode Active"}), 403
        
    try:
        raw_data = request.get_data(as_text=True)
        print(f"Raw webhook body: {raw_data}")
        
        try:
            data = request.get_json(force=True)
        except Exception:
            if raw_data:
                data = json.loads(raw_data)
            else:
                data = None
                
        if not data:
            return jsonify({"error": "No JSON payload found"}), 400
            
        print(f"Parsed JSON data: {data}")
        write_journal_entry(data)
        
        # Add to queue for local agent to pick up
        ALERT_QUEUE.append({
            "received_at": datetime.now().isoformat(),
            "payload": data
        })
        
        token, account_id, acc_num = authenticate()
        
        # Action logic decoding
        action = data.get("action", "").lower()
        
        if action == "signal":
            print(f"Signal received and logged: {data.get('signal')}")
            
        elif action == "close_all":
            close_position(token, account_id, acc_num, data, "all")
            
        elif action == "close":
            target_side = data.get("side", "").lower()
            if target_side in ["long", "buy", "short", "sell"]:
                close_position(token, account_id, acc_num, data, target_side)
            else:
                print(f"Warning: Close action received without valid side: {data}")
                
        elif action in ["close_long", "close_short"]:
            target_side = "long" if action == "close_long" else "short"
            close_position(token, account_id, acc_num, data, target_side)
            
        elif action in ["buy", "sell", "entry"]:
            place_order(token, account_id, acc_num, data)
            
        else:
            print(f"Warning: Unknown action '{action}'. Defaulting to place_order just in case.")
            place_order(token, account_id, acc_num, data)
            
        return jsonify({"status": "success", "message": "Trade processed"}), 200
        
    except Exception as e:
        print(f"Error processing trade: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Wise Steward Executor standing by for webhook payloads on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
