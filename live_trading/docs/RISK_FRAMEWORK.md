# ASR Engine v3 — Risk Management Framework

## Overview

The ASR Engine v3 employs a **multi-layered risk management framework** designed to protect capital at every level: per-trade, per-slot, and portfolio-wide. The system is designed so that **no single failure can cause catastrophic loss**.

---

## Layer 1: Per-Trade Risk

### Position Sizing
```
Risk Amount = Slot Equity × 0.5%
Position Size = Risk Amount / |Entry Price − Stop Loss Price|
```

**Example (Slot 1: BNB/USDT 1m, $1,000 equity):**
```
Risk Amount = $1,000 × 0.005 = $5.00
Entry = $620.50, SL = $618.00 → Distance = $2.50
Position Size = $5.00 / $2.50 = 2.0 BNB
Max Loss on this trade = $5.00 (0.5% of slot equity)
```

### Key Constraints
- **Never** rounds UP position size (uses `ROUND_DOWN`)
- Checks minimum notional ($5 for Binance)
- Checks minimum quantity per market
- Uses `Decimal` arithmetic for precision

### Stop Loss Placement
```
LONG SL = Zone Bottom − 0.5 × ATR(20)
SHORT SL = Zone Top + 0.5 × ATR(20)
```
- Stop loss is **structural** — placed beyond the zone + ATR buffer
- Never moved toward price (only trailing in profit)
- Maximum risk distance: 2.5 × ATR (wider stops rejected)

---

## Layer 2: Per-Slot Risk

### Circuit Breakers
| Trigger | Action | Reset |
|---------|--------|-------|
| 3 consecutive losses | Pause slot 30 min | Auto-resume after cooldown |
| Slot drawdown > 25% | Pause slot indefinitely | Manual review required |
| Single trade loss > 3% | Flag for review | Logged, no auto-pause |

### Slot Isolation
- Each slot has **independent** equity tracking
- Slot PnL does not affect other slots' sizing
- A failing slot cannot consume capital from healthy slots
- Each slot maintains its own `peak_equity` and `max_drawdown`

---

## Layer 3: Portfolio Risk

### Global Kill Switch
```
Portfolio DD = (Peak Equity − Current Equity) / Peak Equity × 100
If Portfolio DD > 15% → GLOBAL KILL SWITCH → All trading stops
```

### Position Limits
| Limit | Value |
|-------|-------|
| Max positions per slot | 1 |
| Max global positions | 10 |
| Max daily trades per slot | 4 |
| Max portfolio drawdown | 15% |

### Margin Diversification
- **USDT Pool:** Slots 1-5 ($5,000)
- **USDC Pool:** Slots 6-10 ($5,000)
- If one stablecoin depegs, only 50% of capital is at risk

---

## Layer 4: Execution Risk

### Drift Guard
Before placing any order, the system checks if the current price has drifted too far from the signal price:
```
Drift = |Current Price − Signal Price| / Signal Price × 100
If Drift > 0.3% → Reject the signal
```

### Order Lifecycle (FSM)
```
NEW → VALIDATING → RISK_CHECK → SUBMITTING → ACKNOWLEDGED → FILLED
                                     ↓
                                  REJECTED
```
Every order transitions through a state machine. Orders cannot skip states.

### Slippage Budget
- Expected slippage: 0.02% per side
- Maximum tolerated: 0.3% per side
- If fill price exceeds slippage budget → log warning

---

## Worst-Case Scenarios

### Scenario 1: Maximum Single-Slot Loss
```
10 consecutive losses at 0.5% each (compounding)
$1,000 → $1,000 × (1 - 0.005)^10 = $951.11
Max loss = $48.89 (4.9% of slot)
```
*Note: Circuit breaker triggers at 3 consecutive losses, preventing this.*

### Scenario 2: All Slots Hit Simultaneously
```
All 10 slots lose 0.5% at same time
Total loss = 10 × $5.00 = $50.00 (0.5% of portfolio)
```
*Extremely unlikely due to temporal diversification.*

### Scenario 3: Black Swan Event
```
Market gaps 10% through all stop losses
Max per-slot loss = ~10% × max_position_value
With 2.5 ATR max risk, this is approximately 2-3% of slot equity
Total portfolio impact = ~2-3% ($200-$300)
```
*Kill switch triggers at 15% portfolio DD, well before catastrophic.*

---

## Risk Monitoring

### Real-Time Metrics (Dashboard)
- Per-slot equity, PnL, drawdown
- Portfolio total equity and drawdown
- Open positions count
- Consecutive loss streaks
- Circuit breaker status

### Logged Metrics (JSON/CSV)
- Every trade entry/exit with full pricing
- Risk decisions (ALLOW/REJECT with reason)
- Portfolio snapshots every cycle
- Session reports on shutdown

---

## Risk Parameters Summary

| Parameter | Value | Configurable |
|-----------|-------|-------------|
| Risk per trade | 0.5% of slot equity | ✅ `config.yaml` |
| Max risk distance | 2.5 × ATR | ✅ `config.yaml` |
| TP1 | 1.5R (33% of position) | ✅ |
| TP2 | 3.0R (33% of position) | ✅ |
| Trail stop | 1.5 ATR | ✅ |
| Max consecutive losses | 3 | ✅ |
| Max slot drawdown | 25% | ✅ |
| Max portfolio drawdown | 15% | ✅ |
| Max positions per slot | 1 | ✅ |
| Max global positions | 10 | ✅ |
| Max daily trades per slot | 4 | ✅ |
| Drift tolerance | 0.3% | ✅ |
| Slippage budget | 0.02% per side | ✅ |
