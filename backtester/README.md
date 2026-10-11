# Backtester Module

> **Canonical Python Backtesting Engine** — Faithful port of the ASR Pine Script v6 indicator with a conservative execution model, walk-forward optimization, and Monte Carlo validation.

---

## 📋 Overview

The backtester module is the **research foundation** of the ASR Execution Engine. It implements the identical zone detection, signal scoring, and trade management logic as the TradingView Pine Script indicator, but in Python — enabling large-scale backtesting across multiple assets and timeframes with statistical rigor.

### Key Capabilities

- **Canonical ASR Engine** — 1,900+ line Python implementation guaranteeing parity with Pine Script
- **55-Combination Portfolio** — Automated backtesting across 5 assets × 11 timeframes
- **No-Lookahead Guarantee** — Pivot confirmation delay, confirmed bars only, conservative same-bar fills
- **Walk-Forward Optimization** — Grid search on training set, validated on holdout data
- **Monte Carlo Simulation** — 10,000 runs for risk-of-ruin estimation
- **Random-Entry Control** — Baseline comparison to confirm the strategy edge is real
- **Institutional Gap Analysis** — MAE/MFE, slippage sensitivity, correlation matrix, VaR/CVaR

---

## 📂 Directory Structure

```text
backtester/
├── README.md                      ← You are here
├── __init__.py                    ← Package init
│
├── asr_engine.py                  ← Core ASR Engine (canonical Python port)
├── data_engine.py                 ← OHLCV data downloader (ccxt + CSV cache)
├── config.yaml                    ← All engine parameters (mirrors Pine Script inputs)
│
├── run_complete_portfolio.py      ← 55-combo portfolio runner (main entry point)
├── run_backtest.py                ← Single-combination backtest runner
├── run_full_backtest.py           ← Extended backtest with WF + Monte Carlo
├── run_all_cache.py               ← Pre-cache OHLCV data for all combinations
│
├── charts.py                      ← Chart generation (equity curves, etc.)
├── portfolio_charts_extra.py      ← Extra portfolio-level charts
├── regenerate_charts.py           ← Chart regeneration without re-running backtests
├── reporting.py                   ← Report generation (markdown, JSON)
├── gap_analysis.py                ← Institutional-grade gap analysis
├── parity_test.py                 ← Pine/Python signal parity validator
├── replay.py                      ← Historical signal replay engine
│
├── resample_to_10m.py             ← 10-minute timeframe resampler
├── resample_to_45m.py             ← 45-minute timeframe resampler
│
├── data_cache/                    ← Cached OHLCV CSVs (gitignored)
│   └── {SYMBOL}_{TF}.csv         ← e.g., BTC_USDT_15m.csv
│
└── results/portfolio/             ← Generated backtest output
    ├── aggregate/                 ← Portfolio-level reports & charts
    │   ├── PORTFOLIO_REPORT.md    ← Full 55-combo breakdown
    │   ├── TOP_10_DEMO_PICKS.md   ← Top 10 selection for live trading
    │   └── charts/                ← Portfolio visualizations
    └── {SYMBOL}/                  ← Per-symbol results
        └── {TF}/                  ← Per-timeframe results
            ├── summary.txt        ← Performance summary
            └── *.png              ← Equity curve charts
```

---

## 🚀 Usage

### Run the Full Portfolio Backtest (55 Combinations)

```bash
# From the project root
python -m backtester.run_complete_portfolio
```

This will:
1. Download/cache OHLCV data for all 5 assets × 11 timeframes via ccxt (Binance)
2. Run the ASR Engine on each combination with the parameters from `config.yaml`
3. Generate per-combination performance summaries
4. Produce portfolio-level aggregate statistics
5. Create equity curve charts and heatmaps
6. Output the full report to `results/portfolio/aggregate/PORTFOLIO_REPORT.md`

### Run a Single Backtest

```bash
python -m backtester.run_backtest
```

### Pre-Cache All Data

```bash
python -m backtester.run_all_cache
```

### Regenerate Charts Only (No Recomputation)

```bash
python -m backtester.regenerate_charts
```

---

## ⚙️ Configuration

All parameters are defined in [`config.yaml`](config.yaml) and mirror the Pine Script inputs:

| Section | Key Parameters | Description |
|---------|---------------|-------------|
| `core` | `lookback_limit`, `use_htf`, `htf_timeframe` | General engine settings |
| `pivots` | `piv_l`, `piv_r`, `n_piv`, `zone_mult` | Pivot detection & zone width |
| `zone_quality` | `decay_factor`, `merge_overlap`, `min_zone_duration` | Zone lifecycle |
| `signal` | `min_score`, `min_wick`, `cooldown_bars`, `trend_mode` | Entry conditions |
| `risk` | `sl_buffer_atr`, `tp1_r`, `tp2_r`, `time_stop_bars` | Risk parameters |
| `backtest` | `initial_capital`, `risk_per_trade_pct` | Capital & sizing |
| `walk_forward` | `train_ratio`, `param_grid` | Optimization settings |
| `monte_carlo` | `n_simulations`, `risk_per_trade` | Simulation settings |
| `acceptance` | `min_trades`, `min_expectancy_r`, `max_dd_r` | Pass/fail thresholds |

---

## 🧠 Core Engine (`asr_engine.py`)

### Processing Pipeline

```
Bar-by-Bar Loop (Confirmed Bars Only)
│
├── 1. Manage Open Positions
│   ├── Check Stop Loss
│   ├── Check TP1 → Move SL to Breakeven
│   ├── Check Breakeven (same-bar trailing)
│   └── Check TP2 / Trail / Time Stop
│
├── 2. Update Zone Lifecycle
│   ├── Age all zones
│   ├── Update touch counts
│   └── Apply freshness decay
│
├── 3. Combine / Merge Zones
│   └── Merge overlapping zones within 0.3 × ATR
│
├── 4. Scan for New Entry Signals
│   ├── Zone rejection detection
│   ├── Wick quality validation
│   ├── Trend + regime gating
│   └── Score calculation (0-100)
│
└── 5. Execute Entries at Bar Close
    └── Record entry price, SL, TP1, TP2
```

### Conservative Same-Bar Model

When SL and TP are both hit within the same candle:

1. **Entry bar:** Assume SL was hit first → record as 1R loss
2. **Open position:** Check SL → TP1 (move SL to BE) → check BE → TP2
3. This prevents optimistic bias from OHLC-only data

### Signal Scoring (0-100)

| Component | Max Points | Factors |
|-----------|-----------|---------|
| Zone Quality | 35 | Displacement, touches, reaction, HTF/MTF/PDW, volume, freshness |
| Setup Score | 35 | Base type (Reject/Flip/Sweep/BOS/Disp), wick quality, break displacement |
| Context Score | 30 | Trend alignment, volatility regime, structure state, volume confirmation |

---

## 📊 Results Summary

> Full report: [`results/portfolio/aggregate/PORTFOLIO_REPORT.md`](results/portfolio/aggregate/PORTFOLIO_REPORT.md)

| Metric | Value |
|--------|-------|
| Total Trades | 15,194 |
| Total Return | +169.27% |
| Expectancy | +0.57 R/trade |
| Profit Factor | 6.33 |
| Profitable Combos | 54 / 55 (98.2%) |
| Risk of Ruin | 0.0000% |
| Edge vs Random | +0.45 R |

---

## 🔗 Related Documentation

- [Strategy Specification](../docs/strategy_spec.md) — Single source of truth for all trading rules
- [Canonical Specification](../docs/canonical_spec.md) — Zone lifecycle, scoring formula
- [Test Methodology](../docs/methodology.md) — No-lookahead guarantees, statistical thresholds
- [Backtest Evidence](../evidence/01_Backtest/Backtest_Evidence.md) — Validation evidence
