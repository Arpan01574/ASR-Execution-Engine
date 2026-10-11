# Changelog

All notable changes to the ASR Execution Engine are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-10-03

### 🎉 Initial Production Release (Beta)

The first complete, end-to-end release of the ASR Execution Engine — from Pine Script indicator through canonical Python backtester to live demo auto-trading.

### Added

#### Research & Backtesting
- **Canonical ASR Engine** (`backtester/asr_engine.py`) — 1,900+ line Python port of the Pine Script v6 indicator with guaranteed no-lookahead execution model
- **55-Combination Portfolio Backtest** — 5 assets (BTC, ETH, SOL, XRP, BNB) × 11 timeframes (1m–1D), 15,194 trades over 2 years
- **Data Engine** (`backtester/data_engine.py`) — OHLCV downloader using ccxt with local CSV caching
- **Walk-Forward Optimization** — 60/20/20 train/validation/test split with grid search
- **Monte Carlo Simulation** — 10,000 runs confirming 0.0000% risk of ruin
- **Random-Entry Control** — Baseline comparison to isolate true strategy edge (+0.45 R)
- **Gap Analysis** — MAE/MFE scatter, slippage sensitivity, correlation matrix, VaR/CVaR
- **Portfolio Reporting** — Automated chart generation (equity curves, heatmaps, rankings)
- **Parity Testing Framework** (`backtester/parity_test.py`) — Pine/Python signal comparison with configurable tolerances
- **Custom Timeframe Resampling** — 10m and 45m timeframe generation from base data

#### Execution Engine
- **FastAPI Webhook Server** (`execution/src/main.py`) — Receives TradingView alerts with HMAC security
- **Signal Queue** (`execution/src/queue/`) — Async processing with exactly-once delivery and TTL validation
- **Risk Engine** (`execution/src/risk/`) — Position sizing, drift guard, drawdown limits
- **Order FSM** (`execution/src/execution/order_fsm.py`) — Deterministic state machine: NEW → VALIDATING → RISK_CHECK → SUBMITTING → FILLED
- **Position FSM** (`execution/src/execution/position_fsm.py`) — FLAT → OPENING → OPEN → REDUCING → CLOSING → CLOSED
- **Broker Adapters** — PaperBroker (simulated) and BinanceAdapter (testnet via ccxt)
- **Paper Trading Simulator** (`execution/paper_sim.py`) — Historical replay with full pipeline validation

#### Live Auto-Trading
- **Autonomous Auto-Trader** (`live_trading/auto_trader.py`) — Self-contained system generating signals from live OHLCV data
- **Portfolio Manager** — 10 independent trading slots with isolated equity tracking
- **Terminal Dashboard** — Real-time display of portfolio status, PnL, drawdown, and circuit breaker state
- **Trade Logging** — CSV trade log, JSON snapshots, JSONL equity history
- **Portfolio Allocation Config** — YAML-based slot configuration with per-slot risk parameters

#### Risk Management
- Per-trade sizing at 0.5% of slot equity with `Decimal` arithmetic
- Per-slot circuit breaker (3 consecutive losses → 30 min pause)
- Per-slot max drawdown (25% → indefinite pause)
- Portfolio kill switch (15% global drawdown)
- Execution drift guard (0.3% tolerance)
- Margin diversification (USDT + USDC pools)

#### Infrastructure
- Pine Script v6 indicator (`ASR_Engine.pine`, ~93K chars) and strategy (`ASR_Engine_Strategy.pine`, ~94K chars)
- SQLite database schema for signals, orders, fills, and positions
- GCP/VPS deployment script with systemd service
- Comprehensive `.gitignore` for data files, caches, and secrets
- `pyproject.toml` with unified dependency management

#### Documentation
- Canonical engine specification (`docs/canonical_spec.md`)
- Strategy specification (`docs/strategy_spec.md`) — single source of truth
- Test methodology (`docs/methodology.md`) — no-lookahead guarantees, statistical thresholds
- Live trading strategy guide, portfolio overview, and risk framework
- Evidence pack with 6 validation reports
- Full portfolio backtest report with 55-combination breakdown

#### Testing
- Unit tests for ASR Engine (zone creation, scoring, signal generation, trade management)
- Integration tests for execution pipeline
- Paper trading simulation (75 trades, +8.11 R expectancy)

---

## [0.1.0] — 2026-09-15

### Added
- Initial project scaffolding and module structure
- First draft of Pine Script ASR Engine indicator
- Basic Python backtester prototype
- Preliminary FastAPI webhook endpoint

---

*For earlier development history, see the Git commit log.*
