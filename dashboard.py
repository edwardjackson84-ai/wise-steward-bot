import streamlit as st
import os
import json
import glob
from datetime import datetime
from dotenv import load_dotenv

# Configure Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(BASE_DIR, "pending_alerts")
JOURNAL_DIR = os.path.join(BASE_DIR, "journal")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# Load .env from same directory as this script
load_dotenv(os.path.join(BASE_DIR, ".env"))

import sys
import requests
import pandas as pd
from datetime import datetime
import google.generativeai as genai

sys.path.append(BASE_DIR)
from fetch_performance import get_strategy_performance
from geopolitics_engine import fetch_world_news_rss, analyze_geopolitics

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
EXECUTOR_BASE = os.environ.get("EXECUTOR_BASE_URL", "https://wise-steward.onrender.com")

@st.cache_data(ttl=15)
def fetch_registry():
    if not WEBHOOK_SECRET:
        st.error("WEBHOOK_SECRET not configured in dashboard environment")
        return {}
    try:
        resp = requests.get(f"{EXECUTOR_BASE}/registry",
                            params={"token": WEBHOOK_SECRET}, timeout=10)
        if resp.ok:
            return resp.json()
        st.error(f"Registry fetch failed: {resp.status_code}")
        return {}
    except Exception as e:
        st.error(f"Registry unreachable: {e}")
        return {}

def flatten_dispatches(reg):
    """Flatten nested registry into one row per (trade_id, env) dispatch."""
    rows = []
    for tid, entry in reg.items():
        for env_name, d in entry.get("dispatches", {}).items():
            rows.append({
                "trade_id": tid,
                "symbol": entry.get("symbol"),
                "side": entry.get("side"),
                "qty": entry.get("qty"),
                "env": env_name,
                "status": d.get("status"),
                "attempted_at": d.get("attempted_at"),
                "filled_at": d.get("filled_at"),
                "failed_at": d.get("failed_at"),
                "closed_at": d.get("closed_at"),
                "broker_order_id": d.get("broker_order_id"),
                "failure_reason": d.get("failure_reason"),
            })
    return rows

def render_dispatch_monitor():
    st.header("📊 Dispatch Monitor")
    reg = fetch_registry()
    rows = flatten_dispatches(reg)
    now = datetime.utcnow()
    
    # Categorize
    stuck_pending = []
    recent_failures = []
    open_trades = []
    for r in rows:
        if r["status"] == "pending":
            if r["attempted_at"]:
                attempted = datetime.fromisoformat(r["attempted_at"])
                age = (now - attempted).total_seconds()
                if age > 60:
                    r["age_seconds"] = int(age)
                    stuck_pending.append(r)
        elif r["status"] == "failed" and r["failed_at"]:
            failed = datetime.fromisoformat(r["failed_at"])
            if (now - failed).total_seconds() < 24 * 3600:
                recent_failures.append(r)
        elif r["status"] == "open":
            open_trades.append(r)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🟡 Stuck Pending", len(stuck_pending),
                delta=None if len(stuck_pending) == 0 else f"+{len(stuck_pending)}",
                delta_color="inverse")
    col2.metric("❌ Failures (24h)", len(recent_failures))
    col3.metric("✅ Healthy Open", len(open_trades))
    
    if stuck_pending:
        st.subheader("⚠️ Stuck Pending Dispatches")
        st.caption("These dispatches have been in `pending` for >60s. The broker likely never responded.")
        st.dataframe(pd.DataFrame(stuck_pending)[
            ["trade_id", "symbol", "side", "qty", "env", "attempted_at", "age_seconds"]
        ])
    
    if recent_failures:
        st.subheader("❌ Recent Failures (24h)")
        df = pd.DataFrame(recent_failures)
        env_filter = st.multiselect("Filter by env", options=df["env"].unique(),
                                     default=df["env"].unique())
        st.dataframe(df[df["env"].isin(env_filter)][
            ["trade_id", "symbol", "side", "env", "failed_at", "failure_reason"]
        ])
    
    if open_trades:
        st.subheader("✅ Currently Open")
        st.dataframe(pd.DataFrame(open_trades)[
            ["trade_id", "symbol", "side", "qty", "env", "filled_at", "broker_order_id"]
        ])

# Ensure directories exist
for directory in [ALERTS_DIR, JOURNAL_DIR, REPORTS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# --- Spiritual Engine Functions ---
@st.cache_data(ttl=3600) # Memory cache for 1 hour
def get_daily_alignment():
    """Fetches a Verse of the Day and generates a reflection with disk-based persistence."""
    cache_file = os.path.join(BASE_DIR, "daily_alignment.json")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 1. Try loading from disk cache first
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                cached_data = json.load(f)
                if cached_data.get("date") == today_str:
                    return cached_data
        except:
            pass

    try:
        # Fallback verses
        verses = [
            {"ref": "Proverbs 16:3", "text": "Commit your work to the Lord, and your plans will be established."},
            {"ref": "Philippians 4:13", "text": "I can do all things through him who strengthens me."},
            {"ref": "Joshua 1:9", "text": "Have I not commanded you? Be strong and courageous. Do not be frightened, and do not be dismayed, for the Lord your God is with you wherever you go."},
            {"ref": "Matthew 6:33", "text": "But seek first the kingdom of God and his righteousness, and all these things will be added to you."},
            {"ref": "Proverbs 3:5-6", "text": "Trust in the Lord with all your heart, and do not lean on your own understanding. In all your ways acknowledge him, and he will make straight your paths."}
        ]
        
        day_of_year = datetime.now().timetuple().tm_yday
        selected = verses[day_of_year % len(verses)]
        
        # 2. Generate the "Deep Study" using Gemini
        api_key = os.environ.get("GEMINI_API_KEY")
        study = None
        if api_key:
            try:
                genai.configure(api_key=api_key)
                # Using 2.0-flash-lite as it often has different/higher quotas
                model = genai.GenerativeModel('gemini-2.0-flash-lite')
                prompt = (
                    f"As a sovereign spiritual guide for a trader, provide a profound 3-sentence reflection "
                    f"on this verse: '{selected['text']}' ({selected['ref']}).\n"
                    "Sentence 1: Mention the specific Hebrew, Latin, or Aramaic etymology of a key word in the verse.\n"
                    "Sentence 2: Provide a deeper esoteric or metaphysical interpretation of the verse as it relates to internal alignment and market reality.\n"
                    "Sentence 3: Give a concise, actionable application for a trader to maintain discipline and stewardship today.\n"
                    "The tone must be premium, authoritative, and esoteric."
                )
                response = model.generate_content(prompt)
                study = response.text.strip()
            except Exception as api_err:
                print(f"Gemini API Error: {api_err}")
                if "quota" in str(api_err).lower():
                    study = "The heavens are silent as the quota has been exceeded. Realign with the existing word and maintain discipline."
                else:
                    study = f"Spiritual channel currently hazy: {api_err}"
        
        result = {
            "ref": selected['ref'],
            "text": selected['text'],
            "study": study or "Stay aligned with your purpose. (Gemini offline)",
            "date": today_str
        }

        # 3. Save to disk cache if we got a valid study
        if study and "quota" not in study.lower():
            try:
                with open(cache_file, "w") as f:
                    json.dump(result, f)
            except:
                pass
                
        return result

    except Exception as e:
        return {
            "ref": "Proverbs 16:3",
            "text": "Commit your work to the Lord, and your plans will be established.",
            "study": f"Stay aligned. (Error: {e})",
            "date": today_str
        }

st.set_page_config(page_title="Wise Steward Agent Dashboard", page_icon="🧿", layout="wide")

# Custom CSS for Apple/TradingView & Esoteric Aesthetic
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=Cinzel:wght@500;700&display=swap');
    
    /* Background & Global Font */
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 50%, #cbd5e1 100%);
        font-family: 'Inter', sans-serif;
        color: #1e293b;
    }
    
    /* Elegant Title */
    h1 {
        font-family: 'Cinzel', serif;
        font-size: 3rem !important;
        background: -webkit-linear-gradient(45deg, #3b82f6, #8b5cf6, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0px 4px 20px rgba(139, 92, 246, 0.2);
        margin-bottom: 0rem !important;
    }
    
    /* Subtitle */
    .subtitle {
        font-family: 'Inter', sans-serif;
        font-weight: 300;
        letter-spacing: 2px;
        color: #475569;
        font-size: 1.1rem;
        margin-bottom: 2rem;
        text-transform: uppercase;
    }
    
    /* Glassmorphism Expanders / Cards */
    div[data-testid="stExpander"] {
        background: rgba(255, 255, 255, 0.7) !important;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.5) !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.05) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        color: #0f172a;
    }
    div[data-testid="stExpander"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px 0 rgba(59, 130, 246, 0.1) !important;
        border: 1px solid rgba(139, 92, 246, 0.3) !important;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: rgba(248, 250, 252, 0.9) !important;
        border-right: 1px solid rgba(0, 0, 0, 0.05);
        color: #0f172a;
    }
    
    /* Metrics */
    div[data-testid="stMetricValue"] {
        font-family: 'Cinzel', serif;
        color: #8b5cf6;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🧿 Wise Steward")
st.markdown('<p class="subtitle">Autonomous Trading & Visual Arbiter Protocol</p>', unsafe_allow_html=True)

# --- Top Menu Spiritual Header ---
alignment = get_daily_alignment()
st.markdown(f"""
    <div style="background: rgba(255, 255, 255, 0.4); border-radius: 15px; padding: 25px; margin-bottom: 30px; border: 1px solid rgba(139, 92, 246, 0.2); backdrop-filter: blur(10px);">
        <h3 style="font-family: 'Cinzel', serif; color: #1e293b; text-align: center; margin-bottom: 15px; letter-spacing: 2px;">Daily Alignment</h3>
        <p style="font-style: italic; font-size: 1.3rem; color: #475569; text-align: center; font-weight: 300; line-height: 1.6;">"{alignment['text']}"</p>
        <p style="text-align: center; color: #8b5cf6; font-weight: 600; margin-bottom: 20px;">— {alignment['ref']}</p>
        <div style="background: rgba(139, 92, 246, 0.05); border-left: 4px solid #8b5cf6; padding: 15px; border-radius: 0 8px 8px 0; max-width: 900px; margin: 0 auto;">
            <p style="color: #1e293b; margin: 0; font-size: 1.05rem; line-height: 1.5;"><strong>Today's Study:</strong> {alignment['study']}</p>
        </div>
    </div>
""", unsafe_allow_html=True)

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Live Sentry Monitor", "Dispatch Monitor", "Economic Calendar", "Global Chessboard (AI)", "Visual Journal", "Performance Reports"])

st.sidebar.markdown("---")
st.sidebar.markdown("---")
st.sidebar.title("Broker Configuration")

# Active Focus Account (For Settings/Risk Editing)
broker_options = {
    "Forex.com RAW": ".env.forexcom",
    "Hanko X Demo (WS)": ".env.hankodemo",
    "Hanko X Live (WS)": ".env.hankolive",
    "Crucial Markets Demo": ".env.crucialdemo",
    "Crucial Markets Live": ".env.cruciallive",
    "Atlas Demo": ".env.atlasdemo",
    "GatesFX Demo": ".env.gatesdemo",
    "E8 Markets Match-Trader": ".env.e8demo",
    "E8 Markets TradeLocker": ".env.e8tradelocker"
}
selected_broker_name = st.sidebar.selectbox("Select Account to Edit Risk", list(broker_options.keys()))
env_file = os.path.join(BASE_DIR, broker_options[selected_broker_name])

# Dynamically reload environment variables for the selected broker to edit
if os.path.exists(env_file):
    # Clear "pollen" from previous broker selections to ensure isolation
    clearing_vars = [
        "HANKOX_EMAIL", "HANKOX_PASSWORD", "HANKOX_SERVER", "HANKOX_DEMO_ACCOUNT_ID", "HANKOX_LIVE_ACCOUNT_ID",
        "TRADELOCKER_EMAIL", "TRADELOCKER_PASSWORD", "TRADELOCKER_SERVER", "TRADELOCKER_ACCOUNT_ID", "TRADELOCKER_API_URL",
        "MT_EMAIL", "MT_PASSWORD", "MT_SERVER", "MT_ACCOUNT_ID", "MT_BASE_URL"
    ]
    for v in clearing_vars:
        os.environ.pop(v, None)
            
    load_dotenv(env_file, override=True)
else:
    st.sidebar.warning(f"Configuration file {broker_options[selected_broker_name]} not found. Risk settings will not save.")

st.sidebar.markdown("---")
st.sidebar.subheader("Multi-Account Signal Routing")
st.sidebar.caption("Toggle which accounts will execute incoming webhook signals simultaneously.")

for b_name, b_env in broker_options.items():
    env_path = os.path.join(BASE_DIR, b_env)
    is_active = False
    
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.startswith("ACCOUNT_ACTIVE="):
                    is_active = (line.strip().split("=")[1].lower() == "true")
                    break
    
    # Toggle widget
    new_active_status = st.sidebar.toggle(f"Route to {b_name}", value=is_active, key=f"toggle_{b_name}")
    
    # Write back to file if changed
    if new_active_status != is_active:
        import requests
        try:
            req = requests.post("https://wise-steward.onrender.com/toggle",
                                params={"token": WEBHOOK_SECRET}, json={
                "env_name": b_env,
                "active": new_active_status
            }, timeout=10)
            if req.ok:
                try: st.toast(f"Live Sync: {b_name} {'ON' if new_active_status else 'OFF'}", icon="✅")
                except: pass
            else:
                try: st.error(f"Render Sync Failed: {req.text}")
                except: pass
        except Exception as e:
            try: st.error(f"Failed to reach Render server: {e}")
            except: pass
            
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
            
            with open(env_path, "w") as f:
                found_active = False
                for line in lines:
                    if line.startswith("ACCOUNT_ACTIVE="):
                        f.write(f"ACCOUNT_ACTIVE={'True' if new_active_status else 'False'}\n")
                        found_active = True
                    else:
                        f.write(line)
                if not found_active:
                    f.write(f"ACCOUNT_ACTIVE={'True' if new_active_status else 'False'}\n")

st.sidebar.markdown("---")
st.sidebar.title("Risk Management")

# Load existing base lot size
current_lot_size = 0.01
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            if line.startswith("BASE_LOT_SIZE="):
                try:
                    current_lot_size = float(line.strip().split("=")[1])
                except:
                    pass

# Slider for lot size
new_lot_size = st.sidebar.slider(
    "Base Lot Size",
    min_value=0.01,
    max_value=5.00,
    value=current_lot_size,
    step=0.01,
    help="Sets the BASE_LOT_SIZE for the TradeLocker executor. Only applies to signals without a forced quantity."
)

# Load existing specific lot sizes and toggles
specific_lots = {
    "US30": 0.0, "NAS100": 0.0, "SPX": 0.0, "EURUSD": 0.0, "GBPUSD": 0.0, 
    "BTCUSD": 0.0, "XAUUSD": 0.0, "XAGUSD": 0.0, "CADJPY": 0.0, "NZDJPY": 0.0, 
    "USDHKD": 0.0, "USDCNH": 0.0, "BRENT": 0.0, "WTI": 0.0
}
specific_sessions = {}
visual_arbiter_enabled = False

if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            if line.startswith("LOT_SIZE_"):
                try:
                    key, val = line.strip().split("=")
                    symbol = key.replace("LOT_SIZE_", "")
                    if symbol in specific_lots:
                        specific_lots[symbol] = float(val)
                except:
                    pass
            elif line.startswith("SESSIONS_"):
                try:
                    key, val = line.strip().split("=")
                    symbol = key.replace("SESSIONS_", "")
                    if symbol in specific_lots and val:
                        specific_sessions[symbol] = [s.strip() for s in val.split(',')]
                except:
                    pass
            elif line.startswith("ENABLE_VISUAL_ARBITER="):
                try:
                    val = line.strip().split("=")[1]
                    visual_arbiter_enabled = (val.lower() == "true")
                except:
                    pass

# Instrument Customization (Lot Size & Sessions)
st.sidebar.markdown("---")
st.sidebar.subheader("Asset-Specific Rules")
new_specific_lots = {}
new_specific_sessions = {}
lots_changed = False
sessions_changed = False

for sym in specific_lots.keys():
    with st.sidebar.expander(f"{sym} Settings", expanded=False):
        new_val = st.number_input(
            "Lot Size (0.0 = Base)",
            min_value=0.00,
            max_value=50.00,
            value=specific_lots[sym],
            step=0.01,
            key=f"lot_{sym}",
            help=f"Lot size for {sym}. Set to 0.0 to fallback to Base Lot Size."
        )
        new_specific_lots[sym] = new_val
        if new_val != specific_lots[sym]:
            lots_changed = True
            
        current_sessions = specific_sessions.get(sym, ["Asian", "London", "New York"])
        new_sessions = st.multiselect(
            "Allowed Sessions",
            options=["Asian", "London", "New York"],
            default=current_sessions,
            key=f"session_{sym}"
        )
        new_specific_sessions[sym] = new_sessions
        if set(new_sessions) != set(current_sessions):
            sessions_changed = True

# Advanced Settings
st.sidebar.markdown("---")
st.sidebar.subheader("Advanced Settings")
new_visual_arbiter = st.sidebar.toggle(
    "Enable Visual Arbiter (Screenshot Validation)",
    value=visual_arbiter_enabled,
    help="When enabled, the bot will take a screenshot of TradingView and use vision models to validate the setup before trading."
)

# Update .env file if changed
if new_lot_size != current_lot_size or lots_changed or sessions_changed or new_visual_arbiter != visual_arbiter_enabled:
    env_vars = {
        "BASE_LOT_SIZE": str(new_lot_size),
        "ENABLE_VISUAL_ARBITER": "true" if new_visual_arbiter else "false"
    }
    for sym, val in new_specific_lots.items():
        env_vars[f"LOT_SIZE_{sym}"] = str(val)
    for sym, sessions_list in new_specific_sessions.items():
        env_vars[f"SESSIONS_{sym}"] = ",".join(sessions_list)
        
    lines = []
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            lines = f.readlines()
            
    with open(env_file, "w") as f:
        for line in lines:
            line_key = line.split("=")[0] if "=" in line else ""
            if line_key in env_vars:
                # We will write these at the end
                pass
            elif line.strip():
                f.write(line)
                
        # Write updated variables
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
            
    st.sidebar.success("Risk settings updated!")

# Propagate to os.environ for immediately running scripts (if applicable)
os.environ["BASE_LOT_SIZE"] = str(new_lot_size)
for k, v in new_specific_lots.items():
    os.environ[f"LOT_SIZE_{k}"] = str(v)
for k, v in new_specific_sessions.items():
    os.environ[f"SESSIONS_{k}"] = ",".join(v)

def load_json_files(directory):
    files = glob.glob(os.path.join(directory, "*.json"))
    data = []
    for f in sorted(files, reverse=True):
        with open(f, "r") as json_file:
            try:
                alert = json.load(json_file)
                # Attempt to extract generic payload info
                payload = alert.get("payload", alert)
                timestamp = alert.get("received_at", "Unknown")
                symbol = payload.get("symbol", "Unknown")
                action = payload.get("action", "Unknown")
                data.append({"filename": os.path.basename(f), "timestamp": timestamp, "symbol": symbol, "action": action, "raw": payload})
            except:
                pass
    return data

def load_md_files(directory):
    files = glob.glob(os.path.join(directory, "*.md"))
    data = []
    for f in sorted(files, reverse=True):
        with open(f, "r") as md_file:
            content = md_file.read()
            data.append({"filename": os.path.basename(f), "content": content})
    return data

import requests
import pandas as pd
from datetime import datetime

def get_val(key, env_name):
    """Helper to get val with priority: os.environ (prefixed) -> os.environ (global)"""
    if not env_name:
        return os.environ.get(key)
    prefix = env_name.replace(".env.", "").upper()
    specific_key = f"{key}_{prefix}"
    return os.environ.get(specific_key) or os.environ.get(key)

def get_auth_token(env_name=None):
    # Read env vars with environmental awareness
    api_url  = get_val("TRADELOCKER_API_URL", env_name) or "https://demo.tradelocker.com/backend-api"
    email    = get_val("TRADELOCKER_EMAIL", env_name)
    password = get_val("TRADELOCKER_PASSWORD", env_name)
    server   = get_val("TRADELOCKER_SERVER", env_name)
    
    if not email or not password or not server:
        return None, None
    try:
        url = f"{api_url}/auth/jwt/token"
        resp = requests.post(url, json={"email": email, "password": password, "server": server},
                             headers={"accept": "application/json", "Content-Type": "application/json"}, timeout=8)
        if resp.ok:
            return resp.json().get("accessToken"), api_url
    except:
        pass
    return None, None

def get_hanko_token(email, password, server_type):
    login_url = "https://tradeapi.hankotrade.com/api/login"
    login_data = {
        "email": email,
        "password": password,
        "server_type": server_type
    }
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Origin': 'https://trade.hankotrade.com',
        'Referer': 'https://trade.hankotrade.com/'
    }
    try:
        resp = requests.post(login_url, json=login_data, headers=headers, timeout=8)
        if resp.ok and 'data' in resp.json():
            return resp.json()['data']['user']['token']
    except:
        pass
    return None

def fetch_account_metrics(broker_name, env_name=None):
    """Fetches metrics for a specific broker name by reading its dedicated .env variables."""
    # 1. Check if we are focusing on a Hanko X Account
    if "Hanko" in broker_name:
        # For Hanko, we use HANKOX specific keys or fallbacks
        hanko_email = get_val("HANKOX_EMAIL", env_name) or get_val("TRADELOCKER_EMAIL", env_name)
        hanko_password = get_val("HANKOX_PASSWORD", env_name) or get_val("TRADELOCKER_PASSWORD", env_name)
        hanko_server = get_val("HANKOX_SERVER", env_name) or ""
        
        server_identifier = "hankotrade_live" if "Live" in hanko_server else "hankotrade_demo"
        token = get_hanko_token(hanko_email, hanko_password, server_identifier)
        if token:
            try:
                acc_url = "https://tradeapi.hankotrade.com/api/act/user/account/balance"
                headers = {
                    'User-Agent': 'Mozilla/5.0',
                    'Origin': 'https://trade.hankotrade.com',
                    'Referer': 'https://trade.hankotrade.com/',
                    'Authorization': f'Bearer {token}'
                }
                resp = requests.post(acc_url, json={}, headers=headers, timeout=8)
                if resp.ok:
                    data = resp.json().get("data", {})
                    balance = float(data.get("AMOUNT", 0))
                    equity = float(data.get("ACCOUNT_EQUITY", balance))
                    return {
                        "balance": balance,
                        "equity": equity,
                        "server": hanko_server,
                        "account_id": data.get("CUSTOMER_ID", "Unknown")
                    }
            except:
                pass
        return None

    # 2. Match-Trader logic (E8 Markets)
    if "Match-Trader" in broker_name or ("E8" in broker_name and "TradeLocker" not in broker_name):
        try:
            from matchtrader_executor import load_e8_config, authenticate_matchtrader
            # We use the env_name to load the correct config
            config = load_e8_config(env_name)
            trading_api_token, system_uuid, trading_account_token = authenticate_matchtrader(config)
            
            base_url = config["base_url"].rstrip("/")
            url = f"{base_url}/mtr-api/{system_uuid}/open-positions" # We'll just fetch accounts for balance
            
            # Re-auth or similar to get account info
            # Usually Match-Trader login returns account details. 
            # For simplicity, we can re-run login to get the latest balance if not cached,
            # or we can add a specific balance call.
            # Match-Trader standard: /manager/co-login returns accounts list with balances.
            
            login_url = f"{base_url}/manager/co-login"
            payload = {"email": config["email"], "password": config["password"]}
            resp = requests.post(login_url, json=payload, timeout=8)
            if resp.ok:
                data = resp.json()
                accounts = data.get("accounts", [])
                target_id = str(config.get("account_id"))
                for acc in accounts:
                    if str(acc.get("accountNumber")) == target_id or str(acc.get("id")) == target_id:
                        balance = float(acc.get("balance", 0))
                        equity = float(acc.get("equity", balance))
                        return {
                            "balance": balance,
                            "equity": equity,
                            "server": config["server"],
                            "account_id": acc.get("accountNumber")
                        }
        except Exception:
            # Silently fail to avoid BrokenPipeError on stdout
            pass
        return None

    # 3. TradeLocker logic for Crucial Markets / Atlas / others
    target_id = get_val("TRADELOCKER_ACCOUNT_ID", env_name)
    token, api_url = get_auth_token(env_name)
    if not token or not target_id:
        return None
    try:
        url = f"{api_url}/auth/jwt/all-accounts"
        headers = {"accept": "application/json", "Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.ok:
            accounts = resp.json().get("accounts", [])
            for acct in accounts:
                if str(acct.get("id")) == str(target_id):
                    balance = float(acct.get("accountBalance", 0))
                    raw_name = acct.get("name", "Unknown")
                    server_name = raw_name.split("#")[0] if "#" in raw_name else raw_name
                    # TradeLocker doesn't always show dynamic equity in this endpoint, balance is safer baseline
                    return {
                        "balance": balance, 
                        "equity": balance,
                        "server": server_name,
                        "account_id": target_id
                    }
    except:
        pass
    return None

# Initialize Session State for Equity Curve per Account
if "current_account" not in st.session_state:
    st.session_state["current_account"] = selected_broker_name

if "equity_history" not in st.session_state or st.session_state["current_account"] != selected_broker_name:
    st.session_state["equity_history"] = pd.DataFrame(columns=["Time", "Balance", "Equity"])
    st.session_state["equity_history"].set_index("Time", inplace=True)
    st.session_state["current_account"] = selected_broker_name
def fetch_render_alerts():
    """Fetch stored alerts from the live Render webhook server."""
    render_url = "https://wise-steward-bot.onrender.com/check-alerts"
    try:
        response = requests.get(render_url, timeout=5)
        if response.ok:
            data = response.json()
            return data.get("alerts", [])
    except Exception as e:
        st.error(f"Failed to connect to Render webhook: {e}")
    return []

if page == "Live Sentry Monitor":
    st.header("📡 Live Sentry Monitor")

    # Metrics + Chart Logic
    current_env = broker_options.get(selected_broker_name)
    metrics = fetch_account_metrics(selected_broker_name, current_env)
    if metrics:
        now_str = datetime.now().strftime("%H:%M:%S")
        new_row = pd.DataFrame({"Balance": [metrics["balance"]], "Equity": [metrics["equity"]]}, index=[now_str])
        
        # Avoid duplicate consecutive timestamps (to prevent spam on UI refresh)
        if st.session_state["equity_history"].empty or st.session_state["equity_history"].index[-1] != now_str:
            st.session_state["equity_history"] = pd.concat([st.session_state["equity_history"], new_row])
            # Keep only the last 50 data points to avoid memory bloat
            if len(st.session_state["equity_history"]) > 50:
                st.session_state["equity_history"] = st.session_state["equity_history"].tail(50)
                
        # Display Metric Cards
        col1, col2, col3 = st.columns(3)
        col1.metric("Live Balance", f"${metrics['balance']:,.2f}")
        col2.metric("Live Equity", f"${metrics['equity']:,.2f}")
        col3.metric("Broker Context", f"{metrics['server']} ({metrics['account_id']})")
        
        st.markdown("---")
        
        with st.expander("📊 Strategy Performance Breakdown", expanded=True):
            stats_data = get_strategy_performance()
            if stats_data:
                df_stats = pd.DataFrame(stats_data)
                # Format currency columns for Streamlit display
                st.dataframe(
                    df_stats.style.format({
                        "Total PnL ($)": "${:,.2f}",
                        "Win Rate (%)": "{:.1f}%"
                    }).bar(subset=["Total PnL ($)"], color=['#d65f5f', '#5fba7d'], align='mid'),
                    hide_index=True,
                    use_container_width=True
                )
            else:
                st.info("No closed trades match your strategy webhooks yet.")
                
        # Display Area/Line Chart of performance over time
        st.markdown("### 📈 Live Equity Curve")
        if not st.session_state["equity_history"].empty:
            st.line_chart(st.session_state["equity_history"], color=["#cbd5e1", "#8b5cf6"])
    else:
        st.warning("⚠️ TradeLocker credentials missing or API unreachable. Unable to fetch equity curve.")

    st.markdown("---")
    
    # We poll directly from the Render `/check-alerts` cache
    alerts_data = fetch_render_alerts()
    
    st.markdown("### 📥 Recent Webhook Payloads")
    
    if not alerts_data:
        st.info("No recent alerts found on the Render server.")
    else:
        for idx, alert in enumerate(reversed(alerts_data)):
            payload = alert.get("payload", {})
            symbol = payload.get("symbol", "Unknown")
            action = payload.get("action", "Unknown")
            timestamp = alert.get("received_at", "Unknown")
            
            with st.expander(f"Alert {len(alerts_data)-idx}: {symbol} | Action: {action} | {timestamp}"):
                st.json(payload)

elif page == "Dispatch Monitor":
    render_dispatch_monitor()

elif page == "Economic Calendar":
    st.header("📅 Economic Calendar (This Week)")
    st.markdown("Macro & micro economic events impacting global markets.")
    
    @st.cache_data(ttl=3600)
    def fetch_ff_calendar():
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        try:
            resp = requests.get(url, timeout=10)
            if resp.ok:
                return resp.json()
        except:
            pass
        return []
        
    events = fetch_ff_calendar()
    if not events:
        st.warning("Failed to fetch calendar data or data is empty.")
    else:
        df = pd.DataFrame(events)
        impact_filter = st.multiselect("Filter by Impact", ["High", "Medium", "Low", "Non-Economic"], default=["High", "Medium"])
        if not df.empty and "impact" in df.columns:
            df = df[df["impact"].isin(impact_filter)]
            
            try:
                df["date_parsed"] = pd.to_datetime(df["date"])
                df["Day"] = df["date_parsed"].dt.strftime("%A, %b %d")
                df["Time (Est Local)"] = df["date_parsed"].dt.strftime("%I:%M %p")
            except:
                df["Day"] = df["date"]
                df["Time (Est Local)"] = ""
            
            display_cols = ["Day", "Time (Est Local)", "country", "impact", "title", "forecast", "previous"]
            display_cols = [c for c in display_cols if c in df.columns]
            
            # Helper to apply color styles via Pandas Styler map
            def color_impact(val):
                if val == "High": return "color: #dc2626; font-weight: bold;" # Red
                elif val == "Medium": return "color: #ea580c; font-weight: bold;" # Orange
                elif val == "Low": return "color: #65a30d;" # Green
                return ""
            
            # Attempt to use map (or applymap for older pandas)
            styled_df = df[display_cols].style
            try:
                styled_df = styled_df.map(color_impact, subset=["impact"])
            except AttributeError:
                try:
                    styled_df = styled_df.applymap(color_impact, subset=["impact"])
                except:
                    pass
                
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True
            )

elif page == "Global Chessboard (AI)":
    st.header("♟️ Sovereign Intelligence: Global Chessboard")
    st.markdown("Analyzes the latest macroeconomic and geopolitical events through a Game Theory lens to anticipate market impacts.")
    
    # Store news text in session state so it survives re-renders when "Run Simulation" is clicked
    if "latest_news" not in st.session_state:
        st.session_state.latest_news = ""
        
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Raw Intelligence Feed")
        if st.button("📡 Fetch Recent News (BBC World)"):
            with st.spinner("Intercepting global headlines..."):
                st.session_state.latest_news = fetch_world_news_rss(limit=25)
                
        if st.session_state.latest_news:
            st.markdown(st.session_state.latest_news)
            
    with col2:
        st.subheader("Game Theory Simulation")
        if st.button("🧠 Run Game Theory Analysis"):
            if not st.session_state.latest_news or st.session_state.latest_news.startswith("Error"):
                st.warning("Please fetch raw intelligence first.")
            else:
                with st.spinner("Sovereign AI is analyzing the board..."):
                    api_key = os.environ.get("GEMINI_API_KEY")
                    analysis = analyze_geopolitics(api_key, st.session_state.latest_news)
                    st.markdown(analysis)

elif page == "Visual Journal":
    st.header("📸 Visual Verification Journal")
    st.markdown("Review the agent's recent screenshot captures and Trading Manifesto analysis.")
    
    journals = load_md_files(JOURNAL_DIR)
    
    if not journals:
        st.info("No journal entries found. The agent hasn't processed any trades yet.")
    else:
        for journal in journals:
            with st.expander(f"Entry: {journal['filename']}", expanded=False):
                # We render the markdown directly, which will inherently parse embedded images 
                # (Assuming the agent saves image paths accurately in the Markdown file)
                st.markdown(journal['content'], unsafe_allow_html=True)

elif page == "Performance Reports":
    st.header("📊 Performance & Strategic Reports")
    
    reports = load_md_files(REPORTS_DIR)
    
    if not reports:
        st.info("No weekly or monthly summaries available yet.")
    else:
        for report in reports:
            st.subheader(report['filename'])
            st.markdown(report['content'], unsafe_allow_html=True)
            st.markdown("---")

st.sidebar.markdown("---")
st.sidebar.caption("Wise Steward Protocol v2.0 - Agentic Mode")
