# ASR Engine v3 - Failure Injection and Incidents
*Data Range: NOT AVAILABLE | Generated: 2026-10-03 | Commit: NOT AVAILABLE*

## 1. Test Summary
- **Unit / Integration / Replay / Failure Counts:** 1 Integration Test created (`tests/test_integration.py`).
- **Pass Rate:** 100% (on integration test).
- **Coverage %:** NOT AVAILABLE.
- **CI Status:** Local only.

## 2. Fault-Injection Matrix
| Fault | How Injected | Time to Detect | Action | State Consistent? | Status |
|---|---|---|---|---|---|
| Duplicate Webhook | Resend exact payload | Immediate (Idempotency Key) | Dropped | Y | PASS |
| Stale Signal | Timestamp > 5 min | Immediate (TTL Check) | Rejected | Y | PASS |
| Drift | Simulated Quote Diff | Immediate (Drift Guard) | Rejected/Resized | Y | PASS |
| WS Disconnect | Not tested | - | - | - | INCONCLUSIVE |
| Missing Stop | Not tested | - | - | - | INCONCLUSIVE |
| Invalid Precision| Not tested | - | - | - | INCONCLUSIVE |

## 3. Incident Reports
*NOT AVAILABLE - No live incidents recorded.*

## 4. Kill-Switch and Risk-Limit Evidence
- **Global Drawdown Breach:** Configured in `engine.py`. Tests pending.
- **Max Open Trades:** Hardcoded to 5. Tests pending.

## 5. Asian-Session Shift Log
*NOT AVAILABLE*

## 6. Known Gaps
- Comprehensive unit testing for `BinanceAdapter` failure scenarios (rate limits, API rejections) required.
- Reconciliation loop REST fallback testing required.

---
**Limitations:** Fault injection tests are mostly pending execution phase.
**Reproduce:** Run `pytest tests/test_integration.py`.
