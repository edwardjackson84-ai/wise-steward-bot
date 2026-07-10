import os
import json
from datetime import datetime
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# -------------------------------------------------------------------
# Wise Steward Trading Agent - TradeLocker Multi-Broker Executor
# -------------------------------------------------------------------

INSTRUMENT_MAP = {
    "US30": 17028, # Mapped from Hankotrade Demo API
    "BTCUSD": 16720,
    "EURUSD": 16985,
    "GBPUSD": 16977,
    "NAS100": 17035,
    "SPX500": 17034
}

def get_broker_configs():
    """Dynamically load broker configurations from environment variables."""
    configs = []
    
    # Legacy support if the user still uses TRADELOCKER_ prefixes
    fallback_email = os.environ.get("TRADELOCKER_EMAIL")
    if fallback_email:
        configs.append({
            "name": "Legacy Broker",
            "api_url": os.environ.get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api"),
            "email": fallback_email,
            "password": os.environ.get("TRADELOCKER_PASSWORD", ""),
            "server": os.environ.get("TRADELOCKER_SERVER", "ATLAS"),
            "accounts": os.environ.get("TRADELOCKER_ACCOUNT_IDS", ""),
            "multipliers": os.environ.get("TRADELOCKER_LOT_MULTIPLIERS", "1.0")
        })
        
    # Scan for BROKER_1_, BROKER_2_, etc.
    for i in range(1, 21):
        email = os.environ.get(f"BROKER_{i}_EMAIL")
        if email:
            configs.append({
                "name": f"Broker {i}",
                "api_url": os.environ.get(f"BROKER_{i}_API_URL", "https://demo.tradelocker.com/backend-api"),
                "email": email,
                "password": os.environ.get(f"BROKER_{i}_PASSWORD", ""),
                "server": os.environ.get(f"BROKER_{i}_SERVER", ""),
                "accounts": os.environ.get(f"BROKER_{i}_ACCOUNTS", ""),
                "multipliers": os.environ.get(f"BROKER_{i}_MULTIPLIERS", "1.0")
            })
            
    return configs

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

def authenticate(broker):
    """Authenticate with TradeLocker API for a specific broker config."""
    print(f"Authenticating with TradeLocker for {broker['name']} on server '{broker['server']}'...")
    auth_url = f"{broker['api_url']}/auth/jwt/token"
    payload = {"email": broker['email'], "password": broker['password'], "server": broker['server']}
    headers = {"Content-Type": "application/json"}
    
    auth_response = requests.post(auth_url, json=payload, headers=headers)
    if not auth_response.ok:
        print(f"[{broker['name']}] Failed to authenticate: {auth_response.text}")
        return None, []
        
    token = auth_response.json().get("accessToken")
    
    accounts_url = f"{broker['api_url']}/auth/jwt/all-accounts"
    acc_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    acc_response = requests.get(accounts_url, headers=acc_headers)
    
    if not acc_response.ok:
        print(f"[{broker['name']}] Failed to fetch accounts: {acc_response.text}")
        return token, []
        
    accounts = acc_response.json().get("accounts", [])
    if not accounts:
        print(f"[{broker['name']}] No TradeLocker accounts found for this user.")
        return token, []
        
    target_accounts = []
    target_id_list = [t.strip() for t in broker['accounts'].split(",") if t.strip()]
    if target_id_list:
        for acc in accounts:
            if str(acc.get("id")) in target_id_list or str(acc.get("accNum")) in target_id_list:
                target_accounts.append(acc)
                
    if not target_accounts:
        print(f"[{broker['name']}] Target account IDs {target_id_list} not found. Defaulting to first account.")
        target_accounts = [accounts[0]]
        
    for acc in target_accounts:
        print(f"[{broker['name']}] Targeting Account ID: {acc.get('id')} - Balance: {acc.get('accountBalance')}")
        
    return token, target_accounts

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

def close_position(api_url, token, account_id, acc_num, signal_data, target_close_side):
    """Closes all open positions for the given symbol matching the side."""
    symbol = signal_data.get("symbol")
    instrument_id = INSTRUMENT_MAP.get(symbol)
    if not instrument_id:
        print(f"Error: {symbol} is not mapped. Cannot close position.")
        return
        
    print(f"Attempting to close {target_close_side} position(s) for {symbol}...")
    
    # Fetch open positions
    pos_url = f"{api_url}/trade/accounts/{account_id}/positions"
    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
    resp = requests.get(pos_url, headers=headers)
    
    if not resp.ok:
        print(f"Failed to fetch positions: {resp.text}")
        return
        
    positions_data = resp.json()
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
        if isinstance(pos, list) and len(pos) >= 5:
            pos_id = pos[0]
            pos_instrument_id = pos[1]
            pos_side = pos[3].lower()
            
            if str(pos_instrument_id) == str(instrument_id):
                target_side_tl = "buy" if target_close_side in ["long", "buy"] else "sell"
                
                if pos_side == target_side_tl:
                    close_url = f"{api_url}/trade/positions/{pos_id}"
                    del_resp = requests.delete(close_url, headers=headers)
                    
                    if del_resp.ok:
                        print(f"Successfully closed {target_close_side} position ID: {pos_id}")
                        positions_closed += 1
                    else:
                        print(f"Failed to close position ID {pos_id}: {del_resp.text}")
                    
    if positions_closed == 0:
        print(f"No open {target_close_side} positions found for {symbol} to close.")

def place_order(api_url, token, account_id, acc_num, signal_data, multiplier=1.0):
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
        
    print(f"Placing {tl_side} order for {symbol} (Instrument ID: {instrument_id}) with multiplier {multiplier}...")
    
    # Fetch dynamic routeId (Required for Hankotrade indices/crypto)
    instruments_url = f"{api_url}/trade/accounts/{account_id}/instruments"
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
                        
    order_url = f"{api_url}/trade/accounts/{account_id}/orders"
    
    # Parse generic defaults or Oliver Velez specific fields
    base_qty = signal_data.get("contracts", signal_data.get("qty", 1.0))
    try:
        final_qty = float(base_qty) * multiplier
    except ValueError:
        final_qty = float(multiplier)
        
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
        "qty": final_qty,
        "side": tl_side,
        "type": "market",
        "validity": "IOC",
        "stopLoss": sl_float,
        "takeProfit": tp_float
    }
    if route_id:
        payload["routeId"] = route_id
        
    print(f"OUTGOING PAYLOAD: {json.dumps(payload)}")
    response = requests.post(order_url, json=payload, headers=headers)
    if response.ok:
        print(f"Trade successfully placed! Order ID: {response.json().get('orderId', 'Unknown')}")
    else:
        print(f"Failed to place trade: {response.text}")

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    print("\n--- Received Webhook Signal ---")
    
    if is_sabbath_mode_active():
        print("Rejecting trade signal: Sabbath Mode Active")
        return jsonify({"status": "rejected", "reason": "Sabbath Mode Active"}), 403
        
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload found"}), 400
            
        print(f"Received data: {data}")
        write_journal_entry(data)
        
        brokers = get_broker_configs()
        if not brokers:
            print("ERROR: No broker configurations found in environment variables!")
            return jsonify({"error": "No brokers configured."}), 400
            
        action = data.get("action", "").lower()
        total_accounts_processed = 0
        
        for broker in brokers:
            token, target_accounts = authenticate(broker)
            if not token or not target_accounts:
                continue
                
            multipliers_str = [m.strip() for m in broker['multipliers'].split(",")]
            target_id_list = [t.strip() for t in broker['accounts'].split(",") if t.strip()]
            multiplier_map = {}
            for i, acc_id in enumerate(target_id_list):
                try:
                    multiplier_map[acc_id] = float(multipliers_str[i]) if i < len(multipliers_str) else 1.0
                except ValueError:
                    multiplier_map[acc_id] = 1.0
                    
            for acc in target_accounts:
                account_id = acc.get("id")
                acc_num = acc.get("accNum", "1")
                
                mult = 1.0
                if str(account_id) in multiplier_map:
                    mult = multiplier_map[str(account_id)]
                elif str(acc_num) in multiplier_map:
                    mult = multiplier_map[str(acc_num)]
                
                print(f"\n--- Processing for {broker['name']} Account: {acc_num} (Lot Multiplier: {mult}x) ---")
                total_accounts_processed += 1
                
                # Check if this is an exit order
                if action in ["close_long", "close_short"]:
                    target_side = "long" if action == "close_long" else "short"
                    close_position(broker['api_url'], token, account_id, acc_num, data, target_side)
                    
                # Check if it's an entry order
                else:
                    place_order(broker['api_url'], token, account_id, acc_num, data, mult)
                    
        return jsonify({"status": "success", "message": f"Trade processed for {total_accounts_processed} account(s) across {len(brokers)} broker(s)"}), 200
        
    except Exception as e:
        print(f"Error processing trade: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Wise Steward Executor standing by for webhook payloads on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
