"""
matchtrader_executor.py
Wise Steward Agent — Match-Trader (E8 Markets) Executor

Integrates into the existing hankox_executor multi-broker routing system.
Handles login, token refresh, and REST-based order/close operations
for any Match-Trader flavoured broker (e.g. E8 Markets Demo).
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dotenv import dotenv_values

# Global flag to prevent BrokenPipeError in restricted environments (e.g. Dashboard)
VERBOSE = os.environ.get("WISE_STEWARD_VERBOSE", "false").lower() == "true" or __name__ == "__main__"

def _log(*args, **kwargs):
    if VERBOSE:
        try:
            print(*args, **kwargs)
        except BrokenPipeError:
            pass

# ---------------------------------------------------------------------------
# CONFIG LOADER
# ---------------------------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))

def load_e8_config(env_name: str = ".env.e8demo") -> dict:
    env_path = os.path.join(script_dir, env_name)
    file_vals = dotenv_values(env_path) if os.path.exists(env_path) else {}

    def g(key):
        prefix = env_name.replace(".env.", "").upper()
        return (
            os.environ.get(f"MT_{key}_{prefix}")
            or os.environ.get(f"MT_{key}")
            or file_vals.get(f"MT_{key}")
        )

    return {
        "name": env_name,
        "type": "matchtrader",
        "base_url": g("BASE_URL") or "https://mtr.e8markets.com",
        "email": g("EMAIL"),
        "password": g("PASSWORD"),
        "server": g("SERVER") or "MatchTrader-Demo",
        "account_id": g("ACCOUNT_ID"),
    }


# ---------------------------------------------------------------------------
# SYMBOL MAP  (TradingView ticker -> Match-Trader symbol name)
# ---------------------------------------------------------------------------
SYMBOL_MAP = {
    "US30":   "US30",
    "DJI":    "US30",
    "NAS100": "NAS100",
    "SPX500": "SPX500",
    "US500":  "SPX500",
    "XAUUSD": "XAUUSD",
    "GOLD":   "XAUUSD",
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "AUDUSD": "AUDUSD",
    "USDCAD": "USDCAD",
    "NZDUSD": "NZDUSD",
    "BTCUSD": "BTCUSD",
}


# ---------------------------------------------------------------------------
# AUTHENTICATION  — returns (tradingApiToken, systemUUID, tradingAccountToken)
# ---------------------------------------------------------------------------
_token_cache: dict = {}   # keyed by env_name

def authenticate_matchtrader(config: dict) -> tuple[str, str, str]:
    """
    Log in to Match-Trader via POST /manager/co-login.
    Returns (tradingApiToken, systemUUID, tradingAccountToken).
    Caches the token for 12 minutes (token TTL is ~15 min).
    """
    global _token_cache
    env_name = config["name"]

    # Return cached token if still fresh
    cached = _token_cache.get(env_name)
    if cached and datetime.utcnow() < cached["expires_at"]:
        _log(f"[{env_name}] Using cached Match-Trader token.")
        return cached["tradingApiToken"], cached["systemUUID"], cached["tradingAccountToken"]

    base_url = config["base_url"].rstrip("/")
    login_url = f"{base_url}/manager/co-login"

    payload = {
        "email":    config["email"],
        "password": config["password"],
    }
    headers = {
        "Content-Type": "application/json",
        "Accept":       "application/json",
        "User-Agent":   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin":       base_url,
        "Referer":      f"{base_url}/",
    }

    _log(f"[{env_name}] Authenticating with Match-Trader at {login_url}...")
    resp = requests.post(login_url, json=payload, headers=headers, timeout=15)

    if not resp.ok:
        raise Exception(f"[{env_name}] Match-Trader login failed ({resp.status_code}): {resp.text}")

    data = resp.json()
    trading_api_token = data.get("tradingApiToken") or data.get("token")
    if not trading_api_token:
        raise Exception(f"[{env_name}] No tradingApiToken in login response: {data}")

    # Pick the target account
    accounts = data.get("accounts", [])
    target_account = None
    target_id = str(config.get("account_id", ""))
    for acc in accounts:
        if str(acc.get("accountNumber", "")) == target_id or str(acc.get("id", "")) == target_id:
            target_account = acc
            break
    if not target_account and accounts:
        target_account = accounts[0]
        _log(f"[{env_name}] Warning: account {target_id} not found — defaulting to first account.")

    if not target_account:
        raise Exception(f"[{env_name}] No accounts returned from Match-Trader login.")

    system_uuid = (
        target_account.get("systemUuid")
        or target_account.get("uuid")
        or target_account.get("systemUUID")
        or ""
    )
    trading_account_token = (
        target_account.get("tradingAccountToken")
        or target_account.get("token")
        or ""
    )

    # Cache for 12 minutes
    _token_cache[env_name] = {
        "tradingApiToken":     trading_api_token,
        "systemUUID":          system_uuid,
        "tradingAccountToken": trading_account_token,
        "expires_at":          datetime.utcnow() + timedelta(minutes=12),
    }

    balance = target_account.get("balance", "N/A")
    acc_num = target_account.get("accountNumber", target_id)
    _log(f"[{env_name}] ✅ Authenticated — Account #{acc_num} | Balance: {balance}")
    return trading_api_token, system_uuid, trading_account_token


# ---------------------------------------------------------------------------
# PLACE ORDER
# ---------------------------------------------------------------------------
def place_order_matchtrader(config: dict, symbol: str, side: str,
                            qty: float, sl=None, tp=None) -> bool:
    """
    Opens a new market position via:
      POST {base_url}/mtr-api/{systemUUID}/position/open
    """
    env_name = config["name"]
    try:
        trading_api_token, system_uuid, trading_account_token = authenticate_matchtrader(config)
    except Exception as e:
        _log(f"[{env_name}] Auth error: {e}")
        return False

    base_url = config["base_url"].rstrip("/")
    mapped_symbol = SYMBOL_MAP.get(symbol.upper(), symbol.upper())

    side_upper = "BUY" if side.lower() in ("buy", "long") else "SELL"

    url = f"{base_url}/mtr-api/{system_uuid}/position/open"

    payload: dict = {
        "instrument": mapped_symbol,
        "side":       side_upper,
        "volume":     float(qty),
    }
    if sl:
        try:
            payload["slPrice"] = float(sl)
        except (ValueError, TypeError):
            pass
    if tp:
        try:
            payload["tpPrice"] = float(tp)
        except (ValueError, TypeError):
            pass

    headers = {
        "Content-Type":       "application/json",
        "Accept":             "application/json",
        "Auth-trading-api":   trading_api_token,
        "trading-account-token": trading_account_token,
    }

    _log(f"[{env_name}] Placing {side_upper} {qty} lots of {mapped_symbol} → {url}")
    _log(f"[{env_name}] Payload: {json.dumps(payload)}")

    resp = requests.post(url, json=payload, headers=headers, timeout=15)

    if resp.ok:
        _log(f"[{env_name}] ✅ Order placed: {resp.text}")
        return True
    else:
        _log(f"[{env_name}] ❌ Order failed ({resp.status_code}): {resp.text}")
        # Clear cached token in case it expired mid-run
        _token_cache.pop(env_name, None)
        return False


# ---------------------------------------------------------------------------
# CLOSE POSITIONS
# ---------------------------------------------------------------------------
def close_positions_matchtrader(config: dict, symbol: str, side: str) -> bool:
    """
    Closes all open positions for the given symbol and direction via:
      GET  {base_url}/mtr-api/{systemUUID}/open-positions
      POST {base_url}/mtr-api/{systemUUID}/position/close/{positionId}
    """
    env_name = config["name"]
    try:
        trading_api_token, system_uuid, trading_account_token = authenticate_matchtrader(config)
    except Exception as e:
        _log(f"[{env_name}] Auth error: {e}")
        return False

    base_url = config["base_url"].rstrip("/")
    mapped_symbol = SYMBOL_MAP.get(symbol.upper(), symbol.upper())
    target_side_upper = "BUY" if side.lower() in ("buy", "long") else "SELL"

    headers = {
        "Accept":                  "application/json",
        "Auth-trading-api":        trading_api_token,
        "trading-account-token":   trading_account_token,
    }

    # Fetch open positions
    positions_url = f"{base_url}/mtr-api/{system_uuid}/open-positions"
    resp = requests.get(positions_url, headers=headers, timeout=15)

    if not resp.ok:
        _log(f"[{env_name}] Failed to fetch positions: {resp.text}")
        return False

    positions = resp.json()
    if not isinstance(positions, list):
        positions = positions.get("positions", [])

    closed = 0
    for pos in positions:
        pos_symbol = pos.get("instrument", pos.get("symbol", ""))
        pos_side   = pos.get("side", "").upper()
        pos_id     = pos.get("id") or pos.get("positionId")

        if pos_symbol == mapped_symbol and pos_side == target_side_upper and pos_id:
            close_url = f"{base_url}/mtr-api/{system_uuid}/position/close/{pos_id}"
            cr = requests.post(close_url, headers={**headers, "Content-Type": "application/json"}, timeout=15)
            if cr.ok:
                _log(f"[{env_name}] ✅ Closed position {pos_id}")
                closed += 1
            else:
                _log(f"[{env_name}] ❌ Close failed for {pos_id}: {cr.text}")

    if closed == 0:
        _log(f"[{env_name}] No open {target_side_upper} positions for {mapped_symbol}.")
    return closed > 0


# ---------------------------------------------------------------------------
# TEST HARNESS (run directly to verify connectivity)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    cfg = load_e8_config(".env.e8demo")
    _log("Config loaded:", cfg)
    try:
        tok, uuid, acc_tok = authenticate_matchtrader(cfg)
        _log(f"tradingApiToken : {tok[:20]}...")
        _log(f"systemUUID      : {uuid}")
        _log(f"accountToken    : {acc_tok[:20] if acc_tok else 'N/A'}...")
    except Exception as ex:
        _log(f"ERROR: {ex}")
