"""
ASR Engine v3 — Charts & Visualizations
=========================================
Generates all required visual outputs using matplotlib:
  - Equity curve
  - Drawdown chart
  - Score calibration plot (monotonicity check)
  - Walk-forward OOS vs IS comparison
  - Monte Carlo distribution plots
  - Per-symbol/regime breakdown charts

All charts save as PNG files. No paid dependencies required.
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Check matplotlib availability
try:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend for server/CI
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    logger.warning("matplotlib not installed. Charts will not be generated. "
                   "Install with: pip install matplotlib")


# ============================================================
# STYLE SETUP
# ============================================================
COLORS = {
    "primary": "#2196F3",
    "win": "#4CAF50",
    "loss": "#F44336",
    "be": "#FFC107",
    "drawdown": "#E91E63",
    "grid": "#E0E0E0",
    "bg": "#FAFAFA",
    "text": "#212121",
    "accent": "#FF9800",
    "mc_fill": "#90CAF9",
}


def _setup_style():
    """Apply consistent chart styling."""
    if not HAS_MPL:
        return
    plt.rcParams.update({
        "figure.facecolor": COLORS["bg"],
        "axes.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.color": COLORS["grid"],
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "figure.dpi": 150,
    })


# ============================================================
# EQUITY CURVE
# ============================================================
def plot_equity_curve(trades, save_path: str = "equity_curve.png",
                      title: str = "ASR Engine v3 — Equity Curve (R)"):
    """
    Plot cumulative R equity curve with drawdown overlay.

    Args:
        trades: List of TradeResult objects (must have .net_r)
        save_path: Output file path
        title: Chart title
    """
    if not HAS_MPL:
        logger.warning("matplotlib not available, skipping equity curve")
        return

    _setup_style()
    net_rs = np.array([t.net_r for t in trades])
    cum_r = np.cumsum(net_rs)
    peak = np.maximum.accumulate(cum_r)
    dd = peak - cum_r

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8),
                                    gridspec_kw={"height_ratios": [3, 1]},
                                    sharex=True)

    # Equity curve
    x = np.arange(len(cum_r))
    ax1.plot(x, cum_r, color=COLORS["primary"], linewidth=1.5, label="Equity (R)")
    ax1.fill_between(x, 0, cum_r, alpha=0.1, color=COLORS["primary"])
    ax1.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax1.set_title(title)
    ax1.set_ylabel("Cumulative R")
    ax1.legend(loc="upper left")

    # Color individual trades
    for i, r in enumerate(net_rs):
        color = COLORS["win"] if r > 0.1 else COLORS["loss"] if r < -0.1 else COLORS["be"]
        ax1.bar(i, r, bottom=cum_r[i] - r, color=color, alpha=0.3, width=1.0)

    # Drawdown
    ax2.fill_between(x, 0, -dd, color=COLORS["drawdown"], alpha=0.5)
    ax2.plot(x, -dd, color=COLORS["drawdown"], linewidth=0.8)
    ax2.set_ylabel("Drawdown (R)")
    ax2.set_xlabel("Trade #")
    ax2.set_title("Drawdown")

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()
    logger.info(f"Equity curve saved to {save_path}")


# ============================================================
# SCORE CALIBRATION PLOT
# ============================================================
def plot_score_calibration(calibration_df: pd.DataFrame,
                           save_path: str = "score_calibration.png"):
    """
    Plot score calibration: avg R and win rate per score bucket.
    Checks for monotonic relationship (higher score → better outcome).

    Args:
        calibration_df: Output from calibrate_scores() with columns:
                        bucket, count, avg_r, win_rate, loss_rate, be_rate
        save_path: Output file path
    """
    if not HAS_MPL or calibration_df.empty:
        return

    _setup_style()
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 6))

    buckets = calibration_df["bucket"].astype(str).values
    x = np.arange(len(buckets))

    # Avg R per bucket
    colors = [COLORS["win"] if r > 0 else COLORS["loss"]
              for r in calibration_df["avg_r"]]
    ax1.bar(x, calibration_df["avg_r"], color=colors, alpha=0.8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(buckets, rotation=45)
    ax1.set_title("Average R by Score Bucket")
    ax1.set_ylabel("Average R")
    ax1.axhline(0, color="gray", linewidth=0.5, linestyle="--")

    # Check monotonicity
    avg_rs = calibration_df["avg_r"].values
    is_monotonic = all(avg_rs[i] <= avg_rs[i + 1] for i in range(len(avg_rs) - 1))
    mono_text = "✅ MONOTONIC" if is_monotonic else "⚠️ NON-MONOTONIC"
    ax1.text(0.02, 0.98, mono_text, transform=ax1.transAxes,
             fontsize=10, verticalalignment="top",
             bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    # Win rate per bucket
    ax2.bar(x, calibration_df["win_rate"], color=COLORS["win"], alpha=0.7,
            label="Win %")
    ax2.bar(x, calibration_df["be_rate"], bottom=calibration_df["win_rate"],
            color=COLORS["be"], alpha=0.7, label="BE %")
    ax2.bar(x, calibration_df["loss_rate"],
            bottom=calibration_df["win_rate"] + calibration_df["be_rate"],
            color=COLORS["loss"], alpha=0.7, label="Loss %")
    ax2.set_xticks(x)
    ax2.set_xticklabels(buckets, rotation=45)
    ax2.set_title("Outcome Distribution by Score Bucket")
    ax2.set_ylabel("Percentage")
    ax2.legend(fontsize=8)

    # Trade count per bucket
    ax3.bar(x, calibration_df["count"], color=COLORS["accent"], alpha=0.7)
    ax3.set_xticks(x)
    ax3.set_xticklabels(buckets, rotation=45)
    ax3.set_title("Trade Count by Score Bucket")
    ax3.set_ylabel("Count")
    ax3.axhline(300, color=COLORS["loss"], linewidth=1, linestyle="--",
                label="Min reliable (300)")
    ax3.legend(fontsize=8)

    fig.suptitle("ASR Engine v3 — Score Calibration Analysis", fontsize=14,
                 fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()
    logger.info(f"Score calibration chart saved to {save_path}")


# ============================================================
# MONTE CARLO DISTRIBUTION
# ============================================================
def plot_monte_carlo(mc_results: dict, save_path: str = "monte_carlo.png"):
    """
    Plot Monte Carlo simulation results.

    Args:
        mc_results: Output from monte_carlo() function
        save_path: Output file path
    """
    if not HAS_MPL or "error" in mc_results:
        return

    _setup_style()
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # Terminal equity distribution
    te = mc_results.get("terminal_equity", {})
    if te:
        values = [te.get("p5", 0), te.get("p25", 0), te.get("median", 0),
                  te.get("p75", 0), te.get("p95", 0)]
        labels = ["5th", "25th", "50th", "75th", "95th"]
        colors_te = [COLORS["loss"], COLORS["accent"], COLORS["primary"],
                     COLORS["win"], COLORS["win"]]
        axes[0].barh(labels, values, color=colors_te, alpha=0.8)
        axes[0].axvline(1.0, color="gray", linewidth=1, linestyle="--",
                        label="Starting equity")
        axes[0].set_title("Terminal Equity Distribution")
        axes[0].set_xlabel("Equity Multiple")
        axes[0].legend(fontsize=8)

    # Max drawdown distribution
    dd = mc_results.get("max_drawdown", {})
    if dd:
        dd_values = [dd.get("mean", 0), dd.get("median", 0),
                     dd.get("p95", 0), dd.get("p99", 0)]
        dd_labels = ["Mean", "Median", "95th", "99th"]
        dd_colors = [COLORS["accent"], COLORS["primary"],
                     COLORS["loss"], COLORS["drawdown"]]
        axes[1].barh(dd_labels, [v * 100 for v in dd_values],
                     color=dd_colors, alpha=0.8)
        axes[1].set_title("Max Drawdown Distribution")
        axes[1].set_xlabel("Drawdown %")

    # Risk metrics
    risk_labels = []
    risk_values = []
    risk_colors_list = []

    prob_20 = mc_results.get("prob_severe_dd_20pct", 0) * 100
    prob_30 = mc_results.get("prob_severe_dd_30pct", 0) * 100
    ruin = mc_results.get("risk_of_ruin_50pct", 0) * 100

    risk_labels = ["P(DD > 20%)", "P(DD > 30%)", "P(Ruin 50%)"]
    risk_values = [prob_20, prob_30, ruin]
    risk_colors_list = [COLORS["accent"], COLORS["loss"], COLORS["drawdown"]]

    axes[2].barh(risk_labels, risk_values, color=risk_colors_list, alpha=0.8)
    axes[2].set_title("Risk Probabilities")
    axes[2].set_xlabel("Probability %")
    axes[2].set_xlim(0, 100)

    fig.suptitle(
        f"ASR Engine v3 — Monte Carlo ({mc_results.get('n_simulations', 0):,} sims, "
        f"{mc_results.get('n_trades', 0)} trades)",
        fontsize=14, fontweight="bold", y=1.02
    )
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()
    logger.info(f"Monte Carlo chart saved to {save_path}")


# ============================================================
# WALK-FORWARD COMPARISON
# ============================================================
def plot_walk_forward(wf_results: dict, save_path: str = "walk_forward.png"):
    """
    Plot walk-forward optimization results: IS vs OOS comparison.

    Args:
        wf_results: Output from walk_forward() function
        save_path: Output file path
    """
    if not HAS_MPL or "error" in wf_results:
        return

    _setup_style()
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))

    val_stats = wf_results.get("validation", {})
    test_stats = wf_results.get("test", {})

    # Metric comparison
    metrics = ["expectancy_r", "profit_factor", "win_rate_ex_BE", "max_dd_r"]
    metric_labels = ["Expectancy R", "Profit Factor", "Win Rate %", "Max DD R"]

    val_values = [val_stats.get(m, 0) for m in metrics]
    test_values = [test_stats.get(m, 0) for m in metrics]

    x = np.arange(len(metrics))
    width = 0.35

    axes[0].bar(x - width / 2, val_values, width, label="Validation (IS)",
                color=COLORS["primary"], alpha=0.8)
    axes[0].bar(x + width / 2, test_values, width, label="Test (OOS)",
                color=COLORS["accent"], alpha=0.8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(metric_labels, rotation=45, ha="right")
    axes[0].set_title("IS vs OOS Performance")
    axes[0].legend(fontsize=8)

    # OOS stability
    oos_stability = wf_results.get("oos_stability", 0)
    stability_color = COLORS["win"] if oos_stability >= 0.7 else COLORS["loss"]
    axes[1].barh(["OOS Stability"], [oos_stability * 100],
                 color=stability_color, alpha=0.8)
    axes[1].axvline(70, color=COLORS["loss"], linewidth=1, linestyle="--",
                    label="Minimum (70%)")
    axes[1].set_title("Out-of-Sample Stability")
    axes[1].set_xlabel("OOS/IS Ratio %")
    axes[1].set_xlim(0, 150)
    axes[1].legend(fontsize=8)

    # Best parameters
    best = wf_results.get("best_params", {})
    if best:
        params = list(best.keys())
        values = [str(v) for v in best.values()]
        axes[2].barh(params, range(len(params)), color=COLORS["primary"], alpha=0)
        for i, (p, v) in enumerate(zip(params, values)):
            axes[2].text(0.5, i, f"{p}: {v}", ha="center", va="center",
                         fontsize=11, fontweight="bold",
                         bbox=dict(boxstyle="round,pad=0.3",
                                   facecolor=COLORS["mc_fill"], alpha=0.5))
        axes[2].set_title("Optimized Parameters")
        axes[2].set_yticks([])
        axes[2].set_xticks([])

    fig.suptitle("ASR Engine v3 — Walk-Forward Optimization",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()
    logger.info(f"Walk-forward chart saved to {save_path}")


# ============================================================
# PER-SYMBOL BREAKDOWN
# ============================================================
def plot_symbol_breakdown(all_trades: Dict[str, list],
                          save_path: str = "symbol_breakdown.png"):
    """
    Plot performance breakdown across symbols.

    Args:
        all_trades: Dict mapping "SYMBOL_TF" to list of TradeResult
        save_path: Output file path
    """
    if not HAS_MPL or not all_trades:
        return

    _setup_style()
    from .reporting import trades_to_dataframe, calculate_stats

    rows = []
    for key, trades in all_trades.items():
        df = trades_to_dataframe(trades)
        if df.empty:
            continue
        stats = calculate_stats(df)
        rows.append({
            "key": key,
            "trades": stats.get("trade_count", 0),
            "exp_r": stats.get("expectancy_R", 0),
            "net_r": stats.get("net_R", 0),
            "wr": stats.get("win_rate_ex_BE", 0),
            "pf": stats.get("profit_factor", 0),
            "dd": stats.get("max_DD_R", 0),
        })

    if not rows:
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    keys = [r["key"] for r in rows]
    x = np.arange(len(keys))

    # Expectancy R
    exp_colors = [COLORS["win"] if r["exp_r"] > 0 else COLORS["loss"] for r in rows]
    axes[0, 0].bar(x, [r["exp_r"] for r in rows], color=exp_colors, alpha=0.8)
    axes[0, 0].set_xticks(x)
    axes[0, 0].set_xticklabels(keys, rotation=45, ha="right", fontsize=8)
    axes[0, 0].set_title("Expectancy R per Symbol")
    axes[0, 0].axhline(0, color="gray", linewidth=0.5, linestyle="--")

    # Net R
    net_colors = [COLORS["win"] if r["net_r"] > 0 else COLORS["loss"] for r in rows]
    axes[0, 1].bar(x, [r["net_r"] for r in rows], color=net_colors, alpha=0.8)
    axes[0, 1].set_xticks(x)
    axes[0, 1].set_xticklabels(keys, rotation=45, ha="right", fontsize=8)
    axes[0, 1].set_title("Net R per Symbol")
    axes[0, 1].axhline(0, color="gray", linewidth=0.5, linestyle="--")

    # Win Rate
    axes[1, 0].bar(x, [r["wr"] for r in rows], color=COLORS["primary"], alpha=0.8)
    axes[1, 0].set_xticks(x)
    axes[1, 0].set_xticklabels(keys, rotation=45, ha="right", fontsize=8)
    axes[1, 0].set_title("Win Rate % (ex BE)")
    axes[1, 0].axhline(50, color="gray", linewidth=0.5, linestyle="--")

    # Trade count
    axes[1, 1].bar(x, [r["trades"] for r in rows], color=COLORS["accent"], alpha=0.8)
    axes[1, 1].set_xticks(x)
    axes[1, 1].set_xticklabels(keys, rotation=45, ha="right", fontsize=8)
    axes[1, 1].set_title("Trade Count")
    axes[1, 1].axhline(300, color=COLORS["loss"], linewidth=1, linestyle="--")

    fig.suptitle("ASR Engine v3 — Symbol Performance Breakdown",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()
    logger.info(f"Symbol breakdown chart saved to {save_path}")


# ============================================================
# REGIME PERFORMANCE CHART
# ============================================================
def plot_regime_breakdown(trades, save_path: str = "regime_breakdown.png"):
    """Plot performance breakdown by market regime."""
    if not HAS_MPL:
        return

    _setup_style()
    from .reporting import trades_to_dataframe, stats_by_group

    df = trades_to_dataframe(trades)
    if df.empty or "regime" not in df.columns:
        return

    grouped = stats_by_group(df, "regime")
    if grouped.empty:
        return

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    regimes = grouped["regime"].astype(str).values
    x = np.arange(len(regimes))

    # Avg R
    colors = [COLORS["win"] if r > 0 else COLORS["loss"]
              for r in grouped["avg_R"]]
    axes[0].bar(x, grouped["avg_R"], color=colors, alpha=0.8)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(regimes, rotation=45, ha="right")
    axes[0].set_title("Avg R by Regime")

    # Win rate
    axes[1].bar(x, grouped["win_rate_%"], color=COLORS["primary"], alpha=0.8)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(regimes, rotation=45, ha="right")
    axes[1].set_title("Win Rate % by Regime")

    # Trade count
    axes[2].bar(x, grouped["trades"], color=COLORS["accent"], alpha=0.8)
    axes[2].set_xticks(x)
    axes[2].set_xticklabels(regimes, rotation=45, ha="right")
    axes[2].set_title("Trade Count by Regime")
    axes[2].axhline(300, color=COLORS["loss"], linewidth=1, linestyle="--")

    fig.suptitle("ASR Engine v3 — Regime Performance",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()
    logger.info(f"Regime breakdown chart saved to {save_path}")


# ============================================================
# GENERATE ALL CHARTS
# ============================================================
def generate_all_charts(trades, calibration_df=None, mc_results=None,
                        wf_results=None, all_trades=None,
                        output_dir: str = "charts"):
    """
    Generate all charts and save to output directory.

    Args:
        trades: List of TradeResult objects
        calibration_df: Output from calibrate_scores()
        mc_results: Output from monte_carlo()
        wf_results: Output from walk_forward()
        all_trades: Dict of symbol → trades for multi-symbol charts
        output_dir: Directory to save charts
    """
    if not HAS_MPL:
        logger.warning("matplotlib not available. Install with: pip install matplotlib")
        return

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating charts in {out}/")

    # 1. Equity curve
    if trades:
        plot_equity_curve(trades, str(out / "equity_curve.png"))

    # 2. Score calibration
    if calibration_df is not None and not calibration_df.empty:
        plot_score_calibration(calibration_df, str(out / "score_calibration.png"))

    # 3. Monte Carlo
    if mc_results and "error" not in mc_results:
        plot_monte_carlo(mc_results, str(out / "monte_carlo.png"))

    # 4. Walk-forward
    if wf_results and "error" not in wf_results:
        plot_walk_forward(wf_results, str(out / "walk_forward.png"))

    # 5. Symbol breakdown
    if all_trades:
        plot_symbol_breakdown(all_trades, str(out / "symbol_breakdown.png"))

    # 6. Regime breakdown
    if trades:
        plot_regime_breakdown(trades, str(out / "regime_breakdown.png"))

    logger.info(f"All charts generated in {out}/")
