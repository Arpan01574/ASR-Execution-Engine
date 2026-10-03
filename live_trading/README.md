# ASR Engine v3 — Live Demo Auto-Trading System

## 🚀 Quick Start

```bash
# 1. Install dependencies (from project root)
pip install -e .

# 2. Start the auto-trader
python -m live_trading.auto_trader
```

That's it. The system will:
- Connect to Binance Testnet using your demo API keys
- Load the Top 10 portfolio allocation (10 slots × $1,000)
- Start scanning for ASR signals across all 10 asset+TF combinations
- Execute trades automatically with full risk management
- Display a real-time dashboard in your terminal
- Log all trades to `results/trade_log.csv`

---

## 📂 Directory Structure

```
live_trading/
├── README.md                              ← You are here
├── RESULTS.md                             ← Live trading results (auto-updated)
├── auto_trader.py                         ← 🔥 Main auto-trading engine
├── __init__.py                            ← Package init
│
├── config/                                ← Configuration
│   ├── __init__.py
│   └── portfolio_allocation.yaml          ← Top 10 slot allocation config
│
├── docs/                                  ← Documentation
│   ├── STRATEGY_GUIDE.md                  ← Full strategy methodology
│   ├── PORTFOLIO_OVERVIEW.md              ← Portfolio architecture & slot details
│   └── RISK_FRAMEWORK.md                  ← Multi-layer risk management
│
├── results/                               ← Trading output (auto-generated)
│   ├── trade_log.csv                      ← All trades (entries + exits)
│   ├── portfolio_snapshot.json            ← Latest portfolio state
│   ├── portfolio_history.jsonl            ← Equity curve data points
│   └── session_report.json                ← Per-session summary
│
└── logs/                                  ← Runtime logs
    └── auto_trader_YYYYMMDD_HHMMSS.log    ← Detailed execution log
```

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    PORTFOLIO MANAGER                     │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐     ┌─────────┐  │
│  │ Slot 1  │ │ Slot 2  │ │ Slot 3  │ ... │ Slot 10 │  │
│  │ BNB 1m  │ │ SOL 3m  │ │ XRP 1m  │     │ ETH 1m  │  │
│  │ $1,000  │ │ $1,000  │ │ $1,000  │     │ $1,000  │  │
│  └────┬────┘ └────┬────┘ └────┬────┘     └────┬────┘  │
│       │           │           │               │        │
│  ┌────▼───────────▼───────────▼───────────────▼────┐  │
│  │              SIGNAL GENERATOR                    │  │
│  │  Fetch OHLCV → Pivots → Zones → Wick → Score   │  │
│  └──────────────────────┬──────────────────────────┘  │
│                         │ Signals (score ≥ 50)         │
│  ┌──────────────────────▼──────────────────────────┐  │
│  │              RISK ENGINE                         │  │
│  │  Sizing → Circuit Breaker → DD Check → Drift    │  │
│  └──────────────────────┬──────────────────────────┘  │
│                         │ Approved Orders              │
│  ┌──────────────────────▼──────────────────────────┐  │
│  │          BINANCE TESTNET (ccxt)                  │  │
│  │  Market Order → SL → TP1 → Monitor → Close     │  │
│  └─────────────────────────────────────────────────┘  │
│                                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │              LOGGING & RESULTS                   │  │
│  │  trade_log.csv │ portfolio_snapshot.json │ logs  │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

---

## 📊 Portfolio Allocation

| Slot | Asset | TF | Margin | Capital | Backtest Score |
|------|-------|----|--------|---------|---------------|
| 1 | BNB/USDT | 1m | USDT | $1,000 | 70.5 ⭐ |
| 2 | SOL/USDT | 3m | USDT | $1,000 | 63.3 |
| 3 | XRP/USDT | 1m | USDT | $1,000 | 59.9 |
| 4 | ETH/USDT | 45m | USDT | $1,000 | 59.5 |
| 5 | BNB/USDT | 4h | USDT | $1,000 | 56.9 |
| 6 | SOL/USDT | 15m | USDC | $1,000 | 56.1 |
| 7 | XRP/USDT | 45m | USDC | $1,000 | 55.2 |
| 8 | XRP/USDT | 30m | USDC | $1,000 | 53.2 |
| 9 | ETH/USDT | 4h | USDC | $1,000 | 52.6 |
| 10 | ETH/USDT | 1m | USDC | $1,000 | 51.8 |

---

## ⚙️ Configuration

### Environment Variables (`.env`)
```env
TRADING_MODE=DEMO
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_USE_TESTNET=true
RISK_PER_TRADE_PCT=0.5
MAX_GLOBAL_DRAWDOWN_PCT=15.0
```

### Portfolio Config (`config/portfolio_allocation.yaml`)
- Edit slot allocations, capital per slot, risk parameters
- Add/remove slots as needed
- Modify risk rules and circuit breaker thresholds

---

## 🛡️ Risk Management

| Layer | Protection |
|-------|-----------|
| **Per-Trade** | 0.5% max risk, structural SL, max 2.5 ATR distance |
| **Per-Slot** | 3-loss circuit breaker, 25% max DD pause |
| **Portfolio** | 15% global kill switch, max 10 open positions |
| **Execution** | Drift guard (0.3%), order FSM, rate limiting |

See [docs/RISK_FRAMEWORK.md](docs/RISK_FRAMEWORK.md) for complete details.

---

## 📈 Monitoring

### Terminal Dashboard (auto-refreshes every 5 cycles)
```
================================================================================
  ASR ENGINE v3 — LIVE DEMO TRADING DASHBOARD
================================================================================
  Runtime: 2.5h | Mode: DEMO (Testnet) | Updated: 21:30:00
--------------------------------------------------------------------------------
  💰 Portfolio: $10,045.23 (Start: $10,000.00)
  📊 PnL: $+45.23 (+0.45%)
  📉 Max DD: 0.82% | Peak: $10,052.10
  🔄 Trades: 12 | Wins: 8 | Open: 2
  📈 Win Rate: 66.7%
--------------------------------------------------------------------------------
  Slot | Symbol     | TF    | Margin | Equity     | PnL        | Trades | Status
  -----------------------------------------------------------------------
     1 | BNBUSDT    | 1m    | USDT   |  $1,012.34 |    $+12.34 |      4 | ✅ READY
     2 | SOLUSDT    | 3m    | USDT   |  $1,003.45 |     $+3.45 |      2 | 📈 OPEN
  ...
================================================================================
```

### Log Files
- **Runtime log:** `logs/auto_trader_YYYYMMDD_HHMMSS.log`
- **Trade CSV:** `results/trade_log.csv`
- **Snapshots:** `results/portfolio_snapshot.json`
- **Equity history:** `results/portfolio_history.jsonl`

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `ccxt` not found | `pip install ccxt` |
| API authentication error | Check `.env` keys, ensure testnet keys match |
| "Markets not loaded" | Exchange rate limit hit, wait and retry |
| No signals generated | Normal — ASR is selective. Wait for zone tests. |
| Position size too small | Increase slot capital or reduce risk distance |
| Circuit breaker triggered | Check logs, review losing streak, resume manually |

---

## 🔗 Related Documentation

- [Strategy Guide](docs/STRATEGY_GUIDE.md) — Full trading methodology
- [Portfolio Overview](docs/PORTFOLIO_OVERVIEW.md) — Detailed slot analysis  
- [Risk Framework](docs/RISK_FRAMEWORK.md) — Multi-layer risk management
- [Results](RESULTS.md) — Live trading performance tracking
- [Main Project README](../README.md) — Full project overview
- [Backtest Evidence](../evidence/) — Historical backtest proof
