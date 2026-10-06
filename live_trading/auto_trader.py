"""
ASR Engine v3 — Autonomous Demo Auto-Trader
=============================================
Multi-slot portfolio auto-trader that connects to Binance Demo/Testnet,
monitors the top 10 backtested asset+TF combinations, generates signals
using the ASR Engine core strategy, and executes trades autonomously.

Features:
- Multi-asset, multi-timeframe portfolio management
- Real-time OHLCV streaming via ccxt
- ASR Engine signal generation (same core as backtester)
- Per-slot capital isolation ($1,000 each)
- Risk management with drawdown circuit breakers
- Trade logging to SQLite + CSV
- Real-time portfolio dashboard in terminal

Usage:
    python -m live_trading.auto_trader
"""

import os
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

import json
import time
import asyncio
import aiohttp
import logging
import signal as os_signal
from datetime import datetime, timezone, timedelta
from pathlib import Path
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

import yaml
import numpy as np
import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import ccxt.async_support as ccxt_async
    import ccxt as ccxt_sync
except ImportError:
    print("ERROR: ccxt is required. Install with: pip install ccxt")
    sys.exit(1)

from dotenv import load_dotenv

# Load environment
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / "execution" / ".env")

# ============================================================
# LOGGING
# ============================================================
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

log_file = LOG_DIR / f"auto_trader_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AutoTrader")

# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class SlotConfig:
    """Configuration for a single trading slot."""
    slot_id: int
    symbol: str
    exchange_symbol: str
    timeframe: str
    capital: float
    margin_asset: str
    rank: int
    composite_score: float
    notes: str = ""


@dataclass
class TradeRecord:
    """Record of a single trade execution."""
    trade_id: str
    slot_id: int
    symbol: str
    timeframe: str
    direction: str  # LONG or SHORT
    entry_price: float
    entry_time: str
    quantity: float
    stop_loss: float
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    pnl_usd: float = 0.0
    pnl_r: float = 0.0
    status: str = "OPEN"  # OPEN, TP1_HIT, TP2_HIT, STOPPED, CLOSED
    setup_type: str = ""
    score: float = 0.0


@dataclass
class SlotState:
    """Runtime state for a single trading slot."""
    config: SlotConfig
    current_equity: float = 0.0
    peak_equity: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    net_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    consecutive_losses: int = 0
    is_paused: bool = False
    pause_reason: str = ""
    open_trade: Optional[TradeRecord] = None
    last_signal_time: Optional[str] = None
    bars_buffer: Optional[pd.DataFrame] = None


# ============================================================
# PORTFOLIO MANAGER
# ============================================================

class PortfolioManager:
    """Manages all trading slots and portfolio-level risk."""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.slots: Dict[int, SlotState] = {}
        self.all_trades: List[TradeRecord] = []
        self.start_time = datetime.now(timezone.utc)
        self.is_running = False
        self.global_pause = False
        self.exchange: Optional[ccxt_async.binanceusdm] = None
        
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        # Portfolio-level settings
        self.max_portfolio_dd_pct = 15.0
        self.portfolio_peak_equity = 0.0
        self.portfolio_start_equity = 0.0

        # Results directory
        self.results_dir = Path(__file__).parent / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Load configuration
        self._load_config()

    async def send_telegram_message(self, text: str):
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {"chat_id": self.telegram_chat_id, "text": text, "parse_mode": "HTML"}
        try:
            async with aiohttp.ClientSession() as session:
                await session.post(url, json=payload)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    def _load_config(self):
        """Load portfolio allocation from YAML config."""
        with open(self.config_path, "r") as f:
            cfg = yaml.safe_load(f)

        portfolio_cfg = cfg["portfolio"]
        self.max_portfolio_dd_pct = cfg.get("risk_rules", {}).get("max_portfolio_drawdown_pct", 15.0)

        # Load USDT slots (1-5)
        for slot_data in cfg.get("usdt_slots", []):
            sc = SlotConfig(
                slot_id=slot_data["slot_id"],
                symbol=slot_data["symbol"],
                exchange_symbol=slot_data["exchange_symbol"],
                timeframe=slot_data["timeframe"],
                capital=slot_data["capital"],
                margin_asset=slot_data["margin_asset"],
                rank=slot_data["rank"],
                composite_score=slot_data["composite_score"],
                notes=slot_data.get("notes", ""),
            )
            state = SlotState(config=sc, current_equity=sc.capital, peak_equity=sc.capital)
            self.slots[sc.slot_id] = state

        # Load USDC slots (6-10)
        for slot_data in cfg.get("usdc_slots", []):
            sc = SlotConfig(
                slot_id=slot_data["slot_id"],
                symbol=slot_data["symbol"],
                exchange_symbol=slot_data["exchange_symbol"],
                timeframe=slot_data["timeframe"],
                capital=slot_data["capital"],
                margin_asset=slot_data["margin_asset"],
                rank=slot_data["rank"],
                composite_score=slot_data["composite_score"],
                notes=slot_data.get("notes", ""),
            )
            state = SlotState(config=sc, current_equity=sc.capital, peak_equity=sc.capital)
            self.slots[sc.slot_id] = state

        total = sum(s.current_equity for s in self.slots.values())
        self.portfolio_start_equity = total
        self.portfolio_peak_equity = total

        logger.info(f"Loaded {len(self.slots)} trading slots | Total capital: ${total:,.2f}")

    async def initialize_exchange(self):
        """Connect to Binance Demo/Testnet."""
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        use_testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"

        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET must be set in .env")

        self.exchange = ccxt_async.binanceusdm({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            },
        })

        if use_testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("🔧 Connected to Binance TESTNET (demo mode)")
        else:
            logger.warning("⚠️ Connected to Binance LIVE — REAL MONEY AT RISK")

        await self.exchange.load_markets()
        logger.info(f"✅ Markets loaded: {len(self.exchange.markets)} pairs available")

        # Fetch and log account balance
        try:
            balance = await self.exchange.fetch_balance()
            usdt_free = float(balance.get("USDT", {}).get("free", 0))
            usdc_free = float(balance.get("USDC", {}).get("free", 0))
            total_free = usdt_free + usdc_free
            logger.info(f"💰 Account Balance: USDT={usdt_free:,.2f} | USDC={usdc_free:,.2f} | Total=${total_free:,.2f}")
        except Exception as e:
            logger.warning(f"Could not fetch balance: {e}")

    async def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        """Fetch OHLCV candles from exchange, with synthetic resampling for non-standard TFs."""
        try:
            fetch_tf = timeframe
            fetch_limit = limit
            is_resampled = False

            if timeframe == "45m":
                fetch_tf = "15m"
                fetch_limit = limit * 3
                is_resampled = True
            elif timeframe == "10m":
                fetch_tf = "5m"
                fetch_limit = limit * 2
                is_resampled = True

            ohlcv = await self.exchange.fetch_ohlcv(symbol, fetch_tf, limit=fetch_limit)
            if not ohlcv:
                return pd.DataFrame()

            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df.set_index("timestamp", inplace=True)

            if is_resampled:
                df = df.resample(timeframe.replace("m", "min")).agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum"
                }).dropna()

            return df.tail(limit)
        except Exception as e:
            logger.error(f"Failed to fetch OHLCV for {symbol} {timeframe}: {e}")
            return pd.DataFrame()

    async def fetch_current_price(self, symbol: str) -> Optional[float]:
        """Get current last price for a symbol."""
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return float(ticker.get("last", 0))
        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return None

    def generate_asr_signals(self, df: pd.DataFrame, slot: SlotState) -> List[dict]:
        """
        Simplified ASR signal generation for live trading.
        Uses key structural concepts from the backtester:
        - Support/Resistance zone detection via pivot highs/lows
        - Price reaction to zones (wick rejection)
        - Momentum filtering
        - Trend alignment
        """
        if df is None or len(df) < 100:
            return []

        signals = []
        try:
            close = df["close"].values
            high = df["high"].values
            low = df["low"].values
            volume = df["volume"].values

            n = len(df)

            # ATR calculation (20-period)
            atr_len = 20
            tr = np.maximum(
                high[1:] - low[1:],
                np.maximum(
                    np.abs(high[1:] - close[:-1]),
                    np.abs(low[1:] - close[:-1])
                )
            )
            atr = np.full(n, np.nan)
            for i in range(atr_len, len(tr)):
                atr[i + 1] = np.mean(tr[i - atr_len + 1: i + 1])

            # EMA for trend (50-period)
            ema_len = 50
            ema = np.full(n, np.nan)
            if n > ema_len:
                ema[ema_len - 1] = np.mean(close[:ema_len])
                mult = 2 / (ema_len + 1)
                for i in range(ema_len, n):
                    ema[i] = close[i] * mult + ema[i - 1] * (1 - mult)

            # Volume SMA (20-period)
            vol_sma = np.full(n, np.nan)
            for i in range(20, n):
                vol_sma[i] = np.mean(volume[i - 20: i])

            # Pivot detection (simplified)
            piv_len = 12
            pivot_highs = np.full(n, np.nan)
            pivot_lows = np.full(n, np.nan)

            for i in range(piv_len, n - piv_len):
                if high[i] == np.max(high[i - piv_len: i + piv_len + 1]):
                    pivot_highs[i] = high[i]
                if low[i] == np.min(low[i - piv_len: i + piv_len + 1]):
                    pivot_lows[i] = low[i]

            # Only check the latest bar for signals
            i = n - 1
            if np.isnan(atr[i]) or np.isnan(ema[i]):
                return []

            current_atr = atr[i]
            current_close = close[i]
            current_high = high[i]
            current_low = low[i]
            current_vol = volume[i]
            current_vol_sma = vol_sma[i] if not np.isnan(vol_sma[i]) else current_vol
            current_ema = ema[i]

            # Find nearest support/resistance zones from recent pivots
            recent_pivot_highs = [pivot_highs[j] for j in range(max(0, i - 100), i) if not np.isnan(pivot_highs[j])]
            recent_pivot_lows = [pivot_lows[j] for j in range(max(0, i - 100), i) if not np.isnan(pivot_lows[j])]

            # LONG signal conditions
            if current_close > current_ema:  # Bullish trend
                for support in recent_pivot_lows[-5:]:  # Last 5 support levels
                    zone_top = support + current_atr * 0.5
                    zone_bot = support - current_atr * 0.5

                    # Price tapped the zone and bounced
                    if zone_bot <= current_low <= zone_top and current_close > support:
                        # Wick rejection check
                        body = abs(current_close - df["open"].values[i])
                        lower_wick = min(current_close, df["open"].values[i]) - current_low
                        if lower_wick > body * 0.5 and lower_wick > current_atr * 0.15:
                            # Volume confirmation
                            vol_ok = current_vol > current_vol_sma * 0.8

                            if vol_ok:
                                sl = support - current_atr * 0.5
                                risk_dist = current_close - sl
                                tp1 = current_close + risk_dist * 1.5
                                tp2 = current_close + risk_dist * 3.0

                                # Score (simplified)
                                score = 50.0
                                if current_vol > current_vol_sma * 1.5:
                                    score += 15
                                if lower_wick > current_atr * 0.3:
                                    score += 10
                                if current_close > current_ema * 1.01:
                                    score += 10

                                if score >= 50 and risk_dist > 0 and risk_dist < current_atr * 2.5:
                                    signals.append({
                                        "direction": "LONG",
                                        "entry": current_close,
                                        "stop": sl,
                                        "tp1": tp1,
                                        "tp2": tp2,
                                        "score": score,
                                        "setup": "ZONE_REJECT_LONG",
                                        "zone_level": support,
                                        "risk_r": risk_dist / current_atr,
                                    })
                                    break

            # SHORT signal conditions
            if current_close < current_ema:  # Bearish trend
                for resistance in recent_pivot_highs[-5:]:
                    zone_top = resistance + current_atr * 0.5
                    zone_bot = resistance - current_atr * 0.5

                    if zone_bot <= current_high <= zone_top and current_close < resistance:
                        body = abs(current_close - df["open"].values[i])
                        upper_wick = current_high - max(current_close, df["open"].values[i])
                        if upper_wick > body * 0.5 and upper_wick > current_atr * 0.15:
                            vol_ok = current_vol > current_vol_sma * 0.8

                            if vol_ok:
                                sl = resistance + current_atr * 0.5
                                risk_dist = sl - current_close
                                tp1 = current_close - risk_dist * 1.5
                                tp2 = current_close - risk_dist * 3.0

                                score = 50.0
                                if current_vol > current_vol_sma * 1.5:
                                    score += 15
                                if upper_wick > current_atr * 0.3:
                                    score += 10
                                if current_close < current_ema * 0.99:
                                    score += 10

                                if score >= 50 and risk_dist > 0 and risk_dist < current_atr * 2.5:
                                    signals.append({
                                        "direction": "SHORT",
                                        "entry": current_close,
                                        "stop": sl,
                                        "tp1": tp1,
                                        "tp2": tp2,
                                        "score": score,
                                        "setup": "ZONE_REJECT_SHORT",
                                        "zone_level": resistance,
                                        "risk_r": risk_dist / current_atr,
                                    })
                                    break

        except Exception as e:
            logger.error(f"Signal generation error for slot {slot.config.slot_id}: {e}")

        return signals

    def calculate_position_size(self, slot: SlotState, entry: float, stop: float) -> float:
        """Calculate position size using fixed-fractional risk model."""
        equity = slot.current_equity
        risk_pct = 0.005  # 0.5%
        risk_amount = equity * risk_pct

        distance = abs(entry - stop)
        if distance <= 0:
            return 0.0

        raw_qty = risk_amount / distance

        # Get lot size from exchange
        symbol = slot.config.symbol
        if symbol in self.exchange.markets:
            market = self.exchange.markets[symbol]
            lot_step = market.get("precision", {}).get("amount", 8)
            min_qty = market.get("limits", {}).get("amount", {}).get("min", 0.001)
            min_notional = market.get("limits", {}).get("cost", {}).get("min", 5.0)

            # Round down to lot step
            if isinstance(lot_step, int):
                factor = 10 ** lot_step
                qty = int(raw_qty * factor) / factor
            else:
                qty = raw_qty

            if qty < (min_qty or 0.001):
                return 0.0

            notional = qty * entry
            if notional < (min_notional or 5.0):
                return 0.0

            return qty

        return raw_qty

    async def execute_trade(self, slot: SlotState, signal: dict) -> bool:
        """Execute a trade for a slot based on a signal."""
        if slot.open_trade is not None:
            logger.debug(f"Slot {slot.config.slot_id} already has open trade — skipping")
            return False

        if slot.is_paused:
            logger.info(f"Slot {slot.config.slot_id} is PAUSED: {slot.pause_reason}")
            return False

        if self.global_pause:
            logger.warning("Portfolio GLOBAL PAUSE active — no new trades")
            return False

        symbol = slot.config.symbol
        direction = signal["direction"]
        entry = signal["entry"]
        stop = signal["stop"]

        qty = self.calculate_position_size(slot, entry, stop)
        if qty <= 0:
            logger.warning(f"Slot {slot.config.slot_id}: Position size too small, skipping")
            return False

        side = "buy" if direction == "LONG" else "sell"
        trade_id = f"asr_{slot.config.slot_id}_{int(time.time() * 1000)}"

        try:
            logger.info(
                f"📈 EXECUTING: Slot {slot.config.slot_id} | {symbol} {slot.config.timeframe} | "
                f"{direction} | Qty={qty:.6f} | Entry≈{entry:.4f} | SL={stop:.4f}"
            )

            # Place market order
            order = await self.exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=qty,
            )

            fill_price = float(order.get("average", order.get("price", entry)))
            filled_qty = float(order.get("filled", qty))

            # Record trade
            trade = TradeRecord(
                trade_id=trade_id,
                slot_id=slot.config.slot_id,
                symbol=symbol,
                timeframe=slot.config.timeframe,
                direction=direction,
                entry_price=fill_price,
                entry_time=datetime.now(timezone.utc).isoformat(),
                quantity=filled_qty,
                stop_loss=stop,
                tp1=signal.get("tp1"),
                tp2=signal.get("tp2"),
                status="OPEN",
                setup_type=signal.get("setup", ""),
                score=signal.get("score", 0),
            )

            slot.open_trade = trade
            slot.total_trades += 1
            self.all_trades.append(trade)

            logger.info(
                f"✅ FILLED: {trade_id} | {direction} {filled_qty:.6f} {symbol} @ {fill_price:.4f} | "
                f"SL={stop:.4f} | TP1={signal.get('tp1', 'N/A')}"
            )
            asyncio.create_task(self.send_telegram_message(
                f"🚀 <b>TRADE EXECUTED</b>\n\n"
                f"<b>Slot {slot.config.slot_id}</b> | {symbol} {slot.config.timeframe}\n"
                f"<b>Direction:</b> {direction}\n"
                f"<b>Entry:</b> {fill_price:.4f}\n"
                f"<b>Size:</b> {filled_qty:.6f}\n"
                f"<b>Stop Loss:</b> {stop:.4f}\n"
                f"<b>Score:</b> {signal.get('score', 0):.0f}"
            ))

            # Place stop loss order
            try:
                sl_side = "sell" if direction == "LONG" else "buy"
                await self.exchange.create_order(
                    symbol=symbol,
                    type="stop_market",
                    side=sl_side,
                    amount=filled_qty,
                    params={"stopPrice": stop, "reduceOnly": True},
                )
                logger.info(f"  🛡️ SL placed @ {stop:.4f}")
            except Exception as e:
                logger.error(f"  ⚠️ Failed to place SL: {e}")

            # Place TP1 (33% of position)
            if signal.get("tp1"):
                try:
                    tp1_qty = round(filled_qty * 0.33, 8)
                    tp1_side = "sell" if direction == "LONG" else "buy"
                    await self.exchange.create_order(
                        symbol=symbol,
                        type="take_profit_market",
                        side=tp1_side,
                        amount=tp1_qty,
                        params={"stopPrice": signal["tp1"], "reduceOnly": True},
                    )
                    logger.info(f"  🎯 TP1 placed @ {signal['tp1']:.4f} (qty={tp1_qty:.6f})")
                except Exception as e:
                    logger.error(f"  ⚠️ Failed to place TP1: {e}")

            self._save_trade_log(trade)
            return True

        except Exception as e:
            logger.error(f"❌ Trade execution failed for slot {slot.config.slot_id}: {e}")
            return False

    async def check_open_positions(self):
        """Monitor open positions and update trade states."""
        try:
            positions = await self.exchange.fetch_positions()
            open_syms = {}
            for p in positions:
                amt = float(p.get("info", {}).get("positionAmt", 0))
                if amt != 0:
                    open_syms[p["symbol"]] = p

            for slot_id, slot in self.slots.items():
                if slot.open_trade is None:
                    continue

                trade = slot.open_trade
                sym = trade.symbol.replace("/", "")

                if sym not in open_syms:
                    # Position was closed (SL or TP hit)
                    current_price = await self.fetch_current_price(trade.symbol)
                    if current_price:
                        if trade.direction == "LONG":
                            pnl = (current_price - trade.entry_price) * trade.quantity
                        else:
                            pnl = (trade.entry_price - current_price) * trade.quantity

                        risk_amount = abs(trade.entry_price - trade.stop_loss) * trade.quantity
                        pnl_r = pnl / risk_amount if risk_amount > 0 else 0

                        trade.exit_price = current_price
                        trade.exit_time = datetime.now(timezone.utc).isoformat()
                        trade.pnl_usd = pnl
                        trade.pnl_r = pnl_r
                        trade.status = "CLOSED"

                        slot.net_pnl += pnl
                        slot.current_equity += pnl
                        if pnl > 0:
                            slot.winning_trades += 1
                            slot.consecutive_losses = 0
                        else:
                            slot.losing_trades += 1
                            slot.consecutive_losses += 1

                        if slot.current_equity > slot.peak_equity:
                            slot.peak_equity = slot.current_equity

                        dd = (slot.peak_equity - slot.current_equity) / slot.peak_equity * 100
                        if dd > slot.max_drawdown_pct:
                            slot.max_drawdown_pct = dd

                        # Circuit breaker
                        if slot.consecutive_losses >= 3:
                            slot.is_paused = True
                            slot.pause_reason = "3 consecutive losses"
                            logger.warning(f"⛔ Slot {slot_id} PAUSED: 3 consecutive losses")
                            asyncio.create_task(self.send_telegram_message(f"⛔ <b>CIRCUIT BREAKER:</b> Slot {slot_id} PAUSED (3 consecutive losses)"))

                        if dd > 25:
                            slot.is_paused = True
                            slot.pause_reason = f"Max drawdown {dd:.1f}%"
                            logger.warning(f"⛔ Slot {slot_id} PAUSED: Drawdown {dd:.1f}%")
                            asyncio.create_task(self.send_telegram_message(f"⛔ <b>CIRCUIT BREAKER:</b> Slot {slot_id} PAUSED (Drawdown {dd:.1f}%)"))

                        logger.info(
                            f"{'🟢' if pnl > 0 else '🔴'} CLOSED: Slot {slot_id} | {trade.symbol} | "
                            f"PnL=${pnl:.2f} ({pnl_r:+.2f}R) | Equity=${slot.current_equity:.2f}"
                        )
                        emoji = '🟢' if pnl > 0 else '🔴'
                        asyncio.create_task(self.send_telegram_message(
                            f"{emoji} <b>TRADE CLOSED</b>\n\n"
                            f"<b>Slot {slot_id}</b> | {trade.symbol}\n"
                            f"<b>PnL:</b> ${pnl:.2f} ({pnl_r:+.2f}R)\n"
                            f"<b>Equity:</b> ${slot.current_equity:.2f}"
                        ))

                        slot.open_trade = None
                        self._save_trade_log(trade)

            # Portfolio-level drawdown check
            total_equity = sum(s.current_equity for s in self.slots.values())
            if total_equity > self.portfolio_peak_equity:
                self.portfolio_peak_equity = total_equity

            portfolio_dd = (self.portfolio_peak_equity - total_equity) / self.portfolio_peak_equity * 100
            if portfolio_dd > self.max_portfolio_dd_pct:
                self.global_pause = True
                logger.critical(f"🚨 GLOBAL KILL SWITCH: Portfolio drawdown {portfolio_dd:.1f}% > {self.max_portfolio_dd_pct}%")
                asyncio.create_task(self.send_telegram_message(f"🚨 <b>GLOBAL KILL SWITCH TRIGGERED</b>\nPortfolio drawdown {portfolio_dd:.1f}% exceeds limit."))

        except Exception as e:
            logger.error(f"Position check error: {e}")

    def _save_trade_log(self, trade: TradeRecord):
        """Append trade to CSV log."""
        log_file = self.results_dir / "trade_log.csv"
        trade_dict = asdict(trade)

        df = pd.DataFrame([trade_dict])
        if log_file.exists():
            df.to_csv(log_file, mode="a", header=False, index=False)
        else:
            df.to_csv(log_file, index=False)

    def save_portfolio_snapshot(self):
        """Save portfolio state snapshot to JSON."""
        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "portfolio": {
                "start_equity": self.portfolio_start_equity,
                "current_equity": sum(s.current_equity for s in self.slots.values()),
                "peak_equity": self.portfolio_peak_equity,
                "total_trades": sum(s.total_trades for s in self.slots.values()),
                "total_pnl": sum(s.net_pnl for s in self.slots.values()),
                "global_paused": self.global_pause,
            },
            "slots": {}
        }

        for sid, slot in self.slots.items():
            snapshot["slots"][str(sid)] = {
                "symbol": slot.config.symbol,
                "timeframe": slot.config.timeframe,
                "margin_asset": slot.config.margin_asset,
                "capital": slot.config.capital,
                "current_equity": slot.current_equity,
                "net_pnl": slot.net_pnl,
                "total_trades": slot.total_trades,
                "wins": slot.winning_trades,
                "losses": slot.losing_trades,
                "win_rate": (slot.winning_trades / slot.total_trades * 100) if slot.total_trades > 0 else 0,
                "max_dd_pct": slot.max_drawdown_pct,
                "is_paused": slot.is_paused,
                "has_open_trade": slot.open_trade is not None,
            }

        snapshot_file = self.results_dir / "portfolio_snapshot.json"
        with open(snapshot_file, "w") as f:
            json.dump(snapshot, f, indent=2)

        # Also append to history
        history_file = self.results_dir / "portfolio_history.jsonl"
        with open(history_file, "a") as f:
            f.write(json.dumps({
                "ts": snapshot["timestamp"],
                "equity": snapshot["portfolio"]["current_equity"],
                "pnl": snapshot["portfolio"]["total_pnl"],
                "trades": snapshot["portfolio"]["total_trades"],
            }) + "\n")

    def print_dashboard(self):
        """Print real-time portfolio dashboard to terminal."""
        total_equity = sum(s.current_equity for s in self.slots.values())
        total_pnl = sum(s.net_pnl for s in self.slots.values())
        total_trades = sum(s.total_trades for s in self.slots.values())
        total_wins = sum(s.winning_trades for s in self.slots.values())
        open_count = sum(1 for s in self.slots.values() if s.open_trade is not None)
        portfolio_dd = (self.portfolio_peak_equity - total_equity) / self.portfolio_peak_equity * 100 if self.portfolio_peak_equity > 0 else 0

        runtime = datetime.now(timezone.utc) - self.start_time
        hours = runtime.total_seconds() / 3600

        print("\n" + "=" * 80)
        print("  ASR ENGINE v3 — LIVE DEMO TRADING DASHBOARD")
        print("=" * 80)
        print(f"  Runtime: {hours:.1f}h | Mode: DEMO (Testnet) | Updated: {datetime.now().strftime('%H:%M:%S')}")
        print("-" * 80)
        print(f"  💰 Portfolio: ${total_equity:,.2f} (Start: ${self.portfolio_start_equity:,.2f})")
        print(f"  📊 PnL: ${total_pnl:+,.2f} ({total_pnl / self.portfolio_start_equity * 100:+.2f}%)")
        print(f"  📉 Max DD: {portfolio_dd:.2f}% | Peak: ${self.portfolio_peak_equity:,.2f}")
        print(f"  🔄 Trades: {total_trades} | Wins: {total_wins} | Open: {open_count}")
        if total_trades > 0:
            print(f"  📈 Win Rate: {total_wins / total_trades * 100:.1f}%")
        print("-" * 80)
        print(f"  {'Slot':>4} | {'Symbol':<10} | {'TF':<5} | {'Margin':<5} | {'Equity':>10} | {'PnL':>10} | {'Trades':>6} | {'Status':<10}")
        print("  " + "-" * 76)

        for sid in sorted(self.slots.keys()):
            s = self.slots[sid]
            status = "🔴 PAUSED" if s.is_paused else ("📈 OPEN" if s.open_trade else "✅ READY")
            print(
                f"  {sid:>4} | {s.config.exchange_symbol:<10} | {s.config.timeframe:<5} | "
                f"{s.config.margin_asset:<5} | ${s.current_equity:>9,.2f} | "
                f"${s.net_pnl:>+9,.2f} | {s.total_trades:>6} | {status}"
            )
        print("=" * 80 + "\n")

    async def run_cycle(self):
        """Run one complete trading cycle across all slots."""
        for slot_id, slot in self.slots.items():
            if slot.is_paused or self.global_pause:
                continue

            if slot.open_trade is not None:
                continue  # Already in a trade

            try:
                # Fetch latest candles
                df = await self.fetch_ohlcv(slot.config.symbol, slot.config.timeframe, limit=200)
                if df.empty:
                    continue

                slot.bars_buffer = df

                # Generate signals
                signals = self.generate_asr_signals(df, slot)

                if signals:
                    best = max(signals, key=lambda s: s["score"])
                    logger.info(
                        f"🔔 SIGNAL: Slot {slot_id} | {slot.config.exchange_symbol} {slot.config.timeframe} | "
                        f"{best['direction']} | Score={best['score']:.0f} | Entry={best['entry']:.4f}"
                    )
                    await self.execute_trade(slot, best)

            except Exception as e:
                logger.error(f"Cycle error for slot {slot_id}: {e}")

            # Small delay between slots to respect rate limits
            await asyncio.sleep(0.5)

        # Check open positions
        await self.check_open_positions()

        # Save snapshot
        self.save_portfolio_snapshot()

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("🛑 Shutting down Auto Trader...")
        self.is_running = False

        # Cancel all open orders
        if self.exchange:
            for slot_id, slot in self.slots.items():
                if slot.open_trade:
                    try:
                        await self.exchange.cancel_all_orders(slot.config.symbol)
                        logger.info(f"Cancelled orders for slot {slot_id} ({slot.config.symbol})")
                    except Exception as e:
                        logger.error(f"Error cancelling orders for slot {slot_id}: {e}")

            await self.exchange.close()

        # Final save
        self.save_portfolio_snapshot()
        self._save_final_report()
        logger.info("✅ Shutdown complete. Results saved.")

    def _save_final_report(self):
        """Save final session report."""
        total_equity = sum(s.current_equity for s in self.slots.values())
        total_pnl = sum(s.net_pnl for s in self.slots.values())
        total_trades = sum(s.total_trades for s in self.slots.values())
        runtime = datetime.now(timezone.utc) - self.start_time

        report = {
            "session": {
                "start": self.start_time.isoformat(),
                "end": datetime.now(timezone.utc).isoformat(),
                "runtime_hours": runtime.total_seconds() / 3600,
            },
            "results": {
                "start_equity": self.portfolio_start_equity,
                "end_equity": total_equity,
                "net_pnl": total_pnl,
                "return_pct": (total_pnl / self.portfolio_start_equity) * 100 if self.portfolio_start_equity > 0 else 0,
                "total_trades": total_trades,
                "peak_equity": self.portfolio_peak_equity,
            },
        }

        with open(self.results_dir / "session_report.json", "w") as f:
            json.dump(report, f, indent=2)


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def get_cycle_interval(slots: Dict[int, SlotState]) -> int:
    """Determine cycle interval based on fastest timeframe in portfolio."""
    tf_seconds = {
        "1m": 60, "3m": 180, "5m": 300, "10m": 600,
        "15m": 900, "30m": 1800, "45m": 2700,
        "1h": 3600, "4h": 14400, "1d": 86400,
    }

    min_tf = min(
        tf_seconds.get(s.config.timeframe, 3600)
        for s in slots.values()
    )

    # Run at ~1/3 of the fastest TF to catch signals early
    return max(20, min_tf // 3)


async def main():
    config_path = Path(__file__).parent / "config" / "portfolio_allocation.yaml"

    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)

    pm = PortfolioManager(str(config_path))

    # Handle graceful shutdown
    loop = asyncio.get_event_loop()
    shutdown_event = asyncio.Event()

    def handle_shutdown(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        shutdown_event.set()

    for sig in [os_signal.SIGINT, os_signal.SIGTERM]:
        try:
            os_signal.signal(sig, handle_shutdown)
        except (ValueError, OSError):
            pass  # Windows doesn't support all signals

    # Initialize exchange
    await pm.initialize_exchange()

    pm.is_running = True
    cycle_interval = get_cycle_interval(pm.slots)

    logger.info(f"🚀 Auto Trader STARTED | {len(pm.slots)} slots | Cycle interval: {cycle_interval}s")
    logger.info("=" * 60)

    pm.print_dashboard()

    cycle_count = 0
    try:
        while pm.is_running and not shutdown_event.is_set():
            cycle_count += 1
            logger.info(f"--- Cycle {cycle_count} ---")

            await pm.run_cycle()

            # Print dashboard every 5 cycles
            if cycle_count % 5 == 0:
                pm.print_dashboard()

            # Wait for next cycle
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=cycle_interval)
                break
            except asyncio.TimeoutError:
                pass

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        await pm.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
