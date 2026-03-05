import os
import json
import time
import asyncio
from datetime import datetime
import requests
import websockets
from flask import Flask, request, jsonify
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
# We look for a Hankox specific env, otherwise fallback to live
env_path = os.path.join(script_dir, ".env.hankolive")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)

app = Flask(__name__)

def get_active_configs():
    """Reads all .env.hanko* files and returns configs for active accounts."""
    from dotenv import dotenv_values
    configs = []
    
    # Load local toggle state cache if it exists
    toggles = {}
    toggle_path = os.path.join(script_dir, "toggles.json")
    if os.path.exists(toggle_path):
        try:
            with open(toggle_path, "r") as f:
                toggles = json.load(f)
        except Exception:
            pass

    # Check both demo and live files
    for env_name in [".env.hankodemo", ".env.hankolive"]:
        # Toggles.json overrides the .env file default
        file_acct_active = str(os.environ.get("HANKOX_DEMO_ACTIVE", "True")).lower() == "true" if "demo" in env_name else str(os.environ.get("HANKOX_LIVE_ACTIVE", "False")).lower() == "true"
        is_active = toggles.get(env_name, file_acct_active)
        
        if is_active:
            if "live" in env_name.lower():  
                server_type = "hankotrade_live"
                ws_url = "wss://livefeed.hankotrade.com/"
                account_id = os.environ.get("HANKOX_LIVE_ACCOUNT_ID", "T347197")
                password = os.environ.get("HANKOX_LIVE_PASSWORD", "Tristan10!")
            else:
                server_type = "hankotrade_demo"
                ws_url = "wss://demofeed.hankotrade.com/"
                account_id = os.environ.get("HANKOX_DEMO_ACCOUNT_ID", "T414677")
                password = os.environ.get("HANKOX_DEMO_PASSWORD", "3797966865")
                
            configs.append({
                "ACCOUNT_ID": account_id,
                "PASSWORD": password,
                "SERVER_TYPE": server_type,
                "WS_URL": ws_url,
                "ENV_NAME": env_name
            })
    return configs

def authenticate_config(config):
    """Authenticate with Hanko X REST API for a specific config."""
    if not config["ACCOUNT_ID"] or not config["PASSWORD"]:
        raise ValueError(f"Missing credentials in {config['ENV_NAME']}")
        
    login_url = "https://tradeapi.hankotrade.com/api/login"
    login_data = {
        "email": config["ACCOUNT_ID"],
        "password": config["PASSWORD"],
        "server_type": config["SERVER_TYPE"]
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': 'https://trade.hankotrade.com',
        'Referer': 'https://trade.hankotrade.com/'
    }
    
    print(f"Authenticating {config['ACCOUNT_ID']} on {config['SERVER_TYPE']}...")
    resp = requests.post(login_url, json=login_data, headers=headers)
    resp_data = resp.json().get('data', {}) if resp.ok else {}
    token = resp_data.get('user', {}).get('token')
    if not token:
        raise Exception(f"{config['ENV_NAME']} Auth failed: {resp.text}")
        
    token = resp.json()['data']['user']['token']
    
    # Fetch Account ID
    headers['Authorization'] = f'Bearer {token}'
    acc_url = "https://tradeapi.hankotrade.com/api/act/user/account/balance"
    acc_resp = requests.post(acc_url, json={}, headers=headers)
    
    acc_id = None
    if acc_resp.ok:
        acc_id = acc_resp.json().get('data', {}).get('ACCOUNT_ID')
        
    if not acc_id:
        raise Exception("Failed to retrieve Hanko X ACCOUNT_ID.")
        
    return token, acc_id

def is_session_active(symbol):
    """Checks string constraints against current time for allowed trading sessions."""
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

async def execute_trade_ws(token, acc_id, symbol, side, qty, wss_url, env_name, sl=0, tp=0):
    """Executes a trade instruction directly over the Hanko X WebSocket."""
    side_int = 1 if side.lower() == "buy" else 2
    
    formatted_symbol = symbol if ".HKT" in symbol else f"{symbol}.HKT"
    
    try:
        async with websockets.connect(wss_url) as websocket:
            auth_msg = {
                "auth": token,
                "defaults": [formatted_symbol],
                "rawFeed": True
            }
            await websocket.send(json.dumps(auth_msg))
            await asyncio.sleep(0.5)
            
            order_msg = {
                "placeOrder": {
                    "symbol": formatted_symbol,
                    "quantity": float(qty),
                    "side": side_int,
                    "stop": float(sl) if sl else 0,
                    "limit": float(tp) if tp else 0,
                    "trail": 0,
                    "commentary": "Wise Steward Webhook",
                    "tempOrderId": int(time.time() * 1000),
                    "account_id": int(acc_id)
                }
            }
            print(f"[{env_name}] WS Payload Dispatch: {json.dumps(order_msg['placeOrder'])}")
            await websocket.send(json.dumps(order_msg))
            
            try:
                for _ in range(3):
                    await asyncio.wait_for(websocket.recv(), timeout=1.5)
            except asyncio.TimeoutError:
                pass
                
            return True
            
    except Exception as e:
        print(f"[{env_name}] WebSocket Error: {e}")
        return False

async def place_multi_orders_async(active_configs, symbol, side, qty, sl=0, tp=0):
    """Run WebSocket trades concurrently for all active configs."""
    tasks = []
    
    for config in active_configs:
        try:
            token, acc_id = authenticate_config(config)
            print(f"[{config['ENV_NAME']}] Routing {side} order for {qty} lots of {symbol} to {config['SERVER_TYPE']}...")
            task = asyncio.create_task(execute_trade_ws(token, acc_id, symbol, side, qty, config["WS_URL"], config["ENV_NAME"], sl, tp))
            tasks.append({
                "env": config["ENV_NAME"],
                "task": task
            })
        except Exception as e:
            print(f"[{config['ENV_NAME']}] Error preparing trade: {e}")
            
    results = {}
    for t in tasks:
        success = await t["task"]
        env_name = t["env"]
        if success:
            print(f"[{env_name}] Trade successfully transmitted!")
        else:
            print(f"[{env_name}] Trade transmission failed.")
        results[env_name] = success
        
    return results

def place_market_orders_sync(active_configs, symbol, side, qty, sl=0, tp=0):
    """Synchronous wrapper to block the Flask thread while deploying."""
    return asyncio.run(place_multi_orders_async(active_configs, symbol, side, qty, sl, tp))



@app.route("/toggle", methods=["POST"])
def toggle_account():
    data = request.json
    env_name = data.get("env_name")
    is_active = data.get("active")
    
    if env_name and env_name in [".env.hankodemo", ".env.hankolive", ".env.forexcom"]:
        toggle_path = os.path.join(script_dir, "toggles.json")
        toggles = {}
        if os.path.exists(toggle_path):
            try:
                with open(toggle_path, "r") as f:
                    toggles = json.load(f)
            except Exception:
                pass
                
        toggles[env_name] = bool(is_active)
        
        with open(toggle_path, "w") as f:
            json.dump(toggles, f)
            
        return jsonify({"status": "success", "message": f"{env_name} set to {is_active} in ephemeral cache"})
    return jsonify({"status": "error", "message": "Invalid environment file"}), 400

@app.route("/webhook", methods=["POST"])

def webhook():
    if request.is_json or request.content_type == 'text/plain':
        try:
            data = request.get_json(force=True) if request.content_type == 'text/plain' else request.json
            print(f"\\n--- Hanko X Webhook Signal ---\\nReceived data: {data}")
            
            symbol = data.get("symbol", "UNKNOWN")
            action = data.get("action", "").lower()
            
            # 1. Session Filter
            if action not in ["close_long", "close_short"] and symbol != "UNKNOWN":
                if not is_session_active(symbol):
                    print(f"Rejecting trade signal for {symbol}: Outside allowed sessions.")
                    return jsonify({"status": "rejected", "reason": "Session Closed"}), 200

            # 2. Visual Arbiter (mocked/placeholder as per other executors)
            enable_vision = str(os.environ.get("ENABLE_VISUAL_ARBITER", "false")).lower() == "true"
            if enable_vision and action not in ["close_long", "close_short"]:
                print("Visual Arbiter checking (stub)...")
                
            # 3. Execution Phase
            try:
                active_configs = get_active_configs()
                if not active_configs:
                    print("Notice: Signal received but no accounts are toggled active.")
                    return jsonify({"status": "ignored", "reason": "No active accounts"}), 200
                
                # Handling order logic
                if action in ["close_long", "close_short"]:
                    print(f"Execution logic for closing {symbol} positions is not yet implemented.")
                else:
                    qty = float(data.get("qty", os.environ.get(f"LOT_SIZE_{symbol}", os.environ.get("BASE_LOT_SIZE", 0.01))))
                    if qty <= 0:
                        print(f"Rejecting trade: Lot size {qty} is <= 0")
                        return jsonify({"status": "ignored", "reason": "Zero Lot Size"}), 200
                        
                    side = data.get("side", "buy")
                    # Try to parse sl and tp from the webhook payload, passing 0 if they don't exist
                    sl = float(data.get("sl", 0) or 0)
                    tp = float(data.get("tp", 0) or 0)
                    
                    results = place_market_orders_sync(active_configs, symbol, side, qty, sl, tp)
                    print(f"Multi-account execution results: {results}")
                    
            except Exception as e:
                import sys
                print(f"Execution Pipeline Error: {e}", file=sys.stderr)
                return jsonify({"status": "error", "message": str(e)}), 500
                
            return jsonify({"status": "success", "message": "Signal processed"}), 200
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 400
    else:
        return jsonify({"status": "error", "message": "Unsupported Media Type"}), 415

if __name__ == "__main__":
    print("Starting Hanko X Webhook Executor...")
    app.run(host="0.0.0.0", port=5001)
