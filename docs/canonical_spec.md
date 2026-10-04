# ASR Canonical Specification (v3)

## 1. Overview
The ASR (Adaptive Support/Resistance) Canonical Engine dictates exactly how signals are generated, ensuring perfect parity between TradingView (Pine Script) and Python environments.

## 2. Event-Time Execution Model
- **Data Dependency**: The system uses `Close`, `High`, `Low`, `Open`, `Volume` of completed bars. Intrabar ticks are not processed for signal generation.
- **Pivot Confirmation**: A pivot high at index `i` is confirmed at index `i + pivR`. No lookahead is allowed.
- **Same-Bar Processing**:
  - Step 1: Manage open positions (Check Stops, then check TP1. If TP1 is hit, evaluate new BE stop dynamically in the same bar, then evaluate TP2).
  - Step 2: Update Zone Lifecycle (age, touch counts, freshness decay).
  - Step 3: Combine/Merge zones.
  - Step 4: Scan for new entry signals based on the updated state.
  - Step 5: Execute new entries at the `Close` of the bar.

## 3. Zone Lifecycle
- `CREATED`: Zone initialized when a pivot is confirmed. Width is ± `zoneMult * ATR(20)`.
- `QUALIFYING`: Zone matures until age ≥ `minZoneDuration`.
- `ACTIVE`: Zone is eligible for trading.
- `RETESTED`: After 1+ touches.
- `FLIPPED`: If price breaks and closes beyond the zone with displacement/volume confirmation.
- `DEGRADED`: Quality score < Tier 1 threshold.
- `INVALIDATED`: Price broke the zone without flip criteria.
- `EXPIRED`: Age > `decayFactor`.

## 4. Signal Scoring Formula (0-100)
1. **Zone Quality (0-35)**:
   - Displacement (0-8)
   - Touches (first two add up to 6, >3 subtracts)
   - Reaction Earned (+4, fast +2)
   - HTF (+5)
   - MTF (+3)
   - PDW (+2)
   - Volume (+1 to +3)
   - Decay Multiplier: `freshness = max(0, 100 - age * 100 / (2 * decayFactor))`
2. **Setup Score (0-35)**:
   - Base Type (Reject=10, Flip=13, Sweep=15, Disp=12, BOS=11)
   - Wick Quality (0-8)
   - Break Displacement (0-7)
   - Flip Bonus (+5)
3. **Context Score (0-30)**:
   - Trend Alignment (+10)
   - Volatility Regime (+5 for normal, +2 high, +3 low)
   - Structure State (+5)
   - Volume Confirmation (+2 to +5)
   - Sweep Context (+5)

## 5. Risk Management
- Initial Stop Loss: Opposite extreme of the setup zone ± `slBufferATR * ATR`.
- TP1: Entry + `tp1R * Risk`. Move SL to Entry.
- TP2: Entry + `tp2R * Risk`. Close remaining position.
- Time Stop: Close all remaining at the close of `timeStopBars` if still open.
