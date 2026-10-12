# ASR Engine v3 — Project Overview

> **System Summary** — A fully integrated, zero-cost systematic trading engine connecting TradingView alerts to live exchange execution with institutional-grade architecture.

---

## What Is This System?

The ASR Engine v3 is a **production-grade algorithmic trading system** that translates a visual Pine Script structural liquidity indicator into a robust Python backtester and live execution pipeline. The system is built entirely on zero-cost infrastructure (FastAPI, SQLite, Python) while implementing institutional-grade patterns:

- **Exact-once signal processing** with idempotency keys
- **Deterministic state machines** for orders and positions
- **Decimal-based position sizing** preventing rounding errors
- **Multi-layer risk management** with automatic circuit breakers

---

## System Components

| Component | Location | Description |
|-----------|----------|-------------|
| Pine Script Indicator | `pine_scripts/` | TradingView v6 indicator (~93K chars) with zone visualization |
| Pine Script Strategy | `pine_scripts/` | TradingView strategy (~94K chars) for built-in backtesting |
| Python Backtester | `backtester/` | Canonical ASR Engine port with 55-combo portfolio testing |
| Execution Engine | `execution/` | FastAPI webhook server with risk-validated order pipeline |
| Auto-Trader | `live_trading/` | Autonomous demo trading system on Binance Testnet |
| Strategy Specification | `docs/strategy_spec.md` | Single source of truth for all implementations |

---

## Headline Results

| Metric | Value |
|--------|-------|
| **Status** | READY FOR LIVE (BETA) |
| **Backtest Trades** | 15,194 across 5 symbols × 11 timeframes (2 years) |
| **Expectancy** | +0.57 R per trade |
| **Profit Factor** | 6.33 |
| **Risk of Ruin** | 0.0000% (10K Monte Carlo simulations) |
| **Edge vs Random** | +0.45 R above random baseline |
| **Paper Sim Parity** | +8.11 R vs +8.15 R backtest (99.5% match) |

---

## Key Features Validated

| Feature | Implementation | Evidence |
|---------|---------------|----------|
| Constant-time Secure Webhook Router | `execution/src/webhook/` | HMAC + URL token auth |
| Order & Position FSMs | `execution/src/execution/` | Deterministic state transitions |
| Exactly-Once Signal Queue | `execution/src/queue/` | DB-backed idempotency + TTL |
| Decimal Position Sizing | `execution/src/risk/sizing.py` | `ROUND_DOWN`, min notional check |
| Risk Engine | `execution/src/risk/engine.py` | Drawdown limits, kill switch |
| Entry Drift Guard | `execution/src/risk/drift_guard.py` | 0.3% max drift tolerance |
| Binance Testnet Adapter | `execution/src/brokers/binance.py` | Async ccxt integration |
| Paper Simulation | `execution/paper_sim.py` | 75-trade historical replay |

---

## Quick Reference

| Action | Command |
|--------|---------|
| Install dependencies | `pip install -e .` |
| Run full backtest | `python -m backtester.run_complete_portfolio` |
| Start auto-trader | `python -m live_trading.auto_trader` |
| Start webhook server | `python -m execution.src.main` |
| Run tests | `pytest tests/` |

Refer to [`README.md`](../../README.md) for full documentation.
