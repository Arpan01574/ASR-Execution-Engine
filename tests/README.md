# Tests

> **Unit and Integration Test Suite** — Validates the ASR Engine's core logic, signal generation, trade management, and execution pipeline.

---

## 📂 Structure

```text
tests/
├── README.md                  ← You are here
└── test_asr_engine.py         ← ASR Engine unit tests

execution/tests/
└── test_integration.py        ← Execution pipeline integration tests
```

---

## 🚀 Running Tests

```bash
# Run all tests (both unit and integration)
pytest tests/ -v

# Run ASR Engine unit tests only
pytest tests/test_asr_engine.py -v

# Run execution integration tests only
pytest execution/tests/test_integration.py -v

# Run with coverage
pytest tests/ --cov=backtester --cov=execution -v
```

---

## 🧪 Test Coverage

### Unit Tests (`test_asr_engine.py`)

| Test | Description |
|------|-------------|
| `test_zone_creation` | Verifies pivot-based zone detection creates valid zones with correct `top >= btm` bounds |
| `test_zone_scoring` | Validates zone tier classification (None/Strong/Elite) and quality score calculation |
| `test_signal_generation` | Confirms entry signals are generated with valid setup names and prices |
| `test_trade_management` | Verifies exit reasons (`SL`, `TP1`, `TP2`, `TRAIL`, `BE`, `TIME`) and exit prices |
| `test_daily_signal_limit` | Enforces the `max_sig_per_day` constraint per trading day |
| `test_choch_gating` | Validates Change of Character (CHoCH) structural confirmation |
| `test_regime_gating` | Confirms volatility and trend regime detection |
| `test_walk_forward` | Placeholder for walk-forward optimization validation |
| `test_monte_carlo` | Placeholder for Monte Carlo simulation validation |

### Integration Tests (`test_integration.py`)

| Test | Description |
|------|-------------|
| End-to-end pipeline | Validates the full webhook → queue → risk → execution flow |

---

## ⚙️ Configuration

Test configuration is defined in [`pyproject.toml`](../pyproject.toml):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests", "execution/tests"]
```

### Dependencies

Test dependencies are specified in `[project.optional-dependencies.dev]`:
- `pytest >= 7.0.0`
- `pytest-asyncio >= 0.21.0`
- `httpx >= 0.24.0`

Install with:
```bash
pip install -e ".[dev]"
```

---

## 🔗 Related Documentation

- [Methodology](../docs/methodology.md) — Statistical thresholds and testing standards
- [Paper Execution Evidence](../evidence/03_Paper_Trading/Paper_Execution_Quality.md) — 75-trade simulation results
- [Failure Injection](../evidence/05_Operations/Failure_Injection_and_Incidents.md) — Fault tolerance tests
