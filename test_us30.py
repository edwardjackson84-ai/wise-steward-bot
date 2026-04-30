import urllib.request
import json
import time

try:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EDJI?interval=1m"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    price = data['chart']['result'][0]['meta']['regularMarketPrice']
    
    # SELL order -> SL higher, TP lower
    sl = round(price + 200, 2)
    tp = round(price - 400, 2)
    print(f"Market Price: {price}, SL: {sl}, TP: {tp}")
    
    payload = {
        "action": "sell",
        "symbol": "DOW+",
        "qty": 0.01,
        "sl": sl,
        "tp": tp,
        "bypass_sabbath": "true"
    }
    
    webhook_url = "https://wise-steward.onrender.com/webhook"
    req = urllib.request.Request(webhook_url, data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    res = urllib.request.urlopen(req)
    print(f"Webhook response: {res.read().decode('utf-8')}")
    
except Exception as e:
    print(f"Error: {e}")
