# ASR Engine v3 — Failure Injection and Incidents

> *Status: 🔶 PARTIAL — Core fault injection tested; advanced scenarios pending*
> *Generated: 2026-10-03*

---

## 1. Test Summary

| Metric | Value |
|--------|-------|
| **Integration Tests** | 1 (`execution/tests/test_integration.py`) |
| **Pass Rate** | 100% |
| **Coverage** | Not measured (pending CI setup) |
| **CI Status** | Local only |

---

## 2. Fault Injection Matrix

Each row represents a failure scenario that was intentionally injected to verify the system's resilience:

| # | Fault | Injection Method | Detection Time | System Action | State Consistent? | Status |
|---|-------|-----------------|----------------|---------------|-------------------|--------|
| 1 | **Duplicate Webhook** | Resend exact payload | Immediate | Dropped (idempotency key) | ✅ Yes | ✅ PASS |
| 2 | **Stale Signal** | Timestamp > 5 min old | Immediate | Rejected (TTL check) | ✅ Yes | ✅ PASS |
| 3 | **Price Drift** | Simulated quote difference | Immediate | Rejected / resized (drift guard) | ✅ Yes | ✅ PASS |
| 4 | **WS Disconnect** | Not tested | — | — | — | ⏳ PENDING |
| 5 | **Missing Stop** | Not tested | — | — | — | ⏳ PENDING |
| 6 | **Invalid Precision** | Not tested | — | — | — | ⏳ PENDING |
| 7 | **Rate Limit** | Not tested | — | — | — | ⏳ PENDING |
| 8 | **Network Timeout** | Not tested | — | — | — | ⏳ PENDING |

---

## 3. Incident Reports

*No live incidents recorded — system has not been deployed to live/testnet for extended periods.*

---

## 4. Kill-Switch and Risk Limit Evidence

| Control | Implementation | Test Status |
|---------|---------------|-------------|
| Global Drawdown Breach (>15%) | Configured in `execution/src/risk/engine.py` | ⏳ Pending live test |
| Max Open Trades (10) | Hardcoded in auto-trader | ⏳ Pending live test |
| Per-Slot Circuit Breaker (3 losses) | Implemented in `live_trading/auto_trader.py` | ⏳ Pending live test |
| Slot Drawdown Limit (25%) | Implemented in `live_trading/auto_trader.py` | ⏳ Pending live test |

---

## 5. Known Gaps

| # | Gap | Priority | Impact | Mitigation Plan |
|---|-----|----------|--------|-----------------|
| 1 | BinanceAdapter failure scenarios (rate limits, API rejections) | High | Could cause missed trades or stuck states | Add unit tests with mocked responses |
| 2 | Reconciliation loop REST fallback | Medium | After WS disconnect, positions may be stale | Implement periodic REST sync |
| 3 | Comprehensive unit test coverage | Medium | Low confidence in edge cases | Expand test suite before live deployment |
| 4 | CI/CD pipeline | Low | Manual testing only | Set up GitHub Actions |

---

## 6. Recommendations

1. **Before Live Trading:** Complete fault injection tests for scenarios 4-8
2. **CI Setup:** Configure GitHub Actions with automated test runs on push
3. **Monitoring:** Add Telegram/Discord notifications for circuit breaker triggers
4. **Reconciliation:** Implement periodic position sync via REST API

---

**Limitations:** Fault injection tests are mostly pending the demo execution phase.
**Reproduce:** `pytest execution/tests/test_integration.py`
