# ASR Engine v3 — Parity and Replay Validation

> *Status: ⏳ INCONCLUSIVE — Awaiting TradingView Parity CSV Exports*
> *Generated: 2026-10-03 | Commit: v3.0.0-rc3*

---

## 1. Purpose

This document validates that the **Python canonical engine** produces identical signals to the **TradingView Pine Script v6** indicator. Parity between implementations is critical because the backtester's results are only meaningful if the Python engine matches what Pine Script would signal in production.

---

## 2. Setup

| Parameter | Value |
|-----------|-------|
| **Symbols/TFs Tested** | Pending |
| **TradingView Signals** | Pending CSV export from Strategy Tester |
| **Tolerance: Entry Price** | ≤ 0.5% difference |
| **Tolerance: Time** | ≤ 2 bars difference |
| **Tolerance: Score** | ≤ 10.0 points difference |
| **Test Framework** | `backtester/parity_test.py` |

---

## 3. Match Rate Per Field

*Awaiting parity CSV exports from TradingView.*

| Field | Match Rate | Status |
|-------|-----------|--------|
| Entry Price | — | ⏳ Pending |
| Entry Time | — | ⏳ Pending |
| Direction | — | ⏳ Pending |
| Score | — | ⏳ Pending |
| Stop Loss | — | ⏳ Pending |
| Take Profit | — | ⏳ Pending |

---

## 4. Mismatch Table

| Timestamp | Symbol | TF | Pine Value | Python Value | Difference | Cause | Severity | Fix |
|-----------|--------|----|-----------|-------------|------------|-------|----------|-----|
| *Awaiting data* | — | — | — | — | — | — | — | — |

---

## 5. Determinism Validation

| Check | Status | Evidence |
|-------|--------|----------|
| Replay stream hash comparison | ⏳ Pending | Requires live replay data |
| `signal_id` stability | ✅ Implemented | UUID v4 or TradingView-generated |
| Duplicate handling | ✅ Implemented | DB idempotency check in `src/queue/signal_queue.py` |

---

## 6. No-Lookahead Tests

| Check | Status | Implementation |
|-------|--------|---------------|
| Pivot confirmation delay | ✅ PASS | `pivR` delay enforced in canonical logic |
| HTF data availability | ✅ PASS | Only uses last closed HTF bar |
| No future data access | ✅ PASS | Verified by static code analysis |

> **Note:** Dynamic test confirmation pending live data comparison.

---

## 7. Conclusion

**INCONCLUSIVE** — The parity testing framework is fully built and ready (`backtester/parity_test.py`), but requires CSV exports from TradingView's Strategy Tester to execute the comparison.

### How to Complete This Validation

1. Apply `ASR_Engine_Strategy.pine` to a TradingView chart
2. Run the Strategy Tester on the desired symbol/timeframe
3. Export the trade list as CSV
4. Run the parity test:

```bash
python -m backtester.parity_test --tv-csv <tv_export.csv> --py-csv <python_trades.csv>
```

---

**Limitations:** Parity CSV exports from TradingView strategy tester not yet provided.
**Reproduce:** `python -m backtester.parity_test --tv-csv <path> --py-csv <path>`
