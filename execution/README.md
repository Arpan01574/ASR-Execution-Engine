# Execution Engine

> **Webhook-Based Live Execution Pipeline** — FastAPI server that receives TradingView alerts and routes them through a risk-validated, state-machine-driven execution pipeline to Binance Futures.

---

## 📋 Overview

The execution engine is the **production trading infrastructure** of the ASR system. It receives signals from TradingView webhooks (or the standalone paper simulator), validates them through a multi-stage risk pipeline, and executes trades on Binance Futures Testnet with deterministic state management.

### Key Capabilities

- **Secure Webhook Receiver** — FastAPI router with HMAC + URL token authentication
- **Exactly-Once Processing** — Signal queue with idempotency keys and TTL validation
- **Risk Engine** — Position sizing (Decimal arithmetic), drift guard, drawdown limits
- **Order FSM** — Deterministic state machine: `NEW → VALIDATING → RISK_CHECK → SUBMITTING → FILLED`
- **Position FSM** — `FLAT → OPENING → OPEN → REDUCING → CLOSING → CLOSED`
- **Broker Abstraction** — Switchable between PaperBroker (simulation) and BinanceAdapter (live)
- **Paper Simulator** — Historical replay engine for validating the full pipeline

---

## 📂 Directory Structure

```text
execution/
├── README.md                      ← You are here
├── .env                           ← Environment config (gitignored)
├── .env.example                   ← Environment template
├── paper_sim.py                   ← Standalone paper trading simulator
│
├── src/
│   ├── __init__.py
│   ├── main.py                    ← FastAPI application entry point
│   ├── config.py                  ← Centralized settings (pydantic-settings)
│   ├── database.py                ← SQLite schema (signals, orders, fills, positions)
│   │
│   ├── webhook/                   ← TradingView webhook handler
│   │   ├── __init__.py
│   │   ├── router.py              ← FastAPI route for /webhook/{token}
│   │   └── security.py            ← HMAC signature + passphrase validation
│   │
│   ├── queue/                     ← Async signal queue
│   │   ├── __init__.py
│   │   ├── signal_queue.py        ← Idempotent enqueue with DB deduplication
│   │   └── processor.py           ← Background consumer processing signals
│   │
│   ├── risk/                      ← Risk management
│   │   ├── __init__.py
│   │   ├── engine.py              ← Risk validation pipeline
│   │   ├── sizing.py              ← Decimal-based position sizing
│   │   └── drift_guard.py         ← Entry price drift validation
│   │
│   ├── execution/                 ← Order execution
│   │   ├── __init__.py
│   │   ├── engine.py              ← Execution engine (orchestrator)
│   │   ├── order_fsm.py           ← Order state machine
│   │   └── position_fsm.py        ← Position state machine
│   │
│   ├── brokers/                   ← Exchange adapters
│   │   ├── __init__.py
│   │   ├── base.py                ← Abstract BrokerAdapter interface
│   │   ├── paper.py               ← Paper trading broker (simulated fills)
│   │   └── binance.py             ← Binance Futures Testnet adapter (ccxt)
│   │
│   ├── models/                    ← Data models
│   │   ├── __init__.py
│   │   ├── enums.py               ← OrderSide, OrderType, TradingMode, etc.
│   │   ├── signals.py             ← Signal payload models (Pydantic)
│   │   └── instruments.py         ← Instrument specifications
│   │
│   └── monitoring/                ← Health & reporting
│       ├── __init__.py
│       ├── reconciliation_report.py ← Position reconciliation
│       └── release_report.py      ← Deployment readiness reports
│
├── data/                          ← Runtime databases (gitignored)
│   ├── asr_engine.db              ← Production database
│   └── asr_demo_trading.db        ← Demo/testnet database
│
├── paper_sim_results/             ← Paper simulation output
│
└── tests/
    └── test_integration.py        ← End-to-end integration tests
```

---

## 🚀 Usage

### Start the Webhook Server

```bash
# From the project root
python -m execution.src.main

# Or with uvicorn directly
uvicorn execution.src.main:app --host 0.0.0.0 --port 8000 --reload
```

The server will:
1. Initialize the SQLite database schema
2. Connect to the configured broker (Paper or Binance Testnet)
3. Start the background signal processor
4. Listen for webhooks at `POST /webhook/{token}`

### Health Check

```bash
curl http://localhost:8000/health
# → {"status": "healthy", "mode": "DEMO"}
```

### Run Paper Trading Simulation

```bash
# From the project root
python execution/paper_sim.py --symbol "BTC/USDT" --timeframe "4h"
```

---

## 🏗️ Architecture

### Signal Processing Pipeline

```
TradingView Alert
        │
        ▼
┌─────────────────────┐
│   Webhook Router     │ ← HMAC + URL token validation
│   POST /webhook/{t}  │
└─────────┬───────────┘
          │ SignalPayload (JSON)
          ▼
┌─────────────────────┐
│   Signal Queue       │ ← Idempotency check (signal_id dedup)
│   (SQLite-backed)    │   TTL validation (reject stale signals)
└─────────┬───────────┘
          │ Validated Signal
          ▼
┌─────────────────────┐
│   Risk Engine        │ ← Position sizing (Decimal arithmetic)
│                      │   Drift guard (|current - signal| < 0.3%)
│                      │   Drawdown check (< 15% portfolio)
│                      │   Position limits (max 10 global)
└─────────┬───────────┘
          │ Approved Order
          ▼
┌─────────────────────┐
│   Execution Engine   │ ← Order FSM transition
│                      │   Broker API call
│                      │   Fill confirmation
│                      │   Position FSM update
└─────────┬───────────┘
          │ Fill
          ▼
┌─────────────────────┐
│   Broker Adapter     │ ← PaperBroker (simulated)
│   (Paper / Binance)  │   BinanceAdapter (testnet via ccxt)
└─────────────────────┘
```

### State Machines

**Order FSM:**
```
NEW → VALIDATING → RISK_CHECK → SUBMITTING → ACKNOWLEDGED → FILLED
                                      ↓
                                   REJECTED (at any stage)
```

**Position FSM:**
```
FLAT → OPENING → OPEN → REDUCING → CLOSING → CLOSED
```

---

## ⚙️ Configuration

### Environment Variables (`.env`)

```env
# System Mode
TRADING_MODE=DEMO                    # DEMO | LIVE

# Binance Credentials
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_USE_TESTNET=true

# Webhook Security
WEBHOOK_URL_TOKEN=your_token         # URL path token
WEBHOOK_PASSPHRASE=your_passphrase   # Payload passphrase

# Database
DATABASE_URL=sqlite:///./execution/data/asr_demo_trading.db

# Risk Parameters
RISK_PER_TRADE_PCT=0.5               # % of slot equity
MAX_GLOBAL_DRAWDOWN_PCT=15.0         # Portfolio kill switch
MAX_SLIPPAGE_PCT=0.3                 # Drift guard tolerance
```

### TradingView Webhook Payload Format

```json
{
  "signal_id": "unique-signal-uuid",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "entry_price": 65000.00,
  "stop_loss": 64200.00,
  "take_profit_1": 66200.00,
  "take_profit_2": 67400.00,
  "score": 62.5,
  "setup_type": "ZONE_REJECT",
  "timeframe": "4h",
  "timestamp": "2026-10-03T14:00:00Z",
  "passphrase": "your_passphrase"
}
```

---

## 🛡️ Risk Controls

| Control | Implementation | File |
|---------|---------------|------|
| Position Sizing | `Decimal` arithmetic, `ROUND_DOWN`, min notional check | `src/risk/sizing.py` |
| Drift Guard | `\|current - signal\| / signal × 100 < 0.3%` | `src/risk/drift_guard.py` |
| Drawdown Limit | Portfolio DD > 15% → global kill switch | `src/risk/engine.py` |
| Signal Dedup | `signal_id` idempotency key in SQLite | `src/queue/signal_queue.py` |
| TTL Validation | Reject signals older than `2 × timeframe_bars` | `src/queue/signal_queue.py` |
| Order FSM | No state skipping, all transitions logged | `src/execution/order_fsm.py` |

---

## 🧪 Testing

```bash
# Run integration tests
pytest execution/tests/test_integration.py -v
```

### Paper Simulation Results (75 Trades)

| Metric | Value |
|--------|-------|
| Win Rate | 62.3% |
| Expectancy | +8.11 R |
| Profit Factor | 22.25 |
| Max Drawdown | 1.64% |
| Avg Latency | 17.03 ms |

---

## 🔗 Related Documentation

- [Strategy Specification](../docs/strategy_spec.md) — Trading rules (single source of truth)
- [Paper Execution Evidence](../evidence/03_Paper_Trading/Paper_Execution_Quality.md) — Simulation results
- [Demo Testnet Evidence](../evidence/04_Demo_Testnet/Demo_Lifecycle_and_Reconciliation.md) — Testnet validation
- [Failure Injection](../evidence/05_Operations/Failure_Injection_and_Incidents.md) — Fault tolerance testing
