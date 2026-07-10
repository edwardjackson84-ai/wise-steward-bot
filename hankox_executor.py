
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

_LAST_NO_ACCOUNTS_ALERT = 0.0
NO_ACCOUNTS_ALERT_COOLDOWN = 300  # 5 minutes

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
    "USDCAD": "USDCAD",
    "BRENT": "BRENT",
    "UKOIL": "BRENT",
    "EURUSD": "EURUSD"
}

# Explicit aliases for cross-broker naming variations.
# Canonical Name -> List of possible broker names
SYMBOL_ALIASES = {
    "BRENT": ["BRENT", "BRENT+", "UKOIL", "BCO", "BRENT.cash"],
    "WTI":   ["USOIL", "OILUSD", "WTI", "WTI+"],
    "US30":  ["US30", "DOW+", "USA30", "WS30", "DJ30", "DOW"],
    "NAS100": ["NAS100", "NSDQ+", "NAS", "NQ100", "NDX"],
    "SPX500": ["SPX500", "SP+", "US500", "SPX"],
    "EURUSD": ["EURUSD", "EURUSD+", "EUR/USD"],
    "GBPUSD": ["GBPUSD", "GBPUSD+", "GBP/USD"],
    "XAUUSD": ["XAUUSD", "XAUUSD+", "GOLD", "GOLD+"],
}

# In-memory registry of resolved instruments per broker account.
# Format: { env_name: { canonical_symbol: instrument_record } }
_INSTRUMENT_REGISTRY = {}

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

def _migrate_legacy_entry(trade_id, entry):
    """Convert a flat legacy entry to the dispatches shape. No-op if already migrated."""
    if "dispatches" in entry:
        return entry
    env = entry.get("env", "unknown")
    legacy_status = entry.get("status", "open")
    return {
        "schema_version": 1,
        "trade_id": trade_id,
        "symbol": entry.get("symbol"),
        "side": entry.get("side"),
        "qty": entry.get("qty"),
        "signal": entry.get("signal"),
        "created_at": entry.get("opened_at"),
        "dispatches": {
            env: {
                "status": "open" if legacy_status == "open" else "closed",
                "broker_order_id": entry.get("broker_order_id"),
                "tl_position_id": entry.get("tl_position_id"),
                "attempted_at": entry.get("opened_at"),
                "filled_at":    entry.get("opened_at"),
                "closed_at":    entry.get("closed_at"),
                "failure_reason": None,
            }
        }
    }

def _load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    try:
        with open(REGISTRY_PATH) as f:
            reg = json.load(f)
        return {tid: _migrate_legacy_entry(tid, e) for tid, e in reg.items()}
    except Exception as e:
        print(f"[Registry] Load error: {e}")
        return {}

def _save_registry(registry):
    """Atomic write: tmp → fsync → replace. Survives crashes mid-write."""
    tmp = REGISTRY_PATH + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(registry, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, REGISTRY_PATH)
    except Exception as e:
        print(f"[Registry] Save error: {e}")

def registry_add_pending(trade_id, symbol, side, qty, signal, env_name):
    """Create or extend a registry entry with a pending dispatch for one broker."""
    now = datetime.utcnow().isoformat()
    with _registry_lock:
        reg = _load_registry()
        if trade_id not in reg:
            reg[trade_id] = {
                "schema_version": 1,
                "trade_id": trade_id,
                "symbol": symbol, "side": side, "qty": qty, "signal": signal,
                "created_at": now,
                "dispatches": {},
            }
        reg[trade_id]["dispatches"][env_name] = {
            "status": "pending",
            "broker_order_id": None,
            "tl_position_id": None,
            "attempted_at": now,
            "filled_at": None,
            "closed_at": None,
            "failure_reason": None,
        }
        _save_registry(reg)
        print(f"[Registry] PENDING {trade_id} on {env_name}")

def registry_mark_filled(trade_id, env_name, broker_order_id):
    with _registry_lock:
        reg = _load_registry()
        if trade_id in reg and env_name in reg[trade_id]["dispatches"]:
            d = reg[trade_id]["dispatches"][env_name]
            d["status"] = "open"
            d["broker_order_id"] = broker_order_id
            d["filled_at"] = datetime.utcnow().isoformat()
            _save_registry(reg)
            print(f"[Registry] FILLED {trade_id} on {env_name} (broker_id={broker_order_id})")

def registry_mark_failed(trade_id, env_name, reason):
    """Mark a dispatch failed. Creates a stub entry if the trade was never pending."""
    now = datetime.utcnow().isoformat()
    with _registry_lock:
        reg = _load_registry()
        if trade_id not in reg:
            reg[trade_id] = {
                "schema_version": 1, "trade_id": trade_id,
                "symbol": None, "side": None, "qty": None, "signal": None,
                "created_at": now, "dispatches": {},
            }
        if env_name not in reg[trade_id]["dispatches"]:
            reg[trade_id]["dispatches"][env_name] = {
                "status": "failed", "broker_order_id": None, "tl_position_id": None,
                "attempted_at": now, "filled_at": None, "closed_at": None,
                "failed_at": now, "failure_reason": str(reason)[:500],
            }
        else:
            d = reg[trade_id]["dispatches"][env_name]
            d["status"] = "failed"
            d["failed_at"] = now
            d["failure_reason"] = str(reason)[:500]
        _save_registry(reg)
        print(f"[Registry] FAILED {trade_id} on {env_name}: {reason}")

def registry_mark_closed(trade_id, env_name=None):
    """Mark dispatches closed. env_name=None closes all open dispatches for this trade."""
    with _registry_lock:
        reg = _load_registry()
        if trade_id not in reg:
            return
        now = datetime.utcnow().isoformat()
        for env, d in reg[trade_id]["dispatches"].items():
            if env_name is None or env == env_name:
                if d["status"] == "open":
                    d["status"] = "closed"
                    d["closed_at"] = now
        _save_registry(reg)
        print(f"[Registry] CLOSED {trade_id} on {env_name or 'all envs'}")

def registry_get_open(symbol, side, env_name=None):
    """Return [(trade_id, env, dispatch), ...] for open dispatches matching filters, FIFO."""
    with _registry_lock:
        reg = _load_registry()
    matches = []
    for tid, entry in reg.items():
        if entry.get("symbol") != symbol or entry.get("side") != side:
            continue
        for env, d in entry.get("dispatches", {}).items():
            if d["status"] == "open" and (env_name is None or env == env_name):
                matches.append((tid, env, d))
    matches.sort(key=lambda x: x[2].get("attempted_at", ""))
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

    env_files = [".env.hankodemo", ".env.hankolive", ".env.crucialdemo", ".env.cruciallive", ".env.atlasdemo", ".env.atlasdemo2", ".env.atlasdemo3", ".env.e8demo", ".env.e8live", ".env.e8markets", ".env.e8markets2", ".env.e8tradelocker"]

    config_dirs = [
        os.environ.get("WISE_STEWARD_CONFIG_DIR"),
        script_dir,
        "/etc/secrets",
    ]
    config_dirs = [d for d in config_dirs if d]

    for env_name in env_files:
        ep = next(
            (os.path.join(d, env_name) for d in config_dirs
             if os.path.exists(os.path.join(d, env_name))),
            None,
        )
        if ep is None:
            continue
        vals = dotenv_values(ep)
        
        # --- CLOUD SYNC FEATURE ---
        cloud_settings_path = os.path.join(script_dir, "cloud_settings.json")
        if os.path.exists(cloud_settings_path):
            try:
                import json
                with open(cloud_settings_path, "r") as f:
                    cs = json.load(f)
                    if env_name in cs:
                        for k, v in cs[env_name].items():
                            vals[k] = v
            except Exception as e:
                print(f"Error reading cloud_settings.json: {e}")
                
        is_active = str(vals.get("ACCOUNT_ACTIVE", "false")).strip().lower() == "true"
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
                "symbol_suffix": ".HKT",
                "env_vars": vals
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
                "acc_num": str(vals.get("TRADELOCKER_ACCNUM", "1" if "e8" in env_name.lower() else vals.get("TRADELOCKER_ACCOUNT_ID"))).replace("D#", "").strip(),
                "symbol_suffix": "",
                "env_vars": vals
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
    if acc_id and len(str(acc_id)) < 12:
        acc_id = None
        
    if not acc_id:
        acc_url = f"{config['api_url']}/trade/accounts"
        acc_resp = requests.get(acc_url, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if acc_resp.ok:
            accounts = acc_resp.json().get("accounts", [])
            target_acc_num = str(config.get("acc_num", "")).strip()
            if accounts:
                if target_acc_num and target_acc_num != "None":
                    for acc in accounts:
                        if str(acc.get("accNum", "")).replace("D#", "").strip() == target_acc_num:
                            acc_id = acc.get("id")
                            break
                if not acc_id:
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
# TRADELOCKER INSTRUMENT REGISTRY
# ======================================================================

def fetch_instrument_registry(config):
    """
    Fetches the full instrument list for a TradeLocker account and populates 
    the _INSTRUMENT_REGISTRY with optimized lookups.
    """
    env_name = config.get("name", "Unknown")
    print(f"[{env_name}] Fetching instrument registry...")
    
    auth_data = authenticate_tradelocker(config)
    if not auth_data:
        raise RuntimeError(f"Failed to authenticate for instrument fetch on {env_name}")
    
    token, acc_id, acc_num = auth_data
    api_url = config.get("api_url")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "accNum": str(acc_num)
    }
    
    inst_url = f"{api_url}/trade/accounts/{acc_id}/instruments"
    resp = requests.get(inst_url, headers=headers, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"Failed to fetch instruments for {env_name}: {resp.text}")
    
    data = resp.json()
    raw_list = data.get("d", {}).get("instruments", []) if isinstance(data, dict) else []
    if not raw_list and isinstance(data, list):
        raw_list = data
        
    registry = {}
    
    def get_plausibility_score(inst):
        # Tie-break logic: prefer standard precision for the asset class
        name = inst.get("name", "").upper()
        ts = inst.get("tickSize")
        if ts is None: return 0
        
        ts = float(ts)
        if "EURUSD" in name or "GBPUSD" in name:
            return 100 if ts == 1e-05 else 10
        if "US30" in name or "DOW" in name:
            return 100 if ts == 1.0 else 10
        return 50

    # Sort so that better records (more plausible) are processed later and overwrite
    indexed_count = 0
    for inst in raw_list:
        name = inst.get("name", "")
        if not name: continue
        
        # 1. Index by exact name
        registry[name.upper()] = inst
        
        # 2. Index by Alias / Canonical mapping
        for canonical, aliases in SYMBOL_ALIASES.items():
            if name.upper() in [a.upper() for a in aliases]:
                existing = registry.get(canonical)
                if not existing or get_plausibility_score(inst) > get_plausibility_score(existing):
                    registry[canonical] = inst
        
        # 3. Automatic suffix stripping (e.g. BRENT+ -> BRENT)
        if "+" in name:
            stripped = name.replace("+", "").upper()
            if stripped not in registry:
                registry[stripped] = inst
        
        indexed_count += 1
        
    _INSTRUMENT_REGISTRY[env_name] = registry
    print(f"[{env_name}] Successfully indexed {indexed_count} instruments into registry.")

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

    # Resolve from dynamic registry
    registry = _INSTRUMENT_REGISTRY.get(env_name, {})
    inst_record = registry.get(mapped_symbol)
    
    if not inst_record:
        # One last try: strip suffixes and check
        inst_record = registry.get(mapped_symbol.replace("+", ""))

    if not inst_record:
        candidates = sorted(list(registry.keys()))[:10] # Show first 10 for debugging
        error_msg = f"[SYMBOL UNMAPPED] {env_name} cannot resolve '{mapped_symbol}'. Candidates: {candidates}..."
        print(error_msg)
        notify_telegram(f"❌ {error_msg}")
        if trade_id:
            registry_mark_failed(trade_id, env_name, f"Symbol lookup failed: {mapped_symbol}")
        return None

    inst_id = inst_record.get("tradableInstrumentId")
    if not inst_id:
        # Fallback to name if ID is missing in record (unlikely)
        inst_id = inst_record.get("name")
        
    print(f"[{env_name}] Resolved {mapped_symbol} -> ID {inst_id} ({inst_record.get('name')})")

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
        # Logic to find the TRADE route and tickSize schedule
        routes = inst_record.get("routes", [])
        for r in routes:
            if r.get("type") == "TRADE":
                route_id = r.get("id")
                detail_url = f"{api_url}/trade/instruments/{inst_id}?routeId={route_id}"
                det_resp = requests.get(detail_url, headers=headers, timeout=10)
                schedule = det_resp.json().get("d", {}).get("tickSize", []) if det_resp.ok else []
                meta = {"routeId": route_id, "tickSizeSchedule": schedule}
                _ROUTE_CACHE[route_cache_key] = meta
                break
        
        if not route_id:
            print(f"[{env_name}] CRITICAL: No TRADE route found for {mapped_symbol} (ID {inst_id})")
            return None

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
        payload["stopLossType"] = "trailingOffset"
        payload["trStopOffset"] = sl_val
        print(f"[{env_name}] [TRAILING STOP] Attached trStopOffset={sl_val} ticks")
    if route_id:
        payload["routeId"] = route_id

    safe_headers = {k: ("***" if k.lower() == 'authorization' else v) for k, v in headers.items()}
    print(f"[{env_name}] OUTBOUND REST: URL={order_url} Headers={json.dumps(safe_headers)} Body={json.dumps(payload)}", flush=True)
    resp = requests.post(order_url, json=payload, headers=headers, timeout=10)
    print(f"[{env_name}] REST RESPONSE: Status={resp.status_code} Body={resp.text}", flush=True)

    if resp.ok:
        resp_data = resp.json()
        print(f"[{env_name}] REST Order Success: {resp.text}")

        # TradeLocker returns orderId inside the response
        broker_order_id = (
            str(resp_data.get("orderId", ""))
            or str(resp_data.get("id", ""))
            or str(resp_data.get("data", {}).get("orderId", ""))
        )

        if trade_id:
            registry_mark_filled(trade_id, env_name, broker_order_id or "unknown")

        return broker_order_id or "unknown"
    else:
        print(f"[{env_name}] REST Order Failed: {resp.text}")
        notify_telegram(f"❌ {env_name} order rejected: {mapped_symbol} {side} {qty}\n{resp.text[:200]}")
        if trade_id:
            registry_mark_failed(trade_id, env_name, f"Order rejected ({resp.status_code}): {resp.text[:200]}")
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

def close_tradelocker_trade(config, trade_id, entry, dispatch):
    """
    Main close logic for a single TradeLocker trade dispatch.
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
        broker_order_id = dispatch.get("broker_order_id")
        qty = entry["qty"]

        position = find_tl_position_by_order(positions, broker_order_id, symbol, open_side)

        if not position:
            print(f"[{config['name']}] Could not find matching position for trade {trade_id} "
                  f"({symbol} {open_side}). It may already be closed.")
            registry_mark_closed(trade_id, config["name"])
            return False

        position_id = position.get("id") or position.get("positionId")
        pos_qty = float(position.get("qty", qty))

        success = close_tl_position(token, acc_id, acc_num, config["api_url"],
                                     config["name"], position_id, pos_qty)
        if success:
            registry_mark_closed(trade_id, config["name"])

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
        config_qty = qty
        if "env_vars" in config:
            sym_qty = float(config["env_vars"].get(f"LOT_SIZE_{symbol}", 0.0))
            if sym_qty > 0:
                config_qty = sym_qty
            else:
                base_qty = float(config["env_vars"].get("BASE_LOT_SIZE", 0.0))
                if base_qty > 0:
                    config_qty = base_qty

        if trade_id:
            registry_add_pending(trade_id, symbol, side, config_qty, signal, config["name"])
            
        if config_qty <= 0:
            print(f"[{config['name']}] Skipping trade: resolved lot size is {config_qty}")
            if trade_id:
                registry_mark_filled(trade_id, config["name"], broker_id="skipped")
            continue
            
        try:
            if config["type"] == "hankotrade":
                token, acc_id = authenticate_hankotrade(config)
                task = asyncio.create_task(
                    execute_trade_ws(token, acc_id, symbol, side, config_qty,
                                     config["ws_url"], config["name"], sl, tp)
                )
                tasks.append({"env": config["name"], "task": task,
                               "type": "hankotrade", "trade_id": trade_id})
            else:
                token, acc_id, acc_num = authenticate_tradelocker(config)
                task = asyncio.create_task(
                    execute_trade_rest(token, acc_id, acc_num, symbol, side, config_qty,
                                       config["api_url"], config["name"],
                                       sl, tp, trade_id, sl_type, tp_type)
                )
                tasks.append({"env": config["name"], "task": task,
                               "type": "tradelocker", "trade_id": trade_id})
        except Exception as e:
            print(f"[{config['name']}] Multi-Routing Fail: {e}")
            notify_telegram(f"❌ {config['name']} multi-routing fail: {e}")
            if trade_id:
                registry_mark_failed(trade_id, config["name"], f"Setup error: {e}")

    results = {}
    for t in tasks:
        try:
            result = await t["task"]
            success = bool(result)
            results[t["env"]] = success

            # For Hanko (no order ID returned), mark filled or failed
            if t["type"] == "hankotrade" and t["trade_id"]:
                if success:
                    registry_mark_filled(t["trade_id"], t["env"], "hanko_ws")
                else:
                    registry_mark_failed(t["trade_id"], t["env"], "WebSocket execute failed")

            status = "SUCCESS" if success else "FAILED"
            print(f"[{t['env']}] Global Routing Result: {status}")
        except Exception as e:
            print(f"[{t['env']}] Task Error: {e}")
            if t.get("trade_id"):
                registry_mark_failed(t["trade_id"], t["env"], f"Task Exception: {e}")
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
    Looks up a trade_id in the registry and closes all matching open dispatches.
    Returns True if at least one broker closed successfully.
    """
    entry = registry_get(trade_id)
    if not entry:
        print(f"[Registry] trade_id '{trade_id}' not found in registry")
        return False

    dispatches = entry.get("dispatches", {})
    if not dispatches:
        print(f"[Registry] trade_id '{trade_id}' has no dispatches")
        return False

    success = False
    
    for env_name, dispatch in dispatches.items():
        if dispatch.get("status") != "open":
            continue
            
        matching_config = next((c for c in active_configs if c["name"] == env_name), None)
        if not matching_config:
            print(f"[Registry] Skipping close for {trade_id} on {env_name}: config not active")
            continue

        if matching_config["type"] == "tradelocker":
            print(f"[Registry] Closing TL trade {trade_id} on {env_name}")
            if close_tradelocker_trade(matching_config, trade_id, entry, dispatch):
                success = True
        else:
            # Hanko fallback: net out with opposite order
            print(f"[Registry] Hanko fallback net-close for {trade_id} on {env_name}")
            close_side = "sell" if entry["side"] == "buy" else "buy"
            place_market_orders_sync([matching_config], entry["symbol"],
                                      close_side, entry["qty"], 0, 0)
            registry_mark_closed(trade_id, env_name)
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
    trade_id, env_name, dispatch = matches[0]
    print(f"[Close FIFO] Closing oldest open trade {trade_id} for {mapped_symbol} {open_side} on {env_name}")
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
                  ".env.cruciallive", ".env.atlasdemo", ".env.atlasdemo2", ".env.atlasdemo3", ".env.forexcom",
                  ".env.e8demo", ".env.e8live", ".env.e8markets", ".env.e8markets2", ".env.e8tradelocker"]
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

    trade_id_filter = request.args.get("trade_id")
    reg = _load_registry()
    if trade_id_filter:
        reg = {k: v for k, v in reg.items() if k == trade_id_filter}
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

    raise ValueError(
        f"No SL/TP info in payload for {symbol}. "
        f"Need one of: sl_points, sl_offset, sl_type, sl_unit, stopLoss. "
        f"sl_unit is auto-injected for known asset classes — verify {symbol} is in "
        f"_FOREX_PIP_SYMBOLS, _GOLD_SYMBOLS, _JPY_SYMBOLS, or treated as 'index'."
    )

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
        
        # Kill Switch Fast-Fail Check
        now_ts = time.time()
        for env_name, state in kill_switch_state.items():
            if (now_ts - state.get("last_updated", 0)) > 120:
                print(f"[KillSwitch] CRITICAL: Cache for {env_name} is STALE. Failing closed.")
                return jsonify({"error": f"Kill switch cache stale for {env_name}. Failsafe active."}), 503
            if state.get("kill_switch_active"):
                print(f"[KillSwitch] BLOCKED webhook. Kill switch ACTIVE for {env_name}.")
                return jsonify({"error": f"Kill switch active for {env_name}"}), 403

        
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
            error_msg = "CRITICAL: Webhook received but zero active accounts configured. Trade dropped."
            print(error_msg)
            
            global _LAST_NO_ACCOUNTS_ALERT
            now_time = time.time()
            if now_time - _LAST_NO_ACCOUNTS_ALERT > NO_ACCOUNTS_ALERT_COOLDOWN:
                notify_telegram(f"❌ {error_msg}")
                _LAST_NO_ACCOUNTS_ALERT = now_time
                
            return jsonify({"status": "ignored", "reason": "No active accounts"}), 200

        # ==============================================================
        # CLOSE ALL
        # ==============================================================
        if action == "close_all":
            print("CLOSE_ALL triggered — flattening all positions.")

            # Close all open dispatches in registry
            with _registry_lock:
                reg = _load_registry()
            open_dispatches = []
            for tid, e in reg.items():
                for env_name, d in e.get("dispatches", {}).items():
                    if d["status"] == "open":
                        open_dispatches.append((tid, env_name, d, e))
                        
            tl_configs = get_tradelocker_configs_only(active_configs)
            closed_count = 0

            for trade_id, env_name, dispatch, entry in open_dispatches:
                matching = [c for c in tl_configs if c["name"] == env_name]
                if matching:
                    if close_tradelocker_trade(matching[0], trade_id, entry, dispatch):
                        closed_count += 1
                else:
                    # Hanko fallback
                    hanko_cfgs = [c for c in active_configs
                                  if c["type"] == "hankotrade" and c["name"] == env_name]
                    if hanko_cfgs:
                        close_side = "sell" if entry["side"] == "buy" else "buy"
                        place_market_orders_sync(hanko_cfgs, entry["symbol"],
                                                  close_side, entry["qty"], 0, 0)
                        registry_mark_closed(trade_id, env_name)
                        closed_count += 1

            print("CLOSE_ALL sequence completed.")
            return jsonify({
                "status": "accepted",
                "closed_count": closed_count,
                "message": f"Close-all dispatched: {closed_count} positions transitioned to closed"
            }), 200

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
            # qty parsed here is the baseline payload quantity. It will be overridden
            # per-broker dynamically in place_multi_orders_async based on each active config.
            qty = float(data.get("contracts", data.get("qty", 0.01)))

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
                "status": "accepted",
                "trade_id": trade_id,
                "message": "Dispatch enqueued — check /registry for outcome"
            }), 200

        else:
            print(f"Unknown action '{action}' — ignoring.")
            return jsonify({"status": "ignored",
                            "reason": f"Unknown action: {action}"}), 200

    except Exception as e:
        import sys, traceback
        traceback.print_exc(file=sys.stderr)
        return jsonify({"status": "error", "message": str(e)}), 500

    return jsonify({"status": "accepted", "message": "Signal processed"}), 200

# ======================================================================
# DAILY LOSS KILL SWITCH DAEMON
# ======================================================================

kill_switch_state = {}
_kill_switch_lock = threading.Lock()

class MemoryRedis:
    def __init__(self):
        self.store = {}
    def get(self, key):
        return self.store.get(key)
    def set(self, key, value):
        self.store[key] = str(value)

def init_redis():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        print("WARNING: REDIS_URL is not set. Using in-memory store (state will wipe on restart).")
        return MemoryRedis()
    try:
        import redis
        client = redis.from_url(redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        print(f"WARNING: Could not connect to Redis at {redis_url}: {e}. Falling back to in-memory store.")
        return MemoryRedis()

redis_client = init_redis()

def get_kill_switch_flag(env_name):
    try:
        return redis_client.get(f"kill_switch_{env_name}") == "true"
    except Exception as e:
        print(f"[KillSwitch] Redis error reading flag: {e}")
        return True # Fail closed

def set_kill_switch_flag(env_name, state: bool):
    try:
        redis_client.set(f"kill_switch_{env_name}", "true" if state else "false")
    except Exception as e:
        print(f"[KillSwitch] Redis error setting flag: {e}")

def get_start_of_day_baseline(env_name):
    try:
        v = redis_client.get(f"start_of_day_baseline_{env_name}")
        return float(v) if v else None
    except:
        return None

def set_start_of_day_baseline(env_name, value, ts):
    try:
        redis_client.set(f"start_of_day_baseline_{env_name}", str(value))
        redis_client.set(f"start_of_day_ts_{env_name}", str(ts))
    except Exception as e:
        print(f"[KillSwitch] Redis error setting baseline: {e}")

def get_start_of_day_ts(env_name):
    try:
        v = redis_client.get(f"start_of_day_ts_{env_name}")
        return float(v) if v else 0.0
    except:
        return 0.0

def _get_midnight_utc_ts():
    now = datetime.utcnow()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()

def flatten_account(config, token, acc_id, acc_num, api_url, env_name):
    print(f"[{env_name}] [KILL SWITCH] Flattening account...")
    retries = 3
    while retries > 0:
        positions = fetch_tl_positions(token, acc_id, acc_num, api_url, env_name)
        if not positions:
            print(f"[{env_name}] [KILL SWITCH] Account confirmed flat.")
            notify_telegram(f"🛡️ Kill Switch triggered for {env_name}. Account is FLAT.")
            return True
        for pos in positions:
            pos_id = pos.get("id") or pos[0] # Handle dict or array
            qty = pos.get("qty") or pos[4]
            close_tl_position(token, acc_id, acc_num, api_url, env_name, pos_id, qty)
        time.sleep(2)
        retries -= 1
    
    positions = fetch_tl_positions(token, acc_id, acc_num, api_url, env_name)
    if positions:
        print(f"[{env_name}] [KILL SWITCH] CRITICAL: Failed to flatten after 3 retries!")
        notify_telegram(f"🚨 CRITICAL: Kill Switch triggered for {env_name} but FAILED to flatten {len(positions)} positions!")
        return False
    return True

def equity_poller_daemon():
    print("[KillSwitch] Daemon thread started.")
    # Keep track of tokens per env
    tokens = {}
    last_refresh = {}
    
    # Let's read config for pct
    personal_pct_str = os.environ.get("ATLAS_PERSONAL_LOSS_PCT", "0.02")
    firm_pct_str = os.environ.get("ATLAS_FIRM_LOSS_PCT", "0.03")
    try:
        personal_pct = float(personal_pct_str)
        firm_pct = float(firm_pct_str)
    except:
        personal_pct = 0.02
        firm_pct = 0.03
        
    while True:
        try:
            configs = get_tradelocker_configs_only(get_active_configs())
            # For this MVP, we focus on configs that have ATLAS in the name or we apply to all active TradeLocker accounts
            for config in configs:
                try:
                    env_name = config["name"]
                    
                    if "atlas" not in env_name.lower():
                        continue # Target Atlas for now
                    
                    # Check Token age
                    now_ts = time.time()
                    if env_name not in tokens or (now_ts - last_refresh.get(env_name, 0)) > 3000: # Refresh every 50 mins
                        try:
                            token, acc_id, acc_num = authenticate_tradelocker(config)
                            tokens[env_name] = (token, acc_id, acc_num, config["api_url"])
                            last_refresh[env_name] = now_ts
                        except Exception as e:
                            print(f"[{env_name}] [KillSwitch] Auth failed: {e}")
                            with _kill_switch_lock:
                                kill_switch_state[env_name] = {"kill_switch_active": True, "last_updated": now_ts, "fail_closed": True}
                            continue
                    
                    token, acc_id, acc_num, api_url = tokens[env_name]
                    
                    headers = {"Authorization": f"Bearer {token}", "accNum": str(acc_num)}
                    state_url = f"{api_url}/trade/accounts/{acc_id}/state"
                    try:
                        resp = requests.get(state_url, headers=headers, timeout=5)
                        
                        if resp.status_code == 401:
                            # Token expired, force refresh next loop
                            last_refresh[env_name] = 0
                            continue
                        elif not resp.ok:
                            print(f"[{env_name}] [KillSwitch] API Error {resp.status_code}: {resp.text}")
                            with _kill_switch_lock:
                                kill_switch_state[env_name] = {"kill_switch_active": True, "last_updated": now_ts, "fail_closed": True}
                            continue
                    except Exception as e:
                        print(f"[{env_name}] [KillSwitch] Network Error during state fetch: {e}")
                        continue
                    
                    try:
                        data = resp.json().get("d", {}).get("accountDetailsData", [])
                    except Exception as e:
                        print(f"[{env_name}] [KillSwitch] JSON parse error: {e}")
                        continue
                        
                    if len(data) < 24:
                        print(f"[{env_name}] [KillSwitch] Unexpected array length: {len(data)}")
                        with _kill_switch_lock:
                            kill_switch_state[env_name] = {"kill_switch_active": True, "last_updated": now_ts, "fail_closed": True}
                        continue
                        
                    balance = float(data[0])
                    projectedBalance = float(data[1])
                    todayNet = float(data[18])
                    openNetPnL = float(data[23])
                    
                    # Sanity check
                    expected_proj = balance + openNetPnL
                    if projectedBalance <= 0:
                        print(f"[{env_name}] [KillSwitch] Sanity check failed! proj={projectedBalance}")
                        with _kill_switch_lock:
                            kill_switch_state[env_name] = {"kill_switch_active": True, "last_updated": now_ts, "fail_closed": True}
                        continue
                    
                    # Baseline logic
                    midnight_ts = _get_midnight_utc_ts()
                    stored_ts = get_start_of_day_ts(env_name)
                    
                    if stored_ts < midnight_ts:
                        # Reset Time! Capture baseline
                        baseline = max(balance, projectedBalance)
                        set_start_of_day_baseline(env_name, baseline, now_ts)
                        set_kill_switch_flag(env_name, False)
                        print(f"[{env_name}] [KillSwitch] NEW DAY BASELINE CAPTURED: {baseline}")
                    else:
                        baseline = get_start_of_day_baseline(env_name)
                        if baseline is None:
                            # Cold start mid-day
                            baseline = balance - todayNet
                            set_start_of_day_baseline(env_name, baseline, now_ts)
                            print(f"[{env_name}] [KillSwitch] COLD START BASELINE RECONSTRUCTED: {baseline}")
                    
                    # Breach calculation
                    personal_floor = baseline * (1 - personal_pct)
                    firm_floor = baseline * (1 - firm_pct)
                    native_pnl = todayNet + openNetPnL
                    
                    breached = False
                    reason = ""
                    
                    if projectedBalance <= personal_floor:
                        breached = True
                        reason = f"Absolute Equity ({projectedBalance}) hit Personal Floor ({personal_floor})"
                    elif native_pnl <= -(baseline * personal_pct):
                        breached = True
                        reason = f"Native P&L ({native_pnl}) exceeded limit ({-baseline * personal_pct})"
                    
                    # Update memory cache
                    is_active = get_kill_switch_flag(env_name)
                    
                    with _kill_switch_lock:
                        kill_switch_state[env_name] = {
                            "kill_switch_active": is_active or breached,
                            "last_updated": now_ts,
                            "fail_closed": False,
                            "equity": projectedBalance
                        }
                    
                    if breached and not is_active:
                        print(f"[{env_name}] [KillSwitch] TRIPPED! {reason}")
                        set_kill_switch_flag(env_name, True)
                        # Flatten
                        flatten_account(config, token, acc_id, acc_num, api_url, env_name)
                except Exception as e:
                    print(f"[KillSwitch] Unexpected error for config {config.get('name', 'unknown')}: {e}")
                    import traceback
                    traceback.print_exc()

                
        except Exception as e:
            print(f"[KillSwitch] Unexpected loop error: {e}")
            import traceback
            traceback.print_exc()
            
        time.sleep(5)

_daemon_started = False
_daemon_lock = threading.Lock()

def start_daemon():
    global _daemon_started
    with _daemon_lock:
        if not _daemon_started:
            threading.Thread(target=equity_poller_daemon, daemon=True).start()
            _daemon_started = True
def check_startup_health():
    import sys
    import os
    # Telegram check
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("CRITICAL: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing from main environment.")
        sys.exit(3)
        
    configs = get_active_configs()
    if not configs:
        msg = "CRITICAL: Wise Steward booted with ZERO active accounts. Shutting down worker."
        print(msg)
        # ... diagnostic code ...
        sys.exit(3)
        
    # --- Instrument Registry Bootstrapping ---
    print("--- Initializing Dynamic Instrument Registry ---")
    tl_configs = get_tradelocker_configs_only(configs)
    for cfg in tl_configs:
        try:
            fetch_instrument_registry(cfg)
        except Exception as e:
            msg = f"CRITICAL BOOT FAILURE: Could not fetch instruments for {cfg.get('name')}. Error: {str(e)}"
            print(msg)
            from notifications import notify_telegram
            notify_telegram(f"❌ {msg}")
            sys.exit(4) # Hard fail as requested
        
    # Send heartbeat alert on successful boot to verify master process context
    active_names = ", ".join([c.get("name", "Unknown") for c in configs])
    msg = f"✅ Wise Steward booted successfully with {len(configs)} active account(s): {active_names}"
    print(msg)
    from notifications import notify_telegram
    notify_telegram(msg)

if __name__ == "__main__":
    check_startup_health()
    print("Starting Wise Steward Webhook Executor (TradeLocker + Hanko)...")
    app.run(host="0.0.0.0", port=5001)
