import os
import json
import base64
from dotenv import load_dotenv

try:
    import google.generativeai as genai
except ImportError:
    print("google-generativeai not installed. Run: pip install google-generativeai")
    genai = None

# We reload env to ensure we get API keys even if called standalone
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Note: we assume load_dotenv is called in the main executor already, but doing a fallback here.
load_dotenv(os.path.join(BASE_DIR, ".env"))

def analyze_chart_with_vision(image_path: str, symbol: str, strategy: str) -> dict:
    """
    Passes the chart screenshot to Gemini 1.5 Pro to evaluate the trade setup
    against the Trading Manifesto.
    
    Returns a dictionary containing:
        - "approved": bool (True to execute, False to block)
        - "reason": str (The AI's reasoning)
    """
    # Defensive check
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {
            "approved": True, 
            "reason": "GEMINI_API_KEY not found. Visual Arbiter bypassed."
        }
        
    if not genai:
        return {
            "approved": True,
            "reason": "google-generativeai not installed. Visual Arbiter bypassed."
        }
        
    if not os.path.exists(image_path):
        return {
            "approved": True,
            "reason": "Screenshot failed or not found. Bypassing Arbiter to ensure trade execution."
        }

    try:
        genai.configure(api_key=api_key)
        
        # Using Gemini 2.5 Flash for complex visual chart analysis (15 RPM Free Tier limit)
        model = genai.GenerativeModel('gemini-2.5-flash')

        with open(image_path, "rb") as image_file:
            print(f"Uploading chart image for {symbol} to Visual Arbiter...")
            image_parts = [
              {
                "mime_type": "image/png",
                "data": image_file.read()
              }
            ]

        prompt = f"""
        You are the 'Wise Steward' Visual Arbiter, an expert algorithmic trading evaluator.
        You are looking at a TradingView chart snapshot for `{symbol}`.
        A webhook alert just fired indicating a potential entry for the '{strategy}' strategy.
        
        Evaluate the chart against our crucial Risk Management Manifesto:
        1. Context: Are we trading directly into heavy support/resistance or a massive recent wick without room to breathe?
        2. Mean Reversion Risk: Is the price dangerously extended far away from the 20 Moving Average (The red/blue line)? If it's a breakout trade but price is isolated in space, it shouldn't be taken. 
        3. Logic: Does the setup visually look like a high-probability A+ setup?
        
        Respond with ONLY a strict JSON payload in the following format. 
        Ensure "approved" is a boolean. Do not include markdown blocks like ```json.
        {{
            "approved": true or false,
            "reason": "A 2-3 sentence technical justification for your decision."
        }}
        """
        
        response = model.generate_content([prompt, image_parts[0]])
        
        # Clean response string to ensure valid JSON parsing
        resp_text = response.text.strip().removeprefix('```json').removesuffix('```').strip()
        result = json.loads(resp_text)
        
        return result

    except Exception as e:
        print(f"Visual Arbiter Exception: {e}")
        return {
            "approved": True,
            "reason": f"Arbiter crashed ({e}). Bypassing safety check."
        }

if __name__ == "__main__":
    # Test block
    test_img = os.path.join(BASE_DIR, "journal/test_chart.png") # Provide a known path here to test
    print("Testing Visual Arbiter...")
    # Find the most recent image in the journal for testing
    journal_dir = os.path.join(BASE_DIR, "journal")
    import glob
    images = glob.glob(f"{journal_dir}/*.png")
    if images:
        latest_image = max(images, key=os.path.getctime)
        print(f"Found recent image: {latest_image}. Evaluating...")
        print(analyze_chart_with_vision(latest_image, "EURUSD", "Test Strategy"))
    else:
        print("No screenshots found in journal folder to test.")
