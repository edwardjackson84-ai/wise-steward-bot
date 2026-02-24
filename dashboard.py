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

st.set_page_config(page_title="Wise Steward Agent Dashboard", page_icon="🕊️", layout="wide")

st.title("🕊️ Wise Steward Autonomous Agent")
st.markdown("Visual Reasoning and Execution Monitoring Matrix")

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Live Sentry Monitor", "Visual Journal", "Performance Reports"])

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
