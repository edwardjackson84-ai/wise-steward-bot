import requests
import json
import time

payload = {
    'ticker': 'USDJPY', 
    'action': 'buy', 
    'qty': 0.01, 
    'stopLoss': 20, 
    'stopLossType': 'trailingOffset', 
    'trStopOffset': 20, 
    'takeProfit': 80, 
    'takeProfitType': 'offset', 
    'comment': '9/20 BUY Trail 20pip'
}

print("Testing direct json:")
r = requests.post("http://127.0.0.1:5001/webhook", json=payload)
print(r.status_code, r.text)

time.sleep(2)

print("\nTesting exact string with single quotes inside double quotes (how tradingview might send it if misconfigured):")
payload2 = {
    "ticker": "'USDJPY'", 
    "action": "'buy'", 
    "qty": 0.01, 
    "stopLoss": 20, 
    "stopLossType": "'trailingOffset'", 
    "trStopOffset": 20, 
    "takeProfit": 80, 
    "takeProfitType": "'offset'", 
    "comment": "'9/20 BUY Trail 20pip'"
}
r = requests.post("http://127.0.0.1:5001/webhook", json=payload2)
print(r.status_code, r.text)
