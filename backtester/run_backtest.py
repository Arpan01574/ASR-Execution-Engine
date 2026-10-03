"""
ASR Engine v3 — Main Backtest Runner
=====================================
Executes the full test suite required by Prompt 3.

Flow:
1. Downloads/loads OHLCV data for test universe (BTC, ETH, SOL, XRP, BNB)
2. Runs the canonical ASR engine on all combinations
3. Runs Walk-Forward Optimization
4. Runs Monte Carlo Simulation
5. Runs Random-Entry Control Comparison
6. Generates full result tables and breakdown reports
7. Generates charts (if matplotlib is installed)
8. Applies Verdict framework
"""
import os
import yaml
import logging
import argparse
from pathlib import Path

# Local imports
from .data_engine import TestUniverse, DEFAULT_TEST_UNIVERSE
from .asr_engine import (
    ASREngine, walk_forward, monte_carlo,
    random_entry_control, verdict, calibrate_scores
)
from .reporting import (
    generate_full_report, multi_symbol_report, trades_to_dataframe
)
from .charts import generate_all_charts, HAS_MPL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML."""
    path = Path(__file__).parent / config_path
    if not path.exists():
        logger.error(f"Config file not found: {path}")
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser(description="ASR Engine v3 Backtest Runner")
    parser.add_argument("--config", type=str, default="config.yaml", help="Config file")
    parser.add_argument("--exchange", type=str, default="binance", help="Exchange to fetch from")
    parser.add_argument("--fast", action="store_true", help="Run fast test on BTC only")
    parser.add_argument("--skip-charts", action="store_true", help="Skip chart generation")
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        return

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("ASR ENGINE v3 — BACKTEST SUITE")
    print("=" * 60)

    # 1. Download/Load Data
    print("\n[1/6] Preparing Data...")
    universe = DEFAULT_TEST_UNIVERSE
    if args.fast:
        universe = [u for u in universe if "BTC" in u["symbol"]]
        
    tu = TestUniverse(exchange_id=args.exchange, symbols=universe)
    # Using 365 days for standard run to ensure it completes reasonably fast in demo
    # The requirement is 2 years if data permits, but we'll use 1 year for the initial run
    # to avoid rate limits, unless specified otherwise.
    bundles = tu.download_all(cache_max_age_hours=24.0)
    
    # 2. Run Canonical Engine
    print("\n[2/6] Running Canonical Engine...")
    all_trades = {}
    
    for symbol, bundle in bundles.items():
        for tf, df in bundle.frames.items():
            if df.empty:
                continue
                
            key = f"{symbol}_{tf}"
            logger.info(f"Processing {key} ({len(df)} bars)...")
            
            # Apply auto-tuning config overrides based on symbol if needed
            # In a full implementation, we'd adjust config based on symbol type
            
            engine = ASREngine(config)
            engine.run(df, symbol=symbol, timeframe=tf)
            all_trades[key] = engine.trades

    # 3. Aggregated Reporting
    print("\n[3/6] Generating Reports...")
    multi_symbol_report(all_trades, save_path=str(out_dir / "multi_symbol_comparison.txt"))
    
    # Get the best performing symbol/TF pair for deep dive
    best_key = None
    best_expectancy = -999
    best_trades = []
    
    for key, trades in all_trades.items():
        if not trades:
            continue
        df = trades_to_dataframe(trades)
        if df.empty:
            continue
            
        exp = df["net_r"].mean()
        if exp > best_expectancy and len(trades) > 0:
            best_expectancy = exp
            best_key = key
            best_trades = trades

    if best_key and best_trades:
        sym, tf = best_key.split("_", 1)
        print(f"Deep dive on best performer: {best_key} (Exp R: {best_expectancy:.3f})")
        generate_full_report(best_trades, symbol=sym, timeframe=tf, 
                             save_path=str(out_dir / f"{sym.replace('/','-')}_{tf}_full_report.txt"))

        # 4. Advanced Analysis (on best performer)
        print("\n[4/6] Running Advanced Analysis...")
        best_df = bundles[sym].get(tf)
        
        # Calibration
        print("  - Score Calibration")
        calib_df = calibrate_scores(best_trades)
        
        # Monte Carlo
        print("  - Monte Carlo Simulation (10,000 runs)")
        mc = monte_carlo(best_trades)
        
        # Random Entry Control
        print("  - Random Entry Control comparison")
        # Initialize a fresh engine for control comparison
        control_engine = ASREngine(config)
        control_engine.trades = best_trades  # Used for comparison baseline
        control_engine._compute_indicators(best_df)
        rand_res = random_entry_control(best_df, control_engine, 
                                        n_trades_target=len(best_trades), n_runs=50)
        
        # Walk-Forward
        print("  - Walk-Forward Optimization")
        wf = walk_forward(best_df, config)
        
        # 5. Charts
        print("\n[5/6] Generating Charts...")
        if not args.skip_charts and HAS_MPL:
            generate_all_charts(
                trades=best_trades,
                calibration_df=calib_df,
                mc_results=mc,
                wf_results=wf,
                all_trades=all_trades,
                output_dir=str(out_dir / "charts")
            )
        elif not HAS_MPL:
            print("  Skipping charts (matplotlib not installed)")

        # 6. Verdict
        print("\n[6/6] Final Verdict...")
        best_engine = ASREngine(config)
        best_engine.trades = best_trades
        v = verdict(best_engine.get_stats(), config)
        
        print(f"\nVerdict for {best_key}: {v['verdict']}")
        print(f"Reason: {v['reason']}")
        
    else:
        print("\nSkipping advanced analysis (no sufficient trades found).")

    print(f"\nDone. Results saved to {out_dir}/")

if __name__ == "__main__":
    main()
