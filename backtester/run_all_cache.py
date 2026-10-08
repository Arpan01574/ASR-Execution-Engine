"""
ASR Engine v3 — Full Data-Cache Backtest Runner
=================================================
Runs the canonical ASR Engine on EVERY CSV in data_cache/,
covering all 5 assets × 6 timeframes = 30 combinations.

Usage:
    python -m backtester.run_all_cache          (from project root)
    python run_all_cache.py                     (from backtester/)
"""
import os
import sys
import time
import yaml
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path so relative imports work either way
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backtester.asr_engine import ASREngine
from backtester.reporting import (
    multi_symbol_report, generate_full_report, trades_to_dataframe,
    calculate_stats, format_stats_report
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CACHE_DIR = _THIS_DIR / "data_cache"
RESULTS_DIR = _THIS_DIR / "results"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def discover_cache_files() -> list[dict]:
    """
    Scan data_cache/ for CSV files and return a list of
    {path, symbol, timeframe, exchange} dicts.

    File naming convention: binance_BTC_USDT_1h.csv
    """
    entries = []
    for f in sorted(CACHE_DIR.glob("*.csv")):
        parts = f.stem.split("_")
        if len(parts) < 4:
            continue
        exchange = parts[0]
        # Rebuild symbol: parts[1]_parts[2] -> BTC/USDT
        base = parts[1]
        quote = parts[2]
        symbol = f"{base}/{quote}"
        tf = "_".join(parts[3:])          # handles edge-cases
        entries.append({
            "path": f,
            "symbol": symbol,
            "timeframe": tf,
            "exchange": exchange,
        })
    return entries


def load_csv(path: Path) -> pd.DataFrame:
    """Load a cached CSV and ensure datetime column is UTC."""
    df = pd.read_csv(path)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    if "time" not in df.columns and "timestamp" in df.columns:
        df["time"] = df["timestamp"]
    return df


def load_config() -> dict:
    cfg_path = _THIS_DIR / "config.yaml"
    with open(cfg_path, "r") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    start_wall = time.time()

    RESULTS_DIR.mkdir(exist_ok=True)
    config = load_config()

    entries = discover_cache_files()
    if not entries:
        print("[ERR] No CSV files found in data_cache/. Run the data downloader first.")
        return

    # De-duplicate in case of naming collisions
    seen = set()
    unique = []
    for e in entries:
        key = f"{e['symbol']}_{e['timeframe']}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    entries = unique

    print("=" * 70)
    print("  ASR ENGINE v3 — FULL DATA-CACHE BACKTEST")
    print(f"  {len(entries)} datasets discovered")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    all_trades: dict[str, list] = {}
    summary_rows = []

    for idx, entry in enumerate(entries, 1):
        sym = entry["symbol"]
        tf = entry["timeframe"]
        key = f"{sym.replace('/', '_')}_{tf}"
        path = entry["path"]
        size_mb = path.stat().st_size / (1024 * 1024)

        print(f"\n[{idx}/{len(entries)}] {key}  ({size_mb:.1f} MB, {path.name})")

        t0 = time.time()
        df = load_csv(path)
        load_s = time.time() - t0

        if df.empty:
            print(f"   [!!] Empty dataframe -- skipped")
            continue

        bars = len(df)
        print(f"   Loaded {bars:,} bars in {load_s:.1f}s")

        # Skip extremely large datasets (>2M bars) with a warning
        # 1-minute data can be ~2M bars for 2 years — very slow
        if bars > 2_000_000:
            print(f"   [!!] {bars:,} bars is very large -- running anyway (may take several minutes)...")

        t1 = time.time()
        engine = ASREngine(config)
        engine.run(df, symbol=sym, timeframe=tf)
        run_s = time.time() - t1

        n_trades = len(engine.trades)
        all_trades[key] = engine.trades

        # Quick stats
        if n_trades > 0:
            tdf = trades_to_dataframe(engine.trades)
            stats = calculate_stats(tdf)
            exp_r = stats.get("expectancy_R", 0)
            wr = stats.get("win_rate_ex_BE", 0)
            pf = stats.get("profit_factor", 0)
            net_r = stats.get("net_R", 0)
            print(f"   [OK] {n_trades} trades | Exp={exp_r:.3f}R | WR={wr:.1f}% | PF={pf:.2f} | NetR={net_r:.1f} | {run_s:.1f}s")
            summary_rows.append({
                "Key": key,
                "Bars": bars,
                "Trades": n_trades,
                "WR%": wr,
                "Exp_R": exp_r,
                "Net_R": net_r,
                "PF": pf,
                "Sharpe": stats.get("sharpe", 0),
                "MaxDD": stats.get("max_DD_R", 0),
                "Time_s": round(run_s, 1),
            })
        else:
            print(f"   [!!] 0 trades | {run_s:.1f}s")
            summary_rows.append({
                "Key": key,
                "Bars": bars,
                "Trades": 0,
                "WR%": 0,
                "Exp_R": 0,
                "Net_R": 0,
                "PF": 0,
                "Sharpe": 0,
                "MaxDD": 0,
                "Time_s": round(run_s, 1),
            })

    # ==================================================================
    # AGGREGATE REPORTING
    # ==================================================================
    print("\n" + "=" * 70)
    print("  GENERATING REPORTS")
    print("=" * 70)

    # 1. Summary table
    summary_df = pd.DataFrame(summary_rows)
    summary_path = RESULTS_DIR / "all_cache_summary.csv"
    summary_df.to_csv(summary_path, index=False)

    print("\n── Per-Combination Summary ──\n")
    if not summary_df.empty:
        print(summary_df.to_string(index=False))

    # 2. Multi-symbol comparison report
    report_path = RESULTS_DIR / "all_cache_multi_symbol.txt"
    report = multi_symbol_report(all_trades, save_path=str(report_path))
    print(report)

    # 3. Full aggregated stats
    all_tdf_frames = [trades_to_dataframe(t) for t in all_trades.values() if t]
    if all_tdf_frames:
        all_tdf = pd.concat(all_tdf_frames, ignore_index=True)
        agg_stats = calculate_stats(all_tdf)

        print("\n── Aggregated (All Datasets) ──")
        print(format_stats_report(agg_stats, "FULL DATA-CACHE AGGREGATED RESULTS"))

        # Save aggregated CSV of all trades
        trades_csv_path = RESULTS_DIR / "all_cache_trades.csv"
        all_tdf.to_csv(trades_csv_path, index=False)
        print(f"\nAll trades saved to: {trades_csv_path}")

    # 4. Elapsed time
    elapsed = time.time() - start_wall
    minutes = int(elapsed // 60)
    seconds = elapsed % 60
    print(f"\n{'=' * 70}")
    print(f"  DONE — Total wall time: {minutes}m {seconds:.0f}s")
    print(f"  Results saved to: {RESULTS_DIR}/")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
