
import os
import json
import time
import math
import asyncio
import threading
from datetime import datetime
import requests
import websockets
from flask import Flask, request, jsonify
from dotenv import load_dotenv, dotenv_values
from notifications import notify_telegram

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(script_dir, ".env.hankolive")
if os.path.exists(env_path):
    load_dotenv(env_path, override=False)

app = Flask(__name__)

# Idempotency / Deduplication state
# Note: This in-memory state resets on Render restarts. If TradingView retries
# during the exact window where Render is restarting, the duplicate will slip through.
_seen_webhooks = {}
_webhooks_lock = threading.Lock()

SYMBOL_MAP = {
    "GOLD": "XAUUSD",
    "XAUUSD": "XAUUSD",
    "US30": "US30",
    "DJI": "US30",
    "USA30": "US30",
    "DOW+": "US30",
    "NAS100": "NAS100",
    "NASDAQ": "NAS100",
    "NQ": "NAS100",
    "SPX": "SPX500",
    "US500": "SPX500",
    "SPX500": "SPX500",
    "BTCUSD": "BTCUSD",
    "USDCAD": "USDCAD"
}

# ======================================================================
# ASSET CLASS CLASSIFICATION
# ======================================================================
# Used by resolve_offset() and the per-class sanity envelope.
# Add new symbols here as new instruments are onboarded.

_GOLD_SYMBOLS = {"XAUUSD", "GOLD", "XAUEUR", "XAGUSD"}
_JPY_SYMBOLS  = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY"}
_FOREX_PIP_SYMBOLS = {
    # Majors
    "EURUSD", "GBPUSD", "USDCAD", "AUDUSD", "NZDUSD", "USDCHF",
    # Non-JPY crosses
    "EURGBP", "EURCHF", "EURAUD", "EURNZD", "EURCAD",
    "GBPCHF", "GBPAUD", "GBPNZD", "GBPCAD",
    "AUDNZD", "AUDCAD", "AUDCHF",
    "NZDCAD", "NZDCHF", "CADCHF",
    # NOTE: Any FX pair NOT in this set falls to the "index" default (multiplier=1.0)
    # which will misclassify it. Add symbols here as new pairs are onboarded.
}

# Max absolute price distance per asset class.
# NOTE: V5 changed index max from 10,000 (V2) to 5,000. Confirm this is
# acceptable before deploy. Strategies with 5,000-10,000 point stops will
# start raising sanity errors.
# TODO: expand to per-symbol dict when FX/Metals are fully onboarded.
_MAX_ABSOLUTE_DISTANCE = {
    "forex": 0.05,    # ~500 pip max on standard FX
    "gold":  50.0,    # $50 max on XAUUSD
    "index": 5000.0,  # 5,000 point max on US30/NAS100
}

def _get_asset_class(symbol):
    s = symbol.upper().replace("+", "")
    if s in _GOLD_SYMBOLS:                              return "gold"
    if s in _JPY_SYMBOLS or s in _FOREX_PIP_SYMBOLS:   return "forex"
    return "index"

def _convert_to_absolute_distance(value, symbol, sl_unit):
    """Converts a user-supplied numeric value to an absolute price distance.
    sl_unit must be one of: 'price', 'pips', 'points', or None (legacy fallback).
    """
    s = symbol.upper().replace("+", "")
    asset_class = _get_asset_class(symbol)

    # Guard: reject negative distances at the input boundary
    if value < 0:
        raise ValueError(
            f"Distance value must be non-negative for {symbol}; got {value}"
        )

    if sl_unit == "price":
        # Caller asserts value is already an absolute price distance — pass through
        return value

    if sl_unit == "pips":
        if asset_class != "forex":
            raise ValueError(
                f"sl_unit='pips' is invalid for {asset_class} symbol {symbol}. "
                f"Use 'points' for indices or 'price' for absolute distance."
            )
        pip_size = 0.001 if s in _JPY_SYMBOLS else 0.0001  # exact set, no substring
        return value * pip_size

    if sl_unit == "points":
        if asset_class != "index":
            raise ValueError(
                f"sl_unit='points' is invalid for {asset_class} symbol {symbol}. "
                f"Use 'pips' for FX or 'price' for absolute distance."
            )
        return value

    # Legacy fallback — sl_unit not set, guess by asset class, log loudly
    if s in _GOLD_SYMBOLS:          multiplier = 0.01
    elif s in _JPY_SYMBOLS:         multiplier = 0.001
    elif s in _FOREX_PIP_SYMBOLS:   multiplier = 0.0001
    else:                           multiplier = 1.0

    dist = value * multiplier
    print(
        f"[PAYLOAD CLASSIFY LEGACY FALLBACK] {symbol} class={asset_class} "
        f"raw={value} multiplier={multiplier} -> dist={dist}. "
        f"ADD sl_unit to your Pine alert to silence this log."
    )
    return dist

_ROUTE_CACHE = {}

# ======================================================================
# TRADE REGISTRY
# ======================================================================
# Persists to trade_registry.json on disk so it survives server restarts.
# Structure per entry:
# {
#   "trade_id": {
#     "symbol":         "EURUSD",
#     "side":           "buy",
#     "qty":            0.01,
#     "signal":         "elephant_buy",
#     "env":            ".env.crucialdemo",
#     "broker_order_id":"12345",        # returned by TradeLocker REST
#     "tl_position_id": "67890",        # fetched after order fills (optional)
#     "opened_at":      "2026-04-21T14:32:00",
#     "status":         "open"          # "open" | "closed"
#   }
# }

REGISTRY_PATH = os.path.join(script_dir, "trade_registry.json")
_registry_lock = threading.Lock()

def _load_registry():
    if os.path.exists(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Registry] Load error: {e}")
    return {}

def _save_registry(registry):
    try:
        with open(REGISTRY_PATH, "w") as f:
            json.dump(registry, f, indent=2)
    except Exception as e:
        print(f"[Registry] Save error: {e}")

def registry_add(trade_id, symbol, side, qty, signal, env_name, broker_order_id=None):
    with _registry_lock:
        reg = _load_registry()
        reg[trade_id] = {
            "symbol":          symbol,
            "side":            side,
            "qty":             qty,
            "signal":          signal,
            "env":             env_name,
            "broker_order_id": broker_order_id,
            "tl_position_id":  None,
            "opened_at":       datetime.utcnow().isoformat(),
            "status":          "open"
        }
        _save_registry(reg)
        print(f"[Registry] Saved trade {trade_id}: {side} {qty} {symbol} on {env_name}")

def registry_mark_closed(trade_id):
    with _registry_lock:
        reg = _load_registry()
        if trade_id in reg:
            reg[trade_id]["status"] = "closed"
            reg[trade_id]["closed_at"] = datetime.utcnow().isoformat()
            _save_registry(reg)
            print(f"[Registry] Marked {trade_id} as closed")

def registry_get_open(symbol, side, env_name=None):
    """
    Returns a list of open trades matching symbol + side (and optionally env).
    Used when no trade_id is provided to find the oldest matching open position.
    """
    with _registry_lock:
        reg = _load_registry()
    matches = []
    for tid, entry in reg.items():
        if (entry["symbol"] == symbol
                and entry["side"] == side
                and entry["status"] == "open"):
            if env_name is None or entry["env"] == env_name:
                matches.append((tid, entry))
    # Sort oldest first so FIFO closing behaviour
    matches.sort(key=lambda x: x[1].get("opened_at", ""))
    return matches

def registry_get(trade_id):
    with _registry_lock:
        reg = _load_registry()
    return reg.get(trade_id)

# ======================================================================
# ACCOUNT CONFIG LOADER
# ======================================================================

def get_active_configs():
    configs = []
    toggles = {}
    toggle_path = os.path.join(script_dir, "toggles.json")
    if os.path.exists(toggle_path):
        try:
            with open(toggle_path, "r") as f:
                toggles = json.load(f)
        except Exception:
            pass

    env_files = [".env.hankodemo", ".env.hankolive", ".env.crucialdemo", ".env.cruciallive", ".env.atlasdemo", ".env.e8demo", ".env.e8live", ".env.e8markets", ".env.e8tradelocker"]

    for env_name in env_files:
        ep = os.path.join(script_dir, env_name)
        if not os.path.exists(ep):
            continue
        vals = dotenv_values(ep)
        is_active = vals.get("ACCOUNT_ACTIVE", "false").lower() == "true"
        if env_name in toggles:
            is_active = bool(toggles[env_name])
        if not is_active:
            continue

        print(f"Routing logic includes active account: {env_name}")

        if "hanko" in env_name.lower():
            b_type = "hankotrade"
            is_live = "live" in env_name.lower()
            configs.append({
                "name": env_name,
                "type": b_type,
                "is_live": is_live,
                "auth_url": "https://tradeapi.hankotrade.com/api/login",
                "acc_info_url": "https://tradeapi.hankotrade.com/api/act/user/account/balance",
                "ws_url": "wss://livefeed.hankotrade.com/" if is_live else "wss://demofeed.hankotrade.com/",
                "email": vals.get("HANKOX_EMAIL") or vals.get("HANKOX_LIVE_ACCOUNT_ID") or vals.get("HANKOX_DEMO_ACCOUNT_ID"),
                "password": vals.get("HANKOX_PASSWORD") or vals.get("HANKOX_LIVE_PASSWORD") or vals.get("HANKOX_DEMO_PASSWORD"),
                "server": vals.get("HANKOX_SERVER", "Hankotrade-Live" if is_live else "Hankotrade-Demo"),
                "symbol_suffix": ".HKT"
            })
        elif "crucial" in env_name.lower() or "atlas" in env_name.lower() or "e8" in env_name.lower():
            b_type = "tradelocker"
            is_live = "live" in env_name.lower()
            api_url = vals.get("TRADELOCKER_API_URL",
                "https://live.tradelocker.com/backend-api" if is_live else "https://demo.tradelocker.com/backend-api")
            configs.append({
                "name": env_name,
                "type": b_type,
                "is_live": is_live,
                "api_url": api_url,
                "email": vals.get("TRADELOCKER_EMAIL"),
                "password": vals.get("TRADELOCKER_PASSWORD"),
                "server": vals.get("TRADELOCKER_SERVER"),
                "account_id": vals.get("TRADELOCKER_ACCOUNT_ID"),
                "acc_num": vals.get("TRADELOCKER_ACCNUM", "1" if "e8" in env_name.lower() else vals.get("TRADELOCKER_ACCOUNT_ID")),
                "symbol_suffix": ""
            })

    return configs

def get_tradelocker_configs_only(active_configs):
    return [c for c in active_configs if c["type"] == "tradelocker"]

# ======================================================================
# AUTHENTICATION
# ======================================================================

def authenticate_tradelocker(config):
    auth_url = f"{config['api_url']}/auth/jwt/token"
    payload = {
        "email": config["email"],
        "password": config["password"],
        "server": config["server"]
    }
    print(f"[{config['name']}] Authenticating via TradeLocker REST...")
    resp = requests.post(auth_url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
    if not resp.ok:
        notify_telegram(f"❌ {config['name']} auth failed: {resp.text[:200]}")
        raise Exception(f"TradeLocker Auth failed: {resp.text}")
    token = resp.json().get("accessToken")
    acc_id = config.get("account_id")
    if not acc_id:
        acc_url = f"{config['api_url']}/trade/accounts"
        acc_resp = requests.get(acc_url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if acc_resp.ok:
            accounts = acc_resp.json().get("accounts", [])
            if accounts:
                acc_id = accounts[0].get("id")
    return token, acc_id, config.get("acc_num", "1")

def authenticate_hankotrade(config):
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
        notify_telegram(f"❌ {config['name']} auth failed: {resp.text[:200]}")
        raise Exception(f"Hanko Auth failed: {resp.text}")
    token = resp.json().get('data', {}).get('user', {}).get('token')
    if not token:
        raise Exception("No token received from Hanko login.")
    headers['Authorization'] = f'Bearer {token}'
    acc_resp = requests.post(config["acc_info_url"], json={}, headers=headers, timeout=10)
    acc_id = acc_resp.json().get('data', {}).get('ACCOUNT_ID') if acc_resp.ok else None
    return token, acc_id

# ======================================================================
# TRADELOCKER INSTRUMENT ID MAP
# ======================================================================

INSTRUMENT_ID_MAP = {
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
        "US30": 16337, "NAS100": 16341, "XAUUSD": 16343, "BTCUSD": 16304,
        "EURUSD": 16325, "GBPUSD": 16317, "USDCAD": 16322
    },
    ".env.e8demo": {
        "US30": 6107, "USDCAD": 6125
    },
    ".env.e8live": {
        "US30": 6107, "USDCAD": 6125
    },
    ".env.e8markets": {
        "US30": 6107, "USDCAD": 6125
    },
    ".env.e8tradelocker": {
        "US30": 6107, "USDCAD": 6125
    }
}

# ======================================================================
# TRADELOCKER REST — OPEN A TRADE
# ======================================================================

async def execute_trade_rest(token, acc_id, acc_num, symbol, side, qty, api_url, env_name,
                              sl=0, tp=0, trade_id=None, sl_type="offset", tp_type="offset"):
    """
    Places a market order via TradeLocker REST.
    Returns the broker_order_id string on success, None on failure.
    """
    side_tl = "buy" if side.lower() in ("buy", "long") else "sell"
    base_symbol = symbol.upper().replace(".HKT", "")
    mapped_symbol = SYMBOL_MAP.get(base_symbol, base_symbol)

    current_map = INSTRUMENT_ID_MAP.get(env_name, INSTRUMENT_ID_MAP[".env.crucialdemo"])
    inst_id = current_map.get(mapped_symbol)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accNum": str(acc_num)
    }

    route_id = None
    meta = None
    route_cache_key = f"{env_name}_{inst_id}"

    if route_cache_key in _ROUTE_CACHE:
        meta = _ROUTE_CACHE[route_cache_key]
        route_id = meta["routeId"]
    else:
        inst_url = f"{api_url}/trade/accounts/{acc_id}/instruments"
        inst_resp = requests.get(inst_url, headers=headers, timeout=10)
        if inst_resp.ok:
            data = inst_resp.json()
            inst_list = data.get("d", []) if isinstance(data, dict) else data
            if isinstance(inst_list, dict) and "instruments" in inst_list:
                inst_list = inst_list["instruments"]
            for inst in inst_list:
                inst_name = str(inst.get("name", ""))
                # Match by explicit ID, exact name, OR broker's '+'-suffixed name (e.g. E8 'EURUSD+')
                name_match = (inst_name == mapped_symbol or inst_name == mapped_symbol + "+")
                if str(inst.get("tradableInstrumentId")) == str(inst_id) or name_match:
                    routes = inst.get("routes", [])
                    for r in routes:
                        if r.get("type") == "TRADE":
                            route_id = r.get("id")
                            real_inst_id = inst.get("tradableInstrumentId")
                            detail_url = f"{api_url}/trade/instruments/{real_inst_id}?routeId={route_id}"
                            det_resp = requests.get(detail_url, headers=headers, timeout=10)
                            schedule = det_resp.json().get("d", {}).get("tickSize", []) if det_resp.ok else []
                            meta = {"routeId": route_id, "tickSizeSchedule": schedule}
                            _ROUTE_CACHE[route_cache_key] = meta
                            break
                    if route_id:
                        break

    order_url = f"{api_url}/trade/accounts/{acc_id}/orders"

    sl_val = None
    tp_val = None

    # Per-asset-class sanity bounds on resolved absolute distance (NOT ticks).
    # These are consistent across brokers because they operate in price units.
    asset_class = _get_asset_class(mapped_symbol)
    max_dist = _MAX_ABSOLUTE_DISTANCE[asset_class]
    if sl and float(sl) > max_dist:
        notify_telegram(f"⚠️ Sanity bound exceeded: {mapped_symbol} sl={sl} max={max_dist}")
        raise ValueError(f"SANITY: sl_distance={sl} exceeds {asset_class} max={max_dist} ticks. Assuming misconfigured offset and aborting to protect account.")
    if tp and float(tp) > max_dist * 2:
        notify_telegram(f"⚠️ Sanity bound exceeded: {mapped_symbol} tp={tp} max={max_dist*2}")
        raise ValueError(
            f"SANITY: tp_distance={tp} exceeds {asset_class} max={max_dist*2} for {mapped_symbol}"
        )

    # TradeLocker REST API requires stopLossType="offset" for both static and trailing stops.
    # The trailing mechanism is activated by passing "trStopOffset" in the payload (handled below).
    if sl_type == "trailing" or sl_type == "offset" or tp_type == "offset":
        schedule = meta.get("tickSizeSchedule") if meta else None
        if not schedule:
            raise RuntimeError(f"CRITICAL: tickSize schedule missing for {mapped_symbol} on {env_name}")
        
        if len(schedule) != 1:
            # TODO: Implement price-aware resolution for multi-tier instruments.
            # Pull current price from /quotes on cache miss, find tier where leftRangeLimit <= current_price
            raise NotImplementedError(
                f"Multi-tier tickSize for {mapped_symbol} on {env_name} requires "
                f"price-aware resolution (got {len(schedule)} tiers). "
                f"Add a /quotes lookup before trading tiered instruments."
            )
            
        tier = schedule[0]
        if "tickSize" not in tier:
            raise RuntimeError(f"tickSize field missing from schedule entry for {mapped_symbol}: {tier}")
            
        tick_size = float(tier["tickSize"])
        
        if sl:
            sl_val = math.floor(float(sl) / tick_size)
            if sl_val <= 0:
                raise ValueError(
                    f"Stop loss offset rounded to {sl_val} ticks "
                    f"(sl_distance={sl}, tickSize={tick_size}) — "
                    f"strategy SL is too tight for this instrument's price granularity"
                )
            # Guard against floating-point rounding artifacts in tick division
            raw_ticks = float(sl) / tick_size
            if abs(raw_ticks - round(raw_ticks)) > 0.01:
                print(f"[{env_name}] [TICK ROUNDING] {mapped_symbol} sl raw={raw_ticks:.6f} -> floored={sl_val}")
        if tp:
            tp_val = math.floor(float(tp) / tick_size)
            if tp_val <= 0:
                raise ValueError(
                    f"Take profit offset rounded to {tp_val} ticks "
                    f"(tp_distance={tp}, tickSize={tick_size}) — "
                    f"strategy TP is too tight for this instrument's price granularity"
                )
                
        print(f"[{env_name}] [ORDER RESOLUTION] {mapped_symbol} sl_pts={sl} tp_pts={tp} tickSize={tick_size} sl_ticks={sl_val} tp_ticks={tp_val}")
    else:
        sl_val = float(sl) if sl else None
        tp_val = float(tp) if tp else None

    payload = {
        "price": 0,
        "qty": float(qty),
        "side": side_tl,
        "type": "market",
        "validity": "IOC",
        "stopLossType": sl_type if sl else None,
        "takeProfitType": tp_type if tp else None,
        "tradableInstrumentId": inst_id if inst_id else mapped_symbol,
        "stopLoss": sl_val,
        "takeProfit": tp_val
    }

    # TradeLocker implements trailing stops by setting stopLossType to "offset"
    # and passing the trail distance in ticks via "trStopOffset".
    if sl_type == "trailing":
        payload["stopLossType"] = "offset"
        payload["trStopOffset"] = sl_val
        print(f"[{env_name}] [TRAILING STOP] Attached trStopOffset={sl_val} ticks")
    if route_id:
        payload["routeId"] = route_id

    print(f"[{env_name}] REST Open Order Payload: {json.dumps(payload)}")
    resp = requests.post(order_url, json=payload, headers=headers, timeout=10)

    if resp.ok:
        resp_data = resp.json()
        print(f"[{env_name}] REST Order Success: {resp.text}")

        # TradeLocker returns orderId inside the response
        broker_order_id = (
            str(resp_data.get("orderId", ""))
            or str(resp_data.get("id", ""))
            or str(resp_data.get("data", {}).get("orderId", ""))
        )

        # Save to registry immediately
        if trade_id:
            registry_add(trade_id, mapped_symbol, side_tl, qty,
                         signal="webhook", env_name=env_name,
                         broker_order_id=broker_order_id)

        return broker_order_id or "unknown"
    else:
        print(f"[{env_name}] REST Order Failed: {resp.text}")
        notify_telegram(f"❌ {env_name} order rejected: {mapped_symbol} {side} {qty}\n{resp.text[:200]}")
        return None

# ======================================================================
# TRADELOCKER REST — CLOSE A SPECIFIC POSITION
# ======================================================================

def fetch_tl_positions(token, acc_id, acc_num, api_url, env_name):
    """
    Fetches all open positions from TradeLocker for a given account.
    Returns a list of position dicts.
    """
    pos_url = f"{api_url}/trade/accounts/{acc_id}/positions"
    headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(acc_num)
    }
    resp = requests.get(pos_url, headers=headers, timeout=10)
    if resp.ok:
        data = resp.json()
        # TradeLocker wraps positions in different keys depending on version
        positions = (data.get("positions")
                     or data.get("data", {}).get("positions")
                     or [])
        print(f"[{env_name}] Fetched {len(positions)} open positions")
        return positions
    else:
        print(f"[{env_name}] Failed to fetch positions: {resp.text}")
        return []

def close_tl_position(token, acc_id, acc_num, api_url, env_name, position_id, qty):
    """
    Closes a specific position by its TradeLocker position ID.
    Uses the /positions/{id} DELETE or close endpoint.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accNum": str(acc_num)
    }

    # TradeLocker close position endpoint
    close_url = f"{api_url}/trade/accounts/{acc_id}/positions/{position_id}"
    payload = {"qty": float(qty)}

    print(f"[{env_name}] Closing position {position_id} qty={qty}")
    resp = requests.delete(close_url, json=payload, headers=headers, timeout=10)

    if resp.ok:
        print(f"[{env_name}] Position {position_id} closed successfully: {resp.text}")
        return True
    else:
        print(f"[{env_name}] Failed to close position {position_id}: {resp.text}")
        return False

def find_tl_position_by_order(positions, broker_order_id, symbol, side):
    """
    Tries to match a TradeLocker position to our registry entry.
    Matching priority:
      1. By broker_order_id if TradeLocker exposes it on the position
      2. By symbol + side (FIFO — oldest first)
    """
    mapped_symbol = SYMBOL_MAP.get(symbol.upper(), symbol.upper())
    side_tl = "buy" if side.lower() in ("buy", "long") else "sell"

    # Priority 1: exact order ID match
    if broker_order_id and broker_order_id != "unknown":
        for pos in positions:
            if str(pos.get("orderId", "")) == str(broker_order_id):
                return pos

    # Priority 2: symbol + side match (take oldest by creation time)
    candidates = []
    for pos in positions:
        raw_pos_symbol = pos.get("symbol", "").replace(".HKT", "").upper()
        pos_symbol = SYMBOL_MAP.get(raw_pos_symbol, raw_pos_symbol)
        pos_side = pos.get("side", "").lower()
        if pos_symbol == mapped_symbol and pos_side == side_tl:
            candidates.append(pos)

    if candidates:
        # Sort by open time ascending (oldest first = FIFO)
        candidates.sort(key=lambda p: p.get("openTime", p.get("createdAt", "")))
        print(f"[Registry] Matched position by symbol+side FIFO for {mapped_symbol} {side_tl}")
        return candidates[0]

    return None

def close_tradelocker_trade(config, trade_id, entry):
    """
    Main close logic for a single TradeLocker trade.
    1. Authenticates
    2. Fetches open positions
    3. Matches the specific position
    4. Closes it
    5. Updates registry
    """
    try:
        token, acc_id, acc_num = authenticate_tradelocker(config)
        positions = fetch_tl_positions(token, acc_id, acc_num, config["api_url"], config["name"])

        if not positions:
            print(f"[{config['name']}] No open positions found — nothing to close for {trade_id}")
            return False

        # Determine the matching side (we're closing, so look for the open side)
        open_side = entry["side"]  # "buy" or "sell"
        symbol = entry["symbol"]
        broker_order_id = entry.get("broker_order_id")
        qty = entry["qty"]

        position = find_tl_position_by_order(positions, broker_order_id, symbol, open_side)

        if not position:
            print(f"[{config['name']}] Could not find matching position for trade {trade_id} "
                  f"({symbol} {open_side}). It may already be closed.")
            registry_mark_closed(trade_id)
            return False

        position_id = position.get("id") or position.get("positionId")
        pos_qty = float(position.get("qty", qty))

        success = close_tl_position(token, acc_id, acc_num, config["api_url"],
                                     config["name"], position_id, pos_qty)
        if success:
            registry_mark_closed(trade_id)

        return success

    except Exception as e:
        print(f"[{config['name']}] close_tradelocker_trade error: {e}")
        notify_telegram(f"⚠️ Close failed: {trade_id} ({entry['symbol']} {entry['side']})")
        return False

# ======================================================================
# HANKO WEBSOCKET — OPEN A TRADE (unchanged, kept for future use)
# ======================================================================

async def execute_trade_ws(token, acc_id, symbol, side, qty, wss_url, env_name, sl=0, tp=0):
    side_lower = side.lower()
    side_int = 1 if side_lower in ("buy", "long") else 2
    base_symbol = symbol.upper().replace(".HKT", "")
    mapped_symbol = SYMBOL_MAP.get(base_symbol, base_symbol)
    formatted_symbol = f"{mapped_symbol}.HKT"

    try:
        async with websockets.connect(wss_url) as websocket:
            auth_msg = {"auth": token, "defaults": [formatted_symbol], "rawFeed": True}
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
                import zlib, base64
                def decode_hanko(msg):
                    try:
                        if isinstance(msg, bytes):
                            if len(msg) > 2 and msg[0] == 0x78 and msg[1] == 0x9c:
                                try: return zlib.decompress(msg).decode('utf-8')
                                except: pass
                        if isinstance(msg, str):
                            if not msg.startswith("eJ"): return msg
                            try:
                                msg_bytes = base64.b64decode(msg)
                                return zlib.decompress(msg_bytes).decode('utf-8')
                            except: return msg
                        if isinstance(msg, bytes):
                            try: return zlib.decompress(msg).decode('utf-8')
                            except: pass
                        return str(msg)
                    except: return str(msg)

                end_time = time.time() + 5.0
                while time.time() < end_time:
                    try:
                        resp = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        decoded = decode_hanko(resp)
                        if "{" in decoded:
                            try:
                                data = json.loads(decoded)
                                if "stat" in str(data) or "tempOrderId" in str(data):
                                    print(f"[{env_name}] WS ORDER RESP: {decoded}")
                                    break
                            except: pass
                        if "error" in decoded.lower() or "NOK" in decoded:
                            print(f"[{env_name}] WS STATUS: {decoded}")
                            if "tempOrderId" in decoded: break
                    except asyncio.TimeoutError: continue
            except Exception as e:
                print(f"[{env_name}] WS Wait Error: {e}")

            return True
    except Exception as e:
        print(f"[{env_name}] WebSocket Error: {e}")
        return False

# ======================================================================
# MULTI-BROKER OPEN — WITH TRADE ID
# ======================================================================

async def place_multi_orders_async(active_configs, symbol, side, qty,
                                    sl=0, tp=0, trade_id=None, signal="", sl_type="offset", tp_type="offset"):
    tasks = []
    for config in active_configs:
        try:
            if config["type"] == "hankotrade":
                token, acc_id = authenticate_hankotrade(config)
                task = asyncio.create_task(
                    execute_trade_ws(token, acc_id, symbol, side, qty,
                                     config["ws_url"], config["name"], sl, tp)
                )
                # Hanko: register with no broker_order_id (WS doesn't return it easily)
                tasks.append({"env": config["name"], "task": task,
                               "type": "hankotrade", "trade_id": trade_id})
            else:
                token, acc_id, acc_num = authenticate_tradelocker(config)
                task = asyncio.create_task(
                    execute_trade_rest(token, acc_id, acc_num, symbol, side, qty,
                                       config["api_url"], config["name"],
                                       sl, tp, trade_id, sl_type, tp_type)
                )
                tasks.append({"env": config["name"], "task": task,
                               "type": "tradelocker", "trade_id": trade_id})
        except Exception as e:
            print(f"[{config['name']}] Multi-Routing Fail: {e}")
            notify_telegram(f"❌ {config['name']} multi-routing fail: {e}")

    results = {}
    for t in tasks:
        try:
            result = await t["task"]
            success = bool(result)
            results[t["env"]] = success

            # For Hanko (no order ID returned), register now with placeholder
            if t["type"] == "hankotrade" and success and t["trade_id"]:
                base_symbol = SYMBOL_MAP.get(symbol.upper(), symbol.upper())
                side_norm = "buy" if side.lower() in ("buy","long") else "sell"
                registry_add(t["trade_id"], base_symbol, side_norm, qty,
                             signal=signal, env_name=t["env"],
                             broker_order_id="hanko_ws")

            status = "SUCCESS" if success else "FAILED"
            print(f"[{t['env']}] Global Routing Result: {status}")
        except Exception as e:
            print(f"[{t['env']}] Task Error: {e}")
            results[t["env"]] = False

    return results

def place_market_orders_sync(active_configs, symbol, side, qty,
                              sl=0, tp=0, trade_id=None, signal="", sl_type="offset", tp_type="offset"):
    try:
        def run_in_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                place_multi_orders_async(active_configs, symbol, side, qty,
                                          sl, tp, trade_id, signal, sl_type, tp_type)
            )
            loop.close()
        thread = threading.Thread(target=run_in_loop)
        thread.daemon = True
        thread.start()
        return "Dispatched to background thread"
    except Exception as e:
        print(f"Failed to dispatch thread: {e}")
        return "Dispatch Error"

# ======================================================================
# CLOSE A SPECIFIC TRADE — TRADELOCKER ONLY
# ======================================================================

def close_specific_trade(active_configs, trade_id):
    """
    Looks up a trade_id in the registry and closes the matching
    TradeLocker position. Hanko closes fall back to netting (unchanged).
    Returns True if at least one broker closed successfully.
    """
    entry = registry_get(trade_id)
    if not entry:
        print(f"[Registry] trade_id '{trade_id}' not found in registry")
        return False

    if entry["status"] == "closed":
        print(f"[Registry] trade_id '{trade_id}' is already marked closed — skipping")
        return False

    env_name = entry["env"]
    success = False

    for config in active_configs:
        if config["name"] != env_name:
            continue

        if config["type"] == "tradelocker":
            print(f"[Registry] Closing TL trade {trade_id} on {env_name}")
            success = close_tradelocker_trade(config, trade_id, entry)
        else:
            # Hanko fallback: net out with opposite order
            print(f"[Registry] Hanko fallback net-close for {trade_id} on {env_name}")
            close_side = "sell" if entry["side"] == "buy" else "buy"
            place_market_orders_sync([config], entry["symbol"],
                                      close_side, entry["qty"], 0, 0)
            registry_mark_closed(trade_id)
            success = True

    return success

def close_by_symbol_side_fifo(active_configs, symbol, action):
    """
    Fallback when no trade_id is provided.
    Closes the oldest open position matching symbol + side (FIFO).
    Only operates on TradeLocker configs.
    """
    open_side = "buy" if action == "close_long" else "sell"
    mapped_symbol = SYMBOL_MAP.get(symbol.upper(), symbol.upper())

    tl_configs = get_tradelocker_configs_only(active_configs)
    if not tl_configs:
        print("[Close FIFO] No active TradeLocker configs found")
        return False

    matches = registry_get_open(mapped_symbol, open_side)
    if not matches:
        print(f"[Close FIFO] No open registry entries for {mapped_symbol} {open_side} — "
              "attempting raw position close on broker")
        # No registry entry — try to close oldest broker position directly
        for config in tl_configs:
            try:
                token, acc_id, acc_num = authenticate_tradelocker(config)
                positions = fetch_tl_positions(token, acc_id, acc_num, config["api_url"], config["name"])
                position = find_tl_position_by_order(positions, None, mapped_symbol, open_side)
                if position:
                    pos_id = position.get("id") or position.get("positionId")
                    pos_qty = float(position.get("qty", 0.01))
                    return close_tl_position(token, acc_id, acc_num, config["api_url"],
                                              config["name"], pos_id, pos_qty)
            except Exception as e:
                print(f"[{config['name']}] Raw close error: {e}")
        return False

    # Close the oldest open match
    trade_id, entry = matches[0]
    print(f"[Close FIFO] Closing oldest open trade {trade_id} for {mapped_symbol} {open_side}")
    return close_specific_trade(active_configs, trade_id)

# ======================================================================
# UTILITY
# ======================================================================

def is_sabbath_mode_active():
    now = datetime.now()
    if now.weekday() == 4 and now.hour >= 16: return True
    if now.weekday() == 5: return True
    if now.weekday() == 6 and now.hour < 17: return True
    return False

def is_session_active(symbol):
    allowed_sessions_str = os.environ.get(f"SESSIONS_{symbol}", "Asian,London,New York")
    if not allowed_sessions_str.strip(): return True
    allowed_sessions = [s.strip() for s in allowed_sessions_str.split(",")]
    now_utc = datetime.utcnow()
    hour = now_utc.hour
    is_asian    = (22 <= hour or hour < 8)
    is_london   = (7 <= hour < 16)
    is_new_york = (13 <= hour < 22)
    if "Asian"    in allowed_sessions and is_asian:    return True
    if "London"   in allowed_sessions and is_london:   return True
    if "New York" in allowed_sessions and is_new_york: return True
    return False

def generate_trade_id(signal, symbol, timeframe=""):
    """
    Generates a unique trade ID using signal name, symbol, and timestamp.
    Example: WS_elephant_buy_EURUSD_3_1745123456789
    """
    ts = int(time.time() * 1000)
    parts = [p for p in ["WS", signal, symbol, timeframe, str(ts)] if p]
    return "_".join(parts)

# ======================================================================
# FLASK ROUTES
# ======================================================================

@app.route("/toggle", methods=["POST"])
def toggle_account():
    # Webhook Authentication
    import hmac
    expected_token = os.environ.get("WEBHOOK_SECRET")
    if not expected_token:
        print("[Auth] CRITICAL: WEBHOOK_SECRET not configured")
        return jsonify({"error": "Service misconfigured"}), 503
    if not hmac.compare_digest(expected_token, request.args.get("token", "")):
        print("[Auth] Rejected unauthenticated /toggle request")
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    env_name = data.get("env_name")
    is_active = data.get("active")
    valid_envs = [".env.hankodemo", ".env.hankolive", ".env.crucialdemo",
                  ".env.cruciallive", ".env.atlasdemo", ".env.forexcom",
                  ".env.e8demo", ".env.e8live", ".env.e8markets", ".env.e8tradelocker"]
    if env_name and env_name in valid_envs:
        toggle_path = os.path.join(script_dir, "toggles.json")
        toggles = {}
        if os.path.exists(toggle_path):
            try:
                with open(toggle_path, "r") as f:
                    toggles = json.load(f)
            except Exception: pass
        toggles[env_name] = bool(is_active)
        with open(toggle_path, "w") as f:
            json.dump(toggles, f)
        return jsonify({"status": "success",
                        "message": f"{env_name} set to {is_active}"})
    return jsonify({"status": "error", "message": "Invalid environment file"}), 400

@app.route("/test-notification", methods=["GET", "POST"])
def test_notification():
    import hmac
    expected_token = os.environ.get("WEBHOOK_SECRET")
    if not expected_token:
        return jsonify({"error": "Service misconfigured"}), 503
    if not hmac.compare_digest(expected_token, request.args.get("token", "")):
        return jsonify({"error": "Unauthorized"}), 401
    
    notify_telegram("Test alert from /test-notification")
    return jsonify({"status": "success", "message": "Telegram notification triggered."})

@app.route("/registry", methods=["GET"])
def view_registry():
    """Debug endpoint — returns the full trade registry."""
    # Webhook Authentication
    import hmac
    expected_token = os.environ.get("WEBHOOK_SECRET")
    if not expected_token:
        print("[Auth] CRITICAL: WEBHOOK_SECRET not configured")
        return jsonify({"error": "Service misconfigured"}), 503
    if not hmac.compare_digest(expected_token, request.args.get("token", "")):
        print("[Auth] Rejected unauthenticated /registry request")
        return jsonify({"error": "Unauthorized"}), 401

    status_filter = request.args.get("status")  # ?status=open or ?status=closed
    reg = _load_registry()
    if status_filter:
        reg = {k: v for k, v in reg.items() if v.get("status") == status_filter}
    return jsonify(reg), 200

def _validate_absolute_direction(symbol, side, target_type, abs_price, price, source):
    if target_type == 'sl':
        if side == "buy" and abs_price >= price:
            raise ValueError(f"Buy SL must be below entry; got {source}={abs_price}, price={price} for {symbol}")
        if side == "sell" and abs_price <= price:
            raise ValueError(f"Sell SL must be above entry; got {source}={abs_price}, price={price} for {symbol}")
    elif target_type == 'tp':
        if side == "buy" and abs_price <= price:
            raise ValueError(f"Buy TP must be above entry; got {source}={abs_price}, price={price} for {symbol}")
        if side == "sell" and abs_price >= price:
            raise ValueError(f"Sell TP must be below entry; got {source}={abs_price}, price={price} for {symbol}")

def resolve_offset(symbol, side, target_type, data, price):
    # Priority 0: sl_points / tp_points — pre-computed absolute distance from Pine Script.
    # f_json() in wise_steward_master.pine sends slp = abs(price - sl) as sl_points.
    # This is the highest-confidence path: Pine already did the math.
    points_key = f"{target_type}_points"
    precomputed = data.get(points_key)
    if precomputed is not None:
        dist = float(precomputed)
        print(f"[PAYLOAD CLASSIFY] {symbol} {side} {points_key}={dist} (pre-computed) -> dist={dist}")
        return dist

    # Priority 1: Explicit absolute PRICE LEVEL key (e.g. sl_price)
    explicit_price = data.get(f"{target_type}_price")
    if explicit_price is not None:
        if not price or price <= 0:
            raise ValueError(
                f"Cannot resolve {target_type}_price={explicit_price} for {symbol}: "
                f"entry price missing or invalid (got {price})"
            )
        abs_val = float(explicit_price)
        _validate_absolute_direction(symbol, side, target_type, abs_val, price, f"explicit_{target_type}_price")
        dist = abs(price - abs_val)
        print(f"[PAYLOAD CLASSIFY] {symbol} {side} explicit={target_type}_price -> dist={dist}")
        return dist

    sl_unit = data.get(f"{target_type}_unit")  # "price", "pips", or "points"

    # Priority 2: Explicit distance key — unit applied via shared converter
    explicit_offset = data.get(f"{target_type}_offset")
    if explicit_offset is not None:
        dist = _convert_to_absolute_distance(float(explicit_offset), symbol, sl_unit)
        print(f"[PAYLOAD CLASSIFY] {symbol} {side} explicit={target_type}_offset sl_unit={sl_unit} -> dist={dist}")
        return dist

    value = float(data.get(target_type, 0))

    # Legitimate "no SL/TP" case — value of zero means not set
    if value == 0:
        return 0

    # Priority 3: Typed legacy key (sl_type)
    # NOTE: price==0 guard is placed AFTER this block intentionally.
    # Pure-offset payloads (sl_type='offset', sl_unit='pips') don't need
    # an anchor price and must not raise here.
    explicit_type = data.get(f"{target_type}_type")
    if explicit_type == "absolute":
        # Absolute price level DOES need anchor price
        if not price or price <= 0:
            raise ValueError(
                f"Cannot resolve {target_type}={value} for {symbol} as absolute: "
                f"entry price missing or invalid (got {price})"
            )
        _validate_absolute_direction(symbol, side, target_type, value, price, "type=absolute")
        dist = abs(price - value)
        print(f"[PAYLOAD CLASSIFY] {symbol} {side} type=absolute -> dist={dist}")
        return dist
    elif explicit_type == "offset":
        dist = _convert_to_absolute_distance(value, symbol, sl_unit)
        print(f"[PAYLOAD CLASSIFY] {symbol} {side} type=offset sl_unit={sl_unit} -> dist={dist}")
        return dist

    # V5: sl_unit is authoritative — bypasses heuristic entirely.
    # Pure-offset payloads with sl_unit set do not need price.
    if sl_unit is not None:
        dist = _convert_to_absolute_distance(value, symbol, sl_unit)
        print(f"[PAYLOAD CLASSIFY] {symbol} {side} sl_unit={sl_unit} (no sl_type) -> dist={dist}")
        return dist

    # From here the heuristic needs price as an anchor — guard now
    if not price or price <= 0:
        raise ValueError(
            f"Cannot resolve {target_type}={value} for {symbol}: "
            f"entry price missing. Add \"price\": {{{{close}}}} to your Pine alert "
            f"or set sl_unit/sl_type to skip the heuristic."
        )

    # Priority 4: Heuristic — ONLY fires when no explicit unit info is present
    is_absolute_candidate = False
    if target_type == 'sl':
        if side == "buy" and value < price:    is_absolute_candidate = True
        elif side == "sell" and value > price: is_absolute_candidate = True
    elif target_type == 'tp':
        if side == "buy" and value > price:    is_absolute_candidate = True
        elif side == "sell" and value < price: is_absolute_candidate = True

    if is_absolute_candidate:
        if value > price * 0.10:
            inferred = "absolute"
            _validate_absolute_direction(symbol, side, target_type, value, price, "inferred_absolute")
            dist = abs(price - value)
        elif value < price * 0.05:
            inferred = "offset"
            dist = _convert_to_absolute_distance(value, symbol, sl_unit)  # sl_unit=None -> legacy fallback
        else:
            raise ValueError(
                f"Ambiguous {target_type}={value} for {symbol} {side} at price={price}. "
                f"Offset zone: <{price*0.05:.5f}, Absolute zone: >{price*0.10:.5f}. "
                f"Add '{target_type}_unit': 'pips' or 'price' to your Pine alert."
            )
    else:
        inferred = "offset"
        dist = _convert_to_absolute_distance(value, symbol, sl_unit)  # sl_unit=None -> legacy fallback

    print(f"[PAYLOAD CLASSIFY] {symbol} {side} price={price} {target_type}_in={value} -> inferred={inferred} -> dist={dist}")
    return dist

@app.route("/webhook", methods=["POST"])
def webhook():
    # Webhook Authentication
    import hmac
    expected_token = os.environ.get("WEBHOOK_SECRET")
    if not expected_token:
        print("[Auth] CRITICAL: WEBHOOK_SECRET not configured")
        return jsonify({"error": "Service misconfigured"}), 503
    if not hmac.compare_digest(expected_token, request.args.get("token", "")):
        print("[Auth] Rejected unauthenticated /webhook request")
        return jsonify({"error": "Unauthorized"}), 401

    if not (request.is_json or request.content_type == 'text/plain'):
        return jsonify({"status": "error", "message": "Unsupported Media Type"}), 415

    try:
        data = request.get_json(force=True)
        
        # Idempotency / Deduplication check
        symbol = data.get("symbol", data.get("ticker", "UNKNOWN")).upper()
        action = data.get("action", "").lower()
        signal = data.get("signal", action)
        qty = str(data.get("contracts", data.get("qty", "")))
        bar_time = str(data.get("bar_time", ""))
        
        fingerprint = f"{symbol}_{action}_{signal}_{bar_time or qty}"
        
        global _seen_webhooks
        with _webhooks_lock:
            now = time.time()
            # Sweep expired entries (TTL = 60s)
            _seen_webhooks = {k: t for k, t in _seen_webhooks.items() if now - t < 60}
            if fingerprint in _seen_webhooks:
                age = now - _seen_webhooks[fingerprint]
                print(f"[DEDUP] Ignored duplicate fingerprint={fingerprint} age={age:.1f}s")
                return jsonify({"status": "ignored", "reason": "Duplicate webhook"}), 200
            _seen_webhooks[fingerprint] = now

        print(f"\n--- Wise Steward Webhook ---\nReceived: {data}")

        # Set DEBUG_PAYLOAD_CAPTURE=true in Render env vars to log full formatted payload.
        # Use this to capture live fixture samples — copy output to tests/fixtures/.
        if os.environ.get("DEBUG_PAYLOAD_CAPTURE", "").lower() == "true":
            import json as _json
            print(f"[DEBUG PAYLOAD]\n{_json.dumps(data, indent=2)}")

        # Pine Script sends "ticker" not "symbol" — check both
        symbol    = data.get("symbol", data.get("ticker", "UNKNOWN")).upper()
        action    = data.get("action", "").lower()
        signal    = data.get("signal", action)
        timeframe = data.get("timeframe", data.get("tf", ""))

        # -- Sabbath check --
        bypass_sabbath = str(data.get("bypass_sabbath", "false")).lower() == "true"
        if is_sabbath_mode_active() and not bypass_sabbath:
            print(f"Rejecting {symbol}: Sabbath Mode Active.")
            return jsonify({"status": "rejected", "reason": "Sabbath Mode Active"}), 200

        # -- Session filter (skip for close actions) --
        if action not in ["close_long", "close_short", "close_all"] and symbol != "UNKNOWN":
            if not is_session_active(symbol):
                print(f"Rejecting {symbol}: Outside allowed sessions.")
                return jsonify({"status": "rejected", "reason": "Session Closed"}), 200

        # -- Signal (informational only) --
        if action == "signal":
            print(f"Signal alert for {symbol} — logging only.")
            return jsonify({"status": "logged",
                            "message": f"Signal for {symbol} recorded"}), 200

        active_configs = get_active_configs()
        if not active_configs:
            print("No active accounts configured.")
            return jsonify({"status": "ignored", "reason": "No active accounts"}), 200

        # ==============================================================
        # CLOSE ALL
        # ==============================================================
        if action == "close_all":
            print("CLOSE_ALL triggered — flattening all positions.")

            # Close all open entries in registry for TradeLocker
            with _registry_lock:
                reg = _load_registry()
            open_trades = [(tid, e) for tid, e in reg.items() if e["status"] == "open"]
            tl_configs = get_tradelocker_configs_only(active_configs)

            for trade_id, entry in open_trades:
                matching = [c for c in tl_configs if c["name"] == entry["env"]]
                if matching:
                    close_tradelocker_trade(matching[0], trade_id, entry)
                else:
                    # Hanko fallback
                    hanko_cfgs = [c for c in active_configs
                                  if c["type"] == "hankotrade" and c["name"] == entry["env"]]
                    if hanko_cfgs:
                        close_side = "sell" if entry["side"] == "buy" else "buy"
                        place_market_orders_sync(hanko_cfgs, entry["symbol"],
                                                  close_side, entry["qty"], 0, 0)
                        registry_mark_closed(trade_id)

            print("CLOSE_ALL sequence completed.")

        # ==============================================================
        # CLOSE LONG / CLOSE SHORT
        # ==============================================================
        elif action in ["close_long", "close_short"]:
            trade_id = data.get("trade_id")

            if trade_id:
                # Preferred path — close the exact trade by ID
                print(f"Close request for specific trade_id: {trade_id}")
                success = close_specific_trade(active_configs, trade_id)
            else:
                # Fallback path — close oldest open position for this symbol/side (FIFO)
                print(f"No trade_id provided — using FIFO close for {symbol} {action}")
                success = close_by_symbol_side_fifo(active_configs, symbol, action)

            status_msg = "closed" if success else "close_attempted_no_match"
            return jsonify({"status": status_msg,
                            "trade_id": trade_id or "fifo"}), 200

        # ==============================================================
        # OPEN A TRADE (buy / sell / long / short / entry)
        # ==============================================================
        elif action in ("buy", "sell", "long", "short", "entry"):
            qty = float(data.get("contracts", data.get("qty", 0.0)))
            if qty <= 0:
                qty = float(os.environ.get(f"LOT_SIZE_{symbol}", 0.0))
            if qty <= 0:
                qty = float(os.environ.get("BASE_LOT_SIZE", 0.01))
            if qty <= 0:
                print(f"Rejecting: resolved lot size is 0")
                return jsonify({"status": "ignored", "reason": "Zero Lot Size"}), 200

            raw_side   = data.get("side", "").lower()
            raw_action = action
            if raw_side in ("buy", "sell", "long", "short"):
                side = "buy" if raw_side in ("buy", "long") else "sell"
            elif raw_action in ("buy", "sell", "long", "short"):
                side = "buy" if raw_action in ("buy", "long") else "sell"
            else:
                side = "buy"

            price_val = float(data.get("price", 0))

            # Normalize Pine Script camelCase field names to executor keys.
            if "stopLoss" in data and "sl" not in data:   data["sl"] = data["stopLoss"]
            if "takeProfit" in data and "tp" not in data:  data["tp"] = data["takeProfit"]
            if "stopLossType" in data and "sl_type" not in data:   data["sl_type"] = data["stopLossType"]
            if "takeProfitType" in data and "tp_type" not in data: data["tp_type"] = data["takeProfitType"]

            # Auto-inject sl_unit / tp_unit ONLY when sl_points/tp_points are NOT present.
            asset_class_hint = _get_asset_class(symbol)
            if "sl_unit" not in data and "sl_points" not in data:
                if asset_class_hint == "forex":   data["sl_unit"] = "pips"
                elif asset_class_hint == "index": data["sl_unit"] = "points"
            if "tp_unit" not in data and "tp_points" not in data:
                if asset_class_hint == "forex":   data["tp_unit"] = "pips"
                elif asset_class_hint == "index": data["tp_unit"] = "points"

            # ---------------------------------------------------------------
            # TRAILING STOP DETECTION
            # When stopLossType is 'trailingOffset' or 'trailing', the SL is
            # maintained dynamically by the broker relative to live price.
            # resolve_offset() must NOT be called — it would convert the offset
            # to a static distance and defeat the trail entirely.
            # trStopOffset (or stopLoss as fallback) is passed straight through.
            # ---------------------------------------------------------------
            raw_sl_type = data.get("sl_type", data.get("stopLossType", ""))
            is_trailing = raw_sl_type in ("trailingOffset", "trailing", "trailingStop")

            if is_trailing:
                # Convert trailing offset from pips to absolute distance for tick math
                trail_raw = float(data.get("trStopOffset", data.get("sl", data.get("stopLoss", 0))))
                if trail_raw > 0:
                    sl = _convert_to_absolute_distance(trail_raw, symbol, data.get("sl_unit"))
                else:
                    sl = 0
                sl_type = "trailing"
                print(f"[TRAILING STOP] {symbol} {side} trail_raw={trail_raw} -> trail_dist={sl}")
            else:
                sl = resolve_offset(symbol, side, 'sl', data, price_val)
                sl_type = "offset"

            tp = resolve_offset(symbol, side, 'tp', data, price_val)
            tp_type = "offset"

            # Generate unique trade ID and attach to this order
            trade_id = generate_trade_id(signal, symbol, timeframe)
            print(f"Opening trade {trade_id}: {side} {qty} {symbol} | SL={sl} ({sl_type}) TP={tp} ({tp_type})")

            results = place_market_orders_sync(
                active_configs, symbol, side, qty, sl, tp,
                trade_id=trade_id, signal=signal, sl_type=sl_type, tp_type=tp_type
            )
            print(f"Dispatch results: {results}")

            return jsonify({
                "status": "success",
                "trade_id": trade_id,
                "message": f"Order dispatched — trade_id: {trade_id}"
            }), 200

        else:
            print(f"Unknown action '{action}' — ignoring.")
            return jsonify({"status": "ignored",
                            "reason": f"Unknown action: {action}"}), 200

    except Exception as e:
        import sys, traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "success", "message": "Signal processed"}), 200


if __name__ == "__main__":
    print("Starting Wise Steward Webhook Executor (TradeLocker + Hanko)...")
    app.run(host="0.0.0.0", port=5001)
