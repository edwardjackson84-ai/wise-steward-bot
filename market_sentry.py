import os
import time
import requests
import json
from datetime import datetime
from dotenv import load_dotenv

# Configure your Render app URL here or via environment variable
RENDER_APP_URL = os.environ.get("RENDER_APP_URL", "https://your-render-app.onrender.com")

POLL_INTERVAL_SEC = 5
PING_INTERVAL_SEC = 600 # 10 minutes

ALERTS_DIR = "pending_alerts"
JOURNAL_DIR = "journal"

def setup():
    if not os.path.exists(ALERTS_DIR):
        os.makedirs(ALERTS_DIR)
    if not os.path.exists(JOURNAL_DIR):
        os.makedirs(JOURNAL_DIR)

def ping_render():
    try:
        url = f"{RENDER_APP_URL.rstrip('/')}/ping"
        resp = requests.get(url, timeout=10)
        if resp.ok:
            print(f"[{datetime.now().isoformat()}] Ping successful. Render is awake.")
        else:
            print(f"[{datetime.now().isoformat()}] Ping failed: {resp.status_code}")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Ping error: {e}")

def poll_alerts():
    try:
        url = f"{RENDER_APP_URL.rstrip('/')}/check-alerts"
        resp = requests.get(url, timeout=10)
        if resp.ok:
            data = resp.json()
            alerts = data.get("alerts", [])
            for alert in alerts:
                timestamp = int(time.time() * 1000)
                filename = os.path.join(ALERTS_DIR, f"alert_{timestamp}.json")
                with open(filename, "w") as f:
                    json.dump(alert, f, indent=2)
                print(f"[{datetime.now().isoformat()}] New alert received! Saved to {filename}")
                
                # Also write to local Visual Journal for the dashboard
                payload = alert.get("payload", {})
                sym = payload.get("symbol", "UNKNOWN")
                act = payload.get("action", "Unknown")
                md_filename = os.path.join(JOURNAL_DIR, f"Alert_{sym}_{timestamp}.md")
                content = f"""# Alert: {sym}
    
**Date & Time:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Action:** {act}
**Technical Confluence:** {payload.get("strategy", "Unknown")}
**Signal Type:** {payload.get("signal_type", payload.get("signal", "Unknown"))}
**Price:** {payload.get("price", "Market")}
**Biblical Principle:** *Exercising Diligence over Haste.*

### Raw Payload
```json
{json.dumps(payload, indent=2)}
```
"""
                with open(md_filename, "w") as f:
                    f.write(content)
                    
                # Visual Arbiter Integration
                load_dotenv(override=True)
                visual_arbiter_enabled = os.environ.get("ENABLE_VISUAL_ARBITER", "false").lower() == "true"
                if visual_arbiter_enabled:
                    print(f"[{datetime.now().isoformat()}] 👁️ Visual Arbiter ENABLED. Triggering screenshot validation pipeline for {sym}...")
                    # TODO: Integrate actual playwright/browser screenshot logic here later
                    # Currently we just log that the pipeline was theoretically triggered
                else:
                    print(f"[{datetime.now().isoformat()}] 👁️ Visual Arbiter DISABLED. Executing trade immediately without screenshot validation.")
        else:
            # Only print polling errors if not a 404 (in case it hasn't deployed fully yet)
            if resp.status_code != 404:
                print(f"[{datetime.now().isoformat()}] Poll failed: {resp.status_code}")
    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Poll error: {e}")

def main():
    print(f"Starting Market Sentry...")
    print(f"Watching Render Server: {RENDER_APP_URL}")
    print(f"Polling every {POLL_INTERVAL_SEC} seconds...")
    setup()
    
    last_ping_time = 0
    
    while True:
        current_time = time.time()
        
        # Check if it's time to ping
        if current_time - last_ping_time >= PING_INTERVAL_SEC:
            ping_render()
            last_ping_time = current_time
            
        # Poll for new alerts
        poll_alerts()
        
        # Wait before polling again
        time.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    main()
