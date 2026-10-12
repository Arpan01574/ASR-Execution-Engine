# ASR Engine v3 — Live Trading Strategy Guide

> **Core Methodology** — A comprehensive breakdown of the structural price action rules governing the auto-trader's entry, exit, and risk logic.

---

## 📋 Table of Contents

- [Strategy Overview](#1-strategy-overview)
- [Core Logic](#2-core-logic)
- [Entry Conditions](#3-entry-conditions)
- [Exit Rules](#4-exit-rules)
- [Risk Management](#5-risk-management)
- [Timeframe Rationale](#6-timeframe-selection-rationale)

---

## 1. Strategy Overview

| Property | Value |
|----------|-------|
| **Name** | ASR Engine v3 (Advanced Support & Resistance) |
| **Type** | Structural Price Action Trading |
| **Markets** | Crypto Perpetual Futures (Binance USDⓈ-M) |
| **Direction** | Long and Short |
| **Holding Period** | Intrabar (1m scalps) to multi-day (4h swings) |

The ASR Engine identifies high-probability trade setups at key structural levels (supply/demand zones) formed by pivot-based support and resistance. It combines zone detection, price action confirmation (wick rejection), momentum filtering, and trend alignment to generate deterministic execution signals.

---

## 2. Core Logic

### 2.1 Zone Detection (Supply & Demand)

```
Support Zone (Demand) = Pivot Low ± 0.5 × ATR(20)
Resistance Zone (Supply) = Pivot High ± 0.5 × ATR(20)
```

- Uses 12-bar lookback/lookforward for pivot detection
- Zones decay over time (800-bar decay factor for crypto)
- Overlapping zones within 0.3 × ATR are merged dynamically

### 2.2 Canonical Setup Types

| Setup | Description | Signal Weight |
|-------|-------------|---------------|
| **Zone Reject** | Price taps zone, wick rejects, closes away | Primary |
| **Flip Retest** | Old resistance becomes support (or vice versa) | High |
| **Sweep & Reclaim** | Liquidity sweep beyond level, reclaim within 3 bars | High |
| **BOS Retest** | Break of Structure, then retest of broken level | Medium |
| **Displacement Retest** | Impulsive move creates FVG, then retest | Medium |

### 2.3 Quality Scoring (0-100)

Every valid setup receives a composite score:
- **Base Score:** 50 points for meeting minimum criteria
- **Volume Surge:** +15 points if volume > 1.5× SMA(20)
- **Wick Quality:** +10 points if rejection wick > 0.3 × ATR
- **Trend Alignment:** +10 points if price > EMA(50) for Longs
- **Zone Tier:** +5/+10 points for Strong/Elite zone classification

> **Minimum score required for execution:** **50**

---

## 3. Entry Conditions

For an order to be submitted, **ALL** of the following must be true simultaneously at bar close:

| # | Check | Condition |
|---|-------|-----------|
| 1 | **Zone Interaction** | Price is within a valid, active supply/demand zone |
| 2 | **Price Action** | Bar shows wick rejection (wick > 50% of body AND wick > 0.15 × ATR) |
| 3 | **Trend Alignment** | Close is above EMA(50) for Longs, below for Shorts |
| 4 | **Volume Check** | Volume is above 80% of 20-period SMA |
| 5 | **Score Check** | Calculated quality score is ≥ 50 |
| 6 | **Risk Distance** | Distance from Entry to SL is < 2.5 × ATR |
| 7 | **Position Limit** | No existing open position on the same symbol for this slot |
| 8 | **Daily Limit** | Maximum 4 trades per day per slot not exceeded |
| 9 | **Circuit Breaker** | Slot is not in a paused or frozen state |

---

## 4. Exit Rules

The system employs a predefined **3-Stage Fractional Exit Model**:

### 4.1 Stop Loss

Stop losses are **structural**, placed beyond the zone extreme plus a volatility buffer:

```
LONG SL = Zone Bottom − 0.5 × ATR(20)
SHORT SL = Zone Top + 0.5 × ATR(20)
```

### 4.2 Take Profit (Scale-Out)

| Stage | Target | Position % | Action |
|-------|--------|------------|--------|
| **TP1** | Entry + 1.5 R | 33% | Book partial profit, move SL to Breakeven |
| **TP2** | Entry + 3.0 R | 33% | Book partial profit, remainder becomes "Runner" |
| **Runner**| Trailing Stop | 34% | Trails price by 1.5 ATR |

### 4.3 Time Stop
If a trade has been open for **60 bars** without hitting SL or TP2, the engine closes the entire remaining position at the current market price to free up capital.

---

## 5. Risk Management

### 5.1 Position Sizing

Position sizes are calculated precisely using `Decimal` arithmetic based on distance to the structural stop loss:

```
Risk Amount = Slot Equity × 0.005 (0.5%)
Position Size = ROUND_DOWN(Risk Amount / |Entry − Stop|)
```

### 5.2 Defense-in-Depth

| Layer | Trigger | Action |
|-------|---------|--------|
| **Execution** | Slippage > 0.3% | Drift Guard rejects entry |
| **Slot** | 3 consecutive losses | 30-minute cooldown pause |
| **Slot** | > 25% slot drawdown | Indefinite slot freeze (requires manual review) |
| **Portfolio** | > 15% global drawdown | Kill switch (halts all trading entirely) |

---

## 6. Timeframe Selection Rationale

The Top 10 slots were selected via composite scoring from the 55-combo backtest (15,194 trades) to achieve high **temporal diversification**:

| Category | Timeframes | Strategy | Impact on Equity Curve |
|----------|------------|----------|------------------------|
| **Scalping** | 1m, 3m | High-frequency | Rapid growth, higher volatility, many trades daily |
| **Intraday** | 10m, 15m, 30m | Medium-frequency | Smooths daily variance, captures standard sessions |
| **Swing** | 45m, 4h | Low-frequency | Captures macro trends, low stress, high win rate |

By running these simultaneously across 10 isolated slots, the portfolio achieves a much smoother aggregate equity curve than any single strategy could provide.

---

*For detailed slot allocation metrics, refer to [PORTFOLIO_OVERVIEW.md](PORTFOLIO_OVERVIEW.md).*
