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
ACCOUNT_ID = os.environ.get("TRADELOCKER_ACC_NUM", "your_account_number")

# Example mapping of TradingView symbols to TradeLocker Instrument IDs
# You will need to query the TradeLocker instruments API to get the exact IDs for Hankotrade
INSTRUMENT_MAP = {
    "US30": 12345, # Example ID, you must fetch the real one via the API or dashboard
    "EURUSD": 67890,
    "BTCUSD": 16711
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
    """Authenticate with TradeLocker API and return JWT access token and account ID."""
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
    
    # TradeLocker API now requires the accNum upfront for /trade/ endpoints.
    # We bypass fetching the account list and use the explicit environment variable.
    if ACCOUNT_ID == "your_account_number" or not ACCOUNT_ID:
        raise Exception("TRADELOCKER_ACC_NUM environment variable is missing or invalid.")
        
    print(f"Authenticated successfully! Using Account ID: {ACCOUNT_ID}")
    
    return token, ACCOUNT_ID

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

def place_order(token, account_id, signal_data):
    """Place a market order on TradeLocker based on the webhook signal."""
    symbol = signal_data.get("symbol")
    side = signal_data.get("side", "buy").lower()
    tl_side = "buy" if side == "long" else "sell"
    
    instrument_id = INSTRUMENT_MAP.get(symbol)
    if not instrument_id:
        print(f"Error: {symbol} is not mapped to a TradeLocker Instrument ID. Cannot place order.")
        return
        
    print(f"Placing {tl_side} order for {symbol} (Instrument ID: {instrument_id})...")
    
    order_url = f"{TRADELOCKER_API_URL}/trade/accounts/{account_id}/orders"
    headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(account_id),
        "Content-Type": "application/json"
    }
    
    # Pine Script sends lots/contracts as 'contracts' or defaulting to 1
    quantity = signal_data.get("contracts", 1.0)
    sl = signal_data.get("sl")
    tp = signal_data.get("tp")
    
    payload = {
        "tradableInstrumentId": instrument_id,
        "quantity": float(quantity),
        "side": tl_side,
        "type": "market",
        "stopLoss": float(sl) if sl else None,
        "takeProfit": float(tp) if tp else None
    }
    
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
        token, account_id = authenticate()
        
        # 3. Place Trade
        place_order(token, account_id, data)
        
        return jsonify({"status": "success", "message": "Trade processed"}), 200
        
    except Exception as e:
        print(f"Error processing trade: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run the Flask app on port 5000
    print("Wise Steward Executor standing by for webhook payloads on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
