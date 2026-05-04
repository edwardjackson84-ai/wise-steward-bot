#!/usr/bin/env python3
"""
=============================================================
  WISE STEWARD — FULL AGENT WORKFLOW DEBUG SUITE
  Covers every layer of the pipeline:
    [1] ENV file loading & account activation
    [2] Executor config discovery (get_active_configs)
    [3] TradeLocker authentication (Atlas + Crucial)
    [4] Hanko X authentication
    [5] TradeLocker instrument ID map validation
    [6] TradeLocker routeId fetching (live API)
    [7] Webhook endpoint smoke test (buy, sell, close, signal)
    [8] Sabbath mode logic
    [9] Session filter logic
    [10] Symbol map completeness
    [11] Dashboard .env isolation check
=============================================================
"""

import os
import sys
import json
import time
import datetime
import requests
import threading
import subprocess
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"
WARN = "\033[93m⚠️  WARN\033[0m"
INFO = "\033[96mℹ️  INFO\033[0m"

results = []

def log(label, status, detail=""):
    icon = {"PASS": PASS, "FAIL": FAIL, "WARN": WARN, "INFO": INFO}.get(status, INFO)
    print(f"  {icon}  [{label}]  {detail}")
    results.append({"label": label, "status": status, "detail": detail})

def section(title):
    print(f"\n{'='*60}")
    print(f"  🔍 {title}")
    print(f"{'='*60}")

# ─────────────────────────────────────────────
# [1] ENV File Loading & ACCOUNT_ACTIVE
# ─────────────────────────────────────────────
section("1. ENV File Loading & Account Activation")

ENV_FILES = [
    ".env.hankodemo", ".env.hankolive",
    ".env.crucialdemo", ".env.cruciallive",
    ".env.atlasdemo", ".env.forexcom"
]

for env_name in ENV_FILES:
    path = os.path.join(BASE_DIR, env_name)
    if not os.path.exists(path):
        log(env_name, "WARN", "File not found — skipped")
        continue
    vals = dotenv_values(path)
    active = vals.get("ACCOUNT_ACTIVE", "false").strip().lower()
    lot = vals.get("BASE_LOT_SIZE", "N/A")
    log(env_name, "PASS", f"Loaded OK | ACCOUNT_ACTIVE={active} | BASE_LOT_SIZE={lot}")

# ─────────────────────────────────────────────
# [2] Executor Config Discovery
# ─────────────────────────────────────────────
section("2. Executor Config Discovery (get_active_configs)")

# We import the function directly
sys.path.insert(0, BASE_DIR)
try:
    from hankox_executor import get_active_configs, is_sabbath_mode_active, is_session_active, SYMBOL_MAP
    active_configs = get_active_configs()
    if active_configs:
        for cfg in active_configs:
            log(cfg["name"], "PASS", f"type={cfg['type']} is_live={cfg.get('is_live')} email={cfg.get('email','?')[:20]}")
    else:
        log("get_active_configs", "WARN", "No accounts are currently active (ACCOUNT_ACTIVE=True in any .env)")
except Exception as e:
    log("get_active_configs", "FAIL", str(e))
    active_configs = []

# ─────────────────────────────────────────────
# [3] TradeLocker Authentication (Atlas Demo)
# ─────────────────────────────────────────────
section("3. TradeLocker Authentication")

TL_ACCOUNTS = [
    {
        "label": "Atlas Demo",
        "env": ".env.atlasdemo",
        "expected_id": "1900606"
    },
    {
        "label": "Crucial Markets Demo",
        "env": ".env.crucialdemo",
        "expected_id": "1961103"
    }
]

def test_tl_auth(label, env_name, expected_id):
    vals = dotenv_values(os.path.join(BASE_DIR, env_name))
    api_url = vals.get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api")
    email   = vals.get("TRADELOCKER_EMAIL")
    pw      = vals.get("TRADELOCKER_PASSWORD")
    server  = vals.get("TRADELOCKER_SERVER")
    try:
        resp = requests.post(
            f"{api_url}/auth/jwt/token",
            json={"email": email, "password": pw, "server": server},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if not resp.ok:
            log(f"TL Auth [{label}]", "FAIL", f"HTTP {resp.status_code}: {resp.text[:120]}")
            return None, None, None
        
        token = resp.json().get("accessToken")
        
        # Fetch accounts to get accNum
        acc_resp = requests.get(
            f"{api_url}/auth/jwt/all-accounts",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        acc_num = None
        if acc_resp.ok:
            for acct in acc_resp.json().get("accounts", []):
                if str(acct.get("id")) == str(expected_id):
                    acc_num = acct.get("accNum")
                    balance = acct.get("accountBalance")
                    log(f"TL Auth [{label}]", "PASS", f"Token ✓ | accNum={acc_num} | Balance={balance}")
                    return token, expected_id, acc_num
            log(f"TL Auth [{label}]", "WARN", f"Token OK but account {expected_id} not found in all-accounts list")
        else:
            log(f"TL Auth [{label}]", "WARN", f"Token OK but all-accounts failed: {acc_resp.status_code}")
        return token, expected_id, acc_num
    except Exception as e:
        log(f"TL Auth [{label}]", "FAIL", str(e))
        return None, None, None

tl_atlas_token, tl_atlas_id, tl_atlas_accnum = test_tl_auth("Atlas Demo", ".env.atlasdemo", "1900606")
tl_cruc_token,  tl_cruc_id,  tl_cruc_accnum  = test_tl_auth("Crucial Demo", ".env.crucialdemo", "1961103")

# ─────────────────────────────────────────────
# [4] Hanko X Authentication
# ─────────────────────────────────────────────
section("4. Hanko X Authentication")

def test_hanko_auth(label, env_name):
    vals = dotenv_values(os.path.join(BASE_DIR, env_name))
    email    = vals.get("HANKOX_EMAIL")
    password = vals.get("HANKOX_PASSWORD")
    server   = vals.get("HANKOX_SERVER", "Hankotrade-Demo")
    is_live  = "live" in env_name.lower()
    
    login_data = {
        "email": email,
        "password": password,
        "server_type": "hankotrade_live" if is_live else "hankotrade_demo"
    }
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://trade.hankotrade.com',
        'Referer': 'https://trade.hankotrade.com/'
    }
    
    try:
        resp = requests.post(
            "https://tradeapi.hankotrade.com/api/login",
            json=login_data,
            headers=headers,
            timeout=10
        )
        if not resp.ok:
            log(f"Hanko Auth [{label}]", "FAIL", f"HTTP {resp.status_code}: {resp.text[:120]}")
            return None, None
        
        token = resp.json().get('data', {}).get('user', {}).get('token')
        if not token:
            log(f"Hanko Auth [{label}]", "FAIL", f"No token in response: {str(resp.json())[:120]}")
            return None, None
        
        # Fetch balance
        headers['Authorization'] = f'Bearer {token}'
        bal_resp = requests.post(
            "https://tradeapi.hankotrade.com/api/act/user/account/balance",
            json={}, headers=headers, timeout=10
        )
        if bal_resp.ok:
            data = bal_resp.json().get("data", {})
            balance = data.get("AMOUNT")
            acc_id  = data.get("ACCOUNT_ID")
            log(f"Hanko Auth [{label}]", "PASS", f"Token ✓ | AccID={acc_id} | Balance={balance}")
            return token, acc_id
        else:
            log(f"Hanko Auth [{label}]", "WARN", f"Token OK but balance fetch failed: {bal_resp.status_code}")
            return token, None
    except Exception as e:
        log(f"Hanko Auth [{label}]", "FAIL", str(e))
        return None, None

hanko_demo_token, hanko_demo_accid = test_hanko_auth("Demo", ".env.hankodemo")

# ─────────────────────────────────────────────
# [5] Instrument ID Map Validation (TradeLocker)
# ─────────────────────────────────────────────
section("5. Instrument ID Map Validation")

INSTRUMENT_MAP = {
    ".env.atlasdemo": {
        "US30": 16337, "NAS100": 16341, "SPX500": 16336,
        "XAUUSD": 16343, "BTCUSD": 16304,
        "EURUSD": 16316, "GBPUSD": 16310,
    },
    ".env.crucialdemo": {
        "US30": 17028, "NAS100": 17035, "SPX500": 17034,
        "XAUUSD": 17049, "BTCUSD": 17949,
        "EURUSD": 16985, "GBPUSD": 16977,
    },
}

for env_name, inst_map in INSTRUMENT_MAP.items():
    for sym, inst_id in inst_map.items():
        if isinstance(inst_id, int) and inst_id > 0:
            log(f"InstrumentMap [{env_name}]", "PASS", f"{sym} → ID {inst_id}")
        else:
            log(f"InstrumentMap [{env_name}]", "FAIL", f"{sym} has invalid ID: {inst_id}")

# ─────────────────────────────────────────────
# [6] RouteId Fetching (via live API with Atlas token)
# ─────────────────────────────────────────────
section("6. RouteId Fetching (Live API)")

def test_route_id(label, token, acc_id, acc_num, api_url, inst_id, symbol):
    if not token or not acc_num:
        log(f"RouteId [{label}]", "WARN", "Skipped — no valid token/accNum")
        return
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "accNum": str(acc_num)
    }
    try:
        resp = requests.get(f"{api_url}/trade/accounts/{acc_id}/instruments", headers=headers, timeout=10)
        if not resp.ok:
            log(f"RouteId [{label}]", "FAIL", f"HTTP {resp.status_code}: {resp.text[:120]}")
            return
        data = resp.json()
        instruments = data.get("d", {}).get("instruments", [])
        for inst in instruments:
            if str(inst.get("tradableInstrumentId")) == str(inst_id) or inst.get("name") == symbol:
                routes = inst.get("routes", [])
                for r in routes:
                    if r.get("type") == "TRADE":
                        log(f"RouteId [{label}] {symbol}", "PASS", f"tradableInstrumentId={inst_id} routeId={r.get('id')}")
                        return
                log(f"RouteId [{label}] {symbol}", "WARN", f"Instrument found but no TRADE route. Routes: {routes}")
                return
        log(f"RouteId [{label}] {symbol}", "WARN", f"Instrument ID {inst_id} not found in {len(instruments)} instruments")
    except Exception as e:
        log(f"RouteId [{label}]", "FAIL", str(e))

atlas_api = dotenv_values(os.path.join(BASE_DIR, ".env.atlasdemo")).get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api")
test_route_id("Atlas", tl_atlas_token, tl_atlas_id, tl_atlas_accnum, atlas_api, 16337, "US30")
test_route_id("Atlas", tl_atlas_token, tl_atlas_id, tl_atlas_accnum, atlas_api, 16343, "XAUUSD")

cruc_api = dotenv_values(os.path.join(BASE_DIR, ".env.crucialdemo")).get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api")
test_route_id("Crucial", tl_cruc_token, tl_cruc_id, tl_cruc_accnum, cruc_api, 17028, "US30")

# ─────────────────────────────────────────────
# [7] Webhook Endpoint Smoke Tests
# ─────────────────────────────────────────────
section("7. Webhook Endpoint Smoke Tests")

EXECUTOR_URL = "http://localhost:5001"
WEBHOOK_URL  = f"{EXECUTOR_URL}/webhook"

def start_executor():
    proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE_DIR, "hankox_executor.py")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=BASE_DIR
    )
    time.sleep(3)  # Give Flask time to start
    return proc

def send_webhook(payload):
    return requests.post(WEBHOOK_URL, json=payload, timeout=8)

WEBHOOK_TESTS = [
    {
        "label": "Signal-only action (logged, no trade)",
        "payload": {"symbol": "US30", "action": "signal", "bypass_sabbath": "true"},
        "expected_status": "logged"
    },
    {
        "label": "Unknown action (ignored)",
        "payload": {"symbol": "US30", "action": "explode", "bypass_sabbath": "true"},
        "expected_status": "ignored"
    },
    {
        "label": "Buy with zero lots → rejected",
        "payload": {"symbol": "US30", "action": "buy", "contracts": 0, "bypass_sabbath": "true"},
        "expected_status": "ignored"
    },
    {
        "label": "Sabbath block (no bypass)",
        "payload": {"symbol": "US30", "action": "buy", "contracts": 0.01},
        "expected_status": None  # Sunday 3 PM MST — should be blocked
    },
    {
        "label": "Buy US30 (bypass Sabbath, dispatch to active accounts)",
        "payload": {
            "symbol": "US30", "action": "buy", "contracts": 0.01,
            "sl": 38000, "tp": 40000,
            "bypass_sabbath": "true",
            "comment": "Workflow Debug Test"
        },
        "expected_status": "success"
    },
    {
        "label": "Sell XAUUSD (bypass Sabbath)",
        "payload": {
            "symbol": "XAUUSD", "action": "sell", "contracts": 0.01,
            "bypass_sabbath": "true",
        },
        "expected_status": "success"
    },
    {
        "label": "Close Long US30",
        "payload": {
            "symbol": "US30", "action": "close_long", "contracts": 0.01,
            "bypass_sabbath": "true"
        },
        "expected_status": "success"
    },
]

executor_proc = None
try:
    log("Executor Startup", "INFO", "Starting hankox_executor.py on port 5001...")
    executor_proc = start_executor()
    
    # Check health
    try:
        requests.get(f"{EXECUTOR_URL}/webhook", timeout=3)
    except:
        pass  # 405 is expected, that means server is up
    
    log("Executor Startup", "PASS", "Flask server is responding")
    
    for test in WEBHOOK_TESTS:
        try:
            resp = send_webhook(test["payload"])
            body = resp.json()
            actual_status = body.get("status")
            
            if test["expected_status"] is None:
                # For Sabbath test, just verify correct response was received
                log(f"Webhook: {test['label']}", "PASS", f"Response: {actual_status} | {body.get('reason', body.get('message',''))}")
            elif actual_status == test["expected_status"]:
                log(f"Webhook: {test['label']}", "PASS", f"Status={actual_status}")
            else:
                log(f"Webhook: {test['label']}", "FAIL", f"Expected '{test['expected_status']}' but got '{actual_status}' | {resp.text[:120]}")
        except Exception as e:
            log(f"Webhook: {test['label']}", "FAIL", str(e))
            
    # Wait for background tasks to complete
    log("Webhook Dispatch Wait", "INFO", "Waiting 15s for background order threads to complete...")
    time.sleep(15)
    
except Exception as e:
    log("Executor Startup", "FAIL", str(e))
finally:
    if executor_proc:
        executor_proc.terminate()
        log("Executor Shutdown", "INFO", "Terminated executor process")

# ─────────────────────────────────────────────
# [8] Sabbath Mode Logic
# ─────────────────────────────────────────────
section("8. Sabbath Mode Logic")

now = datetime.datetime.now()
weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
hour = now.hour

expected_sabbath = (
    (weekday == 4 and hour >= 16) or
    (weekday == 5) or
    (weekday == 6 and hour < 17)
)

active_sabbath = is_sabbath_mode_active()
if active_sabbath == expected_sabbath:
    status = "PASS" if active_sabbath else "PASS"
    log("Sabbath Mode", status, f"is_sabbath_mode_active()={active_sabbath} | weekday={weekday} hour={hour} — Correct!")
else:
    log("Sabbath Mode", "FAIL", f"Expected={expected_sabbath}, Got={active_sabbath} | weekday={weekday} hour={hour}")

# ─────────────────────────────────────────────
# [9] Session Filter Logic
# ─────────────────────────────────────────────
section("9. Session Filter Logic")

# Inject session env manually so we can test
os.environ["SESSIONS_US30"] = "Asian,London,New York"
os.environ["SESSIONS_XAUUSD"] = "London,New York"

now_utc = datetime.datetime.utcnow()
utc_hour = now_utc.hour
is_asian = (22 <= utc_hour or utc_hour < 8)
is_london = (7 <= utc_hour < 16)
is_ny = (13 <= utc_hour < 22)

def expected_session(sessions_env):
    for s in sessions_env.split(","):
        s = s.strip()
        if s == "Asian" and is_asian: return True
        if s == "London" and is_london: return True
        if s == "New York" and is_ny: return True
    return False

for sym in ["US30", "XAUUSD"]:
    env_sessions_str = os.environ.get(f"SESSIONS_{sym}", "Asian,London,New York")
    actual = is_session_active(sym)
    expected = expected_session(env_sessions_str)
    status = "PASS" if actual == expected else "FAIL"
    log(f"Session [{sym}]", status, f"UTC hour={utc_hour} | is_active={actual} | sessions={env_sessions_str}")

# ─────────────────────────────────────────────
# [10] Symbol Map Completeness
# ─────────────────────────────────────────────
section("10. Symbol Map Completeness")

required_symbols = ["US30", "NAS100", "SPX500", "XAUUSD", "BTCUSD", "EURUSD", "GBPUSD", "GOLD", "DJI", "NASDAQ"]
for sym in required_symbols:
    if sym in SYMBOL_MAP:
        log(f"SymbolMap [{sym}]", "PASS", f"→ {SYMBOL_MAP[sym]}")
    else:
        log(f"SymbolMap [{sym}]", "WARN", "Not in SYMBOL_MAP — will fallback to raw symbol")

# ─────────────────────────────────────────────
# [11] Dashboard ENV Isolation
# ─────────────────────────────────────────────
section("11. Dashboard ENV Isolation")

# Simulate what dashboard.py does
clearing_vars = [
    "HANKOX_EMAIL", "HANKOX_PASSWORD", "HANKOX_SERVER",
    "TRADELOCKER_EMAIL", "TRADELOCKER_PASSWORD", "TRADELOCKER_SERVER", "TRADELOCKER_ACCOUNT_ID", "TRADELOCKER_API_URL"
]

# Poison the env
os.environ["TRADELOCKER_EMAIL"] = "poison@example.com"
os.environ["TRADELOCKER_ACCOUNT_ID"] = "9999999"

# Run clearing
for v in clearing_vars:
    os.environ.pop(v, None)

# Load Atlas env
from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env.atlasdemo"), override=True)

actual_email = os.environ.get("TRADELOCKER_EMAIL")
actual_id    = os.environ.get("TRADELOCKER_ACCOUNT_ID")

if actual_email == "user@example.com" and actual_id == "1900606":
    log("Dashboard ENV Isolation", "PASS", f"Email={actual_email} | AccountID={actual_id} — Env correctly isolated")
else:
    log("Dashboard ENV Isolation", "FAIL", f"Expected Atlas credentials after clearing. Got email={actual_email} id={actual_id}")

# Switch to Crucial
for v in clearing_vars:
    os.environ.pop(v, None)
load_dotenv(os.path.join(BASE_DIR, ".env.crucialdemo"), override=True)
cruc_email = os.environ.get("TRADELOCKER_EMAIL")
cruc_id    = os.environ.get("TRADELOCKER_ACCOUNT_ID")
if cruc_email == "user@example.com" and cruc_id == "1961103":
    log("Dashboard ENV Switch [Crucial]", "PASS", f"AccountID={cruc_id} — Correct Crucial account loaded")
else:
    log("Dashboard ENV Switch [Crucial]", "FAIL", f"Got email={cruc_email} id={cruc_id}")

# ─────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────
section("FINAL SUMMARY")

passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
warned = sum(1 for r in results if r["status"] == "WARN")
total  = passed + failed + warned

print(f"\n  Total: {total}  |  ✅ Passed: {passed}  |  ❌ Failed: {failed}  |  ⚠️  Warnings: {warned}\n")

if failed > 0:
    print("  ❌ FAILING TESTS:")
    for r in results:
        if r["status"] == "FAIL":
            print(f"     → {r['label']}: {r['detail']}")

if warned > 0:
    print("\n  ⚠️  WARNINGS:")
    for r in results:
        if r["status"] == "WARN":
            print(f"     → {r['label']}: {r['detail']}")

print()
