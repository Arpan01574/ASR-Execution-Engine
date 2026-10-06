"""
ASR Engine v3 — Reporting Engine
=================================
Formatted statistics output for console and file.
Supports breakdown by: year, symbol, timeframe, setup, zone tier,
regime, session, direction, score bucket.

Flags < 300 trades as statistically unreliable.
"""
import logging
from typing import List, Dict, Optional
from io import StringIO

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Statistical reliability threshold
MIN_RELIABLE_TRADES = 300


# ============================================================
# TRADE RESULT → DATAFRAME
# ============================================================
def trades_to_dataframe(trades) -> pd.DataFrame:
    """Convert list of TradeResult objects to a DataFrame for analysis."""
    if not trades:
        return pd.DataFrame()

    rows = []
    for t in trades:
        rows.append({
            "entry_bar": t.entry_bar,
            "exit_bar": t.exit_bar,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "direction": t.side,
            "entry_price": t.entry_price,
            "stop_price": t.sl,
            "tp1_price": t.tp1,
            "tp2_price": t.tp2,
            "exit_price": t.exit_price,
            "exit_type": t.exit_reason,
            "gross_r": t.gross_r,
            "fee_r": t.gross_r - t.net_r,
            "net_r": t.net_r,
            "score": t.score,
            "setup_type": t.setup_name,
            "zone_tier": t.zone_tier,
            "regime": t.regime,
            "hold_bars": t.bars_held,
            "symbol": t.symbol,
            "timeframe": t.timeframe,
            "mae_r": getattr(t, "mae_r", 0.0),
            "mfe_r": getattr(t, "mfe_r", 0.0),
        })

    return pd.DataFrame(rows)


def _exit_type_name(exit_type: int) -> str:
    """Convert exit type int to human-readable name."""
    names = {
        1: "STOP_LOSS",
        2: "BE_AFTER_TP1",
        3: "TP2",
        4: "TIME_STOP",
        5: "TP1_FULL",
        6: "TRAIL_STOP",
    }
    return names.get(exit_type, f"UNKNOWN_{exit_type}")


# ============================================================
# CORE STATISTICS CALCULATOR
# ============================================================
def calculate_stats(trades_df: pd.DataFrame) -> dict:
    """
    Calculate comprehensive trade statistics.

    Returns dict with all Prompt 3 required statistics:
      trade_count, win_rate_ex_BE, win_rate_including_BE, BE_rate,
      loss_rate, avg_win_R, avg_loss_R, expectancy_R, profit_factor,
      net_R, max_DD_R, longest_loss_streak, average_hold_bars,
      Sharpe, Sortino, payoff_ratio, MAE, MFE
    """
    if trades_df.empty:
        return {"trade_count": 0, "error": "No trades"}

    n = len(trades_df)
    net_rs = trades_df["net_r"].values

    # Win/Loss/BE classification
    wins = trades_df[trades_df["net_r"] > 0.1]
    losses = trades_df[trades_df["net_r"] < -0.1]
    breakevens = trades_df[(trades_df["net_r"] >= -0.1) & (trades_df["net_r"] <= 0.1)]

    n_win = len(wins)
    n_loss = len(losses)
    n_be = len(breakevens)

    # Rates
    win_rate_ex_be = (n_win / (n_win + n_loss) * 100) if (n_win + n_loss) > 0 else 0
    win_rate_inc_be = (n_win / n * 100) if n > 0 else 0
    be_rate = (n_be / n * 100) if n > 0 else 0
    loss_rate = (n_loss / n * 100) if n > 0 else 0

    # Average R
    avg_win_r = float(wins["net_r"].mean()) if n_win > 0 else 0
    avg_loss_r = float(losses["net_r"].mean()) if n_loss > 0 else 0

    # Expectancy
    expectancy = float(net_rs.mean()) if n > 0 else 0

    # Profit factor
    gross_profit = float(wins["net_r"].sum()) if n_win > 0 else 0
    gross_loss = abs(float(losses["net_r"].sum())) if n_loss > 0 else 0.001
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Net R
    net_r_total = float(net_rs.sum())

    # Max drawdown (in R)
    cum_r = np.cumsum(net_rs)
    peak = np.maximum.accumulate(cum_r)
    drawdowns = peak - cum_r
    max_dd_r = float(drawdowns.max()) if len(drawdowns) > 0 else 0

    # Longest loss streak
    streak = 0
    max_streak = 0
    for r in net_rs:
        if r < -0.1:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # Average hold bars
    avg_hold = float(trades_df["hold_bars"].mean()) if "hold_bars" in trades_df else 0

    # Sharpe (annualized, using R values)
    if len(net_rs) > 1 and np.std(net_rs) > 0:
        sharpe = float(np.mean(net_rs) / np.std(net_rs) * np.sqrt(252))
    else:
        sharpe = 0.0

    # Sortino (using downside deviation)
    downside = net_rs[net_rs < 0]
    if len(downside) > 1 and np.std(downside) > 0:
        sortino = float(np.mean(net_rs) / np.std(downside) * np.sqrt(252))
    else:
        sortino = 0.0

    # Payoff ratio
    payoff_ratio = abs(avg_win_r / avg_loss_r) if avg_loss_r != 0 else 0

    # MAE / MFE
    avg_mae = float(trades_df["mae_r"].mean()) if "mae_r" in trades_df and trades_df["mae_r"].notna().any() else 0
    avg_mfe = float(trades_df["mfe_r"].mean()) if "mfe_r" in trades_df and trades_df["mfe_r"].notna().any() else 0

    stats = {
        "trade_count": n,
        "wins": n_win,
        "losses": n_loss,
        "breakevens": n_be,
        "win_rate_ex_BE": round(win_rate_ex_be, 2),
        "win_rate_including_BE": round(win_rate_inc_be, 2),
        "BE_rate": round(be_rate, 2),
        "loss_rate": round(loss_rate, 2),
        "avg_win_R": round(avg_win_r, 4),
        "avg_loss_R": round(avg_loss_r, 4),
        "expectancy_R": round(expectancy, 4),
        "profit_factor": round(profit_factor, 3),
        "net_R": round(net_r_total, 2),
        "max_DD_R": round(max_dd_r, 2),
        "longest_loss_streak": max_streak,
        "average_hold_bars": round(avg_hold, 1),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "payoff_ratio": round(payoff_ratio, 3),
        "avg_MAE_R": round(avg_mae, 4),
        "avg_MFE_R": round(avg_mfe, 4),
        "statistically_reliable": n >= MIN_RELIABLE_TRADES,
    }

    return stats


# ============================================================
# GROUPED STATISTICS
# ============================================================
def stats_by_group(trades_df: pd.DataFrame, group_key: str) -> pd.DataFrame:
    """
    Calculate statistics grouped by a specific key.

    Supported group keys:
      year, symbol, timeframe, setup_type, zone_tier,
      regime, direction, score_bucket, exit_type
    """
    if trades_df.empty:
        return pd.DataFrame()

    df = trades_df.copy()

    # Create derived grouping columns
    if group_key == "year" and "entry_time" in df.columns:
        df["_group"] = pd.to_datetime(df["entry_time"]).dt.year
    elif group_key == "score_bucket":
        bins = [0, 40, 50, 60, 70, 80, 90, 101]
        labels = ["0-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]
        df["_group"] = pd.cut(df["score"], bins=bins, labels=labels, right=False)
    elif group_key in df.columns:
        df["_group"] = df[group_key]
    else:
        logger.warning(f"Unknown group key: {group_key}")
        return pd.DataFrame()

    rows = []
    for name, group in df.groupby("_group", observed=True):
        net_rs = group["net_r"].values
        n = len(net_rs)
        wins = (net_rs > 0.1).sum()
        losses = (net_rs < -0.1).sum()
        bes = n - wins - losses

        cum = np.cumsum(net_rs)
        peak = np.maximum.accumulate(cum)
        max_dd = float((peak - cum).max()) if len(cum) > 0 else 0

        rows.append({
            group_key: name,
            "trades": n,
            "wins": int(wins),
            "losses": int(losses),
            "BEs": int(bes),
            "win_rate_%": round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
            "avg_R": round(float(net_rs.mean()), 4),
            "net_R": round(float(net_rs.sum()), 2),
            "PF": round(float(net_rs[net_rs > 0].sum() / max(abs(net_rs[net_rs < 0].sum()), 0.001)), 2),
            "max_DD_R": round(max_dd, 2),
            "reliable": "✅" if n >= MIN_RELIABLE_TRADES else "⚠️",
        })

    return pd.DataFrame(rows)


# ============================================================
# FORMATTED OUTPUT
# ============================================================
def format_stats_report(stats: dict, title: str = "Backtest Results") -> str:
    """Format statistics as a nicely formatted console report."""
    buf = StringIO()
    w = buf.write

    w(f"\n{'=' * 60}\n")
    w(f" {title}\n")
    w(f"{'=' * 60}\n\n")

    # Reliability warning
    if not stats.get("statistically_reliable", True):
        w(f"  ⚠️  WARNING: Only {stats.get('trade_count', 0)} trades. "
          f"Need {MIN_RELIABLE_TRADES}+ for statistical reliability.\n\n")

    # Core metrics
    w(f"  {'Trade Count:':<25} {stats.get('trade_count', 0):>10}\n")
    w(f"  {'Wins:':<25} {stats.get('wins', 0):>10}\n")
    w(f"  {'Losses:':<25} {stats.get('losses', 0):>10}\n")
    w(f"  {'Breakevens:':<25} {stats.get('breakevens', 0):>10}\n")
    w(f"\n")

    # Rates
    w(f"  {'Win Rate (ex BE):':<25} {stats.get('win_rate_ex_BE', 0):>9.1f}%\n")
    w(f"  {'Win Rate (inc BE):':<25} {stats.get('win_rate_including_BE', 0):>9.1f}%\n")
    w(f"  {'BE Rate:':<25} {stats.get('BE_rate', 0):>9.1f}%\n")
    w(f"  {'Loss Rate:':<25} {stats.get('loss_rate', 0):>9.1f}%\n")
    w(f"\n")

    # R metrics
    w(f"  {'Avg Win R:':<25} {stats.get('avg_win_R', 0):>10.4f}\n")
    w(f"  {'Avg Loss R:':<25} {stats.get('avg_loss_R', 0):>10.4f}\n")
    w(f"  {'Expectancy R:':<25} {stats.get('expectancy_R', 0):>10.4f}\n")
    w(f"  {'Net R:':<25} {stats.get('net_R', 0):>10.2f}\n")
    w(f"  {'Payoff Ratio:':<25} {stats.get('payoff_ratio', 0):>10.3f}\n")
    w(f"\n")

    # Risk metrics
    w(f"  {'Profit Factor:':<25} {stats.get('profit_factor', 0):>10.3f}\n")
    w(f"  {'Max Drawdown R:':<25} {stats.get('max_DD_R', 0):>10.2f}\n")
    w(f"  {'Longest Loss Streak:':<25} {stats.get('longest_loss_streak', 0):>10}\n")
    w(f"  {'Avg Hold Bars:':<25} {stats.get('average_hold_bars', 0):>10.1f}\n")
    w(f"\n")

    # Risk-adjusted
    w(f"  {'Sharpe (annualized):':<25} {stats.get('sharpe', 0):>10.3f}\n")
    w(f"  {'Sortino (annualized):':<25} {stats.get('sortino', 0):>10.3f}\n")
    w(f"\n")

    # MAE/MFE
    w(f"  {'Avg MAE R:':<25} {stats.get('avg_MAE_R', 0):>10.4f}\n")
    w(f"  {'Avg MFE R:':<25} {stats.get('avg_MFE_R', 0):>10.4f}\n")

    w(f"\n{'=' * 60}\n")

    return buf.getvalue()


def format_grouped_report(grouped_df: pd.DataFrame,
                          group_key: str,
                          title: str = "") -> str:
    """Format grouped statistics as a table string."""
    if grouped_df.empty:
        return f"No data for grouping by {group_key}\n"

    buf = StringIO()
    w = buf.write

    t = title or f"Statistics by {group_key}"
    w(f"\n{'=' * 70}\n")
    w(f" {t}\n")
    w(f"{'=' * 70}\n\n")

    w(grouped_df.to_string(index=False))
    w("\n")

    # Reliability note
    unreliable = grouped_df[grouped_df["reliable"] == "⚠️"]
    if len(unreliable) > 0:
        w(f"\n  ⚠️  {len(unreliable)} group(s) below {MIN_RELIABLE_TRADES} trades "
          f"— results may be unreliable.\n")

    w(f"\n{'=' * 70}\n")
    return buf.getvalue()


# ============================================================
# FULL REPORT GENERATOR
# ============================================================
def generate_full_report(trades, symbol: str = "", timeframe: str = "",
                         save_path: Optional[str] = None) -> str:
    """
    Generate a complete backtest report with all required breakdowns.

    Args:
        trades: List of TradeResult objects
        symbol: Symbol name for the report header
        timeframe: Timeframe for the report header
        save_path: Optional file path to save the report

    Returns:
        Complete formatted report string
    """
    df = trades_to_dataframe(trades)
    if df.empty:
        return "No trades to report.\n"

    # Add symbol/tf if not already set
    if symbol and "symbol" not in df.columns:
        df["symbol"] = symbol
    if timeframe and "timeframe" not in df.columns:
        df["timeframe"] = timeframe

    buf = StringIO()
    w = buf.write

    w("\n" + "█" * 60 + "\n")
    w(f"  ASR ENGINE v3 — BACKTEST REPORT\n")
    if symbol:
        w(f"  Symbol: {symbol}")
    if timeframe:
        w(f"  | Timeframe: {timeframe}")
    w("\n" + "█" * 60 + "\n")

    # 1. Overall statistics
    stats = calculate_stats(df)
    w(format_stats_report(stats, "Overall Performance"))

    # 2. Breakdowns
    group_keys = [
        ("direction", "Statistics by Direction"),
        ("setup_type", "Statistics by Setup Type"),
        ("exit_type", "Statistics by Exit Type"),
        ("score_bucket", "Statistics by Score Bucket"),
    ]

    # Add conditional breakdowns
    if "symbol" in df.columns and df["symbol"].nunique() > 1:
        group_keys.append(("symbol", "Statistics by Symbol"))
    if "timeframe" in df.columns and df["timeframe"].nunique() > 1:
        group_keys.append(("timeframe", "Statistics by Timeframe"))
    if "regime" in df.columns and df["regime"].nunique() > 1:
        group_keys.append(("regime", "Statistics by Regime"))
    if "zone_tier" in df.columns and df["zone_tier"].nunique() > 1:
        group_keys.append(("zone_tier", "Statistics by Zone Tier"))
    if "entry_time" in df.columns:
        group_keys.append(("year", "Statistics by Year"))

    for key, title in group_keys:
        grouped = stats_by_group(df, key)
        if not grouped.empty:
            w(format_grouped_report(grouped, key, title))

    # 3. Trade list (first/last 10)
    w(f"\n{'=' * 70}\n")
    w(f" Recent Trades (last 10)\n")
    w(f"{'=' * 70}\n\n")

    display_cols = ["entry_bar", "direction", "entry_price", "exit_price",
                    "exit_type", "net_r", "score", "hold_bars"]
    available_cols = [c for c in display_cols if c in df.columns]
    w(df[available_cols].tail(10).to_string(index=False))
    w("\n")

    report = buf.getvalue()

    if save_path:
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"Report saved to {save_path}")

    return report


# ============================================================
# MULTI-SYMBOL COMPARISON REPORT
# ============================================================
def multi_symbol_report(all_trades: Dict[str, list],
                        save_path: Optional[str] = None) -> str:
    """
    Generate comparison report across multiple symbols.

    Args:
        all_trades: Dict mapping "SYMBOL_TF" to list of TradeResult
    """
    buf = StringIO()
    w = buf.write

    w("\n" + "█" * 60 + "\n")
    w("  ASR ENGINE v3 — MULTI-SYMBOL COMPARISON\n")
    w("█" * 60 + "\n")

    rows = []
    for key, trades in all_trades.items():
        df = trades_to_dataframe(trades)
        if df.empty:
            continue
        stats = calculate_stats(df)
        rows.append({
            "Symbol_TF": key,
            "Trades": stats.get("trade_count", 0),
            "WR%": stats.get("win_rate_ex_BE", 0),
            "Exp_R": stats.get("expectancy_R", 0),
            "Net_R": stats.get("net_R", 0),
            "PF": stats.get("profit_factor", 0),
            "MaxDD": stats.get("max_DD_R", 0),
            "Sharpe": stats.get("sharpe", 0),
            "Reliable": "✅" if stats.get("statistically_reliable") else "⚠️",
        })

    if rows:
        comparison_df = pd.DataFrame(rows)
        w(f"\n{comparison_df.to_string(index=False)}\n")

        # Aggregated
        all_df = pd.concat([
            trades_to_dataframe(t) for t in all_trades.values() if t
        ], ignore_index=True)
        if not all_df.empty:
            agg_stats = calculate_stats(all_df)
            w(format_stats_report(agg_stats, "Aggregated Performance (All Symbols)"))

    report = buf.getvalue()

    if save_path:
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(report)

    return report
