# ASR Engine v3 - Parity and Replay Validation
*Data Range: NOT AVAILABLE | Generated: 2026-10-03 | Commit: NOT AVAILABLE*

## 1. Setup
- **Symbols/TFs:** NOT AVAILABLE
- **TradingView Signals Compared:** NOT AVAILABLE
- **Tolerances:** Entry Price <= 0.5% diff, Time <= 2 bars diff, Score <= 10.0 diff. (Defined in `backtester/parity_test.py`).

## 2. Match Rate Per Field
*NOT AVAILABLE - Awaiting Parity CSV exports from TradingView.*

## 3. Mismatch Table
| Timestamp | Symbol | TF | Pine Value | Python Value | Difference | Cause | Severity | Fix |
|---|---|---|---|---|---|---|---|---|
| NOT AVAILABLE | - | - | - | - | - | - | - | - |

## 4. Unresolved Mismatches
*NOT AVAILABLE*

## 5. Determinism
- Replay stream hash comparison: NOT AVAILABLE
- `signal_id` stability: IMPLEMENTED (UUID v4 or TV generated)
- Duplicate handling: IMPLEMENTED (via `SignalQueue.enqueue` DB idempotency check in `src/queue/signal_queue.py`).

## 6. No-Lookahead Tests
- Pivot confirmation: IMPLEMENTED (`pivR` delay enforced in canonical logic).
- HTF availability: IMPLEMENTED.
- **Status:** PASS (by static code analysis, pending dynamic test confirmation).

## 7. Conclusion
**INCONCLUSIVE** (Awaiting Parity data).

---
**Limitations:** Parity CSV exports from TradingView strategy tester not provided.
**Reproduce:** Run `python -m backtester.parity_test --tv-csv <path> --py-csv <path>`.
