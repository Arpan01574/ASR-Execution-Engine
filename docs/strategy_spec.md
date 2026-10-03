# ASR Engine v3 - Canonical Strategy Specification

## 1. Overview
The ASR Engine v3 is an Advanced Support and Resistance systematic strategy. It detects structural supply and demand zones, validates them with price action context (FVG, CHoCH, Regime), and executes trades mechanically with strict risk management.

**This document is the Single Source of Truth.** Both the Pine Script indicator/strategy and the Python Execution Engine MUST conform to these rules.

## 2. Core Concepts

### 2.1 Zones
- **Definition:** A Support (Demand) or Resistance (Supply) zone is formed by a confirmed Swing Pivot.
- **Confirmation Delay (`pivR`):** A pivot at index `i` is NOT known until `i + pivR`. The zone is `CREATED` at `i + pivR`.
- **Top/Bottom Calculation:** 
  - Resistance (Supply): `Top = High`, `Bottom = max(Close, Open)`.
  - Support (Demand): `Bottom = Low`, `Top = min(Close, Open)`.
- **Polarity:** `1` for Resistance (look for Shorts), `-1` for Support (look for Longs).

### 2.2 Liquidity & Structure
- **Fair Value Gap (FVG):** Measured at the departure from the zone. A strong FVG immediately following a pivot validates the displacement.
- **Change of Character (CHoCH):** Evaluated against the most recent opposite pivot. If a new Demand zone breaks above the previous Supply pivot, it confirms a bullish structural shift.

### 2.3 Setups
1. **ZONE_REJECT:** Price enters the zone, respects the extreme boundary, and closes back inside or below/above it.
2. **ZONE_BREAK:** Price closes beyond the extreme boundary of the zone, invalidating the zone and potentially triggering a breakout trade (if enabled).

## 3. Signal Generation (Entries)

### 3.1 Gating / Context
A zone rejection only generates an `ENTRY` signal if:
1. **Trend Alignment:** The zone polarity matches the HTF Trend (e.g., EMA 200).
2. **Regime:** Market volatility is within acceptable bounds (ATR filter).
3. **Score:** The zone's calculated Quality Score is `>= MIN_SCORE` (default 50).

### 3.2 Order Intent
When an entry condition is met on a *closed bar*:
- **Direction:** `LONG` (if Support reject) or `SHORT` (if Resistance reject).
- **Entry Price:** Close price of the signal bar.
- **Stop Loss:** Zone extreme + ATR Buffer (e.g., `Low - 0.5 * ATR` for Longs).
- **Take Profit 1 (TP1):** `Entry + 1.5 * (Entry - Stop)`.
- **Take Profit 2 (TP2):** `Entry + 3.0 * (Entry - Stop)`.

## 4. Trade Management (Exits)

### 4.1 Fractional Exits (The 3-Stage Model)
- **Stage 1 (SL):** If price hits Stop Loss, 100% of the position is closed. Loss = 1R.
- **Stage 2 (TP1):** If price hits TP1, `33%` of the position is closed. Stop Loss for the remaining `67%` is immediately moved to `Breakeven` (Entry Price).
- **Stage 3 (TP2):** If price hits TP2, `33%` of the position is closed. The remaining `34%` becomes a "Runner".
- **Stage 4 (Runner Trail):** The final `34%` trails an ATR-based stop (e.g., `1.5 ATR`) until stopped out.
- **Stage 5 (Time Stop):** If the trade has been open for `MAX_BARS` (default 24), close the entire remaining position at Market.

### 4.2 Slippage & Fees
- **Execution Assumption:** `MARKET` orders for entries. `STOP_MARKET` for SL. `LIMIT` for TPs.
- **Paper Engine Fees:** Standard `0.04%` taker fee applied to market fills.
- **Slippage:** Slippage drift > `0.5%` from the intended signal entry price will result in a rejected execution (Drift Guard).

## 5. State Transitions

### 5.1 Order FSM
`NEW` -> `VALIDATING` -> `RISK_CHECK` -> `SUBMITTING` -> `OPEN` -> `PARTIAL` -> `FILLED`
(Any failure leads to `REJECTED` or `CANCELLED`).

### 5.2 Position FSM
`FLAT` -> `OPENING` -> `OPEN` -> `REDUCING` -> `CLOSING` -> `CLOSED`.

## 6. Execution Semantics
- **Pine Script:** Acts as the visual and signaling layer. Fires Webhooks on the Close of the signal bar.
- **Python Engine:** Authoritative risk manager. The engine verifies the signal TTL, checks the global drawdown limit, dynamically calculates position size based on exact Decimal arithmetic, and routes to the Venue API.
