import os
import json
import time
from datetime import datetime, timezone
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# -------------------------------------------------------------------
# Wise Steward Trading Agent - TradeLocker Executor
# -------------------------------------------------------------------

TRADELOCKER_API_URL = os.environ.get("TRADELOCKER_API_URL", "https://api.tradelocker.com")
EMAIL = os.environ.get("TRADELOCKER_EMAIL", "your_email")
PASSWORD = os.environ.get("TRADELOCKER_PASSWORD", "your_password")
SERVER = os.environ.get("TRADELOCKER_SERVER", "Hankotrade-Live")

# Example mapping of TradingView symbols to TradeLocker Instrument IDs
# You will need to query the TradeLocker instruments API to get the exact IDs for Hankotrade
INSTRUMENT_MAP = {
    "US30": 12345, # Example ID, you must fetch the real one via the API or dashboard
    "EURUSD": 67890,
    "BTCUSD": 16720
}

def is_sabbath_mode_active():
    """
    Check if the current time is within the Sabbath blackout period:
    Friday 4:00 PM EST to Sunday 5:00 PM EST.
    Returns True if Sabbath Mode is active, False otherwise.
    """
    now = datetime.now()
    if now.weekday() == 4 and now.hour >= 16: # Friday after 4PM
        return True
    if now.weekday() == 5: # Saturday
        return True
    if now.weekday() == 6 and now.hour < 17: # Sunday before 5PM
        return True
    return False

def authenticate():
    """Authenticate with TradeLocker API and return JWT access token, account ID, and accNum."""
    print("Authenticating with TradeLocker...")
    auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
    payload = {
        "email": EMAIL,
        "password": PASSWORD,
        "server": SERVER
    }
    headers = {"Content-Type": "application/json"}
    
    auth_response = requests.post(auth_url, json=payload, headers=headers)
    
    if not auth_response.ok:
        raise Exception(f"Failed to authenticate: {auth_response.text}")
        
    data = auth_response.json()
    token = data.get("accessToken")
    
    # Fetch all accounts associated with the token to get both UUID and accNum
    accounts_url = f"{TRADELOCKER_API_URL}/auth/jwt/all-accounts"
    acc_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    acc_response = requests.get(accounts_url, headers=acc_headers)
    
    if not acc_response.ok:
        raise Exception(f"Failed to fetch accounts: {acc_response.text}")
        
    accounts = acc_response.json().get("accounts", [])
    if not accounts:
        raise Exception("No TradeLocker accounts found for this user.")
        
    # We assume the first account is the primary trading account
    first_account = accounts[0]
    account_id = first_account.get("id")
    acc_num = first_account.get("accNum", "1")
    
    print(f"Authenticated successfully! Account ID: {account_id}, accNum: {acc_num}")
    
    return token, account_id, acc_num

def write_journal_entry(signal_data):
    """Write an entry to the Journal of the Sovereign Arbitrator."""
    print("Writing to Journal of the Sovereign Arbitrator...")
    journal_entry = {
        "timestamp": datetime.now().isoformat(),
        "technical_confluence": signal_data.get("strategy", "Unknown"),
        "temporal_state": "Sabbath Boundary Check Passed",
        "biblical_principle": "Exercising Diligence over Haste.",
        "risk_parameters": f"Risk USD: {signal_data.get('risk_usd', 'Unknown')}"
    }
    print(json.dumps(journal_entry, indent=2))

def place_order(token, account_id, acc_num, signal_data):
    """Place a market order on TradeLocker based on the webhook signal."""
    symbol = signal_data.get("symbol")
    side = signal_data.get("side", "buy").lower()
    tl_side = "buy" if side in ["long", "buy"] else "sell"
    
    instrument_id = INSTRUMENT_MAP.get(symbol)
    if not instrument_id:
        print(f"Error: {symbol} is not mapped to a TradeLocker Instrument ID. Cannot place order.")
        return
        
    print(f"Placing {tl_side} order for {symbol} (Instrument ID: {instrument_id})...")
    
    # First, fetch the correct routeId for this instrument
    instruments_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/instruments"
    inst_headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(acc_num),
        "Content-Type": "application/json"
    }
    inst_response = requests.get(instruments_url, headers=inst_headers)
    route_id = None
    if inst_response.ok:
        data = inst_response.json()
        inst_list = data.get("d", []) if isinstance(data, dict) else data
        if isinstance(inst_list, dict) and "instruments" in inst_list:
            inst_list = inst_list["instruments"]
        
        for inst in inst_list:
            if isinstance(inst, dict) and inst.get("tradableInstrumentId") == instrument_id:
                routes = inst.get("routes", [])
                for r in routes:
                    if r.get("type") == "TRADE":
                        route_id = r.get("id")
                        break
    
    if not route_id:
        print(f"Warning: Could not dynamically fetch routeId for Instrument {instrument_id}. Attempting to proceed without it...")
    
    order_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/orders"
    headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(acc_num),
        "Content-Type": "application/json"
    }
    
    # Pine Script sends lots/contracts as 'contracts' or defaulting to 1
    quantity = signal_data.get("contracts", 1.0)
    sl = signal_data.get("sl")
    tp = signal_data.get("tp")
    
    payload = {
        "tradableInstrumentId": instrument_id,
        "qty": float(quantity),
        "side": tl_side,
        "type": "market",
        "validity": "IOC",
        "stopLoss": float(sl) if sl else None,
        "takeProfit": float(tp) if tp else None
    }
    if route_id:
        payload["routeId"] = route_id
    
    # Note: TradeLocker order payloads often vary slightly by broker routing
    # Some require routeId, others just accept the raw market payload
    response = requests.post(order_url, json=payload, headers=headers)
    
    if response.ok:
        print(f"Trade successfully placed! Tradelocker Order ID: {response.json().get('orderId', 'Unknown')}")
    else:
        print(f"Failed to place trade: {response.text}")

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """Endpoint to receive TradingView webhooks."""
    print("\n--- Received Webhook Signal ---")
    
    if is_sabbath_mode_active():
        print("Rejecting trade signal: Sabbath Mode Active")
        return jsonify({"status": "rejected", "reason": "Sabbath Mode Active"}), 403
    
    print("Sabbath Mode inactive. Proceeding to evaluate trade...")
    
    try:
        # Get JSON data from the request
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload found"}), 400
            
        print(f"Received data: {data}")
        
        # 1. Write Journal
        write_journal_entry(data)
        
        # 2. Authenticate
        token, account_id, acc_num = authenticate()
        
        # 3. Place Trade
        place_order(token, account_id, acc_num, data)
        
        return jsonify({"status": "success", "message": "Trade processed"}), 200
        
    except Exception as e:
        print(f"Error processing trade: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run the Flask app on port 5000
    print("Wise Steward Executor standing by for webhook payloads on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
