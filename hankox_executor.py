import os
import json
import time
import asyncio
from datetime import datetime
import requests
import websockets
from flask import Flask, request, jsonify
from dotenv import load_dotenv, dotenv_values

script_dir = os.path.dirname(os.path.abspath(__file__))
# We look for a Hankox specific env, otherwise fallback to live
env_path = os.path.join(script_dir, ".env.hankolive")
# Only load .env if it exists locally, but do NOT override system/Render env vars
if os.path.exists(env_path):
    load_dotenv(env_path, override=False)

app = Flask(__name__)

SYMBOL_MAP = {
    "GOLD": "XAUUSD",
    "XAUUSD": "XAUUSD",
    "XAGUSD": "XAGUSD",
    "US30": "U30USD",
    "DJI": "U30USD",
    "USA30": "U30USD",
    "NAS100": "U100USD",
    "NASDAQ": "U100USD",
    "NQ": "U100USD",
    "SPX": "U500USD",
    "SPX500": "U500USD",
    "US500": "U500USD",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD",
    "USDCAD": "USDCAD",
    "NZDUSD": "NZDUSD",
    "CADJPY": "CADJPY",
    "NZDJPY": "NZDJPY",
    "GBPJPY": "GBPJPY",
    "EURJPY": "EURJPY",
    "USDCNH": "USDCNH",
    "USDHKD": "USDHKD",
    "BTCUSD": "BTCUSD",
    "WTI": "WTI",
    "BRENT": "BRENT"
}

def get_active_configs():
    """Reads all account configurations from environment variables or .env files."""
    configs = []
    
    # Load local toggle state cache (useful for local dashboard, might be missing on Render)
    toggles = {}
    toggle_path = os.path.join(script_dir, "toggles.json")
    if os.path.exists(toggle_path):
        try:
            with open(toggle_path, "r") as f:
                toggles = json.load(f)
        except Exception:
            pass

    # Known account types/files
    env_files = [".env.hankodemo", ".env.hankolive", ".env.crucialdemo", ".env.cruciallive", ".env.atlasdemo", ".env.gatesdemo"]
    
    for env_name in env_files:
        # 1. Load values from file if it exists
        env_path = os.path.join(script_dir, env_name)
        file_vals = dotenv_values(env_path) if os.path.exists(env_path) else {}
        
        # 2. Activation check: check toggles -> file -> os.environ -> default False
        # We need to know which prefix to check for environment variables if the file is missing
        # For Render, we often set ACCOUNT_ACTIVE_HANKODEMO or similar, but the current dashboard
        # just sets ACCOUNT_ACTIVE inside the specific .env file.
        # To make it robust on Render, we'll check if credentials exist.
        
        is_active = False
        if env_name in toggles:
            is_active = bool(toggles[env_name])
        elif "ACCOUNT_ACTIVE" in file_vals:
            is_active = file_vals.get("ACCOUNT_ACTIVE", "false").lower() == "true"
        else:
            # Fallback for Render: if matching credentials exist in os.environ, assume active
            # unless explicitly disabled.
            prefix = env_name.replace(".env.", "").upper()
            if f"HANKOX_EMAIL_{prefix}" in os.environ or f"TRADELOCKER_EMAIL_{prefix}" in os.environ:
                is_active = True
            elif "hanko" in env_name.lower() and (os.environ.get("HANKOX_EMAIL") or os.environ.get("HANKOX_LIVE_ACCOUNT_ID")):
                # Legacy check for the primary account
                is_active = True
        
        if is_active:
            print(f"Routing logic includes active account: {env_name}")
            
            # Helper to get val with priority: os.environ -> file_vals
            def get_val(key):
                # Try specific env var first (e.g. HANKOX_EMAIL_HANKODEMO)
                prefix = env_name.replace(".env.", "").upper()
                specific_key = f"{key}_{prefix}"
                return os.environ.get(specific_key) or os.environ.get(key) or file_vals.get(key)

            # Identify Broker Category
            if "hanko" in env_name.lower():
                b_type = "hankotrade"
                is_live = "live" in env_name.lower()
                
                email = get_val("HANKOX_EMAIL") or get_val("HANKOX_LIVE_ACCOUNT_ID") or get_val("HANKOX_DEMO_ACCOUNT_ID")
                password = get_val("HANKOX_PASSWORD") or get_val("HANKOX_LIVE_PASSWORD") or get_val("HANKOX_DEMO_PASSWORD")
                
                if email and password:
                    configs.append({
                        "name": env_name,
                        "type": b_type,
                        "is_live": is_live,
                        "auth_url": "https://tradeapi.hankotrade.com/api/login",
                        "acc_info_url": "https://tradeapi.hankotrade.com/api/act/user/account/balance",
                        "ws_url": "wss://livefeed.hankotrade.com/" if is_live else "wss://demofeed.hankotrade.com/",
                        "email": email,
                        "password": password,
                        "server": get_val("HANKOX_SERVER") or ("Hankotrade-Live" if is_live else "Hankotrade-Demo"),
                        "symbol_suffix": ".HKT"
                    })
            elif "crucial" in env_name.lower() or "atlas" in env_name.lower() or "gates" in env_name.lower():
                b_type = "tradelocker"
                is_live = "live" in env_name.lower()
                api_url = get_val("TRADELOCKER_API_URL") or ("https://live.tradelocker.com/backend-api" if is_live else "https://demo.tradelocker.com/backend-api")
                
                email = get_val("TRADELOCKER_EMAIL")
                password = get_val("TRADELOCKER_PASSWORD")
                
                if email and password:
                    configs.append({
                        "name": env_name,
                        "type": b_type,
                        "is_live": is_live,
                        "api_url": api_url,
                        "email": email,
                        "password": password,
                        "server": get_val("TRADELOCKER_SERVER"),
                        "account_id": get_val("TRADELOCKER_ACCOUNT_ID"),
                        "symbol_suffix": "" 
                    })
                
    return configs

def authenticate_tradelocker(config):
    """Authenticate with standard TradeLocker REST API."""
    auth_url = f"{config['api_url']}/auth/jwt/token"
    payload = {
        "email": config["email"],
        "password": config["password"],
        "server": config["server"]
    }
    
    print(f"[{config['name']}] Authenticating via TradeLocker REST...")
    resp = requests.post(auth_url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    if not resp.ok:
        raise Exception(f"TradeLocker Auth failed: {resp.text}")
        
    token = resp.json().get("accessToken")
    
    # If account_id or acc_num is missing, fetch them
    acc_id = config.get("account_id")
    acc_num = config.get("account_num")
    if not acc_id or not acc_num:
        acc_url = f"{config['api_url']}/auth/jwt/all-accounts"
        acc_resp = requests.get(acc_url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if acc_resp.ok:
            accounts = acc_resp.json().get("accounts", [])
            for a in accounts:
                if acc_id and str(a.get("id")) == str(acc_id):
                    acc_num = a.get("accNum")
                    break
                elif not acc_id:
                    acc_id = a.get("id")
                    acc_num = a.get("accNum")
                    break
            
    return token, acc_id, acc_num

def authenticate_hankotrade(config):
    """Authenticate with Hanko X specific REST API."""
    login_data = {
        "email": config["email"],
        "password": config["password"],
        "server_type": "hankotrade_live" if config["is_live"] else "hankotrade_demo"
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://trade.hankotrade.com',
        'Referer': 'https://trade.hankotrade.com/'
    }
    
    print(f"[{config['name']}] Authenticating via Hanko X Specific API...")
    resp = requests.post(config["auth_url"], json=login_data, headers=headers, timeout=10)
    if not resp.ok:
        raise Exception(f"Hanko Auth failed: {resp.text}")
        
    token = resp.json().get('data', {}).get('user', {}).get('token')
    if not token:
        raise Exception("No token received from Hanko login.")
        
    # Fetch Account ID
    headers['Authorization'] = f'Bearer {token}'
    acc_resp = requests.post(config["acc_info_url"], json={}, headers=headers, timeout=10)
    acc_id = acc_resp.json().get('data', {}).get('ACCOUNT_ID') if acc_resp.ok else None
    
    return token, acc_id

def is_sabbath_mode_active():
    """Check if the current time is within the Sabbath blackout period (Friday 4 PM to Sunday 5 PM)."""
    now = datetime.now()
    if now.weekday() == 4 and now.hour >= 16:
        return True
    if now.weekday() == 5:
        return True
    if now.weekday() == 6 and now.hour < 17:
        return True
    return False

def is_session_active(symbol):
    """Checks string constraints against current time for allowed trading sessions."""
    allowed_sessions_str = os.environ.get(f"SESSIONS_{symbol}", "Asian,London,New York")
    if not allowed_sessions_str.strip(): return True
    allowed_sessions = [s.strip() for s in allowed_sessions_str.split(",")]
    
    now_utc = datetime.utcnow()
    hour = now_utc.hour
    
    # Standardized Session Hours
    # Asian Session: 22:00 - 08:00 UTC
    # London Session: 07:00 - 16:00 UTC
    # New York Session: 13:00 - 22:00 UTC
    is_asian = (22 <= hour or hour < 8)
    is_london = (7 <= hour < 16)
    is_new_york = (13 <= hour < 22)
    
    if "Asian" in allowed_sessions and is_asian: return True
    if "London" in allowed_sessions and is_london: return True
    if "New York" in allowed_sessions and is_new_york: return True

    return False

async def execute_trade_rest(token, acc_id, acc_num, symbol, side, qty, api_url, env_name, sl=0, tp=0):
    """Executes a trade instruction directly over the TradeLocker REST API."""
    side_lower = side.lower()
    side_tl = "buy" if side_lower in ("buy", "long") else "sell"
    
    # Map Symbol to Instrument ID (TradeLocker requirement)
    # We use a placeholder mapping or try to find it via API.
    # For now, we'll use base symbol strings if the API supports it, but usually standard TL needs ID.
    # NOTE: In Tradelocker, you place orders to /trade/accounts/{acc_id}/orders
    order_url = f"{api_url}/trade/accounts/{acc_id}/orders"
    
    # Symbol mapping logic for Indices/Forex
    base_symbol = symbol.upper().replace(".HKT", "")
    mapped_symbol = SYMBOL_MAP.get(base_symbol, base_symbol)
    
    # We attempt to find the ID via a quick search or use a baked-in map for Crucial
    # (Based on standard Crucial/Tradelocker IDs)
    # BAKED-IN INSTRUMENT IDs (Broker Specific)
    id_maps = {
        ".env.crucialdemo": {
            "US30": 17028, "NAS100": 17035, "SPX500": 17034,
            "EURUSD": 16985, "GBPUSD": 16977, "XAUUSD": 17049, "XAGUSD": 17048,
            "CADJPY": 16976, "NZDJPY": 16978, "USDHKD": 16980, "USDCNH": 16981,
            "BTCUSD": 17949
        },
        ".env.cruciallive": {
            "US30": 17028, "NAS100": 17035, "SPX500": 17034,
            "EURUSD": 16985, "GBPUSD": 16977, "XAUUSD": 17049, "XAGUSD": 17048,
            "CADJPY": 16976, "NZDJPY": 16978, "USDHKD": 16980, "USDCNH": 16981,
            "BTCUSD": 17949
        },
        ".env.atlasdemo": {
            "US30": 16337, "NAS100": 16341, "SPX500": 16336, "SPX": 16336,
            "XAUUSD": 16343, "XAGUSD": 16344, "BTCUSD": 16304,
            "EURUSD": 16316, "GBPUSD": 16310, "USDJPY": 16309,
            "AUDUSD": 16323, "USDCAD": 16322, "NZDUSD": 16330,
            "CADJPY": 16331, "NZDJPY": 16333, "GBPJPY": 16325, "EURJPY": 16329,
            "WTI": 16306, "BRENT": 16307
        }
    }
    
    current_map = id_maps.get(env_name, id_maps[".env.crucialdemo"])
    inst_id = current_map.get(mapped_symbol)
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accNum": str(acc_num)
    }

    # Fetch Route ID for the instrument
    route_id = None
    try:
        inst_url = f"{api_url}/trade/accounts/{acc_id}/instruments"
        inst_resp = requests.get(inst_url, headers=headers, timeout=10)
        if inst_resp.ok:
            data = inst_resp.json()
            instruments = data.get("d", {}).get("instruments", []) if isinstance(data, dict) else []
            for inst in instruments:
                if str(inst.get("tradableInstrumentId")) == str(inst_id) or inst.get("name") == mapped_symbol:
                    routes = inst.get("routes", [])
                    for r in routes:
                        if r.get("type") == "TRADE":
                            route_id = r.get("id")
                            break
                    if route_id: break
    except Exception as e:
        print(f"[{env_name}] Error fetching routeId: {e}")

    payload = {
        "price": 0, # market
        "qty": float(qty),
        "side": side_tl,
        "type": "market",
        "tradableInstrumentId": inst_id if inst_id else mapped_symbol,
        "routeId": route_id,
        "stopLoss": float(sl) if sl else None,
        "takeProfit": float(tp) if tp else None
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accNum": str(acc_num)
    }
    
    print(f"[{env_name}] REST Payload Dispatch: {json.dumps(payload)}")
    resp = requests.post(order_url, json=payload, headers=headers, timeout=10)
    
    if resp.ok:
        print(f"[{env_name}] REST Order Success: {resp.text}")
        return True
    else:
        print(f"[{env_name}] REST Order Failed: {resp.text}")
        return False

async def execute_trade_ws(token, acc_id, symbol, side, qty, wss_url, env_name, sl=0, tp=0):
    """Executes a trade instruction directly over the Hanko X WebSocket."""
    # Normalize side: accept 'buy', 'long' -> 1;  'sell', 'short' -> 0 (ActTrader spec)
    side_lower = side.lower()
    side_int = 1 if side_lower in ("buy", "long") else 0
    
    base_symbol = symbol.upper().replace(".HKT", "")
    mapped_symbol = SYMBOL_MAP.get(base_symbol, base_symbol)
    formatted_symbol = f"{mapped_symbol}.HKT"
    
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
                import zlib
                import base64
                def decode_hanko(msg):
                    try:
                        # 1. Raw bytes check (direct zlib x9c)
                        if isinstance(msg, bytes):
                            if len(msg) > 2 and msg[0] == 0x78 and msg[1] == 0x9c:
                                try: return zlib.decompress(msg).decode('utf-8')
                                except: pass
                        
                        # 2. String check (base64 zlib or plain)
                        if isinstance(msg, str):
                            if not msg.startswith("eJ"): return msg
                            try:
                                msg_bytes = base64.b64decode(msg)
                                return zlib.decompress(msg_bytes).decode('utf-8')
                            except:
                                return msg # Fallback to plain string
                        
                        # 3. Bytes fallback
                        if isinstance(msg, bytes):
                            try: return zlib.decompress(msg).decode('utf-8')
                            except: pass
                            
                        return str(msg)
                    except:
                        return str(msg)

                order_success = None  # None = no response received yet
                end_time = time.time() + 5.0
                while time.time() < end_time:
                    try:
                        resp = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        decoded = decode_hanko(resp)
                        
                        if "{" in decoded:
                            try:
                                data = json.loads(decoded)
                                msg = data.get("message", data)
                                stat = msg.get("stat") if isinstance(msg, dict) else None
                                
                                # Identify order response by tempOrderId or stat field
                                if "tempOrderId" in str(data) or stat in ("OK", "NOK"):
                                    if stat == "NOK":
                                        resp_msg = msg.get("resp_msg", "Unknown error")
                                        print(f"[{env_name}] WS ORDER NOK: {resp_msg}")
                                        order_success = False
                                    elif stat == "OK" and "tempOrderId" in str(data):
                                        resp_msg = msg.get("resp_msg", "Order placed")
                                        print(f"[{env_name}] WS ORDER OK: {resp_msg}")
                                        order_success = True
                                    else:
                                        # Intermediate OK message (tradeupdate, account, etc.)
                                        print(f"[{env_name}] WS ORDER RESP: {decoded}")
                                    
                                    if order_success is not None:
                                        break
                            except:
                                pass
                        
                        # Check for global errors in non-JSON messages
                        if "error" in decoded.lower() and "tempOrderId" in decoded:
                            print(f"[{env_name}] WS ERROR: {decoded}")
                            order_success = False
                            break
                            
                    except asyncio.TimeoutError:
                        continue
                
                if order_success is None:
                    print(f"[{env_name}] WS: No order confirmation received (timeout)")
                        
            except Exception as e:
                print(f"[{env_name}] WS Wait Error: {e}")
                
            return order_success if order_success is not None else True
            
    except Exception as e:
        print(f"[{env_name}] WebSocket Error: {e}")
        return False

async def place_multi_orders_async(active_configs, symbol, side, qty, sl=0, tp=0):
    """Concurrent execution across multi-broker landscape."""
    tasks = []
    
    for config in active_configs:
        try:
            # 1. Authenticate based on type
            if config["type"] == "hankotrade":
                token, acc_id = authenticate_hankotrade(config)
                # 2. Hanko uses WS dispatch
                task = asyncio.create_task(execute_trade_ws(token, acc_id, symbol, side, qty, config["ws_url"], config["name"], sl, tp))
            else:
                token, acc_id, acc_num = authenticate_tradelocker(config)
                # 2. TradeLocker uses REST dispatch
                task = asyncio.create_task(execute_trade_rest(token, acc_id, acc_num, symbol, side, qty, config["api_url"], config["name"], sl, tp))
                
            tasks.append({"env": config["name"], "task": task})
        except Exception as e:
            print(f"[{config['name']}] Multi-Routing Fail: {e}")
            
    results = {}
    for t in tasks:
        try:
            success = await t["task"]
            results[t["env"]] = success
            status = "✅ SUCCESS" if success else "❌ FAILED"
            print(f"[{t['env']}] Global Routing Result: {status}")
        except Exception as e:
            print(f"[{t['env']}] Task Error: {e}")
            results[t["env"]] = False
        
    return results

def place_market_orders_sync(active_configs, symbol, side, qty, sl=0, tp=0):
    """Synchronous wrapper to deploy orders async in a background thread."""
    import threading
    # Guard: cap concurrent trade threads to avoid memory exhaustion on Render
    active_thread_count = threading.active_count()
    if active_thread_count > 20:
        print(f"WARNING: {active_thread_count} threads active — skipping dispatch to avoid OOM")
        return "Skipped (thread limit)"
    try:
        def run_in_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(place_multi_orders_async(active_configs, symbol, side, qty, sl, tp))
            finally:
                loop.close()
            
        thread = threading.Thread(target=run_in_loop, daemon=True)
        thread.start()
        return "Dispatched to background thread"
    except Exception as e:
        print(f"Failed to dispatch thread: {e}")
        return "Dispatch Error"



@app.route("/toggle", methods=["POST"])
def toggle_account():
    data = request.json
    env_name = data.get("env_name")
    is_active = data.get("active")
    
    if env_name and env_name in [".env.hankodemo", ".env.hankolive", ".env.crucialdemo", ".env.cruciallive", ".env.atlasdemo", ".env.forexcom", ".env.gatesdemo"]:
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

            # 0. Sabbath Mode Check
            bypass_sabbath = str(data.get("bypass_sabbath", "false")).lower() == "true"
            if is_sabbath_mode_active() and not bypass_sabbath:
                print(f"Rejecting trade signal for {symbol}: Sabbath Mode Active.")
                return jsonify({"status": "rejected", "reason": "Sabbath Mode Active"}), 200
            
            # 1. Session Filter — only applies to entry actions, not close/signal
            # Also skip session check if 'signal' action (journal only)
            skip_session_check = action in ["close_long", "close_short", "close_all", "signal"]
            if not skip_session_check and symbol != "UNKNOWN":
                if not is_session_active(symbol):
                    print(f"Rejecting trade signal for {symbol}: Outside allowed sessions.")
                    return jsonify({"status": "rejected", "reason": "Session Closed"}), 200

            # 2. Filter out non-trade actions (signals are journal-only)
            if action == "signal":
                print(f"Signal alert received for {symbol}. Logging only — no trade execution.")
                return jsonify({"status": "logged", "message": f"Signal for {symbol} recorded"}), 200

            # 3. Visual Arbiter (mocked/placeholder as per other executors)
            enable_vision = str(os.environ.get("ENABLE_VISUAL_ARBITER", "false")).lower() == "true"
            if enable_vision and action not in ["close_long", "close_short", "close_all"]:
                print("Visual Arbiter checking (stub)...")
                
            # 4. Execution Phase
            try:
                active_configs = get_active_configs()
                if not active_configs:
                    print("Notice: Signal received but no accounts are toggled active.")
                    return jsonify({"status": "ignored", "reason": "No active accounts"}), 200
                
                # Handling order logic
                if action == "close_all":
                    # Sabbath / End-of-Week: close ALL open positions by netting
                    # We close both buy and sell sides for all mapped symbols
                    print("CLOSE_ALL triggered — attempting to flatten all positions.")
                    all_symbols = list(SYMBOL_MAP.values())
                    for close_sym in set(all_symbols):
                        qty = float(os.environ.get(f"LOT_SIZE_{close_sym}", 0.0))
                        if qty <= 0:
                            qty = float(os.environ.get("BASE_LOT_SIZE", 0.01))
                        # Close any longs (sell) and shorts (buy)
                        place_market_orders_sync(active_configs, close_sym, "sell", qty, 0, 0)
                        place_market_orders_sync(active_configs, close_sym, "buy", qty, 0, 0)
                    print("CLOSE_ALL sequence dispatched.")

                elif action in ["close_long", "close_short"]:
                    # Implement "Netting" close by placing opposite trade
                    side = "sell" if action == "close_long" else "buy"
                    qty = float(data.get("contracts", data.get("qty", 0.0)))
                    if qty <= 0:
                        qty = float(os.environ.get(f"LOT_SIZE_{symbol}", 0.0))
                        if qty <= 0:
                            qty = float(os.environ.get("BASE_LOT_SIZE", 0.01))
                    
                    print(f"Executing Netting CLOSE for {symbol}: placing {side} of {qty} lots")
                    results = place_market_orders_sync(active_configs, symbol, side, qty, 0, 0)

                elif action in ("buy", "sell", "long", "short", "entry"):
                    # Qty logic: prioritize 'contracts' (actual lots) over 'qty' (often 1.0 default)
                    qty = float(data.get("contracts", data.get("qty", 0.0)))
                    if qty <= 0:
                        qty = float(os.environ.get(f"LOT_SIZE_{symbol}", 0.0))
                        if qty <= 0:
                            qty = float(os.environ.get("BASE_LOT_SIZE", 0.01))
                    
                    if qty <= 0:
                        print(f"Rejecting trade: Resolved lot size {qty} is still <= 0")
                        return jsonify({"status": "ignored", "reason": "Zero Lot Size"}), 200
                        
                    # Normalize side direction from any recognized format
                    raw_side = data.get("side", "").lower()
                    raw_action = action  # already lower-cased above

                    if raw_side in ("buy", "sell", "long", "short"):
                        side = "buy" if raw_side in ("buy", "long") else "sell"
                    elif raw_action in ("buy", "sell", "long", "short"):
                        side = "buy" if raw_action in ("buy", "long") else "sell"
                    else:
                        side = "buy"  # safe fallback

                    print(f"[DEBUG] raw_side={repr(raw_side)!r} raw_action={repr(raw_action)!r} resolved_side={side}")
                    sl = data.get("sl", 0)
                    tp = data.get("tp", 0)
                    
                    results = place_market_orders_sync(active_configs, symbol, side, qty, sl, tp)
                    print(f"Multi-account execution results: {results}")
                else:
                    print(f"Unknown action '{action}' — ignoring.")
                    return jsonify({"status": "ignored", "reason": f"Unknown action: {action}"}), 200
                    
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
