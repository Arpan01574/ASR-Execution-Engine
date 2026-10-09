# ASR Engine v3 — Live Demo Trading Strategy Guide

## 📋 Table of Contents
- [Strategy Overview](#strategy-overview)
- [Core Logic](#core-logic)
- [Entry Conditions](#entry-conditions)
- [Exit Rules](#exit-rules)
- [Risk Management](#risk-management)
- [Portfolio Allocation](#portfolio-allocation)
- [Timeframe Selection Rationale](#timeframe-selection-rationale)

---

## Strategy Overview

**Name:** ASR Engine v3 (Advanced Support & Resistance)  
**Type:** Structural Price Action Trading  
**Markets:** Crypto Perpetual Futures (Binance USDⓈ-M)  
**Direction:** Long and Short  
**Holding Period:** Intrabar (1m scalps) to multi-day (4h swings)  

The ASR Engine identifies high-probability trade setups at key structural levels (supply/demand zones) formed by pivot-based support and resistance. It combines zone detection, price action confirmation (wick rejection), momentum filtering, and trend alignment to generate signals.

---

## Core Logic

### 1. Zone Detection (Supply & Demand)
```
Support Zone = Pivot Low ± 0.5 × ATR(20)
Resistance Zone = Pivot High ± 0.5 × ATR(20)
```
- Uses 12-bar lookback/lookforward for pivot detection
- Zones decay over time (800-bar decay factor for crypto)
- Zones are merged when overlapping within 0.3 × ATR

### 2. Setup Types (5 Canonical)
| Setup | Description | Weight |
|-------|-------------|--------|
| Zone Reject | Price taps zone, wick rejects, closes away | Primary |
| Flip Retest | Old resistance becomes support (or vice versa) | High |
| Sweep & Reclaim | Liquidity sweep beyond level, reclaim within 3 bars | High |
| BOS Retest | Break of Structure, then retest of broken level | Medium |
| Displacement Retest | Impulsive move creates FVG, then retest | Medium |

### 3. Quality Scoring (0-100)
Each setup receives a composite score:
- **Base:** 50 points for meeting minimum criteria
- **Volume Surge:** +15 if volume > 1.5× SMA(20)
- **Wick Quality:** +10 if rejection wick > 0.3 × ATR
- **Trend Alignment:** +10 if price > EMA(50) for longs / < EMA(50) for shorts
- **Zone Tier:** +5/+10 for Strong/Elite zone classification

Minimum score for entry: **50**

---

## Entry Conditions

All of these must be TRUE simultaneously:

1. ✅ Price is within a valid supply/demand zone
2. ✅ Bar shows wick rejection (wick > 50% of body AND wick > 0.15 × ATR)
3. ✅ Trend alignment (close above/below EMA50)
4. ✅ Volume above 80% of 20-period SMA
5. ✅ Risk distance (entry to SL) < 2.5 × ATR
6. ✅ Score ≥ 50
7. ✅ No existing position on the same symbol
8. ✅ Daily trade limit not exceeded (max 4/day/slot)
9. ✅ Slot not paused (circuit breaker not triggered)

---

## Exit Rules

### Stop Loss
```
LONG:  SL = Zone Bottom − 0.5 × ATR
SHORT: SL = Zone Top + 0.5 × ATR
```

### Take Profit (3-Stage)
| Stage | Target | Position % | 
|-------|--------|------------|
| TP1 | Entry + 1.5R | 33% scale-out |
| TP2 | Entry + 3.0R | 33% scale-out |
| Trail | 1.5 ATR trailing stop | 34% remainder |

### Time Stop
- Maximum hold: 60 bars (configurable)
- Exit at market if no TP hit within time limit

---

## Risk Management

### Position Sizing
```
Risk per trade = 0.5% of slot equity
Position size = Risk Amount / |Entry − Stop|
```
- Uses `Decimal` arithmetic to prevent rounding up
- Always rounds DOWN to lot size
- Checks minimum notional and minimum quantity

### Circuit Breakers
| Trigger | Action |
|---------|--------|
| 3 consecutive losses | Pause slot for 30 minutes |
| Slot drawdown > 25% | Pause slot indefinitely |
| Portfolio drawdown > 15% | Global kill switch — all trading stops |
| Single trade > 3% loss | Flag for review |

### Position Limits
- Max 1 concurrent position per slot
- Max 10 concurrent positions globally
- Max 4 trades per day per slot

---

## Portfolio Allocation

### Capital Structure
| Pool | Amount | Slots | Per-Slot |
|------|--------|-------|----------|
| USDT | $5,000 | 1-5 | $1,000 |
| USDC | $5,000 | 6-10 | $1,000 |
| **Total** | **$10,000** | **10** | **$1,000** |

### Slot Assignments

#### USDT-Margined (Slots 1-5)
| Slot | Asset | TF | Score | Expectancy | PF |
|------|-------|----|-------|------------|-----|
| 1 | BNB/USDT | 1m | 70.5 | 2.73R | 9.94 |
| 2 | SOL/USDT | 3m | 63.3 | 1.14R | 13.35 |
| 3 | XRP/USDT | 1m | 59.9 | 1.27R | 11.67 |
| 4 | ETH/USDT | 45m | 59.5 | 0.64R | 10.26 |
| 5 | BNB/USDT | 4h | 56.9 | 0.83R | 9.77 |

#### USDC-Margined (Slots 6-10)
| Slot | Asset | TF | Score | Expectancy | PF |
|------|-------|----|-------|------------|-----|
| 6 | SOL/USDT | 15m | 56.1 | 0.59R | 8.45 |
| 7 | XRP/USDT | 45m | 55.2 | 0.52R | 9.15 |
| 8 | XRP/USDT | 30m | 53.2 | 0.52R | 8.01 |
| 9 | ETH/USDT | 4h | 52.6 | 0.73R | 9.63 |
| 10 | ETH/USDT | 1m | 51.8 | 1.01R | 9.25 |

---

## Timeframe Selection Rationale

The top 10 were selected by **composite scoring** across 5 metrics from a 55-combination backtest (5 symbols × 11 timeframes, 15,194 total trades):

```
Composite = 0.30 × Expectancy_norm + 
            0.25 × ProfitFactor_norm + 
            0.20 × Sharpe_norm + 
            0.15 × WinRate_norm + 
            0.10 × TradeVolume_norm
```

### TF Distribution in Top 10
- **1m:** 3 slots (BNB, XRP, ETH) — high-frequency scalping
- **3m:** 1 slot (SOL) — micro-swing
- **15m:** 1 slot (SOL) — intraday swing
- **30m:** 1 slot (XRP) — medium swing
- **45m:** 2 slots (ETH, XRP) — swing
- **4h:** 2 slots (BNB, ETH) — position/swing

This gives excellent **temporal diversification**: some slots trade many times per day (1m), while others trade a few times per week (4h), smoothing the equity curve.

### Symbol Distribution
- **ETH:** 3 slots (1m, 45m, 4h) — multi-TF coverage
- **XRP:** 3 slots (1m, 30m, 45m) — multi-TF coverage
- **BNB:** 2 slots (1m, 4h) — polar extremes
- **SOL:** 2 slots (3m, 15m) — fast/medium

---

## Expected Performance (from Backtest)

| Metric | Portfolio Estimate |
|--------|-------------------|
| Avg Expectancy | ~1.0 R per trade |
| Avg Profit Factor | ~9.9 |
| Avg Win Rate | ~60.6% |
| Estimated Monthly Trades | ~200-400 |
| Risk of Ruin (10K base) | 0.00% |
| Target Monthly Return | +5-15% |

> ⚠️ **Disclaimer:** Past backtest performance does not guarantee future results. Demo trading is for validation purposes. Always start with small capital and validate on testnet before committing real funds.
