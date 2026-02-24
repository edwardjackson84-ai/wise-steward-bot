# Sabbath Mode Guidelines

## Objective
Sabbath Mode is a strict, unbreakable temporal guardrail for the Wise Steward trading agent. 

## The Rule
**ALL TRADING MUST HALT BETWEEN FRIDAY SUNSET AND SUNDAY MORNING.**
This honors the principles of rest, prevents algorithm exhaustion during weekend gaps or low liquidity, and ensures a period of detachment from market activity.

### Enforcement Rules
1. **Closing Open Positions:**
   - Any open trades MUST be evaluated for closure before the close of the regular US trading session on Friday, regardless of P/L status.
   - The system should begin attempting to flatten all positions by Friday 3:45 PM EST.

2. **Blocking New Entries:**
   - The script must reject any new trade signals (from webhook, indicator, or logic) received from Friday 4:00 PM EST through Sunday 5:00 PM EST (the standard forex market open).
   - If a valid setup logic trigger fires during this period, it must be discarded with a log message citing: `Rejecting trade signal: Sabbath Mode Active`.

3. **Morning Prayer/Health Check:**
   - On Sunday morning, before market open, the agent is expected to run a system health check. This includes verifying connection status with Tradelocker, validating account equity limits, and preparing the systems.

### Implementation Logic
*   The Python executor should independently verify the current day/time via system clock or strictly enforce timezones (UTC or EST preferred) before transmitting any order to the Tradelocker API.
*   The Pine Script alerts should also include time-filters to prevent the initial firing of alerts over the weekend. (e.g., `alertcondition(endOfWeek, title="Close All Trades", message='{"action":"close_all"}')` as seen in the King David Multi-TF strategy).
