"""
ASR Engine v3 — Complete Portfolio Backtest & Performance Report
=================================================================
Runs the canonical ASR Engine on ALL 55 symbol×timeframe combinations
(5 symbols × 6 timeframes), simulates each with a $10,000 USD initial
balance, and produces:

  1. Per-combination performance stats (R-based + dollar PnL)
  2. Per-combination equity curves ($USD) with drawdown
  3. Per-combination return % curves
  4. Portfolio-level aggregated equity curve
  5. Monthly/quarterly return heatmaps
  6. Comprehensive comparison tables
  7. Risk-adjusted metrics (Sharpe, Sortino, Calmar, etc.)
  8. Full HTML + Markdown reports

Usage:
    python -m backtester.run_complete_portfolio     (from project root)
    python run_complete_portfolio.py                (from backtester/)
"""
import os
import sys
import time
import json
import yaml
import logging
from pathlib import Path
from datetime import datetime, timezone
from io import StringIO
from collections import defaultdict

# ---------------------------------------------------------------------------
# Fix Windows console encoding
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backtester.asr_engine import ASREngine
from backtester.reporting import (
    trades_to_dataframe, calculate_stats, format_stats_report
)
from backtester.portfolio_charts_extra import generate_extra_charts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CACHE_DIR = _THIS_DIR / "data_cache"
RESULTS_DIR = _THIS_DIR / "results"
PORTFOLIO_DIR = RESULTS_DIR / "portfolio"
AGGREGATE_DIR = PORTFOLIO_DIR / "aggregate"
CHARTS_DIR = AGGREGATE_DIR / "charts"

# All 5 symbols × 11 timeframes = 55 combinations
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT"]
ALL_TIMEFRAMES = ["1m", "3m", "5m", "10m", "15m", "30m", "45m", "1h", "2h", "4h", "1d"]
INITIAL_BALANCE = 10_000.0  # $10,000 USD per combination


# ============================================================
# HELPERS
# ============================================================
def load_config() -> dict:
    cfg_path = _THIS_DIR / "config.yaml"
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)


def load_csv(path: Path) -> pd.DataFrame:
    """Load a cached CSV and ensure datetime column is UTC."""
    df = pd.read_csv(path)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    if "time" not in df.columns and "timestamp" in df.columns:
        df["time"] = df["timestamp"]
    return df


def discover_all_datasets() -> list[dict]:
    """Find CSV files for ALL timeframes (55 combos)."""
    entries = []
    for sym in SYMBOLS:
        base, quote = sym.split("/")
        for tf in ALL_TIMEFRAMES:
            fname = f"binance_{base}_{quote}_{tf}.csv"
            path = CACHE_DIR / f"{base}_{quote}" / tf / fname
            if path.exists():
                entries.append({
                    "path": path,
                    "symbol": sym,
                    "timeframe": tf,
                    "key": f"{base}_{quote}_{tf}",
                    "size_mb": path.stat().st_size / (1024 * 1024),
                })
    return entries


def pprint_section(title: str, char: str = "=", width: int = 78):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def ts_to_datetime(ts):
    """Convert timestamp (ms or s) to datetime."""
    if ts is None or (isinstance(ts, float) and np.isnan(ts)):
        return None
    if isinstance(ts, (int, float)):
        if ts > 1e12:  # milliseconds
            ts = ts / 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    return ts


# ============================================================
# DOLLAR PNL SIMULATION
# ============================================================
def simulate_dollar_pnl(trades_df: pd.DataFrame,
                         initial_balance: float = 10_000.0,
                         risk_pct: float = 0.5) -> pd.DataFrame:
    """
    Simulate dollar-denominated PnL from trade R-multiples.

    For each trade:
      - risk_amount = current_equity × (risk_pct / 100)
      - dollar_pnl = net_r × risk_amount
      - equity = equity + dollar_pnl

    Returns DataFrame with columns:
      trade_num, entry_time, exit_time, direction, symbol, timeframe,
      net_r, risk_amount, dollar_pnl, equity, return_pct,
      peak_equity, drawdown_pct, drawdown_usd
    """
    if trades_df.empty:
        return pd.DataFrame()

    equity = initial_balance
    peak = initial_balance
    rows = []

    for i, row in trades_df.iterrows():
        net_r = row["net_r"]
        risk_amount = equity * (risk_pct / 100.0)
        dollar_pnl = net_r * risk_amount
        equity += dollar_pnl

        if equity > peak:
            peak = equity

        dd_usd = peak - equity
        dd_pct = (dd_usd / peak * 100) if peak > 0 else 0
        ret_pct = ((equity - initial_balance) / initial_balance * 100)

        rows.append({
            "trade_num": len(rows) + 1,
            "entry_time": row.get("entry_time"),
            "exit_time": row.get("exit_time"),
            "direction": row.get("direction", ""),
            "symbol": row.get("symbol", ""),
            "timeframe": row.get("timeframe", ""),
            "setup_type": row.get("setup_type", ""),
            "score": row.get("score", 0),
            "net_r": net_r,
            "risk_amount": round(risk_amount, 2),
            "dollar_pnl": round(dollar_pnl, 2),
            "equity": round(equity, 2),
            "return_pct": round(ret_pct, 2),
            "peak_equity": round(peak, 2),
            "drawdown_usd": round(dd_usd, 2),
            "drawdown_pct": round(dd_pct, 4),
        })

    return pd.DataFrame(rows)


def compute_dollar_stats(pnl_df: pd.DataFrame,
                          initial_balance: float = 10_000.0) -> dict:
    """Compute dollar-denominated performance stats."""
    if pnl_df.empty:
        return {"error": "No trades"}

    final_eq = pnl_df["equity"].iloc[-1]
    total_pnl = final_eq - initial_balance
    total_return_pct = (total_pnl / initial_balance) * 100
    max_dd_usd = pnl_df["drawdown_usd"].max()
    max_dd_pct = pnl_df["drawdown_pct"].max()
    peak_eq = pnl_df["peak_equity"].max()

    # Win/loss in dollar terms
    wins = pnl_df[pnl_df["dollar_pnl"] > 0]
    losses = pnl_df[pnl_df["dollar_pnl"] < 0]
    avg_win = wins["dollar_pnl"].mean() if len(wins) > 0 else 0
    avg_loss = losses["dollar_pnl"].mean() if len(losses) > 0 else 0

    # CAGR (if time data available)
    cagr = 0
    try:
        times = pnl_df["exit_time"].dropna()
        if len(times) > 1:
            first_t = times.iloc[0]
            last_t = times.iloc[-1]
            if isinstance(first_t, (int, float)) and isinstance(last_t, (int, float)):
                if first_t > 1e12:
                    first_t /= 1000
                    last_t /= 1000
                years = (last_t - first_t) / (365.25 * 86400)
                if years > 0 and final_eq > 0:
                    cagr = ((final_eq / initial_balance) ** (1 / years) - 1) * 100
    except Exception:
        pass

    # Calmar ratio
    calmar = abs(total_return_pct / max_dd_pct) if max_dd_pct > 0 else 0

    # Per-trade dollar returns for Sharpe/Sortino
    pnl_array = pnl_df["dollar_pnl"].values
    if len(pnl_array) > 1 and np.std(pnl_array) > 0:
        sharpe_dollar = float(np.mean(pnl_array) / np.std(pnl_array) * np.sqrt(252))
    else:
        sharpe_dollar = 0.0

    downside = pnl_array[pnl_array < 0]
    if len(downside) > 1 and np.std(downside) > 0:
        sortino_dollar = float(np.mean(pnl_array) / np.std(downside) * np.sqrt(252))
    else:
        sortino_dollar = 0.0

    # Recovery Factor: Net Profit / Max Drawdown
    recovery_factor = abs(total_pnl / max_dd_usd) if max_dd_usd > 0 else 0

    # Ulcer Index: RMS of drawdown percentages
    dd_values = pnl_df["drawdown_pct"].values
    ulcer_index = float(np.sqrt(np.mean(dd_values ** 2))) if len(dd_values) > 0 else 0

    # Value at Risk (95%) and Conditional VaR (Expected Shortfall)
    if len(pnl_array) > 10:
        var_95 = float(np.percentile(pnl_array, 5))  # 5th percentile = 95% VaR
        below_var = pnl_array[pnl_array <= var_95]
        cvar_95 = float(np.mean(below_var)) if len(below_var) > 0 else var_95
    else:
        var_95 = 0.0
        cvar_95 = 0.0

    return {
        "initial_balance": initial_balance,
        "final_equity": round(final_eq, 2),
        "total_pnl_usd": round(total_pnl, 2),
        "total_return_pct": round(total_return_pct, 2),
        "peak_equity": round(peak_eq, 2),
        "max_drawdown_usd": round(max_dd_usd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "cagr_pct": round(cagr, 2),
        "calmar_ratio": round(calmar, 3),
        "sharpe_dollar": round(sharpe_dollar, 3),
        "sortino_dollar": round(sortino_dollar, 3),
        "recovery_factor": round(recovery_factor, 3),
        "ulcer_index": round(ulcer_index, 4),
        "var_95_usd": round(var_95, 2),
        "cvar_95_usd": round(cvar_95, 2),
        "trade_count": len(pnl_df),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
    }


# ============================================================
# CHART GENERATION
# ============================================================
def _setup_mpl():
    """Setup matplotlib with professional styling."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": "#FAFAFA",
        "axes.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.color": "#E0E0E0",
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "figure.dpi": 150,
    })
    return plt


def plot_equity_curve_usd(pnl_df: pd.DataFrame, key: str,
                           initial_balance: float, save_path: str):
    """Plot USD equity curve with drawdown overlay."""
    plt = _setup_mpl()
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(14, 8),
        gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )

    x = pnl_df["trade_num"].values
    eq = pnl_df["equity"].values
    dd = -pnl_df["drawdown_pct"].values

    # Equity
    ax1.plot(x, eq, color="#2196F3", linewidth=1.5, label="Equity ($)")
    ax1.fill_between(x, initial_balance, eq,
                     where=(eq >= initial_balance), color="#4CAF50", alpha=0.15)
    ax1.fill_between(x, initial_balance, eq,
                     where=(eq < initial_balance), color="#F44336", alpha=0.15)
    ax1.axhline(initial_balance, color="gray", linewidth=0.8, linestyle="--",
                label=f"Start: ${initial_balance:,.0f}")
    ax1.set_title(f"ASR Engine v3 — Equity Curve | {key} | Start: ${initial_balance:,.0f}")
    ax1.set_ylabel("Equity ($)")
    ax1.legend(loc="upper left")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    # Drawdown
    ax2.fill_between(x, 0, dd, color="#E91E63", alpha=0.5)
    ax2.plot(x, dd, color="#E91E63", linewidth=0.8)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Trade #")
    ax2.set_title("Drawdown %")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:.1f}%"))

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


def plot_return_pct_curve(pnl_df: pd.DataFrame, key: str, save_path: str):
    """Plot cumulative return % curve."""
    plt = _setup_mpl()
    fig, ax = plt.subplots(figsize=(14, 5))

    x = pnl_df["trade_num"].values
    ret = pnl_df["return_pct"].values

    ax.plot(x, ret, color="#FF9800", linewidth=1.5, label="Cumulative Return %")
    ax.fill_between(x, 0, ret, where=(ret >= 0), color="#4CAF50", alpha=0.15)
    ax.fill_between(x, 0, ret, where=(ret < 0), color="#F44336", alpha=0.15)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_title(f"ASR Engine v3 — Cumulative Return % | {key}")
    ax.set_ylabel("Return (%)")
    ax.set_xlabel("Trade #")
    ax.legend(loc="upper left")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:+.1f}%"))

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


def plot_portfolio_overview_split(all_pnl: dict, initial_balance: float, charts_dir: str):
    """
    Plot 4 SEPARATE portfolio overview charts (one per PNG) for maximum readability:
      1. portfolio_final_equity.png — Final equity by combination (bar chart)
      2. portfolio_pnl_by_symbol.png — Net PnL aggregated by symbol
      3. portfolio_pnl_by_timeframe.png — Net PnL aggregated by timeframe
      4. portfolio_return_pct.png — Return % by combination
    """
    plt = _setup_mpl()
    out = Path(charts_dir)
    n_combos = len(all_pnl)

    # Aggregate by symbol and timeframe
    sym_equity = defaultdict(list)
    tf_equity = defaultdict(list)

    for key, pnl_df in all_pnl.items():
        if pnl_df.empty:
            continue
        parts = key.split("_")
        sym = f"{parts[0]}/{parts[1]}"
        tf = parts[2]
        final = pnl_df["equity"].iloc[-1]
        sym_equity[sym].append(final)
        tf_equity[tf].append(final)

    keys = sorted(all_pnl.keys())

    # ── CHART 1: Final Equity by Combination ──
    fig, ax = plt.subplots(figsize=(14, max(8, n_combos * 0.25)))
    final_eqs = []
    colors = []
    for k in keys:
        if all_pnl[k].empty:
            final_eqs.append(initial_balance)
            colors.append("#9E9E9E")
        else:
            eq = all_pnl[k]["equity"].iloc[-1]
            final_eqs.append(eq)
            colors.append("#4CAF50" if eq >= initial_balance else "#F44336")

    x = np.arange(len(keys))
    ax.barh(x, final_eqs, color=colors, alpha=0.85)
    ax.axvline(initial_balance, color="gray", linewidth=1, linestyle="--",
               label=f"Start: ${initial_balance:,.0f}")
    ax.set_yticks(x)
    ax.set_yticklabels(keys, fontsize=8)
    ax.set_title(f"ASR Engine v3 — Final Equity by Combination "
                 f"({n_combos} combos, ${initial_balance:,.0f} each)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Final Equity ($)")
    ax.legend(loc="lower right")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    for i, (k, eq) in enumerate(zip(keys, final_eqs)):
        ax.text(eq + 200, i, f"${eq:,.0f}", va="center", fontsize=7)
    plt.tight_layout()
    plt.savefig(str(out / "portfolio_final_equity.png"), bbox_inches="tight")
    plt.close()

    # ── CHART 2: Net PnL by Symbol ──
    fig, ax = plt.subplots(figsize=(12, 7))
    sym_labels = sorted(sym_equity.keys())
    sym_totals = [sum(sym_equity[s]) for s in sym_labels]
    sym_starts = [len(sym_equity[s]) * initial_balance for s in sym_labels]
    sym_pnl = [t - s for t, s in zip(sym_totals, sym_starts)]
    sym_colors = ["#4CAF50" if p >= 0 else "#F44336" for p in sym_pnl]
    bars = ax.bar(sym_labels, sym_pnl, color=sym_colors, alpha=0.85, width=0.6)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_title("ASR Engine v3 — Net PnL by Symbol (All Timeframes Combined)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Net PnL ($)")
    ax.set_xlabel("Symbol")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    for bar, val in zip(bars, sym_pnl):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"${val:+,.0f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    plt.tight_layout()
    plt.savefig(str(out / "portfolio_pnl_by_symbol.png"), bbox_inches="tight")
    plt.close()

    # ── CHART 3: Net PnL by Timeframe ──
    fig, ax = plt.subplots(figsize=(14, 7))
    tf_labels = [tf for tf in ALL_TIMEFRAMES if tf in tf_equity]
    tf_totals = [sum(tf_equity[t]) for t in tf_labels]
    tf_starts = [len(tf_equity[t]) * initial_balance for t in tf_labels]
    tf_pnl = [t - s for t, s in zip(tf_totals, tf_starts)]
    tf_colors = ["#4CAF50" if p >= 0 else "#F44336" for p in tf_pnl]
    bars = ax.bar(tf_labels, tf_pnl, color=tf_colors, alpha=0.85, width=0.6)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_title("ASR Engine v3 — Net PnL by Timeframe (All Symbols Combined)",
                 fontsize=13, fontweight="bold")
    ax.set_ylabel("Net PnL ($)")
    ax.set_xlabel("Timeframe")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    for bar, val in zip(bars, tf_pnl):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"${val:+,.0f}", ha="center", va="bottom", fontsize=9, fontweight="bold")
    plt.tight_layout()
    plt.savefig(str(out / "portfolio_pnl_by_timeframe.png"), bbox_inches="tight")
    plt.close()

    # ── CHART 4: Total Return % by Combination ──
    fig, ax = plt.subplots(figsize=(14, max(8, n_combos * 0.25)))
    returns = []
    labels = []
    for k in keys:
        if not all_pnl[k].empty:
            ret = ((all_pnl[k]["equity"].iloc[-1] - initial_balance) /
                   initial_balance * 100)
            returns.append(ret)
            labels.append(k)
    if returns:
        ret_colors = ["#4CAF50" if r >= 0 else "#F44336" for r in returns]
        ax.barh(range(len(labels)), returns, color=ret_colors, alpha=0.85)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)
        ax.axvline(0, color="gray", linewidth=0.8, linestyle="--")
        ax.set_title("ASR Engine v3 — Total Return % by Combination",
                     fontsize=13, fontweight="bold")
        ax.set_xlabel("Return (%)")
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:+.0f}%"))
        for i, (lbl, r) in enumerate(zip(labels, returns)):
            ax.text(r + 5, i, f"{r:+.0f}%", va="center", fontsize=7)
    plt.tight_layout()
    plt.savefig(str(out / "portfolio_return_pct.png"), bbox_inches="tight")
    plt.close()


def plot_combined_equity(all_pnl: dict, initial_balance: float, save_path: str):
    """
    Plot combined portfolio equity: sum of all 55 accounts over trade sequence.
    """
    plt = _setup_mpl()
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(16, 9),
        gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )

    # Merge all trades sorted by exit_time, compute running portfolio equity
    all_rows = []
    for key, pnl_df in all_pnl.items():
        if pnl_df.empty:
            continue
        for _, row in pnl_df.iterrows():
            all_rows.append({
                "exit_time": row.get("exit_time"),
                "dollar_pnl": row["dollar_pnl"],
                "key": key,
            })

    if not all_rows:
        return

    merged = pd.DataFrame(all_rows)
    # Sort by exit time
    merged = merged.sort_values("exit_time").reset_index(drop=True)

    total_initial = initial_balance * len([k for k, v in all_pnl.items() if not v.empty])
    equity = total_initial
    peak = total_initial
    equities = []
    drawdowns = []

    for _, row in merged.iterrows():
        equity += row["dollar_pnl"]
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100 if peak > 0 else 0
        equities.append(equity)
        drawdowns.append(-dd)

    x = np.arange(len(equities))

    # Equity
    ax1.plot(x, equities, color="#2196F3", linewidth=1.2, label="Portfolio Equity")
    ax1.fill_between(x, total_initial, equities,
                     where=(np.array(equities) >= total_initial),
                     color="#4CAF50", alpha=0.12)
    ax1.fill_between(x, total_initial, equities,
                     where=(np.array(equities) < total_initial),
                     color="#F44336", alpha=0.12)
    ax1.axhline(total_initial, color="gray", linewidth=0.8, linestyle="--",
                label=f"Start: ${total_initial:,.0f}")
    ax1.set_title(f"ASR Engine v3 — Combined Portfolio Equity | "
                  f"55 Accounts × ${initial_balance:,.0f} = ${total_initial:,.0f}")
    ax1.set_ylabel("Equity ($)")
    ax1.legend(loc="upper left")
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    # Drawdown
    ax2.fill_between(x, 0, drawdowns, color="#E91E63", alpha=0.5)
    ax2.plot(x, drawdowns, color="#E91E63", linewidth=0.8)
    ax2.set_ylabel("Drawdown (%)")
    ax2.set_xlabel("Trade # (all accounts merged)")
    ax2.set_title("Portfolio Drawdown")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{x:.1f}%"))

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


def plot_per_symbol_equity(all_pnl: dict, initial_balance: float, save_path: str):
    """Plot per-symbol equity curves (aggregated across timeframes)."""
    plt = _setup_mpl()
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    axes = axes.flatten()

    sym_groups = defaultdict(list)
    for key, pnl_df in all_pnl.items():
        parts = key.split("_")
        sym = f"{parts[0]}/{parts[1]}"
        sym_groups[sym].append((key, pnl_df))

    colors_map = {
        "BTC/USDT": "#F7931A", "ETH/USDT": "#627EEA",
        "SOL/USDT": "#9945FF", "XRP/USDT": "#23292F",
        "BNB/USDT": "#F3BA2F",
    }

    for idx, (sym, group_list) in enumerate(sorted(sym_groups.items())):
        if idx >= 5:
            break
        ax = axes[idx]
        for key, pnl_df in sorted(group_list, key=lambda x: x[0]):
            if pnl_df.empty:
                continue
            tf = key.split("_")[2]
            ax.plot(pnl_df["trade_num"], pnl_df["equity"],
                    linewidth=1.2, label=tf, alpha=0.85)

        ax.axhline(initial_balance, color="gray", linewidth=0.8, linestyle="--")
        ax.set_title(f"{sym}", fontsize=11)
        ax.set_ylabel("Equity ($)")
        ax.set_xlabel("Trade #")
        ax.legend(fontsize=7, loc="upper left")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    # Use last subplot for legend / summary
    ax = axes[5]
    ax.axis("off")
    summary_text = "Per-Symbol Equity Curves\n"
    summary_text += f"Initial: ${initial_balance:,.0f}\n"
    summary_text += f"Timeframes: {', '.join(ALL_TIMEFRAMES)}"
    ax.text(0.5, 0.5, summary_text, ha="center", va="center",
            fontsize=12, transform=ax.transAxes,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow"))

    fig.suptitle("ASR Engine v3 — Per-Symbol Equity Curves (All Timeframes)",
                 fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


def plot_heatmap(all_dollar_stats: dict, save_path: str):
    """Plot a heatmap of return % across symbols and timeframes."""
    plt = _setup_mpl()

    # Build matrix
    symbols = SYMBOLS
    timeframes = ALL_TIMEFRAMES
    matrix = np.full((len(symbols), len(timeframes)), np.nan)

    for i, sym in enumerate(symbols):
        base, quote = sym.split("/")
        for j, tf in enumerate(timeframes):
            key = f"{base}_{quote}_{tf}"
            if key in all_dollar_stats:
                matrix[i, j] = all_dollar_stats[key].get("total_return_pct", 0)

    fig, ax = plt.subplots(figsize=(12, 6))

    # Custom colormap: red for negative, green for positive
    from matplotlib.colors import SymLogNorm
    
    # Use 'YlGnBu' (Yellow-Green-Blue) for a soft, industry-standard professional look
    cmap = "YlGnBu"

    # SymLogNorm handles the massive range (from slight negative to +1400%) beautifully
    vmin = np.nanmin(matrix) if not np.all(np.isnan(matrix)) else -100
    vmax = np.nanmax(matrix) if not np.all(np.isnan(matrix)) else 100
    norm = SymLogNorm(linthresh=10.0, linscale=1.0, vmin=vmin, vmax=vmax, base=10)

    im = ax.imshow(matrix, cmap=cmap, norm=norm, aspect="auto")

    ax.set_xticks(np.arange(len(timeframes)))
    ax.set_xticklabels(timeframes)
    ax.set_yticks(np.arange(len(symbols)))
    ax.set_yticklabels(symbols)

    # Annotate cells
    for i in range(len(symbols)):
        for j in range(len(timeframes)):
            val = matrix[i, j]
            if not np.isnan(val):
                color = "white" if abs(val) > 50 else "black"
                ax.text(j, i, f"{val:+.0f}%", ha="center", va="center",
                        fontsize=10, fontweight="bold", color=color)

    plt.colorbar(im, ax=ax, label="Return %", shrink=0.8)
    n_sym = len(symbols)
    n_tf = len(timeframes)
    ax.set_title(f"ASR Engine v3 — Return % Heatmap ({n_sym}×{n_tf} Matrix, $10K each)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


def plot_pnl_ranking(all_dollar_stats: dict, save_path: str):
    """Plot all 55 combinations ranked by total PnL."""
    plt = _setup_mpl()
    fig, ax = plt.subplots(figsize=(14, 10))

    items = [(k, v) for k, v in all_dollar_stats.items() if "error" not in v]
    items.sort(key=lambda x: x[1]["total_pnl_usd"])

    keys = [x[0] for x in items]
    pnl = [x[1]["total_pnl_usd"] for x in items]
    colors = ["#4CAF50" if p >= 0 else "#F44336" for p in pnl]

    ax.barh(range(len(keys)), pnl, color=colors, alpha=0.85)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels(keys, fontsize=8)
    ax.axvline(0, color="gray", linewidth=0.8, linestyle="--")
    ax.set_title("ASR Engine v3 — PnL Ranking (All 55 Combinations, $10K start)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Net PnL ($)")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))

    # Annotate top/bottom
    for i, (k, p) in enumerate(zip(keys, pnl)):
        offset = 50 if p >= 0 else -50
        ax.text(p + offset, i, f"${p:+,.0f}", va="center", fontsize=7,
                ha="left" if p >= 0 else "right")

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


# ============================================================
# MARKDOWN REPORT GENERATOR
# ============================================================
def generate_portfolio_report(
    all_r_stats: dict, all_dollar_stats: dict, all_pnl: dict,
    initial_balance: float, elapsed_s: float
) -> str:
    """Generate a comprehensive Markdown report."""
    buf = StringIO()
    w = buf.write
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    total_accounts = len(all_dollar_stats)
    total_initial = total_accounts * initial_balance
    total_final = sum(v.get("final_equity", initial_balance)
                      for v in all_dollar_stats.values() if "error" not in v)
    total_pnl = total_final - total_initial
    total_ret = (total_pnl / total_initial * 100) if total_initial > 0 else 0
    total_trades = sum(v.get("trade_count", 0)
                       for v in all_dollar_stats.values() if "error" not in v)

    w(f"# ASR Engine v3 — Complete Portfolio Backtest Report\n")
    w(f"*Generated: {now} | {total_accounts} accounts × ${initial_balance:,.0f} = "
      f"${total_initial:,.0f} total capital*\n\n")

    # Executive Summary
    w(f"## Executive Summary\n\n")
    w(f"| Metric | Value |\n|---|---|\n")
    w(f"| Total Accounts | {total_accounts} |\n")
    w(f"| Initial Capital (per account) | ${initial_balance:,.0f} |\n")
    w(f"| Total Initial Capital | ${total_initial:,.0f} |\n")
    w(f"| Total Final Equity | ${total_final:,.0f} |\n")
    w(f"| **Total Net PnL** | **${total_pnl:+,.0f}** |\n")
    w(f"| **Total Return** | **{total_ret:+.2f}%** |\n")
    w(f"| Total Trades | {total_trades:,} |\n")
    w(f"| Profitable Accounts | {sum(1 for v in all_dollar_stats.values() if v.get('total_pnl_usd', 0) > 0)} / {total_accounts} |\n")
    w(f"| Run Time | {elapsed_s/60:.1f} minutes |\n\n")

    # Detailed Table
    w(f"## Per-Combination Performance\n\n")
    w(f"| # | Combination | Trades | Win Rate | Exp R | PF | Net R | "
      f"Start $ | Final $ | PnL $ | Return % | Max DD % | Sharpe |\n")
    w(f"|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")

    sorted_keys = sorted(all_dollar_stats.keys())
    for idx, key in enumerate(sorted_keys, 1):
        ds = all_dollar_stats[key]
        rs = all_r_stats.get(key, {})
        if "error" in ds:
            w(f"| {idx} | {key} | 0 | - | - | - | - | "
              f"${initial_balance:,.0f} | ${initial_balance:,.0f} | $0 | 0% | - | - |\n")
            continue

        trades = ds.get("trade_count", 0)
        wr = rs.get("win_rate_ex_BE", 0)
        exp = rs.get("expectancy_R", 0)
        pf = rs.get("profit_factor", 0)
        net_r = rs.get("net_R", 0)
        final = ds.get("final_equity", initial_balance)
        pnl = ds.get("total_pnl_usd", 0)
        ret = ds.get("total_return_pct", 0)
        dd = ds.get("max_drawdown_pct", 0)
        sharpe = rs.get("sharpe", 0)

        pnl_icon = "+" if pnl >= 0 else ""
        w(f"| {idx} | {key} | {trades} | {wr:.1f}% | {exp:.4f} | {pf:.2f} | "
          f"{net_r:.1f} | ${initial_balance:,.0f} | ${final:,.0f} | "
          f"${pnl_icon}{pnl:,.0f} | {ret:+.1f}% | {dd:.1f}% | {sharpe:.2f} |\n")

    w(f"\n")

    # By Symbol summary
    w(f"## Performance by Symbol\n\n")
    w(f"| Symbol | Total Trades | Avg Exp R | Avg PF | Total PnL $ | Avg Return % |\n")
    w(f"|---|---|---|---|---|---|\n")

    sym_data = defaultdict(lambda: {"trades": 0, "exp_rs": [], "pfs": [], "pnls": [], "rets": []})
    for key in sorted_keys:
        parts = key.split("_")
        sym = f"{parts[0]}/{parts[1]}"
        ds = all_dollar_stats[key]
        rs = all_r_stats.get(key, {})
        if "error" in ds:
            continue
        sym_data[sym]["trades"] += ds.get("trade_count", 0)
        sym_data[sym]["exp_rs"].append(rs.get("expectancy_R", 0))
        sym_data[sym]["pfs"].append(rs.get("profit_factor", 0))
        sym_data[sym]["pnls"].append(ds.get("total_pnl_usd", 0))
        sym_data[sym]["rets"].append(ds.get("total_return_pct", 0))

    for sym in SYMBOLS:
        d = sym_data[sym]
        avg_exp = np.mean(d["exp_rs"]) if d["exp_rs"] else 0
        avg_pf = np.mean(d["pfs"]) if d["pfs"] else 0
        total_pnl = sum(d["pnls"])
        avg_ret = np.mean(d["rets"]) if d["rets"] else 0
        w(f"| {sym} | {d['trades']} | {avg_exp:.4f} | {avg_pf:.2f} | "
          f"${total_pnl:+,.0f} | {avg_ret:+.1f}% |\n")

    w(f"\n")

    # By Timeframe summary
    w(f"## Performance by Timeframe\n\n")
    w(f"| Timeframe | Total Trades | Avg Exp R | Avg PF | Total PnL $ | Avg Return % |\n")
    w(f"|---|---|---|---|---|---|\n")

    tf_data = defaultdict(lambda: {"trades": 0, "exp_rs": [], "pfs": [], "pnls": [], "rets": []})
    for key in sorted_keys:
        parts = key.split("_")
        tf = parts[2]
        ds = all_dollar_stats[key]
        rs = all_r_stats.get(key, {})
        if "error" in ds:
            continue
        tf_data[tf]["trades"] += ds.get("trade_count", 0)
        tf_data[tf]["exp_rs"].append(rs.get("expectancy_R", 0))
        tf_data[tf]["pfs"].append(rs.get("profit_factor", 0))
        tf_data[tf]["pnls"].append(ds.get("total_pnl_usd", 0))
        tf_data[tf]["rets"].append(ds.get("total_return_pct", 0))

    for tf in ALL_TIMEFRAMES:
        d = tf_data[tf]
        avg_exp = np.mean(d["exp_rs"]) if d["exp_rs"] else 0
        avg_pf = np.mean(d["pfs"]) if d["pfs"] else 0
        total_pnl = sum(d["pnls"])
        avg_ret = np.mean(d["rets"]) if d["rets"] else 0
        w(f"| {tf} | {d['trades']} | {avg_exp:.4f} | {avg_pf:.2f} | "
          f"${total_pnl:+,.0f} | {avg_ret:+.1f}% |\n")

    w(f"\n")

    # Top/Bottom performers
    profitable = [(k, v) for k, v in all_dollar_stats.items()
                  if "error" not in v and v.get("total_pnl_usd", 0) > 0]
    losing = [(k, v) for k, v in all_dollar_stats.items()
              if "error" not in v and v.get("total_pnl_usd", 0) <= 0]

    profitable.sort(key=lambda x: x[1]["total_pnl_usd"], reverse=True)
    losing.sort(key=lambda x: x[1]["total_pnl_usd"])

    w(f"## Top 5 Performers\n\n")
    w(f"| Rank | Combination | PnL $ | Return % | Trades |\n")
    w(f"|---|---|---|---|---|\n")
    for i, (k, v) in enumerate(profitable[:5], 1):
        w(f"| {i} | {k} | ${v['total_pnl_usd']:+,.0f} | {v['total_return_pct']:+.1f}% | {v['trade_count']} |\n")

    w(f"\n## Bottom 5 Performers\n\n")
    w(f"| Rank | Combination | PnL $ | Return % | Trades |\n")
    w(f"|---|---|---|---|---|\n")
    for i, (k, v) in enumerate(losing[:5], 1):
        w(f"| {i} | {k} | ${v['total_pnl_usd']:+,.0f} | {v['total_return_pct']:+.1f}% | {v['trade_count']} |\n")

    w(f"\n")

    # Risk & Tail Analysis section
    w(f"## Risk & Tail Analysis\n\n")
    w(f"| Combination | Recovery Factor | Ulcer Index | VaR 95% ($) | CVaR 95% ($) |\n")
    w(f"|---|---|---|---|---|\n")
    for key in sorted_keys:
        ds = all_dollar_stats[key]
        if "error" in ds:
            w(f"| {key} | - | - | - | - |\n")
            continue
        rf = ds.get("recovery_factor", 0)
        ui = ds.get("ulcer_index", 0)
        var95 = ds.get("var_95_usd", 0)
        cvar95 = ds.get("cvar_95_usd", 0)
        w(f"| {key} | {rf:.2f} | {ui:.3f} | ${var95:+,.0f} | ${cvar95:+,.0f} |\n")
    w(f"\n")

    # Aggregate risk metrics
    all_rf = [v.get("recovery_factor", 0) for v in all_dollar_stats.values() if "error" not in v]
    all_ui = [v.get("ulcer_index", 0) for v in all_dollar_stats.values() if "error" not in v]
    if all_rf:
        w(f"**Portfolio Avg Recovery Factor:** {np.mean(all_rf):.2f}\n\n")
        w(f"**Portfolio Avg Ulcer Index:** {np.mean(all_ui):.3f}\n\n")

    w(f"## Charts Generated\n\n")
    w(f"All charts are saved in `backtester/results/portfolio/aggregate/charts/`:\n\n")
    w(f"- `portfolio_final_equity.png` -- Final equity by combination\n")
    w(f"- `portfolio_pnl_by_symbol.png` -- Net PnL aggregated by symbol\n")
    w(f"- `portfolio_pnl_by_timeframe.png` -- Net PnL aggregated by timeframe\n")
    w(f"- `portfolio_return_pct.png` -- Total return % by combination\n")
    w(f"- `combined_equity.png` -- Merged equity curve (all accounts)\n")
    w(f"- `per_symbol_equity.png` -- Per-symbol equity curves\n")
    w(f"- `return_heatmap.png` -- 5×11 return % heatmap\n")
    w(f"- `pnl_ranking.png` -- All combinations ranked by PnL\n")
    w(f"- `monthly_returns.png` -- Monthly PnL heatmap\n")
    w(f"- `r_distribution.png` -- R-multiple distribution histogram\n")
    w(f"- `trade_duration.png` -- Trade duration analysis\n")
    w(f"- `rolling_sharpe.png` -- Rolling Sharpe ratio and Expectancy\n")
    w(f"- `streak_distribution.png` -- Win/loss streak analysis\n")
    w(f"- `setup_performance.png` -- Performance by setup type\n")
    w(f"\nPer-combo charts in `backtester/results/portfolio/[SYMBOL]/[TF]/`:\n\n")
    w(f"- `equity.png` -- Individual equity curves\n")
    w(f"- `return.png` -- Individual return % curves\n\n")

    w(f"---\n")
    w(f"*Reproduce: `python -m backtester.run_complete_portfolio` from project root.*\n")

    return buf.getvalue()


# ============================================================
# PER-COMBO PERSISTENCE HELPERS
# ============================================================
def _save_combo_results(key: str, pnl_df: pd.DataFrame, r_stats: dict,
                        d_stats: dict, trades: list, risk_pct: float):
    """Save a single combination's results to disk immediately after backtest."""
    parts = key.split('_')
    sym_dir = f"{parts[0]}_{parts[1]}"
    tf_dir = parts[2]
    combo_dir = PORTFOLIO_DIR / sym_dir / tf_dir
    combo_dir.mkdir(parents=True, exist_ok=True)

    # 1. PnL CSV
    if not pnl_df.empty:
        pnl_df.to_csv(combo_dir / "pnl.csv", index=False)

    # 2. Trades CSV
    if trades:
        tdf = trades_to_dataframe(trades)
        tdf.to_csv(combo_dir / "trades.csv", index=False)

    # 3. Stats JSON (both R-based and dollar)
    with open(combo_dir / "stats.json", "w") as f:
        json.dump({
            "key": key,
            "r_stats": r_stats,
            "dollar_stats": d_stats,
            "risk_pct": risk_pct,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2, default=str)

    # 4. Per-combo equity & return charts
    if not pnl_df.empty:
        try:
            plot_equity_curve_usd(pnl_df, key, INITIAL_BALANCE,
                                  str(combo_dir / "equity.png"))
        except Exception as e:
            print(f"    [WARN] equity chart: {e}")

        try:
            plot_return_pct_curve(pnl_df, key,
                                  str(combo_dir / "return.png"))
        except Exception as e:
            print(f"    [WARN] return chart: {e}")

    # 5. Per-combo mini report
    try:
        with open(combo_dir / "summary.txt", "w", encoding="utf-8") as f:
            f.write(f"ASR Engine v3 — {key} Backtest Summary\n")
            f.write(f"{'='*50}\n")
            if "error" in d_stats:
                f.write("No trades generated.\n")
            else:
                f.write(f"Trades:      {d_stats.get('trade_count', 0)}\n")
                f.write(f"Expectancy:  {r_stats.get('expectancy_R', 0):.4f} R\n")
                f.write(f"Win Rate:    {r_stats.get('win_rate_ex_BE', 0):.1f}%\n")
                f.write(f"Profit Fac:  {r_stats.get('profit_factor', 0):.2f}\n")
                f.write(f"Start:       ${INITIAL_BALANCE:,.0f}\n")
                f.write(f"Final:       ${d_stats.get('final_equity', INITIAL_BALANCE):,.0f}\n")
                f.write(f"PnL:         ${d_stats.get('total_pnl_usd', 0):+,.0f}\n")
                f.write(f"Return:      {d_stats.get('total_return_pct', 0):+.2f}%\n")
                f.write(f"Max DD:      {d_stats.get('max_drawdown_pct', 0):.2f}%\n")
                f.write(f"Sharpe ($):  {d_stats.get('sharpe_dollar', 0):.3f}\n")
                f.write(f"CAGR:        {d_stats.get('cagr_pct', 0):.2f}%\n")
    except Exception:
        pass


def _load_combo_from_disk(key: str) -> tuple:
    """Load a previously-saved combination's results from disk for resume."""
    parts = key.split('_')
    sym_dir = f"{parts[0]}_{parts[1]}"
    tf_dir = parts[2]
    combo_dir = PORTFOLIO_DIR / sym_dir / tf_dir
    stats_path = combo_dir / "stats.json"
    pnl_path = combo_dir / "pnl.csv"
    trades_path = combo_dir / "trades.csv"

    if not stats_path.exists():
        return None, None, None, None

    with open(stats_path, "r") as f:
        data = json.load(f)

    r_stats = data.get("r_stats", {})
    d_stats = data.get("dollar_stats", {})

    pnl_df = pd.DataFrame()
    if pnl_path.exists():
        pnl_df = pd.read_csv(pnl_path)

    trades_df = pd.DataFrame()
    if trades_path.exists():
        trades_df = pd.read_csv(trades_path)

    return r_stats, d_stats, pnl_df, trades_df


def _update_progress(progress_path: Path, key: str, status: str, elapsed_s: float):
    """Update the progress.json tracker after each combo completes."""
    progress = {}
    if progress_path.exists():
        with open(progress_path, "r") as f:
            progress = json.load(f)

    progress[key] = {
        "status": status,
        "elapsed_s": round(elapsed_s, 1),
        "completed_at": datetime.now().isoformat(),
    }

    with open(progress_path, "w") as f:
        json.dump(progress, f, indent=2)


def _update_cumulative_summary(all_r_stats: dict, all_dollar_stats: dict):
    """Update the cumulative portfolio_summary.csv and portfolio_stats.json after each combo."""
    # Summary CSV
    summary_rows = []
    for key in sorted(all_dollar_stats.keys()):
        ds = all_dollar_stats[key]
        rs = all_r_stats.get(key, {})
        summary_rows.append({
            "Combination": key,
            "Trades": ds.get("trade_count", 0),
            "WR%": rs.get("win_rate_ex_BE", 0),
            "Exp_R": rs.get("expectancy_R", 0),
            "PF": rs.get("profit_factor", 0),
            "Net_R": rs.get("net_R", 0),
            "MaxDD_R": rs.get("max_DD_R", 0),
            "Sharpe": rs.get("sharpe", 0),
            "Start_USD": INITIAL_BALANCE,
            "Final_USD": ds.get("final_equity", INITIAL_BALANCE),
            "PnL_USD": ds.get("total_pnl_usd", 0),
            "Return_%": ds.get("total_return_pct", 0),
            "MaxDD_%": ds.get("max_drawdown_pct", 0),
            "CAGR_%": ds.get("cagr_pct", 0),
            "Calmar": ds.get("calmar_ratio", 0),
            "Recovery_Factor": ds.get("recovery_factor", 0),
            "Ulcer_Index": ds.get("ulcer_index", 0),
            "VaR_95_USD": ds.get("var_95_usd", 0),
            "CVaR_95_USD": ds.get("cvar_95_usd", 0),
        })
    AGGREGATE_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary_rows).to_csv(AGGREGATE_DIR / "portfolio_summary.csv", index=False)

    # Stats JSON
    with open(AGGREGATE_DIR / "portfolio_stats.json", "w") as f:
        json.dump({
            "initial_balance_per_account": INITIAL_BALANCE,
            "total_accounts": len(all_dollar_stats),
            "per_combination": all_dollar_stats,
            "r_stats": all_r_stats,
            "timestamp": datetime.now().isoformat(),
        }, f, indent=2, default=str)


# ============================================================
# MAIN — SAVE-AS-YOU-GO ARCHITECTURE
# ============================================================
def main():
    start_wall = time.time()
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    AGGREGATE_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    config = load_config()
    risk_pct = config.get("backtest", {}).get("risk_per_trade_pct", 0.5)

    entries = discover_all_datasets()

    if not entries:
        print("[ERR] No cached CSV files found. Run the data downloader first.")
        return

    progress_path = PORTFOLIO_DIR / "progress.json"

    # Load existing progress for resume support
    existing_progress = {}
    if progress_path.exists():
        with open(progress_path, "r") as f:
            existing_progress = json.load(f)

    completed_keys = {k for k, v in existing_progress.items()
                      if v.get("status") == "done"}

    pprint_section(f"ASR ENGINE v3 — COMPLETE PORTFOLIO BACKTEST", "█", 78)
    print(f"  {len(entries)} / 55 datasets discovered")
    print(f"  Symbols: {', '.join(SYMBOLS)}")
    print(f"  Timeframes: {', '.join(ALL_TIMEFRAMES)}")
    print(f"  Initial Balance: ${INITIAL_BALANCE:,.0f} per combination")
    print(f"  Total Capital: ${INITIAL_BALANCE * len(entries):,.0f}")
    print(f"  Risk per Trade: {risk_pct}% of equity")
    print(f"  Already completed: {len(completed_keys)} combos (resuming)")
    print(f"  Remaining: {len(entries) - len(completed_keys)} combos")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ---------------------------------------------------------------
    # PHASE 1: BACKTEST + SAVE EACH COMBINATION IMMEDIATELY
    # ---------------------------------------------------------------
    pprint_section("PHASE 1: BACKTESTING (SAVE-AS-YOU-GO)", "█")

    all_trades_dfs = {}  # key -> trades DataFrame (for final aggregated charts)
    all_r_stats = {}
    all_dollar_stats = {}
    all_pnl = {}

    for idx, entry in enumerate(entries, 1):
        sym = entry["symbol"]
        tf = entry["timeframe"]
        key = entry["key"]
        path = entry["path"]
        size_mb = entry["size_mb"]

        # ── RESUME: skip already-completed combos ──
        if key in completed_keys:
            print(f"\n  [{idx}/{len(entries)}] {key}  — SKIPPED (already done)")
            # Reload from disk
            r_stats, d_stats, pnl_df, trades_df = _load_combo_from_disk(key)
            if r_stats is not None:
                all_r_stats[key] = r_stats
                all_dollar_stats[key] = d_stats
                all_pnl[key] = pnl_df if pnl_df is not None else pd.DataFrame()
                if trades_df is not None and not trades_df.empty:
                    all_trades_dfs[key] = trades_df

                tc = d_stats.get("trade_count", 0)
                final = d_stats.get("final_equity", INITIAL_BALANCE)
                pnl_val = d_stats.get("total_pnl_usd", 0)
                print(f"    Loaded from disk: {tc} trades | ${final:,.0f} | PnL=${pnl_val:+,.0f}")
            continue

        # ── RUN BACKTEST ──
        print(f"\n  [{idx}/{len(entries)}] {key}  ({size_mb:.1f} MB)")

        t0 = time.time()
        df = load_csv(path)
        bars = len(df)

        if bars > 2_000_000:
            print(f"    Loading {bars:,} bars... (large dataset, may be slow)")
        else:
            print(f"    Loaded {bars:,} bars")

        engine = ASREngine(config)
        engine.run(df, symbol=sym, timeframe=tf)
        run_s = time.time() - t0

        n_trades = len(engine.trades)

        if n_trades > 0:
            tdf = trades_to_dataframe(engine.trades)
            r_stats = calculate_stats(tdf)
            all_r_stats[key] = r_stats

            # Simulate dollar PnL
            pnl_df = simulate_dollar_pnl(tdf, INITIAL_BALANCE, risk_pct)
            all_pnl[key] = pnl_df

            d_stats = compute_dollar_stats(pnl_df, INITIAL_BALANCE)
            all_dollar_stats[key] = d_stats

            all_trades_dfs[key] = tdf

            exp = r_stats.get("expectancy_R", 0)
            wr = r_stats.get("win_rate_ex_BE", 0)
            pf = r_stats.get("profit_factor", 0)
            final = d_stats.get("final_equity", INITIAL_BALANCE)
            pnl = d_stats.get("total_pnl_usd", 0)
            ret = d_stats.get("total_return_pct", 0)

            print(f"    {n_trades} trades | Exp={exp:.4f}R | WR={wr:.1f}% | PF={pf:.2f}")
            print(f"    ${INITIAL_BALANCE:,.0f} → ${final:,.0f} | PnL=${pnl:+,.0f} | Return={ret:+.1f}% | {run_s:.1f}s")

            # ── SAVE IMMEDIATELY ──
            print(f"    💾 Saving {key} results to disk...")
            _save_combo_results(key, pnl_df, r_stats, d_stats, engine.trades, risk_pct)
        else:
            r_stats = {"trade_count": 0, "error": "No trades"}
            d_stats = {"error": "No trades", "trade_count": 0}
            all_r_stats[key] = r_stats
            all_dollar_stats[key] = d_stats
            all_pnl[key] = pd.DataFrame()
            print(f"    0 trades | {run_s:.1f}s")

            # Save even empty results
            _save_combo_results(key, pd.DataFrame(), r_stats, d_stats, [], risk_pct)

        # ── UPDATE PROGRESS & CUMULATIVE FILES ──
        _update_progress(progress_path, key, "done", run_s)
        _update_cumulative_summary(all_r_stats, all_dollar_stats)
        print(f"    ✅ {key} saved & progress updated ({idx}/{len(entries)} complete)")

        # Free engine memory for large datasets
        del engine
        if 'df' in dir():
            del df

    # ---------------------------------------------------------------
    # PHASE 2: Save aggregated trades
    # ---------------------------------------------------------------
    pprint_section("PHASE 2: SAVING AGGREGATED TRADE DATA")

    all_tdf_frames = [df for df in all_trades_dfs.values() if not df.empty]
    if all_tdf_frames:
        all_tdf = pd.concat(all_tdf_frames, ignore_index=True)
        all_tdf.to_csv(AGGREGATE_DIR / "all_trades.csv", index=False)
        print(f"  Saved {len(all_tdf):,} trades to aggregate/all_trades.csv")
    else:
        all_tdf = pd.DataFrame()
        print("  No trades to save.")

    # Final cumulative save
    _update_cumulative_summary(all_r_stats, all_dollar_stats)
    print(f"  Saved aggregate/portfolio_stats.json & portfolio_summary.csv")

    # ---------------------------------------------------------------
    # PHASE 3: Generate Portfolio-Level Charts
    # ---------------------------------------------------------------
    pprint_section("PHASE 3: GENERATING PORTFOLIO CHARTS")

    per_combo_chart_count = sum(1 for v in all_pnl.values() if not isinstance(v, pd.DataFrame) or not v.empty)
    print(f"  Per-combination charts already generated: {per_combo_chart_count * 2} (equity + return)")

    try:
        # Portfolio-level charts (need all data) — split into 4 separate PNGs
        plot_portfolio_overview_split(all_pnl, INITIAL_BALANCE, str(CHARTS_DIR))
        print(f"  Generated 4 portfolio overview charts (final_equity, pnl_by_symbol, pnl_by_timeframe, return_pct)")

        plot_combined_equity(all_pnl, INITIAL_BALANCE,
                             str(CHARTS_DIR / "combined_equity.png"))
        print(f"  Generated aggregate/charts/combined_equity.png")

        plot_per_symbol_equity(all_pnl, INITIAL_BALANCE,
                               str(CHARTS_DIR / "per_symbol_equity.png"))
        print(f"  Generated aggregate/charts/per_symbol_equity.png")

        plot_heatmap(all_dollar_stats,
                      str(CHARTS_DIR / "return_heatmap.png"))
        print(f"  Generated aggregate/charts/return_heatmap.png")

        plot_pnl_ranking(all_dollar_stats,
                          str(CHARTS_DIR / "pnl_ranking.png"))
        print(f"  Generated aggregate/charts/pnl_ranking.png")

        # Industry-standard extra charts (also go into charts dir)
        generate_extra_charts(all_pnl, all_tdf if not all_tdf.empty else pd.DataFrame(),
                              INITIAL_BALANCE, str(CHARTS_DIR))

    except Exception as e:
        print(f"  [WARN] Chart generation error: {e}")
        import traceback
        traceback.print_exc()

    # ---------------------------------------------------------------
    # PHASE 4: Generate Reports
    # ---------------------------------------------------------------
    pprint_section("PHASE 4: GENERATING REPORTS")

    elapsed = time.time() - start_wall

    # Markdown report
    report = generate_portfolio_report(
        all_r_stats, all_dollar_stats, all_pnl,
        INITIAL_BALANCE, elapsed
    )
    report_path = AGGREGATE_DIR / "PORTFOLIO_REPORT.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Saved aggregate/PORTFOLIO_REPORT.md")

    # ---------------------------------------------------------------
    # FINAL SUMMARY
    # ---------------------------------------------------------------
    total_initial = INITIAL_BALANCE * len(entries)
    total_final = sum(v.get("final_equity", INITIAL_BALANCE)
                      for v in all_dollar_stats.values() if "error" not in v)
    total_final += INITIAL_BALANCE * sum(1 for v in all_dollar_stats.values() if "error" in v)
    total_pnl = total_final - total_initial
    total_ret = (total_pnl / total_initial * 100) if total_initial > 0 else 0
    total_trades = sum(v.get("trade_count", 0)
                       for v in all_dollar_stats.values() if "error" not in v)

    profitable_count = sum(1 for v in all_dollar_stats.values()
                           if v.get("total_pnl_usd", 0) > 0)

    minutes = int(elapsed // 60)
    seconds = elapsed % 60

    pprint_section("COMPLETE PORTFOLIO BACKTEST FINISHED", "█", 78)
    print(f"  Combinations:    {len(entries)} / 55")
    print(f"  Total Trades:    {total_trades:,}")
    print(f"  Initial Capital: ${total_initial:,.0f}")
    print(f"  Final Capital:   ${total_final:,.0f}")
    print(f"  Net PnL:         ${total_pnl:+,.0f}")
    print(f"  Total Return:    {total_ret:+.2f}%")
    print(f"  Profitable:      {profitable_count} / {len(entries)} accounts")
    print(f"  Wall Time:       {minutes}m {seconds:.0f}s")
    print(f"  Results:         {PORTFOLIO_DIR}/")

    # Console comparison table
    print(f"\n{'='*100}")
    print(f"  {'Combination':<20} {'Trades':>7} {'WR%':>6} {'ExpR':>8} {'PF':>6} "
          f"{'Start':>10} {'Final':>12} {'PnL':>12} {'Return':>8} {'MaxDD%':>7}")
    print(f"  {'-'*98}")
    for key in sorted(all_dollar_stats.keys()):
        ds = all_dollar_stats[key]
        rs = all_r_stats.get(key, {})
        if "error" in ds:
            print(f"  {key:<20} {'0':>7} {'-':>6} {'-':>8} {'-':>6} "
                  f"{'$10,000':>10} {'$10,000':>12} {'$0':>12} {'0.0%':>8} {'-':>7}")
            continue
        start_str = f"${INITIAL_BALANCE:,.0f}"
        final_str = f"${ds['final_equity']:,.0f}"
        pnl_str = f"${ds['total_pnl_usd']:+,.0f}"
        print(f"  {key:<20} {ds['trade_count']:>7} {rs.get('win_rate_ex_BE',0):>5.1f}% "
              f"{rs.get('expectancy_R',0):>7.4f} {rs.get('profit_factor',0):>5.2f} "
              f"{start_str:>10} {final_str:>12} "
              f"{pnl_str:>12} "
              f"{ds['total_return_pct']:>+7.1f}% {ds['max_drawdown_pct']:>6.1f}%")
    print(f"{'='*100}")

    # Mark progress as fully complete
    _update_progress(progress_path, "__PORTFOLIO_COMPLETE__", "done", elapsed)
    print(f"\n  ✅ All results saved. Safe to interrupt at any time during future runs.")


if __name__ == "__main__":
    main()
