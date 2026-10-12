# ASR Engine v3 — Demo Lifecycle and Reconciliation

> *Status: ⏳ INCONCLUSIVE — Demo execution phase not yet started*
> *Generated: 2026-10-03*

---

## 1. Environment

| Parameter | Value |
|-----------|-------|
| **Exchange** | Binance Testnet (USDⓈ-M Futures) |
| **Configuration** | `.env` → `BINANCE_USE_TESTNET=true` |
| **Engine Version** | v0.1.0 |
| **Venues Tested** | Binance Testnet only |

---

## 2. Summary

| Metric | Value |
|--------|-------|
| Test Dates | Pending |
| Trade Count | 0 |
| Symbols Tested | Pending |
| Fill Rate | Pending |

---

## 3. Lifecycle Validation Matrix

Each row represents a critical lifecycle scenario that must be verified on the live testnet:

| # | Scenario | Expected Behavior | Observed | Status |
|---|----------|-------------------|----------|--------|
| 1 | **Entry** | Submit MARKET order → FILLED state | Pending | ⏳ |
| 2 | **Stop Placed** | STOP_MARKET submitted immediately after entry | Pending | ⏳ |
| 3 | **TP1 Partial** | LIMIT fill at TP1 → trigger BE stop adjustment | Pending | ⏳ |
| 4 | **BE Trigger** | SL moved to Entry price after TP1 | Pending | ⏳ |
| 5 | **TP2 Fill** | Final LIMIT fill at TP2 → position closed | Pending | ⏳ |
| 6 | **Time Stop** | Market close after `MAX_BARS` exceeded | Pending | ⏳ |
| 7 | **Risk Rejection** | Risk engine blocks invalid signal | Pending | ⏳ |
| 8 | **WS Reconnect** | State restored from REST API after disconnect | Pending | ⏳ |

---

## 4. Paper vs Demo Comparison

| Metric | Paper Sim | Demo (Testnet) | Difference |
|--------|-----------|---------------|------------|
| Expectancy | +8.11 R | Pending | — |
| Fill Rate | 100% | Pending | — |
| Avg Slippage | 0.10% | Pending | — |
| Latency | 17 ms | Pending | — |

---

## 5. Reconciliation Events

*No reconciliation events recorded — awaiting live demo session.*

---

## 6. Trade Traces

*No trade traces available — awaiting live demo session.*

---

## 7. Open Issues

| # | Issue | Priority | Status |
|---|-------|----------|--------|
| 1 | End-to-end live testing on Binance Testnet pending | High | ⏳ Blocked |
| 2 | WebSocket reconnection handling not validated | Medium | ⏳ Pending |
| 3 | Rate limit behavior under high-frequency slots (1m) | Medium | ⏳ Pending |

---

### How to Complete This Validation

1. Configure Binance Testnet API keys in `.env`
2. Start the auto-trader: `python -m live_trading.auto_trader`
3. Let it run for 24-48 hours minimum
4. Collect trade traces from `live_trading/results/`
5. Update this document with observed behaviors

---

**Limitations:** Demo execution phase not yet started.
**Reproduce:** Start FastAPI server with Binance Testnet credentials and forward TradingView webhooks.
