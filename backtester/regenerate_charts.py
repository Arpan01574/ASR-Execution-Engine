"""
ASR Engine v3 — Chart Regeneration & Top 10 Report Generator
==============================================================
Regenerates ALL portfolio charts from saved data (no re-backtest needed)
and generates the Top 10 Demo Trading Picks report.

Usage:
    python -m backtester.regenerate_charts     (from project root)
    python regenerate_charts.py                (from backtester/)
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backtester.run_complete_portfolio import (
    SYMBOLS, ALL_TIMEFRAMES, INITIAL_BALANCE,
    PORTFOLIO_DIR, AGGREGATE_DIR, CHARTS_DIR,
    plot_portfolio_overview_split,
    plot_combined_equity,
    plot_per_symbol_equity,
    plot_heatmap,
    plot_pnl_ranking,
    _setup_mpl,
)
from backtester.portfolio_charts_extra import generate_extra_charts


def load_all_data():
    """Load all saved PnL data and stats from disk."""
    all_pnl = {}
    all_r_stats = {}
    all_dollar_stats = {}
    all_trades_dfs = {}

    for sym in SYMBOLS:
        base, quote = sym.split("/")
        for tf in ALL_TIMEFRAMES:
            key = f"{base}_{quote}_{tf}"
            combo_dir = PORTFOLIO_DIR / f"{base}_{quote}" / tf

            stats_path = combo_dir / "stats.json"
            pnl_path = combo_dir / "pnl.csv"
            trades_path = combo_dir / "trades.csv"

            if not stats_path.exists():
                continue

            with open(stats_path) as f:
                data = json.load(f)

            all_r_stats[key] = data.get("r_stats", {})
            all_dollar_stats[key] = data.get("dollar_stats", {})

            if pnl_path.exists():
                all_pnl[key] = pd.read_csv(pnl_path)
            else:
                all_pnl[key] = pd.DataFrame()

            if trades_path.exists():
                tdf = pd.read_csv(trades_path)
                if not tdf.empty:
                    all_trades_dfs[key] = tdf

    return all_pnl, all_r_stats, all_dollar_stats, all_trades_dfs


def generate_top10_report(all_r_stats: dict, all_dollar_stats: dict,
                           all_pnl: dict, output_path: str):
    """
    Generate a comprehensive Top 10 Demo Trading Picks report.
    
    Ranking criteria (industry-standard composite score):
    - 30% Expectancy (R)
    - 25% Profit Factor
    - 20% Risk-Adjusted Return (Sharpe)
    - 15% Win Rate
    - 10% Trade Volume (enough sample size)
    """
    candidates = []
    for key in sorted(all_dollar_stats.keys()):
        ds = all_dollar_stats[key]
        rs = all_r_stats.get(key, {})
        if "error" in ds or ds.get("trade_count", 0) < 20:
            continue

        parts = key.split("_")
        sym = f"{parts[0]}/{parts[1]}"
        tf = parts[2]

        exp_r = rs.get("expectancy_R", 0)
        pf = rs.get("profit_factor", 0)
        wr = rs.get("win_rate_ex_BE", 0)
        sharpe = rs.get("sharpe", 0)
        trades = ds.get("trade_count", 0)
        pnl = ds.get("total_pnl_usd", 0)
        ret = ds.get("total_return_pct", 0)
        max_dd = ds.get("max_drawdown_pct", 0)
        calmar = ds.get("calmar_ratio", 0)
        recovery = ds.get("recovery_factor", 0)
        sortino = ds.get("sortino_dollar", 0)

        # Composite score (normalized)
        # Higher is better for all metrics
        score = (
            0.30 * min(exp_r, 3.0) / 3.0 +       # Cap at 3R
            0.25 * min(pf, 15.0) / 15.0 +          # Cap at 15
            0.20 * min(sharpe, 12.0) / 12.0 +      # Cap at 12
            0.15 * min(wr, 80.0) / 80.0 +          # Cap at 80%
            0.10 * min(trades, 500) / 500           # Cap at 500
        ) * 100  # Scale to 0-100

        candidates.append({
            "key": key,
            "symbol": sym,
            "timeframe": tf,
            "score": round(score, 2),
            "exp_r": exp_r,
            "pf": pf,
            "wr": wr,
            "sharpe": sharpe,
            "sortino": sortino,
            "trades": trades,
            "pnl": pnl,
            "ret": ret,
            "max_dd": max_dd,
            "calmar": calmar,
            "recovery": recovery,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top10 = candidates[:10]

    # Generate report
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append("# ASR Engine v3 — Top 10 Demo Trading Picks")
    lines.append(f"*Generated: {now} | Ranked by composite score (Expectancy × PF × Sharpe × WR × Volume)*\n")

    lines.append("## Selection Criteria")
    lines.append("| Weight | Factor | Rationale |")
    lines.append("|--------|--------|-----------|")
    lines.append("| 30% | Expectancy (R) | Edge per trade — the most important metric |")
    lines.append("| 25% | Profit Factor | Gross profit / gross loss ratio |")
    lines.append("| 20% | Sharpe Ratio | Risk-adjusted returns (annualized) |")
    lines.append("| 15% | Win Rate | Psychological comfort & execution consistency |")
    lines.append("| 10% | Trade Volume | Statistical significance of the sample |")
    lines.append(f"\n*Minimum qualification: ≥ 20 trades in backtest period*\n")

    lines.append("## 🏆 Top 10 Recommended Combos for Demo Trading\n")
    lines.append("| Rank | Combination | Symbol | TF | Score | Trades | WR% | Exp R | PF | Sharpe | PnL $ | Return % | MaxDD % |")
    lines.append("|------|-------------|--------|-----|-------|--------|------|-------|-----|--------|-------|----------|---------|")

    for rank, c in enumerate(top10, 1):
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"#{rank}"
        lines.append(
            f"| {medal} | {c['key']} | {c['symbol']} | {c['timeframe']} | "
            f"{c['score']:.1f} | {c['trades']} | {c['wr']:.1f}% | "
            f"{c['exp_r']:.4f} | {c['pf']:.2f} | {c['sharpe']:.2f} | "
            f"${c['pnl']:+,.0f} | {c['ret']:+.1f}% | {c['max_dd']:.2f}% |"
        )

    lines.append("")

    # Per-pick detailed analysis
    lines.append("## Detailed Pick Analysis\n")
    for rank, c in enumerate(top10, 1):
        lines.append(f"### #{rank}: {c['key']} ({c['symbol']} on {c['timeframe']})")
        lines.append(f"- **Composite Score:** {c['score']:.1f}/100")
        lines.append(f"- **Why Selected:** ", )

        reasons = []
        if c['exp_r'] > 0.5:
            reasons.append(f"High expectancy ({c['exp_r']:.3f}R)")
        if c['pf'] > 5:
            reasons.append(f"Strong profit factor ({c['pf']:.2f})")
        if c['sharpe'] > 7:
            reasons.append(f"Excellent Sharpe ({c['sharpe']:.2f})")
        if c['wr'] > 60:
            reasons.append(f"High win rate ({c['wr']:.1f}%)")
        if c['trades'] > 200:
            reasons.append(f"Large sample size ({c['trades']} trades)")
        if c['max_dd'] < 2:
            reasons.append(f"Low drawdown ({c['max_dd']:.2f}%)")

        lines[-1] = f"- **Why Selected:** {', '.join(reasons) if reasons else 'Balanced across all metrics'}"

        lines.append(f"- **Performance:** ${c['pnl']:+,.0f} ({c['ret']:+.1f}%) from {c['trades']} trades")
        lines.append(f"- **Risk:** Max DD {c['max_dd']:.2f}% | Calmar {c['calmar']:.2f} | Recovery {c['recovery']:.2f}")
        lines.append(f"- **Sortino:** {c['sortino']:.3f}")
        lines.append("")

    # Deployment guide
    lines.append("## 🚀 Demo Deployment Guide\n")
    lines.append("### Step 1: Configure `.env`")
    lines.append("```bash")
    lines.append("BROKER=binance_paper")
    lines.append("BINANCE_API_KEY=your_demo_key")
    lines.append("BINANCE_API_SECRET=your_demo_secret")
    lines.append("BINANCE_TESTNET=true")
    lines.append("RISK_PER_TRADE_PCT=0.5")
    lines.append("INITIAL_CAPITAL=10000")
    lines.append("```\n")

    lines.append("### Step 2: TradingView Alert Configuration")
    lines.append("Set up webhook alerts for each of the Top 10 combos on TradingView:")
    lines.append("```json")
    lines.append('{')
    lines.append('  "action": "{{strategy.order.action}}",')
    lines.append('  "symbol": "{{ticker}}",')
    lines.append('  "timeframe": "<TF>",')
    lines.append('  "price": {{close}},')
    lines.append('  "secret": "<YOUR_WEBHOOK_SECRET>"')
    lines.append('}')
    lines.append("```\n")

    lines.append("### Step 3: Start Execution Engine")
    lines.append("```bash")
    lines.append("python -m execution.main")
    lines.append("```\n")

    # Portfolio allocation
    lines.append("## 💰 Suggested Portfolio Allocation\n")
    total_score = sum(c["score"] for c in top10)
    lines.append("| Rank | Combination | Score Weight | Allocation % | Capital ($10K total) |")
    lines.append("|------|-------------|-------------|--------------|---------------------|")
    for rank, c in enumerate(top10, 1):
        weight = c["score"] / total_score * 100
        alloc = 10000 * weight / 100
        lines.append(f"| {rank} | {c['key']} | {weight:.1f}% | {weight:.1f}% | ${alloc:,.0f} |")
    lines.append("")

    # Risk summary
    lines.append("## ⚠️ Risk Disclaimer\n")
    lines.append("- Past backtest performance does not guarantee future results")
    lines.append("- Start with paper/demo trading before committing real capital")
    lines.append("- Monitor drawdowns closely during the first 100 live trades")
    lines.append("- Consider reducing position sizes by 50% during the validation phase")
    lines.append("- The 0.5% risk per trade is already conservative; do not increase\n")

    report_text = "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    # Also save as CSV for easy import
    csv_path = str(Path(output_path).parent / "top10_picks.csv")
    pd.DataFrame(top10).to_csv(csv_path, index=False)

    return top10


def generate_top10_chart(top10: list, save_path: str):
    """Generate a visual chart of the Top 10 picks."""
    plt = _setup_mpl()
    fig, axes = plt.subplots(1, 3, figsize=(20, 8))

    keys = [c["key"] for c in top10]
    scores = [c["score"] for c in top10]
    pnls = [c["pnl"] for c in top10]
    exp_rs = [c["exp_r"] for c in top10]

    # 1. Composite Score
    colors = plt.cm.RdYlGn(np.linspace(0.4, 1.0, len(top10)))
    axes[0].barh(range(len(keys)), scores, color=colors[::-1], alpha=0.9)
    axes[0].set_yticks(range(len(keys)))
    axes[0].set_yticklabels(keys, fontsize=9)
    axes[0].set_xlabel("Composite Score (0-100)")
    axes[0].set_title("Composite Score Ranking", fontweight="bold")
    for i, s in enumerate(scores):
        axes[0].text(s + 0.5, i, f"{s:.1f}", va="center", fontsize=8)

    # 2. Net PnL
    pnl_colors = ["#4CAF50" if p >= 0 else "#F44336" for p in pnls]
    axes[1].barh(range(len(keys)), pnls, color=pnl_colors, alpha=0.85)
    axes[1].set_yticks(range(len(keys)))
    axes[1].set_yticklabels(keys, fontsize=9)
    axes[1].set_xlabel("Net PnL ($)")
    axes[1].set_title("Net PnL ($10K start)", fontweight="bold")
    axes[1].xaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"${x:,.0f}"))
    for i, p in enumerate(pnls):
        axes[1].text(p + 200, i, f"${p:+,.0f}", va="center", fontsize=7)

    # 3. Expectancy
    exp_colors = ["#4CAF50" if e > 0 else "#F44336" for e in exp_rs]
    axes[2].barh(range(len(keys)), exp_rs, color=exp_colors, alpha=0.85)
    axes[2].set_yticks(range(len(keys)))
    axes[2].set_yticklabels(keys, fontsize=9)
    axes[2].set_xlabel("Expectancy (R)")
    axes[2].set_title("Expectancy per Trade (R)", fontweight="bold")
    for i, e in enumerate(exp_rs):
        axes[2].text(e + 0.02, i, f"{e:.3f}R", va="center", fontsize=8)

    fig.suptitle("ASR Engine v3 — Top 10 Demo Trading Picks",
                 fontsize=15, fontweight="bold")
    plt.tight_layout()
    plt.savefig(save_path, bbox_inches="tight")
    plt.close()


def main():
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  ASR Engine v3 — Chart Regeneration & Top 10 Report")
    print("=" * 70)

    # Load data
    print("\n[1/4] Loading saved data from disk...")
    all_pnl, all_r_stats, all_dollar_stats, all_trades_dfs = load_all_data()
    print(f"  Loaded {len(all_pnl)} combinations")

    if not all_pnl:
        print("[ERR] No saved data found. Run the full backtest first.")
        return

    # Regenerate all charts
    print("\n[2/4] Regenerating portfolio charts...")

    try:
        plot_portfolio_overview_split(all_pnl, INITIAL_BALANCE, str(CHARTS_DIR))
        print("  ✅ Generated 4 portfolio overview charts")
    except Exception as e:
        print(f"  [WARN] portfolio overview: {e}")

    try:
        plot_combined_equity(all_pnl, INITIAL_BALANCE,
                             str(CHARTS_DIR / "combined_equity.png"))
        print("  ✅ Generated combined_equity.png")
    except Exception as e:
        print(f"  [WARN] combined_equity: {e}")

    try:
        plot_per_symbol_equity(all_pnl, INITIAL_BALANCE,
                               str(CHARTS_DIR / "per_symbol_equity.png"))
        print("  ✅ Generated per_symbol_equity.png")
    except Exception as e:
        print(f"  [WARN] per_symbol_equity: {e}")

    try:
        plot_heatmap(all_dollar_stats,
                      str(CHARTS_DIR / "return_heatmap.png"))
        print("  ✅ Generated return_heatmap.png")
    except Exception as e:
        print(f"  [WARN] return_heatmap: {e}")

    try:
        plot_pnl_ranking(all_dollar_stats,
                          str(CHARTS_DIR / "pnl_ranking.png"))
        print("  ✅ Generated pnl_ranking.png")
    except Exception as e:
        print(f"  [WARN] pnl_ranking: {e}")

    # Extra charts
    all_tdf_frames = [df for df in all_trades_dfs.values() if not df.empty]
    all_tdf = pd.concat(all_tdf_frames, ignore_index=True) if all_tdf_frames else pd.DataFrame()

    try:
        generate_extra_charts(all_pnl, all_tdf, INITIAL_BALANCE, str(CHARTS_DIR))
        print("  ✅ Generated all extra industry charts")
    except Exception as e:
        print(f"  [WARN] extra charts: {e}")

    # Top 10 report
    print("\n[3/4] Generating Top 10 Demo Trading Picks report...")
    try:
        top10 = generate_top10_report(
            all_r_stats, all_dollar_stats, all_pnl,
            str(AGGREGATE_DIR / "TOP_10_DEMO_PICKS.md")
        )
        print(f"  ✅ Generated TOP_10_DEMO_PICKS.md")
        print(f"  ✅ Generated top10_picks.csv")

        print("\n  🏆 TOP 10 PICKS:")
        for i, c in enumerate(top10, 1):
            print(f"    #{i}: {c['key']:20s} | Score={c['score']:.1f} | "
                  f"Exp={c['exp_r']:.4f}R | PF={c['pf']:.2f} | "
                  f"WR={c['wr']:.1f}% | PnL=${c['pnl']:+,.0f}")

        # Top 10 chart
        generate_top10_chart(top10, str(CHARTS_DIR / "top10_picks.png"))
        print("  ✅ Generated top10_picks.png")

    except Exception as e:
        print(f"  [WARN] Top 10 report: {e}")
        import traceback
        traceback.print_exc()

    # Delete old portfolio_overview.png if it exists
    old_overview = CHARTS_DIR / "portfolio_overview.png"
    if old_overview.exists():
        old_overview.unlink()
        print("\n  🗑️ Deleted old portfolio_overview.png (replaced with 4 split charts)")

    print("\n[4/4] Done!")
    print(f"  Charts directory: {CHARTS_DIR}")
    print(f"  Report directory: {AGGREGATE_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
