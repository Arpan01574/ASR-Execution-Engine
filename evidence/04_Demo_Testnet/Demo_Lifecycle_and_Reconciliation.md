# ASR Engine v3 - Demo Lifecycle and Reconciliation
*Data Range: NOT AVAILABLE | Generated: 2026-10-03 | Commit: NOT AVAILABLE*

## 1. Environment
- **Environment Used:** Binance Testnet (Future). configured in `.env` via `BINANCE_USE_TESTNET=true`.
- **Venues Tested via Mocks Only:** None.

## 2. Summary
- **Dates:** NOT AVAILABLE
- **Trade Count:** 0
- **Symbols:** NOT AVAILABLE
- **Versions:** Engine v0.1.0
- **Fill Rate:** NOT AVAILABLE

## 3. Lifecycle Table
| Scenario | Expected | Observed | Status | Evidence Ref |
|---|---|---|---|---|
| Entry | Submit MARKET -> FILLED | NOT AVAILABLE | INCONCLUSIVE | - |
| Stop Placed | STOP_MARKET Submitted | NOT AVAILABLE | INCONCLUSIVE | - |
| TP1 Partial | LIMIT Fill -> BE Trigger | NOT AVAILABLE | INCONCLUSIVE | - |
| BE Trigger | SL moved to Entry | NOT AVAILABLE | INCONCLUSIVE | - |
| TP2 | Final LIMIT Fill | NOT AVAILABLE | INCONCLUSIVE | - |
| Time Stop | Market Close | NOT AVAILABLE | INCONCLUSIVE | - |
| Rejection | Risk logic blocks intent | NOT AVAILABLE | INCONCLUSIVE | - |
| WS Reconnect| State restored from REST | NOT AVAILABLE | INCONCLUSIVE | - |

## 4. Paper vs Demo
*NOT AVAILABLE*

## 5. Reconciliation Events
*NOT AVAILABLE*

## 6. Trade Traces
*NOT AVAILABLE*

## 7. Open Issues
- End-to-end live testing on Binance testnet is pending historical simulation approval.

---
**Limitations:** Demo execution phase not yet started.
**Reproduce:** Start FastAPI server with Binance Testnet credentials and forward TradingView webhooks.
