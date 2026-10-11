# Pine Scripts

> **TradingView Pine Script v6** — The visual and signaling layer of the ASR Engine. These scripts detect structural supply/demand zones, generate trade signals, and fire webhooks to the execution engine.

---

## 📋 Overview

The Pine Scripts are the **origin point** of the ASR trading system. They implement the full ASR Engine logic in TradingView's Pine Script v6 language, providing:

- **Real-time zone visualization** on TradingView charts
- **Signal generation** with composite scoring (0-100)
- **Webhook alerts** for the execution engine
- **Strategy mode** for TradingView's built-in backtester

---

## 📂 Files

| File | Size | Type | Description |
|------|------|------|-------------|
| `ASR_Engine.pine` | ~93K chars | **Indicator** | Full ASR Engine with zone visualization, signal overlays, and webhook alerts. Apply to any chart for real-time analysis. |
| `ASR_Engine_Strategy.pine` | ~94K chars | **Strategy** | Same logic as the indicator, but wrapped as a TradingView strategy for built-in backtesting, performance reporting, and strategy tester exports. |

---

## 🧠 Core Logic

### Zone Detection
- Identifies **pivot highs/lows** with configurable lookback/lookforward (`pivL` / `pivR`)
- Creates **supply zones** (resistance) and **demand zones** (support) around pivots
- Zone width: `pivot price ± zoneMult × ATR(20)`

### Zone Lifecycle
```
CREATED → QUALIFYING → ACTIVE → RETESTED → FLIPPED/DEGRADED/INVALIDATED/EXPIRED
```

### Signal Scoring (0-100)
| Component | Weight | Factors |
|-----------|--------|---------|
| Zone Quality | 0-35 | Displacement, touches, reaction, HTF/MTF confluence, volume, freshness |
| Setup Score | 0-35 | Setup type (Reject/Flip/Sweep/BOS/Displacement), wick quality, break displacement |
| Context Score | 0-30 | Trend alignment, volatility regime, structure state, volume confirmation |

### Setup Types
1. **Zone Reject** — Price taps zone, wick rejects, closes away
2. **Flip Retest** — Old resistance becomes support (or vice versa)
3. **Sweep & Reclaim** — Liquidity sweep beyond level, reclaim within 3 bars
4. **BOS Retest** — Break of Structure, then retest of broken level
5. **Displacement Retest** — Impulsive FVG move, then retest

---

## 🚀 Installation

### As an Indicator (Recommended for Live Trading)
1. Open [TradingView](https://www.tradingview.com)
2. Go to **Pine Editor** (bottom panel)
3. Click **Open** → **New Indicator**
4. Paste the contents of `ASR_Engine.pine`
5. Click **Save** and then **Add to Chart**

### As a Strategy (For TradingView Backtesting)
1. Follow the same steps, but select **New Strategy**
2. Paste the contents of `ASR_Engine_Strategy.pine`
3. Use TradingView's **Strategy Tester** tab to view performance

---

## ⚙️ Configuration

Both scripts expose extensive inputs in TradingView's settings panel:

| Category | Key Inputs | Defaults |
|----------|-----------|----------|
| **Pivots** | `pivL`, `pivR`, `nPiv` | 12, 12, 10 |
| **Zones** | `zoneMult`, `decayFactor`, `mergeOverlap` | 0.5, 800, true |
| **Signals** | `minScore`, `minWick`, `trendMode` | 45, 0.20, "Soft" |
| **Risk** | `slBufferATR`, `tp1R`, `tp2R` | 0.50, 1.5, 3.0 |
| **Volume** | `volSmaLen`, `volSurgeThresh` | 20, 20.0 |

---

## 🔗 Webhook Integration

### Setting Up Alerts

1. Apply `ASR_Engine.pine` to your chart
2. Right-click → **Add Alert**
3. Condition: Select the ASR Engine alert condition
4. Webhook URL: `https://your-server:8000/webhook/{your_token}`
5. Message: The script auto-generates JSON payloads

### Alert Payload Format

```json
{
  "signal_id": "{{timenow}}_{{ticker}}_{{interval}}",
  "symbol": "{{ticker}}",
  "side": "{{strategy.order.action}}",
  "entry_price": {{close}},
  "score": 62.5,
  "setup_type": "ZONE_REJECT",
  "timeframe": "{{interval}}",
  "timestamp": "{{timenow}}",
  "passphrase": "your_passphrase"
}
```

---

## 📊 Parity with Python

The Python backtester (`backtester/asr_engine.py`) is a **canonical port** of these Pine Scripts. Both implementations:

- Use identical pivot detection logic
- Apply the same zone width calculation
- Follow the same scoring formula
- Enforce the same no-lookahead constraints

To validate parity, export trades from TradingView's Strategy Tester and run:
```bash
python -m backtester.parity_test --tv-csv <path> --py-csv <path>
```

---

## 🔗 Related Documentation

- [Canonical Specification](../docs/canonical_spec.md) — Definitive zone lifecycle and scoring rules
- [Strategy Specification](../docs/strategy_spec.md) — Single source of truth for both Pine and Python
- [Parity Validation](../evidence/02_Parity/Parity_and_Replay_Validation.md) — Pine/Python comparison evidence
