# Auto-Journaling & Visual Verification

This skill defines the autonomous process for visually verifying TradingView alerts and journaling the results. This is executed whenever a new alert JSON file is detected in the `pending_alerts/` directory.

## Trigger
- The `market_sentry.py` script downloads a new alert JSON into `pending_alerts/`.
- The Agent is invoked (or runs on a loop) to process this pending alert.

## Execution Steps

### 1. Read Alert Data
- Read the oldest `.json` file in the `pending_alerts/` directory.
- Extract the `symbol`, `action` (buy/sell/signal), `timeframe`, and `price`.

### 2. Browser Verification (Visual Reasoning)
- Use the **Browser Sub-Agent** to navigate to the TradingView chart for the given `symbol`.
- Ensure the chart is on the correct timeframe.
- **Capture a high-resolution screenshot** of the current chart state.

### 2.5. Session Volume & Liquidity Verification (15m BOS Signals)
If the alert action is `signal` and the signal type is `visual_verify_bos_up` or `visual_verify_bos_down`, the AI must perform a temporal volume check to determine if this is a liquidity grab or a true breakout:
1. **Identify Asset & Core Session Open:**
   - **US Indices (US30, NAS100, SPX):** High volume occurs at the NY Open (9:30 AM - 11:30 AM EST).
   - **Forex (EURUSD, GBPUSD):** High volume occurs at London Open (3:00 AM - 5:00 AM EST) and NY overlap (8:00 AM - 11:00 AM EST).
2. **Evaluate Timestamp:** Does the alert timestamp fall within the first 1-2 hours of the asset's core session open?
3. **Determine Classification:**
   - **Inside Opening Window (High Volume):** The 15m Break of Structure (BOS) is highly likely a **Liquidity Grab**. 
     - *Bullish BOS (Up)* -> REVERSE to a **SELL** (Short) trade.
     - *Bearish BOS (Down)* -> REVERSE to a **BUY** (Long) trade.
   - **Outside Opening Window (Lower Volume) OR < 15m Timeframe:** Treat as a standard **True Breakout**.
     - *Bullish BOS (Up)* -> Standard **BUY** (Long) trade.
     - *Bearish BOS (Down)* -> Standard **SELL** (Short) trade.

### 3. The Trading Manifesto Analysis
Analyze the screenshot using Visual Reasoning to check the following strict conditions:
1. **Candle Body:** The most recent closed candle's body must be > 60% of its total high-to-low string/range (strong momentum).
2. **RSI:** The Relative Strength Index (RSI) must be between **50 and 70** (for longs) or **30 and 50** (for shorts). If RSI > 75 or < 25, REJECT as overextended.
3. **200 EMA:** Price must be closing **above** the 200 EMA for longs, and **below** the 200 EMA for shorts.
4. **Volume:** The breakout candle's volume must visually stand out, higher than the recent 20-period moving average of volume.

### 4. Decision & Journaling
- Based on the visual analysis, determine if the trade is **CONFIRMED** or **REJECTED**.
- Create a Markdown file in the `journal/` directory named `Alert_<SYMBOL>_<TIMESTAMP>.md`.
- Ensure the screenshot image is copied/saved into the `journal/` directory so it can be embedded.
- **Journal Format:**
  - Date & Time
  - Symbol and Action
  - Snapshot Image embedded
  - Analysis Breakdown (Candle Body, RSI, EMA, Volume)
  - Final Decision (CONFIRMED / REJECTED)
  - Rationale linking biblical principles (e.g., "Exercising Diligence over Haste" by visually confirming before executing).

### 5. Execution & Cleanup
- If **CONFIRMED** and the action is an entry (`buy`/`sell`), execute the trade via the `tradelocker_executor.py` system.
- If **REJECTED**, do nothing but log the rejection in the journal.
- Delete the processed `.json` file from `pending_alerts/` to prevent duplicate processing.
