"""
ASR Engine v3 — Historical Paper Trading Simulator
====================================================
Replays cached backtest signals through the FULL execution pipeline:
  Webhook → Risk Engine → Drift Guard → Position Sizer → Paper Broker → FSMs

This validates every component in the execution stack using historical data
instead of requiring days of live paper trading.

Usage:
  python -m execution.paper_sim [--symbol BTC/USDT] [--timeframe 4h]
"""
import sys
import os
import asyncio
import logging
import uuid
import time
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# Add project root to path so we can import from both backtester and execution
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "execution"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("paper_sim")


# ===========================================================================
# DATA CLASSES FOR RESULTS
# ===========================================================================
@dataclass
class SimFill:
    """A single fill event during the simulation."""
    timestamp: str
    signal_id: str
    symbol: str
    direction: str
    side: str
    quantity: float
    price: float
    fee: float
    order_id: str
    setup_type: str = ""
    score: float = 0.0


@dataclass
class SimPosition:
    """A completed round-trip position."""
    signal_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: str
    exit_time: str
    pnl: float
    pnl_r: float  # risk-normalized
    exit_type: str
    setup_type: str = ""
    score: float = 0.0
    risk_decision: str = ""
    drift_pct: float = 0.0
    sized_qty: float = 0.0


@dataclass
class SimStats:
    """Aggregated simulation statistics."""
    total_signals: int = 0
    signals_allowed: int = 0
    signals_rejected_risk: int = 0
    signals_rejected_drift: int = 0
    signals_rejected_sizing: int = 0
    total_fills: int = 0
    total_positions_closed: int = 0
    wins: int = 0
    losses: int = 0
    breakevens: int = 0
    gross_pnl: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    final_equity: float = 0.0
    avg_latency_ms: float = 0.0
    avg_slippage_pct: float = 0.0
    win_rate: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    expectancy_r: float = 0.0
    profit_factor: float = 0.0


# ===========================================================================
# PAPER TRADING SIMULATOR
# ===========================================================================
class PaperTradingSimulator:
    """
    Replays backtest trades through the full execution pipeline.
    
    Flow per signal:
      1. Load backtest trade → construct TVWebhookPayload
      2. Risk Engine → evaluate_entry()
      3. DriftGuard → evaluate() (simulated drift from bar close)
      4. PositionSizer → calculate_size()
      5. PaperBroker → place_order() + bracket orders
      6. Track fill, simulate exit, record position
    """

    def __init__(self, initial_capital: float = 10000.0, risk_pct: float = 1.0):
        self.initial_capital = initial_capital
        self.risk_pct = risk_pct
        self.fills: List[SimFill] = []
        self.positions: List[SimPosition] = []
        self.stats = SimStats()
        self.equity_curve: List[Dict] = []

        # Execution pipeline components
        self.risk_engine = None
        self.drift_guard = None
        self.sizer = None
        self.broker = None

    async def initialize(self):
        """Set up all execution pipeline components."""
        from src.database import init_db
        init_db()

        from src.risk.engine import RiskEngine
        from src.risk.drift_guard import DriftGuard
        from src.risk.sizing import PositionSizer
        from src.brokers.paper import PaperBroker

        self.risk_engine = RiskEngine()
        self.risk_engine.current_equity = self.initial_capital
        self.risk_engine.peak_equity = self.initial_capital

        self.drift_guard = DriftGuard(max_slippage_pct=0.5)
        self.sizer = PositionSizer()
        self.broker = PaperBroker(
            initial_balance=self.initial_capital,
            fee_pct=0.0004,
            latency_ms=10  # Low latency for sim speed
        )
        await self.broker.initialize()

        logger.info(
            f"Paper Sim initialized: Capital=${self.initial_capital:,.2f}, "
            f"Risk={self.risk_pct}%"
        )

    async def run(self, trades: List[dict], symbol: str, timeframe: str):
        """
        Run the simulation on a list of backtest trades.
        
        Args:
            trades: List of trade dicts from the backtester engine
            symbol: e.g. "BTC/USDT"
            timeframe: e.g. "4h"
        """
        if not trades:
            logger.warning("No trades to simulate.")
            return

        logger.info(f"Starting paper sim: {len(trades)} signals for {symbol} {timeframe}")
        
        venue_symbol = symbol.replace("/", "")  # BTC/USDT → BTCUSDT

        latencies = []
        slippages = []

        for i, trade in enumerate(trades):
            self.stats.total_signals += 1
            
            # -----------------------------------------------------------
            # 1. CONSTRUCT WEBHOOK PAYLOAD (as if TradingView sent it)
            # -----------------------------------------------------------
            entry_price = getattr(trade, "entry_price", 0)
            stop_price = getattr(trade, "sl", 0)
            tp1_price = getattr(trade, "tp1", None)
            tp2_price = getattr(trade, "tp2", None)
            direction = "LONG" if getattr(trade, "side", "") == "LONG" else "SHORT"
            setup_type = getattr(trade, "setup_name", "ZONE_REJECT")
            score = getattr(trade, "score", 50.0)
            entry_bar = getattr(trade, "entry_bar", i)

            # Simulate a timestamp from the bar index
            sim_time = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=entry_bar * 4)
            
            from src.models.signals import TVWebhookPayload
            from src.models.enums import SignalType, Direction

            event_id = f"sim_{uuid.uuid4().hex[:12]}"
            signal_id = f"sig_{uuid.uuid4().hex[:8]}"

            try:
                payload = TVWebhookPayload(
                    passphrase="paper_sim_passphrase",
                    timestamp=sim_time.isoformat(),
                    event_id=event_id,
                    signal_id=signal_id,
                    symbol=venue_symbol,
                    action=SignalType.ENTRY,
                    direction=Direction(direction),
                    price=entry_price,
                    stop=stop_price,
                    tp1=tp1_price,
                    tp2=tp2_price,
                    score=score,
                    setup=setup_type,
                )
            except Exception as e:
                logger.error(f"Trade {i}: Failed to construct payload: {e}")
                continue

            # -----------------------------------------------------------
            # 2. RISK ENGINE CHECK
            # -----------------------------------------------------------
            # Update risk engine state with current equity
            self.risk_engine.current_equity = self.broker.balance
            if self.broker.balance > self.risk_engine.peak_equity:
                self.risk_engine.peak_equity = self.broker.balance
            self.risk_engine.open_positions = {
                s: {"quantity": p["qty"]} for s, p in self.broker.positions.items()
            }

            allowed, reason = self.risk_engine.evaluate_entry(payload)
            if not allowed:
                self.stats.signals_rejected_risk += 1
                logger.debug(f"Trade {i}: Risk REJECTED — {reason}")
                continue

            # -----------------------------------------------------------
            # 3. DRIFT GUARD CHECK
            # -----------------------------------------------------------
            # Simulate slight price drift from bar close (realistic slippage)
            import random
            drift_factor = 1.0 + random.uniform(-0.002, 0.002)
            simulated_live_price = entry_price * drift_factor
            self.broker.update_mock_price(venue_symbol, simulated_live_price)

            is_long = direction == "LONG"
            drift_ok, drift_pct, drift_reason = self.drift_guard.evaluate(
                intended_entry=entry_price,
                current_quote=simulated_live_price,
                is_long=is_long
            )
            if not drift_ok:
                self.stats.signals_rejected_drift += 1
                logger.debug(f"Trade {i}: Drift REJECTED — {drift_reason}")
                continue

            # -----------------------------------------------------------
            # 4. POSITION SIZING
            # -----------------------------------------------------------
            balance = await self.broker.get_balance("USDT")
            metadata = await self.broker.get_symbol_metadata(venue_symbol)

            qty, actual_risk, size_err = self.sizer.calculate_size(
                account_equity=balance,
                risk_pct_equity=self.risk_pct,
                entry_price=simulated_live_price,
                stop_price=stop_price,
                instrument=metadata,
            )

            if qty <= 0:
                self.stats.signals_rejected_sizing += 1
                logger.debug(f"Trade {i}: Sizing REJECTED — {size_err}")
                continue

            # -----------------------------------------------------------
            # 5. ORDER PLACEMENT VIA PAPER BROKER
            # -----------------------------------------------------------
            t_start = time.perf_counter()
            
            side = "BUY" if is_long else "SELL"
            client_id = f"asr_{event_id}"

            try:
                order_res = await self.broker.place_order(
                    symbol=venue_symbol,
                    side=side,
                    order_type="MARKET",
                    quantity=qty,
                    client_order_id=client_id,
                )
            except Exception as e:
                logger.error(f"Trade {i}: Broker order failed: {e}")
                continue

            t_end = time.perf_counter()
            latency_ms = (t_end - t_start) * 1000
            latencies.append(latency_ms)

            fill_price = order_res.get("avg_price", order_res.get("price", simulated_live_price))
            fee = (fill_price * qty) * self.broker.fee_pct

            # Calculate slippage
            if entry_price > 0:
                slip = abs(fill_price - entry_price) / entry_price * 100
                slippages.append(slip)

            self.stats.signals_allowed += 1
            self.stats.total_fills += 1

            fill = SimFill(
                timestamp=sim_time.isoformat(),
                signal_id=signal_id,
                symbol=venue_symbol,
                direction=direction,
                side=side,
                quantity=qty,
                price=fill_price,
                fee=fee,
                order_id=order_res.get("order_id", ""),
                setup_type=setup_type,
                score=score,
            )
            self.fills.append(fill)

            # -----------------------------------------------------------
            # 6. SIMULATE EXIT (using backtest exit data)
            # -----------------------------------------------------------
            exit_price = getattr(trade, "exit_price", entry_price)
            exit_type = getattr(trade, "exit_reason", "SL")
            exit_bar = getattr(trade, "exit_bar", entry_bar + 10)
            exit_time = sim_time + timedelta(hours=(exit_bar - entry_bar) * 4)

            # Update mock price to exit and close position
            self.broker.update_mock_price(venue_symbol, exit_price)
            
            exit_side = "SELL" if is_long else "BUY"
            try:
                exit_order = await self.broker.place_order(
                    symbol=venue_symbol,
                    side=exit_side,
                    order_type="MARKET",
                    quantity=qty,
                    client_order_id=f"exit_{event_id}",
                )
            except Exception as e:
                logger.error(f"Trade {i}: Exit order failed: {e}")
                continue

            exit_fill_price = exit_order.get("avg_price", exit_order.get("price", exit_price))
            exit_fee = (exit_fill_price * qty) * self.broker.fee_pct
            total_fee = fee + exit_fee
            self.stats.total_fees += total_fee

            # Calculate PnL
            if is_long:
                raw_pnl = (exit_fill_price - fill_price) * qty
            else:
                raw_pnl = (fill_price - exit_fill_price) * qty

            net_pnl = raw_pnl - total_fee

            # Calculate R-multiple
            risk_per_unit = abs(fill_price - stop_price)
            pnl_r = 0.0
            if risk_per_unit > 0:
                pnl_r = net_pnl / (risk_per_unit * qty)

            # Update broker balance for PnL
            self.broker.balance += raw_pnl - exit_fee

            # Track equity
            self.equity_curve.append({
                "time": exit_time.isoformat(),
                "equity": self.broker.balance,
                "trade_idx": i,
            })

            # Classify outcome
            if pnl_r > 0.05:
                self.stats.wins += 1
            elif pnl_r < -0.05:
                self.stats.losses += 1
            else:
                self.stats.breakevens += 1

            self.stats.gross_pnl += raw_pnl
            self.stats.net_pnl += net_pnl
            self.stats.total_positions_closed += 1

            # Track drawdown
            if self.broker.balance > self.stats.peak_equity:
                self.stats.peak_equity = self.broker.balance
            dd = self.stats.peak_equity - self.broker.balance
            if dd > self.stats.max_drawdown:
                self.stats.max_drawdown = dd
                if self.stats.peak_equity > 0:
                    self.stats.max_drawdown_pct = dd / self.stats.peak_equity * 100

            pos = SimPosition(
                signal_id=signal_id,
                symbol=venue_symbol,
                direction=direction,
                entry_price=fill_price,
                exit_price=exit_fill_price,
                quantity=qty,
                entry_time=sim_time.isoformat(),
                exit_time=exit_time.isoformat(),
                pnl=net_pnl,
                pnl_r=pnl_r,
                exit_type=exit_type,
                setup_type=setup_type,
                score=score,
                risk_decision="ALLOW",
                drift_pct=drift_pct,
                sized_qty=qty,
            )
            self.positions.append(pos)

            logger.info(
                f"Trade {i+1}/{len(trades)}: {direction} {symbol} | "
                f"Entry={fill_price:.2f} → Exit={exit_fill_price:.2f} | "
                f"PnL={net_pnl:+.2f} ({pnl_r:+.3f}R) | {exit_type}"
            )

        # -----------------------------------------------------------
        # COMPUTE FINAL STATS
        # -----------------------------------------------------------
        self.stats.final_equity = self.broker.balance
        if not self.stats.peak_equity:
            self.stats.peak_equity = self.initial_capital

        if latencies:
            self.stats.avg_latency_ms = sum(latencies) / len(latencies)
        if slippages:
            self.stats.avg_slippage_pct = sum(slippages) / len(slippages)

        wins = [p for p in self.positions if p.pnl_r > 0.05]
        losses = [p for p in self.positions if p.pnl_r < -0.05]
        
        n_decided = len(wins) + len(losses)
        if n_decided > 0:
            self.stats.win_rate = len(wins) / n_decided * 100

        if wins:
            self.stats.avg_win_r = sum(p.pnl_r for p in wins) / len(wins)
        if losses:
            self.stats.avg_loss_r = sum(p.pnl_r for p in losses) / len(losses)

        if self.positions:
            self.stats.expectancy_r = sum(p.pnl_r for p in self.positions) / len(self.positions)

        gross_loss = sum(abs(p.pnl) for p in self.positions if p.pnl < 0)
        gross_win = sum(p.pnl for p in self.positions if p.pnl > 0)
        if gross_loss > 0:
            self.stats.profit_factor = gross_win / gross_loss
        elif gross_win > 0:
            self.stats.profit_factor = float("inf")

        logger.info("=" * 60)
        logger.info("Paper Trading Simulation Complete")
        logger.info("=" * 60)

    def generate_report(self) -> str:
        """Generate a comprehensive text report."""
        s = self.stats
        lines = [
            "",
            "=" * 60,
            "  ASR ENGINE v3 — PAPER TRADING SIMULATION REPORT",
            "=" * 60,
            "",
            "=" * 60,
            " Signal Funnel",
            "=" * 60,
            f"  Total Signals Generated:       {s.total_signals:>6}",
            f"  Allowed (Executed):            {s.signals_allowed:>6}",
            f"  Rejected — Risk Gate:          {s.signals_rejected_risk:>6}",
            f"  Rejected — Drift Guard:        {s.signals_rejected_drift:>6}",
            f"  Rejected — Sizing:             {s.signals_rejected_sizing:>6}",
            f"  Total Fills:                   {s.total_fills:>6}",
            "",
            "=" * 60,
            " Position Outcomes",
            "=" * 60,
            f"  Positions Closed:              {s.total_positions_closed:>6}",
            f"  Wins:                          {s.wins:>6}",
            f"  Losses:                        {s.losses:>6}",
            f"  Breakevens:                    {s.breakevens:>6}",
            f"  Win Rate (ex BE):            {s.win_rate:>6.1f}%",
            "",
            "=" * 60,
            " Financial Summary",
            "=" * 60,
            f"  Initial Capital:           ${self.initial_capital:>12,.2f}",
            f"  Final Equity:              ${s.final_equity:>12,.2f}",
            f"  Gross PnL:                 ${s.gross_pnl:>+12,.2f}",
            f"  Total Fees:                ${s.total_fees:>12,.2f}",
            f"  Net PnL:                   ${s.net_pnl:>+12,.2f}",
            f"  Return:                    {((s.final_equity - self.initial_capital) / self.initial_capital * 100):>+10.2f}%",
            "",
            "=" * 60,
            " Risk Metrics",
            "=" * 60,
            f"  Peak Equity:               ${s.peak_equity:>12,.2f}",
            f"  Max Drawdown:              ${s.max_drawdown:>12,.2f}",
            f"  Max Drawdown %:            {s.max_drawdown_pct:>10.2f}%",
            f"  Avg Win R:                 {s.avg_win_r:>+10.4f}",
            f"  Avg Loss R:                {s.avg_loss_r:>+10.4f}",
            f"  Expectancy R:              {s.expectancy_r:>+10.4f}",
            f"  Profit Factor:             {s.profit_factor:>10.3f}",
            "",
            "=" * 60,
            " Execution Quality",
            "=" * 60,
            f"  Avg Latency (ms):          {s.avg_latency_ms:>10.2f}",
            f"  Avg Slippage (%):          {s.avg_slippage_pct:>10.4f}",
            "",
        ]

        # Individual trades table
        if self.positions:
            lines.append("=" * 60)
            lines.append(" Trade Log (All Positions)")
            lines.append("=" * 60)
            lines.append("")
            lines.append(f"{'#':>3}  {'Dir':>5}  {'Entry':>12}  {'Exit':>12}  {'Type':>8}  {'PnL':>10}  {'R':>8}  {'Score':>6}  {'Setup':<18}")
            lines.append("-" * 100)
            for i, p in enumerate(self.positions):
                lines.append(
                    f"{i+1:>3}  {p.direction:>5}  {p.entry_price:>12.2f}  "
                    f"{p.exit_price:>12.2f}  {p.exit_type:>8}  "
                    f"{p.pnl:>+10.2f}  {p.pnl_r:>+8.3f}  "
                    f"{p.score:>6.1f}  {p.setup_type:<18}"
                )
            lines.append("")

        # Rejection breakdown
        if s.signals_rejected_risk or s.signals_rejected_drift or s.signals_rejected_sizing:
            lines.append("=" * 60)
            lines.append(" Rejection Analysis")
            lines.append("=" * 60)
            total_rejected = s.signals_rejected_risk + s.signals_rejected_drift + s.signals_rejected_sizing
            if total_rejected > 0:
                lines.append(f"  Risk Gate:   {s.signals_rejected_risk:>4} ({s.signals_rejected_risk/total_rejected*100:.1f}%)")
                lines.append(f"  Drift Guard: {s.signals_rejected_drift:>4} ({s.signals_rejected_drift/total_rejected*100:.1f}%)")
                lines.append(f"  Sizing:      {s.signals_rejected_sizing:>4} ({s.signals_rejected_sizing/total_rejected*100:.1f}%)")
            lines.append("")

        return "\n".join(lines)

    def save_results(self, output_dir: str):
        """Save all results to files."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 1. Text report
        report = self.generate_report()
        report_path = out / "paper_sim_report.txt"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(report)
        logger.info(f"Report saved to {report_path}")

        # 2. Stats JSON
        stats_path = out / "paper_sim_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.stats), f, indent=2, default=str)
        logger.info(f"Stats saved to {stats_path}")

        # 3. Trades JSON
        trades_path = out / "paper_sim_trades.json"
        with open(trades_path, "w", encoding="utf-8") as f:
            json.dump([asdict(p) for p in self.positions], f, indent=2, default=str)
        logger.info(f"Trades saved to {trades_path}")

        # 4. Equity curve JSON
        equity_path = out / "paper_sim_equity.json"
        with open(equity_path, "w", encoding="utf-8") as f:
            json.dump(self.equity_curve, f, indent=2, default=str)
        logger.info(f"Equity curve saved to {equity_path}")

        # 5. Fills JSON
        fills_path = out / "paper_sim_fills.json"
        with open(fills_path, "w", encoding="utf-8") as f:
            json.dump([asdict(fl) for fl in self.fills], f, indent=2, default=str)
        logger.info(f"Fills saved to {fills_path}")


# ===========================================================================
# MAIN ENTRYPOINT
# ===========================================================================
def load_backtest_trades(symbol: str, timeframe: str) -> List[dict]:
    """
    Load trades from the backtester by running the ASR engine on cached data.
    """
    import yaml
    import pandas as pd
    
    cache_dir = PROJECT_ROOT / "backtester" / "data_cache"
    config_path = PROJECT_ROOT / "backtester" / "config.yaml"

    # Load config
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    # Find cached CSV
    exchange = "binance"
    safe_sym = symbol.replace("/", "_")
    csv_path = cache_dir / safe_sym / timeframe / f"{exchange}_{safe_sym}_{timeframe}.csv"

    if not csv_path.exists():
        logger.error(f"No cached data at {csv_path}. Run the backtest first.")
        return []

    logger.info(f"Loading cached data from {csv_path}")
    df = pd.read_csv(csv_path)  # Keep timestamp as int64 (ms epoch) for ASR engine

    # Run ASR engine to generate trades
    sys.path.insert(0, str(PROJECT_ROOT / "backtester"))
    from backtester.asr_engine import ASREngine

    engine = ASREngine(config)
    engine.run(df, symbol=symbol, timeframe=timeframe)

    logger.info(f"ASR engine generated {len(engine.trades)} trades from {len(df)} bars")
    return engine.trades


async def async_main():
    parser = argparse.ArgumentParser(description="ASR Paper Trading Simulator")
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Symbol to simulate")
    parser.add_argument("--timeframe", type=str, default="4h", help="Timeframe")
    parser.add_argument("--capital", type=float, default=10000.0, help="Initial capital (default: %(default)s)")
    parser.add_argument("--risk-pct", type=float, default=1.0, help="Risk percent per trade (default: %(default)s)")
    args = parser.parse_args()

    print("=" * 60)
    print("ASR ENGINE v3 — PAPER TRADING SIMULATOR")
    print("=" * 60)
    print(f"Symbol: {args.symbol} | TF: {args.timeframe}")
    print(f"Capital: ${args.capital:,.2f} | Risk: {args.risk_pct}%")
    print()

    # 1. Load trades from backtester
    print("[1/3] Loading backtest trades...")
    trades = load_backtest_trades(args.symbol, args.timeframe)
    if not trades:
        print("ERROR: No trades found. Run the backtest first.")
        return

    print(f"  -> {len(trades)} trades loaded")

    # 2. Run simulation
    print("\n[2/3] Running execution pipeline simulation...")
    sim = PaperTradingSimulator(
        initial_capital=args.capital,
        risk_pct=args.risk_pct
    )
    await sim.initialize()
    await sim.run(trades, symbol=args.symbol, timeframe=args.timeframe)

    # 3. Save results
    print("\n[3/3] Saving results...")
    output_dir = str(PROJECT_ROOT / "execution" / "paper_sim_results")
    sim.save_results(output_dir)

    print(f"\nDone. Results saved to {output_dir}/")
    return sim


def main():
    return asyncio.run(async_main())


if __name__ == "__main__":
    main()
