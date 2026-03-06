# Reporting & Strategic Review Skills

This skill defines the autonomous reporting mechanisms for the Wise Steward trading agent. These reports help provide human oversight over the autonomous agent's performance and suggest strategic adjustments.

## 1. Weekly Performance Summary
**Trigger:** Run automatically every Saturday morning (during Sabbath mode).

### Execution Steps
1. **Gather Data:** Scan the local `journal/` directory for all `Alert_*.md` files created in the past 7 days.
2. **Analysis:**
   - Tally the total number of alerts received.
   - Count how many were **CONFIRMED** (executed) vs. **REJECTED**.
   - Review the primary reasons for rejections (e.g., "RSI too high", "Price below 200 EMA").
   - Extract the financial results (P&L) of the CONFIRMED trades from TradeLocker terminal history (if accessible) or track entries vs. exits in the journal.
3. **Artifact Generation:**
   - Create a Master Ledger Markdown file: `reports/Weekly_Summary_YYYY_MM_DD.md`.
   - Organize the summary into an executive format: Win/Loss rate, Total P&L, and common rejection themes.
   - Include a section highlighting the "Best Setup of the Week" (embedding the original visual screenshot).

## 2. Monthly Strategic Review
**Trigger:** Run on the 23rd of every month (or the last weekend of the month).

### Execution Steps
1. **Aggregated Analysis:** Review the past 4 Weekly Summaries.
2. **Strategy Optimization:**
   - Analyze the win/loss ratios against the Trading Manifesto rules.
   - *Example:* Are too many valid break-outs being rejected because the RSI threshold (70) is too strict? Is the 200 EMA serving as a reliable dynamic support?
3. **Adjustments:** Propose specific parameter adjustments for the Pine Script indicator (e.g., "Recommend changing RSI overbought threshold from 70 to 75 based on missed 4H breakouts").
4. **Artifact Generation:** 
   - Create `reports/Monthly_Review_YYYY_MM.md` containing the strategic insights and proposed system updates for human review and approval.
