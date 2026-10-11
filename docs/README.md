# Documentation

> **Core Specifications & References** — The canonical documents governing the ASR Engine's behavior across all implementations.

---

## 📂 Documents

| Document | Description | Audience |
|----------|-------------|----------|
| [`strategy_spec.md`](strategy_spec.md) | **Single Source of Truth** — Complete strategy rules for zone detection, signal generation, trade management, and state machines. Both Pine Script and Python must conform to this. | Developers, Reviewers |
| [`canonical_spec.md`](canonical_spec.md) | **Canonical Engine Specification** — Zone lifecycle states, signal scoring formula (0-100), event-time execution model, and risk parameters. | Developers, Quantitative Analysts |
| [`methodology.md`](methodology.md) | **Test Methodology** — No-lookahead guarantees, conservative same-bar execution model, statistical reliability thresholds, random-entry controls, and walk-forward stability. | Reviewers, Interviewers |

---

## 🔗 Additional Documentation

Documentation is also distributed across module-specific locations:

| Location | Content |
|----------|---------|
| [`live_trading/docs/STRATEGY_GUIDE.md`](../live_trading/docs/STRATEGY_GUIDE.md) | Live trading strategy guide with entry/exit rules and portfolio allocation rationale |
| [`live_trading/docs/PORTFOLIO_OVERVIEW.md`](../live_trading/docs/PORTFOLIO_OVERVIEW.md) | Portfolio architecture, slot details, correlation analysis, and performance projections |
| [`live_trading/docs/RISK_FRAMEWORK.md`](../live_trading/docs/RISK_FRAMEWORK.md) | Multi-layer risk management framework with worst-case scenario analysis |
| [`evidence/`](../evidence/) | Validation evidence pack — backtest reports, parity tests, paper trading quality |

---

## 📖 Reading Order (Recommended)

1. **Start here:** [`strategy_spec.md`](strategy_spec.md) — Understand the trading system
2. **Deep dive:** [`canonical_spec.md`](canonical_spec.md) — Zone lifecycle and scoring details
3. **Methodology:** [`methodology.md`](methodology.md) — How results are validated
4. **Results:** [`../evidence/01_Backtest/Backtest_Evidence.md`](../evidence/01_Backtest/Backtest_Evidence.md) — Backtest evidence
5. **Live system:** [`../live_trading/README.md`](../live_trading/README.md) — Running the auto-trader
