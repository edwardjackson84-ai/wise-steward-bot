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
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #000000 100%);
        font-family: 'Inter', sans-serif;
        color: #e2e8f0;
    }
    
    /* Elegant Title */
    h1 {
        font-family: 'Cinzel', serif;
        font-size: 3rem !important;
        background: -webkit-linear-gradient(45deg, #bfdbfe, #c084fc, #93c5fd);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0px 4px 20px rgba(192, 132, 252, 0.4);
        margin-bottom: 0rem !important;
    }
    
    /* Subtitle */
    .subtitle {
        font-family: 'Inter', sans-serif;
        font-weight: 300;
        letter-spacing: 2px;
        color: #94a3b8;
        font-size: 1.1rem;
        margin-bottom: 2rem;
        text-transform: uppercase;
    }
    
    /* Glassmorphism Expanders / Cards */
    div[data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.6) !important;
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(148, 163, 184, 0.1) !important;
        border-radius: 12px !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="stExpander"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 40px 0 rgba(192, 132, 252, 0.15) !important;
        border: 1px solid rgba(192, 132, 252, 0.3) !important;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: rgba(0, 0, 0, 0.8) !important;
        border-right: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Metrics */
    div[data-testid="stMetricValue"] {
        font-family: 'Cinzel', serif;
        color: #c084fc;
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

# Update .env file if changed
if new_lot_size != current_lot_size:
    lines = []
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            lines = f.readlines()
            
    with open(env_file, "w") as f:
        found = False
        for line in lines:
            if line.startswith("BASE_LOT_SIZE="):
                f.write(f"BASE_LOT_SIZE={new_lot_size}\n")
                found = True
            else:
                f.write(line)
        if not found:
            f.write(f"BASE_LOT_SIZE={new_lot_size}\n")
    st.sidebar.success(f"Lot size updated to {new_lot_size}!")

# Propagate to os.environ for immediately running scripts (if applicable)
os.environ["BASE_LOT_SIZE"] = str(new_lot_size)

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
