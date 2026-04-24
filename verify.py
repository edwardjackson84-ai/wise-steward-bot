import sys
import os
from dotenv import load_dotenv

# Append the current directory so we can import dashboard
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dashboard import fetch_account_metrics

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("Testing Atlas Demo...")
    # Clear environment specific variables to prevent pollen
    for key in list(os.environ.keys()):
        if "TRADELOCKER" in key:
            del os.environ[key]
            
    load_dotenv(os.path.join(base_dir, ".env.atlasdemo"), override=True)
    atlas_metrics = fetch_account_metrics("Atlas Demo", ".env.atlasdemo")
    print(f"Atlas Metrics: {atlas_metrics}")
    
    print("\nTesting E8 TradeLocker Demo...")
    for key in list(os.environ.keys()):
        if "TRADELOCKER" in key:
            del os.environ[key]
            
    load_dotenv(os.path.join(base_dir, ".env.e8tradelocker"), override=True)
    e8_metrics = fetch_account_metrics("E8 Markets TradeLocker", ".env.e8tradelocker")
    print(f"E8 Metrics: {e8_metrics}")

if __name__ == "__main__":
    main()
