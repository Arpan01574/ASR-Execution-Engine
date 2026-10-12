# ASR Engine v3 — Portfolio Overview

> **Portfolio Architecture** — Detailed breakdown of the $10,000 live demo portfolio, encompassing 10 isolated slots selected from 55 backtested combinations.

---

## 🏗️ Portfolio Architecture

The portfolio is structured to maximize diversification across assets, timeframes, and margin types, minimizing the risk of systemic failure.

```
┌─────────────────────────────────────────────────────────┐
│              ASR v3 Demo Portfolio ($10,000)            │
├────────────────────────┬────────────────────────────────┤
│   USDT Pool ($5,000)   │      USDC Pool ($5,000)        │
├────────────────────────┼────────────────────────────────┤
│ Slot 1: BNB/USDT 1m    │ Slot 6:  SOL/USDT 15m          │
│ Slot 2: SOL/USDT 3m    │ Slot 7:  XRP/USDT 45m          │
│ Slot 3: XRP/USDT 1m    │ Slot 8:  XRP/USDT 30m          │
│ Slot 4: ETH/USDT 45m   │ Slot 9:  ETH/USDT 4h           │
│ Slot 5: BNB/USDT 4h    │ Slot 10: ETH/USDT 1m           │
├────────────────────────┴────────────────────────────────┤
│ $1,000 per slot │ 0.5% risk per trade │ Max 10 open     │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Detailed Slot Breakdown

### USDT-Margined Slots (High Priority)

| Slot | Setup | Score | Expectancy | PF | Win Rate | Strategy Character |
|------|-------|-------|------------|----|----------|-------------------|
| **1** | **BNB/USDT 1m** ⭐ | 70.5 | 2.73 R | 9.94 | 69.8% | Ultra-high-frequency scalping. Fast recovery from DD. |
| **2** | **SOL/USDT 3m** | 63.3 | 1.14 R | 13.35 | 64.2% | Extremely clean signals. Highest profit factor. |
| **3** | **XRP/USDT 1m** | 59.9 | 1.27 R | 11.67 | 62.5% | High volume volatility scalping. |
| **4** | **ETH/USDT 45m** | 59.5 | 0.64 R | 10.26 | 58.9% | Balanced swing trading. Medium frequency. |
| **5** | **BNB/USDT 4h** | 56.9 | 0.83 R | 9.77 | 60.1% | Multi-day structural swings. High conviction. |

### USDC-Margined Slots

| Slot | Setup | Score | Expectancy | PF | Win Rate | Strategy Character |
|------|-------|-------|------------|----|----------|-------------------|
| **6** | **SOL/USDT 15m** | 56.1 | 0.59 R | 8.45 | 57.3% | Intraday swings. Highest absolute return (+1,409%). |
| **7** | **XRP/USDT 45m** | 55.2 | 0.52 R | 9.15 | 56.8% | Medium-term XRP swings. Complements Slot 3. |
| **8** | **XRP/USDT 30m** | 53.2 | 0.52 R | 8.01 | 55.4% | Bridges the gap between 1m and 45m. |
| **9** | **ETH/USDT 4h** | 52.6 | 0.73 R | 9.63 | 59.2% | Macro position trading. Very low frequency. |
| **10**| **ETH/USDT 1m** | 51.8 | 1.01 R | 9.25 | 61.7% | High trade volume. Fast equity curve growth. |

---

## 🔗 Correlation Structure

The portfolio is designed for **low inter-slot correlation**, acting as a shock absorber against adverse market regimes:

1. **Temporal Diversification:** Timeframes range from 1m to 4h, capturing entirely different market cycles.
2. **Asset Diversification:** 4 distinct altcoins (BTC was excluded from the Top 10 due to high correlation dragging down portfolio Sharpe).
3. **Margin Diversification:** A 50/50 split between USDT and USDC reduces systemic risk if a stablecoin depegs.

### Expected Correlation Matrix (From Backtest)

```text
         BNB_1m  SOL_3m  XRP_1m  ETH_45m  BNB_4h  SOL_15m
BNB_1m   1.00    0.15    0.22    0.08     0.31    0.11
SOL_3m   0.15    1.00    0.18    0.12     0.09    0.45
XRP_1m   0.22    0.18    1.00    0.10     0.08    0.15
ETH_45m  0.08    0.12    0.10    1.00     0.11    0.09
BNB_4h   0.31    0.09    0.08    0.11     1.00    0.07
SOL_15m  0.11    0.45    0.15    0.09     0.07    1.00
```
> *Values are approximate cross-correlations derived from backtest return series. Scores < 0.30 indicate excellent diversification.*

---

## 📈 Performance Expectations

> ⚠️ **Disclaimer:** These metrics represent backtested estimates. Live execution will experience variance due to slippage and market conditions.

### Estimated Output

| Metric | Portfolio Estimate |
|--------|-------------------|
| **Average Expectancy** | ~1.0 R per trade |
| **Average Profit Factor**| ~9.9 |
| **Average Win Rate** | ~60.6% |
| **Estimated Trades** | 200–400 per month |
| **Risk of Ruin** | 0.00% (at 0.5% risk) |
| **Target Monthly Return**| +5% to +15% |

### Risk Scenarios & Mitigations

| Market Event | Expected Impact | Mitigation Strategy |
|--------------|----------------|---------------------|
| **Flash Crash** | -5% to -10% | Hard structural SL always placed; max DD circuit breaker |
| **Tight Range** | -2% to 0% | Multi-TF structure means only scalping slots trigger |
| **API Rate Limits** | Delayed fills | Automatic backoff in `ccxt`; async queue handling |
| **Stablecoin Depeg** | -50% (worst case) | Capital split 50/50 between USDT and USDC |
