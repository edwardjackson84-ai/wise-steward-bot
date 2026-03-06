import os
import time
from datetime import datetime

# Setup Playwright for headless browser automation
# Note: User will need to run: pip install playwright && playwright install chromium
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    print("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sync_playwright = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOURNAL_DIR = os.path.join(BASE_DIR, "journal")

if not os.path.exists(JOURNAL_DIR):
    os.makedirs(JOURNAL_DIR)

def capture_chart_screenshot(symbol: str, timeframe: str = "60") -> str:
    """
    Spins up a headless browser, navigates to a TradingView chart for the given symbol,
    and takes a screenshot.
    
    Returns the absolute path to the saved screenshot image.
    """
    if not sync_playwright:
        raise Exception("Playwright is not installed. Cannot take screenshot.")
        
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📸 Visual Arbiter: Capturing {symbol} ({timeframe}m) chart...")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_path = os.path.join(JOURNAL_DIR, f"{symbol}_{timeframe}_{timestamp}.png")
    
    # Use the advanced chart widget URL (Requires less overhead than the main app)
    # We pass the symbol and interval in the URL parameters
    tv_url = f"https://www.tradingview.com/chart/?symbol={symbol}&interval={timeframe}"
    
    with sync_playwright() as p:
        # Launch Chromium headless
        browser = p.chromium.launch(headless=True)
        
        # Set a realistic viewport size for a good chart analysis
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        try:
            # Navigate to the chart
            page.goto(tv_url, timeout=30000, wait_until="domcontentloaded")
            
            # Wait for the main chart canvas to render
            # TradingView charts are complex canvases, we wait for a specific selector
            page.wait_for_selector(".chart-gui-wrapper", timeout=15000)
            
            # Give it an extra 3 seconds to ensure indicators and candles fully draw
            time.sleep(3)
            
            # Take the screenshot
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Screenshot saved successfully to: {screenshot_path}")
            
        except PlaywrightTimeoutError:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Timeout error while loading TradingView chart for {symbol}")
            screenshot_path = ""
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Failed to take screenshot: {e}")
            screenshot_path = ""
        finally:
            browser.close()
            
    return screenshot_path

if __name__ == "__main__":
    # Test the function if run directly
    print("Testing Visual Arbiter Screenshot Engine...")
    img = capture_chart_screenshot("OANDA:EURUSD", "60")
    if img:
        print(f"Test completed. Image located at: {img}")
