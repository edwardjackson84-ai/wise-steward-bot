# TradingView Alert JSON Webhook Guide

This guide provides the exact JSON payloads you should copy and paste into the **Message** box when creating an alert in TradingView for the **Wise Steward Master System**.

Our Render webhook server (`tradelocker_executor.py`) is designed to look for the `"action"` key in the JSON payload to decide what to do (e.g., `buy`, `sell`, `close`, `close_all`, or simply log a `signal`). 

---

## 1. Trade Execution Alerts (Active Trading)

Use these alerts to physically place trades or close positions on TradeLocker.

**Unified BUY Alert / VWAP Long Entry**
*Use this for any long/buy entry signal where you want TradeLocker to immediately buy.*
```json
{
  "action": "buy",
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "price": "{{close}}",
  "signal": "long_entry",
  "bar_time": "{{time}}"
}
```

**Unified SELL Alert / VWAP Short Entry**
*Use this for any short/sell entry signal where you want TradeLocker to immediately sell.*
```json
{
  "action": "sell",
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "price": "{{close}}",
  "signal": "short_entry",
  "bar_time": "{{time}}"
}
```

**Close All Trades (End of Week / Sabbath Mode)**
*Use this to forcefully close all open positions across the entire account.*
```json
{
  "action": "close_all",
  "message": "Sabbath/End of Week close triggered. All positions liquidated.",
  "bar_time": "{{time}}"
}
```

**Take Profit / Stop Loss Hit (Long)**
*Closes specifically long positions for the given symbol.*
```json
{
  "action": "close_long",
  "symbol": "{{ticker}}",
  "message": "Long TP/SL Hit",
  "bar_time": "{{time}}"
}
```

**Take Profit / Stop Loss Hit (Short)**
*Closes specifically short positions for the given symbol.*
```json
{
  "action": "close_short",
  "symbol": "{{ticker}}",
  "message": "Short TP/SL Hit",
  "bar_time": "{{time}}"
}
```

### 15-Minute Liquidity Grabs (First 1-2 Hours of Market Open)

**BOS Up / BOS Bullish -> Visual Verification (Signal)**
*Use this when price breaks a swing high on the 15m chart near market open. The AI will verify if it's a true breakout (buy) or a liquidity grab (sell) before executing.*
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "timeframe": "15",
  "price": "{{close}}",
  "signal": "visual_verify_bos_up",
  "bar_time": "{{time}}"
}
```

**BOS Down / BOS Bearish -> Visual Verification (Signal)**
*Use this when price breaks a swing low on the 15m chart near market open. The AI will verify if it's a true breakdown (sell) or a liquidity grab (buy) before executing.*
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "timeframe": "15",
  "price": "{{close}}",
  "signal": "visual_verify_bos_down",
  "bar_time": "{{time}}"
}
```

---

## 2. Market Structure & FVG Alerts (Journaling / Sentry)

For these structural alerts, we don't want TradeLocker to execute a market order. We just want the AI Agent (Market Sentry) to log them to your `journal/` for recording. 
Using `"action": "signal"` ensures the webhook server simply records the event without executing a trade.

### Fair Value Gaps (FVG)

**Bullish FVG Created**
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "signal_type": "Bullish FVG Created",
  "price": "{{close}}",
  "bar_time": "{{time}}"
}
```

**Bearish FVG Created**
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "signal_type": "Bearish FVG Created",
  "price": "{{close}}",
  "bar_time": "{{time}}"
}
```

**Price Enters Bullish/Bearish FVG**
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "signal_type": "Price Entered FVG",
  "price": "{{close}}",
  "bar_time": "{{time}}"
}
```

### Break of Structure (BOS) & Change of Character (ChoCH)

**BOS Up / BOS Bullish**
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "signal_type": "Break of Structure UP",
  "price": "{{close}}",
  "bar_time": "{{time}}"
}
```

**BOS Down / BOS Bearish**
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "signal_type": "Break of Structure DOWN",
  "price": "{{close}}",
  "bar_time": "{{time}}"
}
```

**CHOCH Up / ChoCH Bullish**
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "signal_type": "Change of Character UP",
  "price": "{{close}}",
  "bar_time": "{{time}}"
}
```

**CHOCH Down / ChoCH Bearish**
```json
{
  "action": "signal",
  "symbol": "{{ticker}}",
  "signal_type": "Change of Character DOWN",
  "price": "{{close}}",
  "bar_time": "{{time}}"
}
```

---

## Pro-Tips for TradingView Setup:
1. **Webhook URL:** Make sure you check "Webhook URL" in TradingView and paste your Render URL (for example: `https://wise-steward.onrender.com/webhook`).
2. **Double Quotes:** Ensure your JSON strings are enclosed in straight double quotes (`"`), not curly quotes (`”`).
3. **Variables:** TradingView automatically swaps variables like `{{ticker}}` (e.g., BTCUSD) and `{{close}}` (e.g., 64000) when the alert fires!
