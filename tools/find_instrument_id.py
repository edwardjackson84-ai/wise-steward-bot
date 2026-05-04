import requests
import getpass
import json

# -------------------------------------------------------------------
# TradeLocker Instrument ID Finder
# -------------------------------------------------------------------

TRADELOCKER_API_URL = "https://api.tradelocker.com"

def get_instrument_input():
    print("\n--- TradeLocker Instrument Search ---")
    symbol = input("Enter the symbol you want the ID for (e.g., BTCUSD, US30): ").strip().upper()
    return symbol

def authenticate():
    """Authenticate with TradeLocker and return token/account details."""
    print("\n--- Authentication ---")
    email = input("Hankotrade Email: ").strip()
    password = getpass.getpass("Hankotrade Password: ")
    server = input("Server (e.g., Hankotrade-Live or Hankotrade-Demo): ").strip()

    print("\nAuthenticating...")
    
    auth_url = f"{TRADELOCKER_API_URL}/auth/jwt/token"
    payload = {"email": email, "password": password, "server": server}
    headers = {"Content-Type": "application/json"}
    
    auth_response = requests.post(auth_url, json=payload, headers=headers)
    
    if auth_response.status_code != 200:
        print(f"\n[ERROR] Authentication failed. Check your password and server name.\nAPI Response: {auth_response.text}")
        exit()
        
    token = auth_response.json().get("accessToken")
    
    # Get active account ID
    acc_url = f"{TRADELOCKER_API_URL}/trade/accounts"
    acc_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    acc_response = requests.get(acc_url, headers=acc_headers)
    if acc_response.status_code != 200:
        print(f"\n[ERROR] Failed to fetch accounts.\nAPI Response: {acc_response.text}")
        exit()
        
    accounts = acc_response.json().get("accounts", [])
    if not accounts:
        print("\n[ERROR] No TradeLocker accounts found for this user.")
        exit()
        
    account_id = accounts[0].get("id")
    return token, account_id

def search_instruments(token, account_id, target_symbol):
    """Search the TradeLocker instruments list for the target symbol."""
    print(f"\nSearching Hankotrade instruments for: {target_symbol} ...")
    
    # TradeLocker API for fetching all instruments
    instruments_url = f"{TRADELOCKER_API_URL}/trade/markets/instruments"
    headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(account_id),
        "Content-Type": "application/json"
    }
    
    response = requests.get(instruments_url, headers=headers)
    
    if response.status_code != 200:
        print(f"\n[ERROR] Failed to fetch instruments.\nAPI Response: {response.text}")
        return

    data = response.json()
    instruments = data.get("d", []) # Tradelocker often wraps arrays in 'd'
    
    if not instruments: # Fallback if array is direct
        instruments = data if isinstance(data, list) else []

    found = False
    for inst in instruments:
        # Check against the generic 'name' or 'symbol' fields provided by the broker
        name = inst.get("name", "").upper()
        sym = inst.get("symbol", "").upper()
        
        if target_symbol in name or target_symbol in sym:
            found = True
            inst_id = inst.get("tradableInstrumentId")
            print(f"\n[SUCCESS] Found Match!")
            print(f"Name / Symbol: {name} / {sym}")
            print(f"👉 REQUIRED INSTRUMENT ID: {inst_id} 👈")
            print(f"\nAdd this straight to your Python script like this:")
            print(f'"{target_symbol}": {inst_id},')
            
    if not found:
        print(f"\n[WARNING] Could not find any exact matches for '{target_symbol}'. Try searching a broader term like 'BTC' instead.")

if __name__ == "__main__":
    target = get_instrument_input()
    token, account_id = authenticate()
    search_instruments(token, account_id, target)
