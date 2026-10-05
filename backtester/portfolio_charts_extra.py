"""
ASR Engine v3 — Industry-Standard Extra Portfolio Charts
=========================================================
Additional charts for a complete industry-grade portfolio report:
  - Monthly returns calendar heatmap
  - R-multiple distribution histogram
  - Trade duration histogram (winners vs losers)
  - Rolling Sharpe / Expectancy chart
  - Win/Loss streak distribution
  - Setup type performance breakdown
"""
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path


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


def _ts_to_datetime(ts):
    """Convert timestamp (ms or s) to datetime."""
    if ts is None or (isinstance(ts, float) and np.isnan(ts)):
        return None
    if isinstance(ts, (int, float)):
        if ts > 1e12:
            ts = ts / 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (OSError, ValueError):
            return None
    return ts


# ============================================================
# MONTHLY RETURNS HEATMAP
# ============================================================
def plot_monthly_returns(all_pnl: dict, initial_balance: float, save_path: str):
    """Plot monthly returns heatmap from all combined trades."""
    plt = _setup_mpl()

    all_rows = []
    for key, pnl_df in all_pnl.items():
        if pnl_df.empty:
            continue
        for _, row in pnl_df.iterrows():
            et = row.get("exit_time")
            dt = _ts_to_datetime(et)
            if dt is not None:
                all_rows.append({
                    "year": dt.year,
                    "month": dt.month,
                    "dollar_pnl": row["dollar_pnl"],
                })

    if not all_rows:
        return

    df = pd.DataFrame(all_rows)
    pivot = df.pivot_table(values="dollar_pnl", index="year", columns="month",
                           aggfunc="sum", fill_value=0)

    month_names = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                   7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}
    pivot.columns = [month_names.get(c, c) for c in pivot.columns]

    fig, ax = plt.subplots(figsize=(14, max(3, len(pivot) * 1.2)))

    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "pnl", ["#F44336", "#FFCDD2", "#FFFFFF", "#C8E6C9", "#4CAF50"]
    )

    matrix = pivot.values
    abs_max = max(abs(np.nanmin(matrix)), abs(np.nanmax(matrix)), 1)
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=-abs_max, vmax=abs_max)

    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_yticklabels(pivot.index)

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = matrix[i, j]
            color = "white" if abs(val) > abs_max * 0.6 else "black"
            ax.text(j, i, f"${val:+,.0f}", ha="center", va="center",
                    fontsize=8, fontweight="bold", color=color)

    plt.colorbar(im, ax=ax, label="Monthly PnL ($)", shrink=0.8)
    ax.set_title("ASR Engine v3 — Monthly Returns Heatmap (All Accounts Combined)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


# ============================================================
# R-MULTIPLE DISTRIBUTION
# ============================================================
def plot_r_distribution(all_pnl: dict, save_path: str):
    """Plot R-multiple distribution histogram."""
    plt = _setup_mpl()

    all_r = []
    for pnl_df in all_pnl.values():
        if not pnl_df.empty:
            all_r.extend(pnl_df["net_r"].tolist())

    if not all_r:
        return

    r_arr = np.array(all_r)

    fig, ax = plt.subplots(figsize=(14, 6))

    lo = max(r_arr.min(), -3)
    hi = min(r_arr.max(), 6)
    bins = np.arange(lo, hi + 0.2, 0.2)
    n, bins_out, patches = ax.hist(r_arr, bins=bins, edgecolor="white",
                                    linewidth=0.5, alpha=0.85)

    for patch, left_edge in zip(patches, bins_out[:-1]):
        if left_edge >= 0:
            patch.set_facecolor("#4CAF50")
        else:
            patch.set_facecolor("#F44336")

    ax.axvline(np.mean(r_arr), color="#2196F3", linewidth=2, linestyle="--",
               label=f"Mean: {np.mean(r_arr):.3f}R")
    ax.axvline(np.median(r_arr), color="#FF9800", linewidth=2, linestyle="--",
               label=f"Median: {np.median(r_arr):.3f}R")
    ax.axvline(0, color="black", linewidth=1.5, linestyle="-")

    ax.set_title(f"ASR Engine v3 — R-Multiple Distribution ({len(r_arr):,} trades)",
                 fontsize=13, fontweight="bold")
    ax.set_xlabel("Net R-Multiple")
    ax.set_ylabel("Frequency")
    ax.legend(loc="upper right")

    stats_text = (f"N = {len(r_arr):,}\n"
                  f"Mean = {np.mean(r_arr):.4f}R\n"
                  f"Std = {np.std(r_arr):.4f}R\n"
                  f"Skew = {float(pd.Series(r_arr).skew()):.3f}\n"
                  f"Kurt = {float(pd.Series(r_arr).kurtosis()):.3f}")
    ax.text(0.98, 0.95, stats_text, transform=ax.transAxes,
            fontsize=9, verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow"))

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


# ============================================================
# TRADE DURATION HISTOGRAM
# ============================================================
def plot_trade_duration(all_trades_df: pd.DataFrame, save_path: str):
    """Plot trade duration (hold bars) histogram."""
    plt = _setup_mpl()

    if all_trades_df.empty or "hold_bars" not in all_trades_df.columns:
        return

    hold = all_trades_df["hold_bars"].dropna().values
    if len(hold) == 0:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    max_hold = int(np.percentile(hold, 99))
    bins = np.arange(0, max_hold + 2, max(1, max_hold // 40))

    ax1.hist(hold, bins=bins, color="#2196F3", edgecolor="white",
             linewidth=0.5, alpha=0.85)
    ax1.axvline(np.mean(hold), color="#F44336", linewidth=2, linestyle="--",
                label=f"Mean: {np.mean(hold):.1f} bars")
    ax1.axvline(np.median(hold), color="#FF9800", linewidth=2, linestyle="--",
                label=f"Median: {np.median(hold):.0f} bars")
    ax1.set_title("Trade Duration Distribution", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Hold Duration (bars)")
    ax1.set_ylabel("Frequency")
    ax1.legend()

    wins = all_trades_df[all_trades_df["net_r"] > 0.1]["hold_bars"].dropna().values
    losses = all_trades_df[all_trades_df["net_r"] < -0.1]["hold_bars"].dropna().values
    w_label = f"Wins (avg {np.mean(wins):.1f})" if len(wins) > 0 else "Wins"
    l_label = f"Losses (avg {np.mean(losses):.1f})" if len(losses) > 0 else "Losses"
    ax2.hist(wins, bins=bins, color="#4CAF50", alpha=0.6, label=w_label, edgecolor="white")
    ax2.hist(losses, bins=bins, color="#F44336", alpha=0.6, label=l_label, edgecolor="white")
    ax2.set_title("Duration: Winners vs Losers", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Hold Duration (bars)")
    ax2.set_ylabel("Frequency")
    ax2.legend()

    fig.suptitle("ASR Engine v3 — Trade Duration Analysis", fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


# ============================================================
# ROLLING SHARPE & EXPECTANCY
# ============================================================
def plot_rolling_sharpe(all_pnl: dict, save_path: str, window: int = 100):
    """Plot rolling Sharpe ratio and expectancy over trade sequence."""
    plt = _setup_mpl()

    all_rows = []
    for key, pnl_df in all_pnl.items():
        if pnl_df.empty:
            continue
        for _, row in pnl_df.iterrows():
            all_rows.append({
                "exit_time": row.get("exit_time"),
                "dollar_pnl": row["dollar_pnl"],
                "net_r": row["net_r"],
            })

    if not all_rows:
        return

    merged = pd.DataFrame(all_rows).sort_values("exit_time").reset_index(drop=True)

    if len(merged) < window:
        window = max(20, len(merged) // 3)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), sharex=True)

    r_vals = merged["net_r"].values
    rolling_mean = pd.Series(r_vals).rolling(window).mean()
    rolling_std = pd.Series(r_vals).rolling(window).std()
    valid_mask = rolling_std > 0
    rolling_sharpe = pd.Series(np.nan, index=rolling_mean.index)
    rolling_sharpe[valid_mask] = rolling_mean[valid_mask] / rolling_std[valid_mask] * np.sqrt(252)
    rolling_sharpe = rolling_sharpe.dropna()

    x = rolling_sharpe.index.values
    ax1.plot(x, rolling_sharpe.values, color="#2196F3", linewidth=1.2)
    ax1.fill_between(x, 0, rolling_sharpe.values,
                     where=(rolling_sharpe.values >= 0), color="#4CAF50", alpha=0.15)
    ax1.fill_between(x, 0, rolling_sharpe.values,
                     where=(rolling_sharpe.values < 0), color="#F44336", alpha=0.15)
    ax1.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax1.axhline(1, color="#4CAF50", linewidth=0.8, linestyle=":", alpha=0.6, label="Sharpe = 1")
    ax1.axhline(2, color="#2196F3", linewidth=0.8, linestyle=":", alpha=0.6, label="Sharpe = 2")
    ax1.set_title(f"ASR Engine v3 — Rolling {window}-Trade Sharpe Ratio",
                  fontsize=13, fontweight="bold")
    ax1.set_ylabel("Sharpe Ratio (ann.)")
    ax1.legend(loc="upper right")

    rolling_exp = pd.Series(r_vals).rolling(window).mean().dropna()
    x2 = rolling_exp.index.values
    ax2.plot(x2, rolling_exp.values, color="#FF9800", linewidth=1.2)
    ax2.fill_between(x2, 0, rolling_exp.values,
                     where=(rolling_exp.values >= 0), color="#4CAF50", alpha=0.15)
    ax2.fill_between(x2, 0, rolling_exp.values,
                     where=(rolling_exp.values < 0), color="#F44336", alpha=0.15)
    ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax2.set_title(f"Rolling {window}-Trade Expectancy (R)", fontsize=12, fontweight="bold")
    ax2.set_ylabel("Expectancy (R)")
    ax2.set_xlabel("Trade #")

    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


# ============================================================
# WIN/LOSS STREAK DISTRIBUTION
# ============================================================
def plot_streak_distribution(all_trades_df: pd.DataFrame, save_path: str):
    """Plot win/loss streak distribution."""
    plt = _setup_mpl()

    if all_trades_df.empty:
        return

    r_vals = all_trades_df["net_r"].values
    win_streaks = []
    loss_streaks = []
    curr_w = 0
    curr_l = 0

    for r in r_vals:
        if r > 0.1:
            curr_w += 1
            if curr_l > 0:
                loss_streaks.append(curr_l)
                curr_l = 0
        elif r < -0.1:
            curr_l += 1
            if curr_w > 0:
                win_streaks.append(curr_w)
                curr_w = 0
        else:
            if curr_w > 0:
                win_streaks.append(curr_w)
                curr_w = 0
            if curr_l > 0:
                loss_streaks.append(curr_l)
                curr_l = 0

    if curr_w > 0:
        win_streaks.append(curr_w)
    if curr_l > 0:
        loss_streaks.append(curr_l)

    if not win_streaks and not loss_streaks:
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    if win_streaks:
        max_ws = max(win_streaks)
        bins = np.arange(0.5, max_ws + 1.5, 1)
        ax1.hist(win_streaks, bins=bins, color="#4CAF50", edgecolor="white",
                 alpha=0.85, rwidth=0.85)
        ax1.set_title(f"Winning Streak Distribution (max: {max_ws})",
                      fontsize=12, fontweight="bold")
        ax1.set_xlabel("Streak Length")
        ax1.set_ylabel("Frequency")
        ax1.text(0.95, 0.95, f"Avg: {np.mean(win_streaks):.1f}\nMax: {max_ws}",
                 transform=ax1.transAxes, fontsize=10, va="top", ha="right",
                 bbox=dict(boxstyle="round", facecolor="lightyellow"))

    if loss_streaks:
        max_ls = max(loss_streaks)
        bins = np.arange(0.5, max_ls + 1.5, 1)
        ax2.hist(loss_streaks, bins=bins, color="#F44336", edgecolor="white",
                 alpha=0.85, rwidth=0.85)
        ax2.set_title(f"Losing Streak Distribution (max: {max_ls})",
                      fontsize=12, fontweight="bold")
        ax2.set_xlabel("Streak Length")
        ax2.set_ylabel("Frequency")
        ax2.text(0.95, 0.95, f"Avg: {np.mean(loss_streaks):.1f}\nMax: {max_ls}",
                 transform=ax2.transAxes, fontsize=10, va="top", ha="right",
                 bbox=dict(boxstyle="round", facecolor="lightyellow"))

    fig.suptitle("ASR Engine v3 — Win/Loss Streak Analysis",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


# ============================================================
# SETUP TYPE PERFORMANCE
# ============================================================
def plot_setup_performance(all_trades_df: pd.DataFrame, save_path: str):
    """Plot performance by setup type."""
    plt = _setup_mpl()

    if all_trades_df.empty or "setup_type" not in all_trades_df.columns:
        return

    setup_groups = all_trades_df.groupby("setup_type")

    setups = []
    exp_rs = []
    counts = []
    win_rates = []

    for name, group in setup_groups:
        if len(group) < 5:
            continue
        r_vals = group["net_r"].values
        wins = (r_vals > 0.1).sum()
        losses = (r_vals < -0.1).sum()

        setups.append(str(name))
        exp_rs.append(float(r_vals.mean()))
        counts.append(len(group))
        win_rates.append(wins / (wins + losses) * 100 if (wins + losses) > 0 else 0)

    if not setups:
        return

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    colors = ["#4CAF50" if e >= 0 else "#F44336" for e in exp_rs]
    axes[0].barh(setups, exp_rs, color=colors, alpha=0.85)
    axes[0].axvline(0, color="gray", linewidth=0.8, linestyle="--")
    axes[0].set_title("Expectancy (R) by Setup", fontweight="bold")
    axes[0].set_xlabel("Expectancy (R)")

    axes[1].barh(setups, win_rates, color="#2196F3", alpha=0.85)
    axes[1].axvline(50, color="gray", linewidth=0.8, linestyle="--")
    axes[1].set_title("Win Rate by Setup", fontweight="bold")
    axes[1].set_xlabel("Win Rate (%)")

    axes[2].barh(setups, counts, color="#FF9800", alpha=0.85)
    axes[2].set_title("Trade Count by Setup", fontweight="bold")
    axes[2].set_xlabel("Number of Trades")

    fig.suptitle("ASR Engine v3 — Setup Type Performance Analysis",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


# ============================================================
# WRAPPER: Generate all extra charts
# ============================================================
def generate_extra_charts(all_pnl: dict, all_trades_df: pd.DataFrame,
                          initial_balance: float, output_dir: str):
    """
    Generate all industry-standard extra charts.
    
    Args:
        all_pnl: Dict[key, DataFrame] with dollar PnL per combination
        all_trades_df: Concatenated DataFrame of all trades (from trades_to_dataframe)
        initial_balance: Starting balance per account
        output_dir: Directory to save charts
    """
    out = Path(output_dir)
    generated = 0

    try:
        plot_monthly_returns(all_pnl, initial_balance, str(out / "monthly_returns.png"))
        print("  Generated monthly_returns.png")
        generated += 1
    except Exception as e:
        print(f"  [WARN] monthly_returns: {e}")

    try:
        plot_r_distribution(all_pnl, str(out / "r_distribution.png"))
        print("  Generated r_distribution.png")
        generated += 1
    except Exception as e:
        print(f"  [WARN] r_distribution: {e}")

    try:
        plot_trade_duration(all_trades_df, str(out / "trade_duration.png"))
        print("  Generated trade_duration.png")
        generated += 1
    except Exception as e:
        print(f"  [WARN] trade_duration: {e}")

    try:
        plot_rolling_sharpe(all_pnl, str(out / "rolling_sharpe.png"))
        print("  Generated rolling_sharpe.png")
        generated += 1
    except Exception as e:
        print(f"  [WARN] rolling_sharpe: {e}")

    try:
        plot_streak_distribution(all_trades_df, str(out / "streak_distribution.png"))
        print("  Generated streak_distribution.png")
        generated += 1
    except Exception as e:
        print(f"  [WARN] streak_distribution: {e}")

    try:
        plot_setup_performance(all_trades_df, str(out / "setup_performance.png"))
        print("  Generated setup_performance.png")
        generated += 1
    except Exception as e:
        print(f"  [WARN] setup_performance: {e}")

    print(f"  Generated {generated}/6 extra industry-standard charts")
    return generated
