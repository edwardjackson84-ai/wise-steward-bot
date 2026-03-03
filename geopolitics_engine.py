import os
import requests
import xml.etree.ElementTree as ET

try:
    import google.generativeai as genai
except ImportError:
    genai = None

def fetch_world_news_rss(limit=15):
    """Fetches top world news headlines from a public RSS feed."""
    url = "http://feeds.bbci.co.uk/news/world/rss.xml"
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            root = ET.fromstring(response.content)
            items = []
            for item in root.findall('./channel/item')[:limit]:
                title = item.find('title')
                desc = item.find('description')
                
                t_text = title.text if title is not None else ""
                d_text = desc.text if desc is not None else ""
                
                if t_text:
                    items.append(f"- {t_text}: {d_text}")
            
            if items:
                return "\n".join(items)
    except Exception as e:
        print(f"Error fetching RSS: {e}")
        return f"Error fetching news: {e}"
        
    return "No significant news found."

def analyze_geopolitics(api_key, news_text):
    """Uses Gemini to evaluate news through a Game Theory lens."""
    if not genai:
        return "Error: google-generativeai module not installed."
    if not api_key:
        return "Error: GEMINI_API_KEY environment variable not set. Please add it to your .env file."
        
    try:
        genai.configure(api_key=api_key)
        # Using Gemini 1.5 Flash for speed and excellent reasoning
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = f"""
        You are an advanced Geopolitical Game Theory AI, codenamed 'Sovereign'.
        Analyze the following recent global news headlines as if they are moves on a global chessboard.
        
        Recent News:
        {news_text}
        
        Provide a structured analysis in Markdown format:
        
        ### ♟️ Current State of the Board
        Briefly summarize the major conflicts, alliances, or economic shifts happening right now based purely on the provided news.
        
        ### 👑 Major Players & Moves
        Identify key nations/entities and their recent "moves". Bullet points are best here.
        
        ### 🎯 Game Theory Predictions
        What are the most likely counter-moves, escalations, or de-escalations in the short to medium term? Apply Zero-Sum or Non-Zero-Sum logic where applicable.
        
        ### 📉 Market Impact (Macro)
        How does this specific state of the board likely affect global markets (e.g., Safe Havens like Gold/USD, Energy like Oil, or Equities)? Be specific and analytical.
        
        Keep your tone analytical, objective, and strategic. Do not use generic filler language.
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI Analysis Failed: {e}"

if __name__ == "__main__":
    from dotenv import load_dotenv
    # Test script execution
    load_dotenv(".env")
    key = os.environ.get("GEMINI_API_KEY")
    print("Fetching News...")
    news = fetch_world_news_rss(limit=5)
    print("--- News ---")
    print(news)
    print("\n--- AI Analysis ---")
    if key:
        print(analyze_geopolitics(key, news))
    else:
        print("Set GEMINI_API_KEY in .env to test AI generation.")
