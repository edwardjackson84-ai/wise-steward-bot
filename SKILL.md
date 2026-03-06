---
name: Wise Steward Trading
description: Instructions, architecture, and principles for the Wise Steward trading agent using TradeLocker API.
---

# Wise Steward Trading Project

## Overview
This skill contains the framework and rules for the "Wise Steward" trading agent. The agent uses Pine Script logic in conjunction with the TradeLocker API. It is designed to trade autonomously while abiding by biblical insight, esoteric wisdom (such as lunar cycles), and strict temporal guardrails.

## Architecture & Components
1. **`tradelocker_executor.py`**
   - **Purpose:** Python script for handling JWT authentication and executing order placements via the TradeLocker API.

2. **`wisdom_context.md`**
   - **Purpose:** Provides a framework for financial discernment based on scripture, celestial alignments, and specific principles like avoiding haste and keeping a 10% reserve.

3. **`sabbath_mode.md`**
   - **Purpose:** Acts as a temporal guardrail. It must stop all trading activities from Friday sunset to Sunday morning.

4. **`market_sentry.py`**
   - **Purpose:** Background script that polls the Render webhook for new TradingView alerts and saves them to `pending_alerts/`.

5. **`auto_journal.md`**
   - **Purpose:** Instruction file for the agent to execute Visual Verification via the Browser, enforce the Trading Manifesto rules, and document actions.

6. **`reporting_skills.md`**
   - **Purpose:** Defines the end-of-week and end-of-month reporting cadences to summarize P&L, win/loss stats, and suggest strategy optimizations.

## Artifacts & Reporting
- **Journal of the Sovereign Arbitrator:** For every trade executed, the agent must generate this artifact. It should thoroughly document both the technical reasoning (from Pine Script/TradeLocker) and the spiritual justifications (from the wisdom context) for the trade.

## Key Rules
- **No Haste:** Evaluate trades deliberately.
- **Sabbath Reserve:** Ensure that a 10% reserve rule is followed in risk management.
- **Sabbath Mode:** Enforce the strict no-trading period between Friday sunset and Sunday morning.
- **Health Checks:** Perform a "Morning Prayer" health check before the trading week begins (e.g., on Sunday morning) to ensure the system is ready.
