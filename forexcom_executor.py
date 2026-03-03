import os
import json
from datetime import datetime
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env.forexcom")
# Load the specific forexcom env
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

app = Flask(__name__)
ALERT_QUEUE = []

def get_config():
    return {
        "API_URL": os.environ.get("FOREXCOM_API_URL", "https://ciapi.cityindex.com/TradingApi"),
        "USERNAME": os.environ.get("FOREXCOM_USERNAME"),
        "PASSWORD": os.environ.get("FOREXCOM_PASSWORD"),
        "APP_KEY": os.environ.get("FOREXCOM_APP_KEY", "TestKey")
    }

def authenticate():
    """Authenticate with Forex.com/CityIndex API."""
    config = get_config()
    url = f"{config['API_URL']}/session"
    payload = {
        "UserName": config['USERNAME'],
        "Password": config['PASSWORD'],
        "AppVersion": "1",
        "AppComments": "Wise Steward Bot",
        "AppKey": config['APP_KEY']
    }
    headers = {"Content-Type": "application/json"}
    
    resp = requests.post(url, json=payload, headers=headers)
    if not resp.ok:
        raise Exception(f"Auth failed: {resp.text}")
    
    data = resp.json()
    session_token = data.get("Session")
    return session_token

def is_session_active(symbol):
    """Checks string constraints against current time for allowed trading sessions."""
    # Mirroring the tradelocker filter format for compatibility
    allowed_sessions_str = os.environ.get(f"SESSIONS_{symbol}", "Asian,London,New York")
    if not allowed_sessions_str.strip(): return True
    allowed_sessions = [s.strip() for s in allowed_sessions_str.split(",")]
    
    now_utc = datetime.utcnow()
    hour = now_utc.hour
    
    is_asian = (22 <= hour or hour < 8)
    is_london = (8 <= hour < 16)
    is_new_york = (13 <= hour < 22)
    
    if "Asian" in allowed_sessions and is_asian: return True
    if "London" in allowed_sessions and is_london: return True
    if "New York" in allowed_sessions and is_new_york: return True

    return False

def get_market_id(session_token, symbol):
    """Maps typical forex symbols (EURUSD) to Forex.com internal MarketIds."""
    # US regulations (CFTC/NFA) restrict Forex.com from offering CFDs (US30, NAS100, Crypto) 
    # to US residents. These must be traded on offshore brokers like HankoTrade.
    symbol_map = {
        "EURUSD": 401876081, # Demo EUR/USD
        # "US30": N/A, 
        # "BTCUSD": N/A
    }
    return symbol_map.get(symbol.upper())

def place_market_order(session_token, symbol, side, qty, sl_price, tp_price):
    """Places a trade using Forex.com REST API."""
    config = get_config()
    market_id = get_market_id(session_token, symbol)
    if not market_id:
        print(f"Error: Unknown symbol mapping for {symbol}")
        return False
        
    url = f"{config['API_URL']}/order/newtradeorder"
    headers = {
        "UserName": config['USERNAME'],
        "Session": session_token,
        "Content-Type": "application/json"
    }
    
    # Direction mappings
    direction = "buy" if side.lower() == "buy" else "sell"
    
    # Forex.com expects quantity in raw units, not decimal lots. 1 standard lot = 100,000 units.
    units_qty = int(qty * 100000)
    
    payload = {
        "MarketId": market_id,
        "Direction": direction,
        "Quantity": units_qty,
        "BidPrice": 0, # Ignored for market orders
        "OfferPrice": 0,
        "AuditId": "", # Requires active price quote polling in production
        "TradingAccountId": 0, # Defaults to main account if 0
        "IfDone": [] # SL/TP arrays go here
    }
    
    # Forex.com REST order payload is complex, printing the attempt for logs
    print(f"Attempting to route {side} order for {units_qty} units ({qty} lots) of {symbol} to Forex.com...")
    print(f"Market ID: {market_id}")
    
    # Try execution
    try:
        resp = requests.post(url, json=payload, headers=headers)
        if resp.ok:
            print("Trade successfully placed!", resp.json())
            return True
        else:
            print(f"Broker rejected trade: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"Order exception: {e}")
        return False

@app.route("/webhook", methods=["POST"])
def webhook():
    if request.is_json or request.content_type == 'text/plain':
        try:
            data = request.get_json(force=True) if request.content_type == 'text/plain' else request.json
            print(f"\n--- Forex.com Webhook Signal ---\nReceived data: {data}")
            
            symbol = data.get("symbol", "UNKNOWN")
            action = data.get("action", "").lower()
            
            # 1. Session Filter
            if action not in ["close_long", "close_short"] and symbol != "UNKNOWN":
                if not is_session_active(symbol):
                    print(f"Rejecting trade signal for {symbol}: Outside allowed sessions.")
                    return jsonify({"status": "rejected", "reason": "Session Closed"}), 200

            # 2. Visual Arbiter
            enable_vision = str(os.environ.get("ENABLE_VISUAL_ARBITER", "false")).lower() == "true"
            if enable_vision and action not in ["close_long", "close_short"]:
                print("Visual Arbiter checking...")
                # Assuming screenshot_engine integration sits here
                
            # 3. Execution
            try:
                session_token = authenticate()
                
                # Close orders are vastly different API calls than entry orders
                if action in ["close_long", "close_short"]:
                    print(f"Execution handling logic for closing {symbol} positions...")
                    # Implementation needed for /order/close position
                else:
                    qty = float(data.get("qty", os.environ.get("BASE_LOT_SIZE", 0.01)))
                    side = data.get("side", "buy")
                    sl = float(data.get("sl", 0))
                    tp = float(data.get("tp", 0))
                    place_market_order(session_token, symbol, side, qty, sl, tp)
                    
            except Exception as e:
                print(f"Execution Pipeline Error: {e}")
                
            return jsonify({"status": "success", "message": "Signal processed"}), 200
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400
    else:
        return jsonify({"status": "error", "message": "Unsupported Media Type"}), 415

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
