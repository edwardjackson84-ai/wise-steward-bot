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
sys.path.append(BASE_DIR)
from fetch_performance import get_strategy_performance
from geopolitics_engine import fetch_world_news_rss, analyze_geopolitics

# Ensure directories exist
for directory in [ALERTS_DIR, JOURNAL_DIR, REPORTS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

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

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Live Sentry Monitor", "Economic Calendar", "Global Chessboard (AI)", "Visual Journal", "Performance Reports"])

st.sidebar.markdown("---")
st.sidebar.markdown("---")
st.sidebar.title("Broker Configuration")

# Active Focus Account (For Settings/Risk Editing)
broker_options = {
    "Forex.com RAW": ".env.forexcom",
    "Hanko X Demo (WS)": ".env.hankodemo",
    "Hanko X Live (WS)": ".env.hankolive"
}
selected_broker_name = st.sidebar.selectbox("Select Account to Edit Risk", list(broker_options.keys()))
env_file = os.path.join(BASE_DIR, broker_options[selected_broker_name])

# Dynamically reload environment variables for the selected broker to edit
if os.path.exists(env_file):
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
            req = requests.post("https://wise-steward.onrender.com/toggle", json={
                "env_name": b_env,
                "active": new_active_status
            }, timeout=5)
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

def get_auth_token():
    # Read env vars INSIDE the function so they are read AFTER load_dotenv() runs
    api_url  = os.environ.get("TRADELOCKER_API_URL", "https://demo.tradelocker.com/backend-api")
    email    = os.environ.get("TRADELOCKER_EMAIL")
    password = os.environ.get("TRADELOCKER_PASSWORD")
    server   = os.environ.get("TRADELOCKER_SERVER")
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

def fetch_account_metrics():
    # 1. Check if we are focusing on a Hanko X Account
    hanko_email = os.environ.get("HANKOX_EMAIL") or os.environ.get("TRADELOCKER_EMAIL")
    hanko_password = os.environ.get("HANKOX_PASSWORD") or os.environ.get("TRADELOCKER_PASSWORD")
    hanko_server = os.environ.get("HANKOX_SERVER", "")
    
    if hanko_email and hanko_password and "Hanko" in hanko_server:
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
        
    # 2. Fallback to older TradeLocker logic for Crucial Markets / others
    target_id = os.environ.get("TRADELOCKER_ACCOUNT_ID", "1961103")
    token, api_url = get_auth_token()
    if not token:
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
    metrics = fetch_account_metrics()
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
