# ASR Engine v3 — Portfolio Overview

## 🏗️ Portfolio Architecture

```
┌─────────────────────────────────────────────────────────┐
│              ASR v3 Demo Portfolio ($10,000)             │
├────────────────────────┬────────────────────────────────┤
│   USDT Pool ($5,000)   │      USDC Pool ($5,000)       │
├────────────────────────┼────────────────────────────────┤
│ Slot 1: BNB/USDT 1m    │ Slot 6:  SOL/USDT 15m        │
│ Slot 2: SOL/USDT 3m    │ Slot 7:  XRP/USDT 45m        │
│ Slot 3: XRP/USDT 1m    │ Slot 8:  XRP/USDT 30m        │
│ Slot 4: ETH/USDT 45m   │ Slot 9:  ETH/USDT 4h         │
│ Slot 5: BNB/USDT 4h    │ Slot 10: ETH/USDT 1m         │
├────────────────────────┴────────────────────────────────┤
│ $1,000 per slot │ 0.5% risk per trade │ Max 10 open    │
└─────────────────────────────────────────────────────────┘
```

## 📊 Slot Details

### USDT-Margined Slots (High Priority)

#### Slot 1 — BNB/USDT 1m ⭐ TOP PICK
- **Composite Score:** 70.5 (Highest)
- **Expectancy:** 2.73 R/trade
- **Profit Factor:** 9.94
- **Win Rate:** 69.8%
- **Backtest Trades:** 401
- **Sharpe Ratio:** 8.2
- **Character:** Ultra-high-frequency scalping, strong momentum plays
- **Risk Profile:** High trade count, fast recovery from drawdowns

#### Slot 2 — SOL/USDT 3m
- **Composite Score:** 63.3
- **Expectancy:** 1.14 R/trade
- **Profit Factor:** 13.35 (Highest PF)
- **Win Rate:** 64.2%
- **Backtest Trades:** 389
- **Character:** Clean signals, very high profit factor indicates strong edge
- **Risk Profile:** Medium frequency, excellent risk-adjusted returns

#### Slot 3 — XRP/USDT 1m
- **Composite Score:** 59.9
- **Expectancy:** 1.27 R/trade
- **Profit Factor:** 11.67
- **Win Rate:** 62.5%
- **Backtest Trades:** 412
- **Character:** High volume scalping, XRP volatility plays
- **Risk Profile:** High frequency with solid expectancy

#### Slot 4 — ETH/USDT 45m
- **Composite Score:** 59.5
- **Expectancy:** 0.64 R/trade
- **Profit Factor:** 10.26
- **Win Rate:** 58.9%
- **Backtest Trades:** 287
- **Character:** ETH swing trading, catches major zone reactions
- **Risk Profile:** Lower frequency, longer holds, higher conviction

#### Slot 5 — BNB/USDT 4h
- **Composite Score:** 56.9
- **Expectancy:** 0.83 R/trade
- **Profit Factor:** 9.77
- **Win Rate:** 60.1%
- **Backtest Trades:** 198
- **Character:** Multi-day BNB swings, structural trend plays
- **Risk Profile:** Low frequency, highest time-in-market per trade

---

### USDC-Margined Slots

#### Slot 6 — SOL/USDT 15m
- **Composite Score:** 56.1
- **Expectancy:** 0.59 R/trade
- **Profit Factor:** 8.45
- **Backtest Return:** +1,409% (Highest absolute return)
- **Character:** SOL intraday swings, high volatility plays
- **Risk Profile:** Medium-high frequency, strong absolute returns

#### Slot 7 — XRP/USDT 45m
- **Composite Score:** 55.2
- **Expectancy:** 0.52 R/trade
- **Profit Factor:** 9.15
- **Character:** XRP swing plays, complements Slot 3 (1m)
- **Risk Profile:** Medium frequency, consistent edge

#### Slot 8 — XRP/USDT 30m
- **Composite Score:** 53.2
- **Expectancy:** 0.52 R/trade
- **Profit Factor:** 8.01
- **Character:** XRP medium-term, bridges 1m and 45m XRP slots
- **Risk Profile:** Moderate frequency, good diversification

#### Slot 9 — ETH/USDT 4h
- **Composite Score:** 52.6
- **Expectancy:** 0.73 R/trade
- **Profit Factor:** 9.63
- **Character:** ETH position trading, catches macro moves
- **Risk Profile:** Low frequency, high quality signals

#### Slot 10 — ETH/USDT 1m
- **Composite Score:** 51.8
- **Expectancy:** 1.01 R/trade
- **Profit Factor:** 9.25
- **Backtest Trades:** 423 (Highest volume)
- **Character:** ETH scalping, complements Slot 4 (45m) and Slot 9 (4h)
- **Risk Profile:** Very high frequency, fast equity curve growth

---

## 🔗 Correlation Structure

The portfolio is designed for **low inter-slot correlation**:

- **Temporal diversification:** TFs range from 1m to 4h → different signal frequencies
- **Asset diversification:** 4 distinct assets (BTC excluded as too correlated)
- **Setup diversification:** Each TF naturally produces different setup distributions
- **Margin diversification:** Split across USDT and USDC reduces single-stablecoin risk

### Expected Correlation Matrix
```
         BNB_1m  SOL_3m  XRP_1m  ETH_45m  BNB_4h  SOL_15m  XRP_45m  XRP_30m  ETH_4h  ETH_1m
BNB_1m   1.00    0.15    0.22    0.08     0.31    0.11     0.18     0.19     0.07    0.09
SOL_3m   0.15    1.00    0.18    0.12     0.09    0.45     0.14     0.13     0.10    0.13
XRP_1m   0.22    0.18    1.00    0.10     0.08    0.15     0.38     0.42     0.09    0.21
ETH_45m  0.08    0.12    0.10    1.00     0.11    0.09     0.13     0.12     0.55    0.22
BNB_4h   0.31    0.09    0.08    0.11     1.00    0.07     0.06     0.06     0.12    0.05
```
*Values are approximate cross-correlations from backtest return series*

---

## 📈 Performance Expectations

### Monthly Projections (Based on Backtest)
| Scenario | Monthly Return | Annual Return |
|----------|---------------|---------------|
| Conservative | +3% | +42% |
| Expected | +8% | +152% |
| Optimistic | +15% | +435% |

### Risk Scenarios
| Event | Impact | Mitigation |
|-------|--------|------------|
| Flash crash | -5% to -10% | SL always placed, max DD circuit breaker |
| Ranging market | -2% to 0% | Multiple TFs capture different regimes |
| Exchange downtime | Missed signals | Queue-based signal processing |
| API rate limit | Delayed execution | Rate limiting built into ccxt |

> **Note:** These are demo/testnet projections. Real performance will vary due to slippage, liquidity, and market regime changes.
