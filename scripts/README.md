# Scripts

> **Utility and Deployment Scripts** — Helper scripts for data management, manual testing, and production deployment.

---

## 📂 Files

| Script | Language | Description |
|--------|----------|-------------|
| `setup_vps.sh` | Bash | **GCP/VPS Deployment Script** — Automates server setup, virtual environment creation, dependency installation, and systemd service configuration for 24/7 auto-trading |
| `download_data.py` | Python | **OHLCV Data Downloader** — Downloads historical candlestick data from Binance via ccxt for backtesting |
| `fast_download.py` | Python | **Parallel Data Downloader** — Multi-threaded version of the data downloader for faster bulk downloads |
| `test_trade.py` | Python | **Manual Trade Tester** — Submits test trades to Binance Testnet to verify API connectivity, order placement, and fill execution |
| `cleanup_positions.py` | Python | **Position Cleanup** — Closes all open positions and cancels pending orders on Binance Testnet (useful for resetting state) |

---

## 🚀 Usage

### Deploy to VPS (24/7 Trading)

```bash
# On your GCP/VPS server
cd ~/ASR-Execution-Engine
bash scripts/setup_vps.sh
```

This script will:
1. Install system dependencies (`python3-pip`, `python3-venv`, `git`)
2. Create a Python virtual environment and install project dependencies
3. Create a `systemd` service (`asr-bot.service`) for auto-restart on crash/reboot
4. Start the auto-trader as a background daemon

**Post-deployment commands:**
```bash
# View live logs
sudo journalctl -u asr-bot -f

# Check service status
sudo systemctl status asr-bot

# Stop the bot
sudo systemctl stop asr-bot

# Restart the bot
sudo systemctl restart asr-bot
```

### Download Market Data

```bash
# Standard download
python scripts/download_data.py

# Fast parallel download
python scripts/fast_download.py
```

### Test Exchange Connectivity

```bash
# Submit test trades to Binance Testnet
python scripts/test_trade.py
```

### Clean Up Testnet Positions

```bash
# Close all open positions and cancel orders
python scripts/cleanup_positions.py
```

---

## ⚠️ Prerequisites

- **`setup_vps.sh`** — Requires Ubuntu 20.04+ on the target server
- **`test_trade.py`** — Requires valid Binance Testnet API keys in `.env`
- **`cleanup_positions.py`** — Requires valid Binance Testnet API keys in `.env`
- **All Python scripts** — Require project dependencies (`pip install -e .`)

---

## 🔗 Related Documentation

- [Main README](../README.md) — Project overview and quick start
- [Live Trading README](../live_trading/README.md) — Auto-trading system documentation
