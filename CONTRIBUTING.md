# Contributing to ASR Execution Engine

Thank you for your interest in contributing to the ASR Execution Engine! This document provides guidelines and instructions for contributing to this project.

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)
- [Architecture Guidelines](#architecture-guidelines)

---

## Code of Conduct

This project follows a professional standard of conduct. Please be respectful, constructive, and collaborative in all interactions.

---

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/Arpan01574/ASR-Execution-Engine.git
   cd ASR-Execution-Engine
   ```
3. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes**, commit, and push
5. **Open a Pull Request** against the `main` branch

---

## Development Setup

### Prerequisites

- Python 3.10 or higher
- pip (package manager)
- Git

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Install with dev dependencies
pip install -e ".[dev]"
```

### Environment Configuration

```bash
cp .env.example .env
# Edit .env with your configuration (Binance Testnet keys, etc.)
```

---

## Code Style

This project uses **Ruff** for linting and formatting:

```bash
# Run linter
ruff check .

# Auto-fix issues
ruff check --fix .

# Type checking
mypy backtester/ execution/ live_trading/
```

### Key Style Rules

- **Line length:** 120 characters maximum
- **Target Python version:** 3.10+
- **Import sorting:** Ruff `isort` mode enabled
- **Docstrings:** Required for all public classes and functions
- **Type hints:** Encouraged for all function signatures
- **Comments:** Preserve all existing comments unrelated to your changes

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files & modules | `snake_case` | `asr_engine.py` |
| Classes | `PascalCase` | `ExecutionEngine` |
| Functions & methods | `snake_case` | `calculate_zone_score()` |
| Constants | `UPPER_SNAKE_CASE` | `MAX_DRAWDOWN_PCT` |
| Config keys | `snake_case` | `risk_per_trade_pct` |

---

## Testing

All contributions **must** include tests for new functionality and must not break existing tests.

```bash
# Run full test suite
pytest tests/ -v

# Run specific test modules
pytest tests/test_asr_engine.py -v
pytest execution/tests/test_integration.py -v

# Run with coverage report
pytest tests/ --cov=backtester --cov=execution -v
```

### Test Requirements

- **Backtester changes:** Add unit tests in `tests/test_asr_engine.py`
- **Execution engine changes:** Add integration tests in `execution/tests/`
- **All changes:** Must pass existing test suite with 0 failures

---

## Pull Request Process

1. **Ensure all tests pass** before submitting
2. **Update documentation** if your changes affect public APIs, configuration, or behavior
3. **Update the CHANGELOG.md** with a brief description of your changes
4. **Link related issues** in your PR description
5. **Keep PRs focused** — one feature or fix per PR
6. **Write descriptive commit messages** following conventional commit format:
   ```
   feat: add trailing stop for runner positions
   fix: correct zone scoring when FVG is absent
   docs: update risk framework with new circuit breaker logic
   test: add edge case tests for same-bar TP1+SL
   ```

### PR Checklist

- [ ] Code follows the project's style guidelines
- [ ] Tests added/updated for new functionality
- [ ] All existing tests pass
- [ ] Documentation updated (if applicable)
- [ ] CHANGELOG.md updated
- [ ] No sensitive data (API keys, secrets) committed
- [ ] No large data files committed (CSVs, databases)

---

## Reporting Issues

When reporting bugs, please include:

1. **Description** — Clear, concise description of the issue
2. **Steps to Reproduce** — Exact steps to trigger the bug
3. **Expected Behavior** — What should happen
4. **Actual Behavior** — What actually happens
5. **Environment** — Python version, OS, relevant config
6. **Logs** — Relevant error messages or log output

---

## Architecture Guidelines

### Critical Rules for Contributors

1. **No Lookahead Bias** — The backtester must never use future data. Pivots confirmed at `i + pivR`, HTF data uses last *closed* bar only.
2. **Conservative Same-Bar Model** — When SL and TP are both touched on the same bar, assume SL was hit first.
3. **Single Source of Truth** — [`docs/strategy_spec.md`](docs/strategy_spec.md) is the canonical specification. Pine Script and Python implementations must both conform to it.
4. **State Machine Integrity** — Order and Position FSMs must transition through all required states. No state skipping.
5. **Decimal Precision** — Position sizing must use `Decimal` arithmetic with `ROUND_DOWN`.

### Module Responsibilities

| Module | Responsibility | Constraints |
|--------|---------------|-------------|
| `backtester/asr_engine.py` | Canonical signal generation | Must match Pine Script logic exactly |
| `execution/src/risk/` | Risk validation & sizing | Must never round UP position size |
| `execution/src/queue/` | Signal deduplication | Must guarantee exactly-once processing |
| `execution/src/brokers/` | Exchange communication | Must handle all API errors gracefully |
| `live_trading/auto_trader.py` | Autonomous trading loop | Must respect all circuit breaker rules |

---

## Questions?

If you have questions about contributing, feel free to open a GitHub issue with the `question` label.

Thank you for helping improve the ASR Execution Engine! 🚀
