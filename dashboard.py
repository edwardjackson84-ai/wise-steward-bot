import streamlit as st
import os
import json
import glob
from datetime import datetime

# Configure Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_DIR = os.path.join(BASE_DIR, "pending_alerts")
JOURNAL_DIR = os.path.join(BASE_DIR, "journal")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

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
page = st.sidebar.radio("Go to", ["Live Sentry Monitor", "Visual Journal", "Performance Reports"])

st.sidebar.markdown("---")
st.sidebar.title("Risk Management")

# Load existing base lot size
env_file = os.path.join(BASE_DIR, ".env")
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
    "XAUUSD": 0.0, "XAGUSD": 0.0, "CADJPY": 0.0, "NZDJPY": 0.0, "USDHKD": 0.0, 
    "USDCNH": 0.0, "BRENT": 0.0, "WTI": 0.0
}
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
            elif line.startswith("ENABLE_VISUAL_ARBITER="):
                try:
                    val = line.strip().split("=")[1]
                    visual_arbiter_enabled = (val.lower() == "true")
                except:
                    pass

# Sliders for specific lot sizes
st.sidebar.markdown("---")
st.sidebar.subheader("Asset-Specific Sets (0.0 = Base)")
new_specific_lots = {}
lots_changed = False

for sym in specific_lots.keys():
    new_val = st.sidebar.number_input(
        f"{sym} Lot",
        min_value=0.00,
        max_value=50.00,
        value=specific_lots[sym],
        step=0.01,
        help=f"Lot size for {sym}. Set to 0.0 to fallback to Base Lot Size."
    )
    new_specific_lots[sym] = new_val
    if new_val != specific_lots[sym]:
        lots_changed = True

# Advanced Settings
st.sidebar.markdown("---")
st.sidebar.subheader("Advanced Settings")
new_visual_arbiter = st.sidebar.toggle(
    "Enable Visual Arbiter (Screenshot Validation)",
    value=visual_arbiter_enabled,
    help="When enabled, the bot will take a screenshot of TradingView and use vision models to validate the setup before trading."
)

# Update .env file if changed
if new_lot_size != current_lot_size or lots_changed or new_visual_arbiter != visual_arbiter_enabled:
    env_vars = {
        "BASE_LOT_SIZE": str(new_lot_size),
        "ENABLE_VISUAL_ARBITER": "true" if new_visual_arbiter else "false"
    }
    for sym, val in new_specific_lots.items():
        env_vars[f"LOT_SIZE_{sym}"] = str(val)
        
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

if page == "Live Sentry Monitor":
    st.header("📡 Live Sentry Monitor")
    
    alerts = load_json_files(ALERTS_DIR)
    
    st.metric(label="Pending Alerts Queue", value=len(alerts))
    st.markdown("---")
    
    if not alerts:
        st.info("No pending alerts from TradingView at the moment.")
    else:
        for alert in alerts:
            with st.expander(f"Alert: {alert['symbol']} | Action: {alert['action']} | {alert['timestamp']}"):
                st.json(alert['raw'])

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
