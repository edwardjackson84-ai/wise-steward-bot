import os
import json
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env")
load_dotenv(env_path)

app = Flask(__name__)

# Queue to hold recent alerts for the dashboard
ALERT_QUEUE = []

# -------------------------------------------------------------------
# Wise Steward Trading Agent - TradeLocker Executor
# -------------------------------------------------------------------

def get_config():
    return {
        "API_URL": os.environ.get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api"),
        "EMAIL": os.environ.get("TRADELOCKER_EMAIL", "edward.jackson84@gmail.com"),
        "PASSWORD": os.environ.get("TRADELOCKER_PASSWORD", "v&LA2LWmN5kG"),
        "SERVER": os.environ.get("TRADELOCKER_SERVER", "CRUC"),
        "ACCOUNT_ID": os.environ.get("TRADELOCKER_ACCOUNT_ID", "1961103")
    }

INSTRUMENT_MAP = {
    "US30": 17028, # Mapped from Hankotrade Demo API
    "BTCUSD": 17949,
    "EURUSD": 16985,
    "GBPUSD": 16977,
    "NAS100": 17035,
    "SPX500": 17034,
    "US500": 17034  # Alias for SPX500
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
    config = get_config()
    print("Authenticating with TradeLocker...")
    auth_url = f"{config['API_URL']}/auth/jwt/token"
    payload = {"email": config['EMAIL'], "password": config['PASSWORD'], "server": config['SERVER']}
    headers = {"Content-Type": "application/json"}
    
    auth_response = requests.post(auth_url, json=payload, headers=headers)
    if not auth_response.ok:
        raise Exception(f"Failed to authenticate: {auth_response.text}")
        
    token = auth_response.json().get("accessToken")
    
    accounts_url = f"{config['API_URL']}/auth/jwt/all-accounts"
    acc_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    acc_response = requests.get(accounts_url, headers=acc_headers)
    
    if not acc_response.ok:
        raise Exception(f"Failed to fetch accounts: {acc_response.text}")
        
    accounts = acc_response.json().get("accounts", [])
    if not accounts:
        raise Exception("No TradeLocker accounts found for this user.")
        
    target_account = None
    if config['ACCOUNT_ID']:
        for acc in accounts:
            if str(acc.get("id")) == str(config['ACCOUNT_ID']):
                target_account = acc
                break
                
    if not target_account:
        print(f"Target account ID {config['ACCOUNT_ID']} not found. Defaulting to first account.")
        target_account = accounts[0]
        
    print(f"Targeting Account ID: {target_account.get('id')} - Balance: {target_account.get('accountBalance')}")
    return token, target_account.get("id"), target_account.get("accNum", "1")

def write_journal_entry(signal_data):
    """Write an entry to the Journal of the Sovereign Arbitrator."""
    print("Writing to Journal of the Sovereign Arbitrator...")
    journal_entry = {
        "timestamp": datetime.now().isoformat(),
        "strategy": signal_data.get("strategy", "Unknown"),
        "signal": signal_data.get("signal", "Unknown"),
        "action": signal_data.get("action", "Unknown"),
        "biblical_principle": "Exercising Diligence over Haste."
    }
    print(json.dumps(journal_entry, indent=2))

def create_visual_journal_entry(signal_data, img_path, vision_result):
    """Compiles the trade setup and AI review into a Markdown file for the dashboard."""
    journal_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal")
    os.makedirs(journal_dir, exist_ok=True)
    
    symbol = signal_data.get("symbol", "Unknown")
    strategy = signal_data.get("strategy", "Unknown")
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    filename = os.path.join(journal_dir, f"{symbol}_{timestamp_str}.md")
    
    status_icon = "✅" if vision_result.get("approved") else "❌"
    
    md_content = f"""### {symbol} - {strategy}
**Action:** {signal_data.get('action')} | **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Visual Arbiter Status:** {status_icon} {'PASSED' if vision_result.get('approved') else 'REJECTED'}
**AI Reasoning:**
> {vision_result.get('reason')}

**Webhook Payload:**
```json
{json.dumps(signal_data, indent=2)}
```
"""
    # Embed image if we have it
    if img_path and os.path.exists(img_path):
        # We need relative path or absolute for streamlit
        md_content += f"\n**Screenshot Analysis:**\n![Chart Snapshot]({img_path})\n"

    with open(filename, "w") as f:
        f.write(md_content)

def map_order_to_strategy(order_id, strategy, symbol):
    """Map a TradeLocker order ID to the Pine Script strategy that generated it."""
    if not order_id or not strategy: return
    journal_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal")
    os.makedirs(journal_dir, exist_ok=True)
    map_file = os.path.join(journal_dir, "order_strategy_map.json")
    
    mapping = {}
    if os.path.exists(map_file):
        try:
            with open(map_file, "r") as f:
                mapping = json.load(f)
        except: pass
        
    mapping[str(order_id)] = {
        "strategy": strategy,
        "symbol": symbol,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(map_file, "w") as f:
        json.dump(mapping, f, indent=2)

def close_position(token, account_id, acc_num, signal_data, target_close_side):
    """Closes all open positions for the given symbol matching the side."""
    config = get_config()
    symbol = signal_data.get("symbol")
    instrument_id = INSTRUMENT_MAP.get(symbol)
    if not instrument_id:
        print(f"Error: {symbol} is not mapped. Cannot close position.")
        return
        
    print(f"Attempting to close {target_close_side} position(s) for {symbol}...")
    
    # Fetch open positions
    pos_url = f"{config['API_URL']}/trade/accounts/{account_id}/positions"
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
            
            if str(pos_instrument_id) == str(instrument_id):
                target_side_tl = "buy" if target_close_side in ["long", "buy"] else "sell"
                
                if pos_side == target_side_tl:
                    # Issue Global DELETE request to close the position
                    # Hankotrade's wrapper uses /trade/positions/{id} instead of /trade/accounts/
                    close_url = f"{config['API_URL']}/trade/positions/{pos_id}"
                    del_resp = requests.delete(close_url, headers=headers)
                    
                    if del_resp.ok:
                        print(f"Successfully closed {target_close_side} position ID: {pos_id}")
                        positions_closed += 1
                    else:
                        print(f"Failed to close position ID {pos_id}: {del_resp.text}")
                    
    if positions_closed == 0:
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
    
    config = get_config()
    # Fetch dynamic routeId (Required for Hankotrade indices/crypto)
    instruments_url = f"{config['API_URL']}/trade/accounts/{account_id}/instruments"
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
                        
    order_url = f"{config['API_URL']}/trade/accounts/{account_id}/orders"
    
    # Parse generic defaults or Oliver Velez specific fields
    quantity = signal_data.get("contracts", signal_data.get("qty", 0.01))
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
        order_id = response.json().get('orderId', 'Unknown')
        print(f"Trade successfully placed! Order ID: {order_id}")
        
        # Link order ID to strategy for Performance Tracking Dashboard
        strategy = signal_data.get("strategy", "Unknown Strategy")
        map_order_to_strategy(order_id, strategy, symbol)
    else:
        print(f"Failed to place trade: {response.text}")

@app.route('/ping', methods=['GET'])
def ping():
    """Heartbeat endpoint to keep Render alive."""
    return jsonify({"status": "alive", "timestamp": datetime.now().isoformat()}), 200

@app.route('/check-alerts', methods=['GET'])
def check_alerts():
    """Endpoint for the local dashboard to poll for new alerts."""
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
    
    # Force parse JSON regardless of Content-Type 
    data = request.get_json(force=True, silent=True)
    if not data:
        try:
            data = json.loads(request.data)
        except Exception:
            return jsonify({"error": "No JSON payload found"}), 400
        
    # Check Sabbath Mode (unless bypass flag is fully authorized)
    bypass_sabbath = data.get("bypass_sabbath", False)
    if is_sabbath_mode_active() and not bypass_sabbath:
        print("Rejecting trade signal: Sabbath Mode Active")
        return jsonify({"status": "rejected", "reason": "Sabbath Mode Active"}), 200
        
    try:
        print(f"Received data: {data}")
        write_journal_entry(data)
        
        # Add to queue for local dashboard to pick up
        ALERT_QUEUE.append({
            "received_at": datetime.now().isoformat(),
            "payload": data
        })
        
        token, account_id, acc_num = authenticate()
        
        # Action logic decoding
        action = data.get("action", "").lower()
        
        # Check if this is an exit order (e.g., "close_long", "close_short")
        if action in ["close_long", "close_short"]:
            target_side = "long" if action == "close_long" else "short"
            close_position(token, account_id, acc_num, data, target_side)
            
        # Check if it's an entry order (e.g., "buy", "sell", "entry")
        else:
            # === VISUAL ARBITER PIPELINE ===
            enable_vision = str(os.environ.get("ENABLE_VISUAL_ARBITER", "false")).lower() == "true"
            if enable_vision:
                symbol = data.get("symbol", "UNKNOWN")
                timeframe = str(data.get("timeframe", "60"))
                strategy = data.get("strategy", "Unknown Strategy")
                
                print(f"Visual Arbiter enabled. Triggering screenshot for {symbol}...")
                try:
                    from screenshot_engine import capture_chart_screenshot
                    from vision_arbiter import analyze_chart_with_vision
                    
                    img_path = capture_chart_screenshot(symbol, timeframe)
                    if img_path:
                        vision_result = analyze_chart_with_vision(img_path, symbol, strategy)
                        
                        # Document the Arbiter's reasoning
                        data["arbiter_approved"] = vision_result.get("approved", True)
                        data["arbiter_reason"] = vision_result.get("reason", "No reason provided.")
                        
                        # Generate the Markdown journal piece
                        create_visual_journal_entry(data, img_path, vision_result)
                        
                        if not vision_result.get("approved"):
                            print(f"❌ Visual Arbiter REJECTED trade: {data['arbiter_reason']}")
                            return jsonify({"status": "rejected_by_arbiter", "reason": data['arbiter_reason']}), 200
                        else:
                            print(f"✅ Visual Arbiter APPROVED trade: {data['arbiter_reason']}")
                    else:
                        print("Failed to capture screenshot. Bypassing Arbiter and executing blindly.")
                except Exception as e:
                    print(f"Visual Arbiter Exception: {e}. Executing blindly.")
            # ===============================

            place_order(token, account_id, acc_num, data)
            
        return jsonify({"status": "success", "message": "Trade processed"}), 200
        
    except Exception as e:
        print(f"Error processing trade: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Wise Steward Executor standing by for webhook payloads on port 5000...")
    app.run(host='0.0.0.0', port=5000)
