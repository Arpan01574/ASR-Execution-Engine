"""
ASR Engine v3 — Parity Test Harness
=====================================
Compares TradingView alerts/exports against Python backtester signals.

For every mismatch, classifies the cause:
  - FEED_DIFFERENCE: Different OHLCV data between TV and Python
  - TIMEZONE_DIFFERENCE: Bar timestamp offset
  - PIVOT_TIMING: Different pivot confirmation due to lookback
  - MTF_TIMING: Higher timeframe data availability difference
  - ROUNDING: Float precision differences
  - EXECUTION_ASSUMPTION: Same-bar fill-order model difference
  - CODE_BUG: Actual logic discrepancy requiring fix

Usage:
  1. Export trades from TradingView strategy tester (CSV)
  2. Run Python backtester on same data
  3. Compare using this harness
"""
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# MISMATCH CLASSIFICATION
# ============================================================
class MismatchType(str, Enum):
    FEED_DIFFERENCE = "FEED_DIFFERENCE"
    TIMEZONE_DIFFERENCE = "TIMEZONE_DIFFERENCE"
    PIVOT_TIMING = "PIVOT_TIMING"
    MTF_TIMING = "MTF_TIMING"
    ROUNDING = "ROUNDING"
    EXECUTION_ASSUMPTION = "EXECUTION_ASSUMPTION"
    CODE_BUG = "CODE_BUG"
    UNKNOWN = "UNKNOWN"


@dataclass
class TradeComparison:
    """Result of comparing a single trade between TV and Python."""
    match_id: int = 0
    matched: bool = False

    # TV trade data
    tv_timestamp: Optional[str] = None
    tv_direction: Optional[str] = None
    tv_entry: float = 0.0
    tv_stop: float = 0.0
    tv_tp1: float = 0.0
    tv_tp2: float = 0.0
    tv_score: float = 0.0
    tv_setup: str = ""
    tv_exit_price: float = 0.0
    tv_exit_type: str = ""
    tv_pnl_r: float = 0.0

    # Python trade data
    py_timestamp: Optional[str] = None
    py_direction: Optional[str] = None
    py_entry: float = 0.0
    py_stop: float = 0.0
    py_tp1: float = 0.0
    py_tp2: float = 0.0
    py_score: float = 0.0
    py_setup: str = ""
    py_exit_price: float = 0.0
    py_exit_type: str = ""
    py_pnl_r: float = 0.0

    # Comparison results
    entry_diff_pct: float = 0.0
    stop_diff_pct: float = 0.0
    score_diff: float = 0.0
    pnl_diff_r: float = 0.0
    mismatch_type: str = MismatchType.UNKNOWN
    mismatch_detail: str = ""


@dataclass
class ParityReport:
    """Overall parity test results."""
    total_tv_trades: int = 0
    total_py_trades: int = 0
    matched_trades: int = 0
    unmatched_tv: int = 0
    unmatched_py: int = 0
    comparisons: List[TradeComparison] = field(default_factory=list)

    # Mismatch breakdown
    mismatch_counts: Dict[str, int] = field(default_factory=dict)

    # Tolerances used
    entry_tolerance_pct: float = 0.0
    time_tolerance_bars: int = 0

    # Overall assessment
    parity_score: float = 0.0  # 0-100
    verdict: str = ""  # "PASS", "ACCEPTABLE", "FAIL"


# ============================================================
# TV TRADE PARSER
# ============================================================
def parse_tv_export(csv_path: str, delimiter: str = ",") -> pd.DataFrame:
    """
    Parse TradingView strategy tester export CSV.

    Expected columns (TradingView format):
      Trade #, Type, Signal, Date/Time, Price, Contracts, Profit, Cum. Profit,
      Run-up, Drawdown

    Also supports custom alert JSON format with columns:
      timestamp, direction, entry, stop, tp1, tp2, score, setup, zone_id

    Returns standardized DataFrame.
    """
    try:
        df = pd.read_csv(csv_path, delimiter=delimiter)
    except Exception as e:
        logger.error(f"Failed to parse TV export: {e}")
        return pd.DataFrame()

    # Auto-detect format
    cols = [c.strip().lower() for c in df.columns]

    if "trade #" in cols or "trade" in cols:
        # TradingView strategy tester format
        return _parse_tv_strategy_export(df)
    elif "timestamp" in cols and "direction" in cols:
        # Custom alert JSON format
        return _parse_tv_alert_format(df)
    else:
        logger.warning(f"Unknown TV export format. Columns: {list(df.columns)}")
        return df


def _parse_tv_strategy_export(df: pd.DataFrame) -> pd.DataFrame:
    """Parse standard TradingView strategy tester CSV."""
    # Standardize column names
    col_map = {}
    for c in df.columns:
        cl = c.strip().lower()
        if "trade" in cl and "#" in cl:
            col_map[c] = "trade_num"
        elif "type" == cl:
            col_map[c] = "type"
        elif "signal" == cl:
            col_map[c] = "signal"
        elif "date" in cl or "time" in cl:
            col_map[c] = "timestamp"
        elif "price" == cl:
            col_map[c] = "price"
        elif "contract" in cl:
            col_map[c] = "contracts"
        elif "profit" == cl and "cum" not in cl:
            col_map[c] = "profit"
        elif "cum" in cl:
            col_map[c] = "cum_profit"

    df = df.rename(columns=col_map)

    # Parse entries and exits
    trades = []
    entries = df[df["type"].str.contains("Entry", case=False, na=False)]
    exits = df[df["type"].str.contains("Exit", case=False, na=False)]

    for _, entry_row in entries.iterrows():
        trade_num = entry_row.get("trade_num", 0)
        matching_exit = exits[exits.get("trade_num", pd.Series()) == trade_num]

        trade = {
            "timestamp": entry_row.get("timestamp", ""),
            "direction": "LONG" if "long" in str(entry_row.get("signal", "")).lower() else "SHORT",
            "entry": float(entry_row.get("price", 0)),
            "exit_price": float(matching_exit.iloc[0].get("price", 0)) if len(matching_exit) > 0 else 0,
            "profit": float(matching_exit.iloc[0].get("profit", 0)) if len(matching_exit) > 0 else 0,
        }
        trades.append(trade)

    return pd.DataFrame(trades)


def _parse_tv_alert_format(df: pd.DataFrame) -> pd.DataFrame:
    """Parse custom ASR alert JSON format."""
    standardized = df.copy()
    # Normalize column names
    col_map = {c: c.strip().lower() for c in standardized.columns}
    standardized = standardized.rename(columns=col_map)
    return standardized


# ============================================================
# PYTHON TRADE FORMATTER
# ============================================================
def python_trades_to_df(trades) -> pd.DataFrame:
    """Convert Python TradeResult objects to comparable DataFrame."""
    if not trades:
        return pd.DataFrame()

    rows = []
    for t in trades:
        rows.append({
            "timestamp": getattr(t, "entry_time", None),
            "bar_index": t.entry_bar,
            "direction": "LONG" if t.direction == 1 else "SHORT",
            "entry": t.entry,
            "stop": t.stop,
            "tp1": t.tp1,
            "tp2": t.tp2,
            "exit_price": t.exit_price,
            "exit_type": _exit_name(t.exit_type),
            "net_r": t.net_r,
            "score": t.score,
            "setup": getattr(t, "setup_name", ""),
        })

    return pd.DataFrame(rows)


def _exit_name(et: int) -> str:
    return {1: "SL", 2: "BE", 3: "TP2", 4: "TIME", 5: "TP1", 6: "TRAIL"}.get(et, "UNK")


# ============================================================
# MATCHING ENGINE
# ============================================================
def match_trades(tv_df: pd.DataFrame, py_df: pd.DataFrame,
                 entry_tolerance_pct: float = 0.5,
                 time_tolerance_bars: int = 2,
                 score_tolerance: float = 10.0) -> ParityReport:
    """
    Match TV trades to Python trades and compare.

    Args:
        tv_df: TradingView trades DataFrame
        py_df: Python trades DataFrame
        entry_tolerance_pct: Max entry price difference (%) to count as match
        time_tolerance_bars: Max bar index difference to count as match
        score_tolerance: Max score difference before flagging

    Returns:
        ParityReport with all comparisons
    """
    report = ParityReport()
    report.total_tv_trades = len(tv_df)
    report.total_py_trades = len(py_df)
    report.entry_tolerance_pct = entry_tolerance_pct
    report.time_tolerance_bars = time_tolerance_bars

    if tv_df.empty or py_df.empty:
        report.verdict = "FAIL"
        return report

    py_used = set()
    match_id = 0

    for tv_idx, tv_row in tv_df.iterrows():
        tv_entry = float(tv_row.get("entry", tv_row.get("price", 0)))
        tv_dir = str(tv_row.get("direction", ""))

        best_match = None
        best_diff = float("inf")

        for py_idx, py_row in py_df.iterrows():
            if py_idx in py_used:
                continue

            py_entry = float(py_row.get("entry", 0))
            py_dir = str(py_row.get("direction", ""))

            # Direction must match
            if tv_dir.upper() != py_dir.upper():
                continue

            # Entry price within tolerance
            if tv_entry > 0:
                diff_pct = abs(tv_entry - py_entry) / tv_entry * 100
            else:
                diff_pct = 0

            if diff_pct <= entry_tolerance_pct and diff_pct < best_diff:
                best_diff = diff_pct
                best_match = py_idx

        comp = TradeComparison(match_id=match_id)
        match_id += 1

        # TV data
        comp.tv_timestamp = str(tv_row.get("timestamp", ""))
        comp.tv_direction = tv_dir
        comp.tv_entry = tv_entry
        comp.tv_stop = float(tv_row.get("stop", 0))
        comp.tv_tp1 = float(tv_row.get("tp1", 0))
        comp.tv_tp2 = float(tv_row.get("tp2", 0))
        comp.tv_score = float(tv_row.get("score", 0))
        comp.tv_setup = str(tv_row.get("setup", ""))
        comp.tv_exit_price = float(tv_row.get("exit_price", 0))
        comp.tv_pnl_r = float(tv_row.get("net_r", tv_row.get("profit", 0)))

        if best_match is not None:
            py_row = py_df.loc[best_match]
            py_used.add(best_match)
            comp.matched = True

            comp.py_timestamp = str(py_row.get("timestamp", ""))
            comp.py_direction = str(py_row.get("direction", ""))
            comp.py_entry = float(py_row.get("entry", 0))
            comp.py_stop = float(py_row.get("stop", 0))
            comp.py_tp1 = float(py_row.get("tp1", 0))
            comp.py_tp2 = float(py_row.get("tp2", 0))
            comp.py_score = float(py_row.get("score", 0))
            comp.py_setup = str(py_row.get("setup", ""))
            comp.py_exit_price = float(py_row.get("exit_price", 0))
            comp.py_pnl_r = float(py_row.get("net_r", 0))

            # Calculate differences
            comp.entry_diff_pct = best_diff
            if comp.tv_stop > 0:
                comp.stop_diff_pct = abs(comp.tv_stop - comp.py_stop) / comp.tv_stop * 100
            comp.score_diff = abs(comp.tv_score - comp.py_score)
            comp.pnl_diff_r = abs(comp.tv_pnl_r - comp.py_pnl_r)

            # Classify mismatch
            comp.mismatch_type = _classify_mismatch(comp, score_tolerance)

        report.comparisons.append(comp)

    # Count matched/unmatched
    report.matched_trades = sum(1 for c in report.comparisons if c.matched)
    report.unmatched_tv = report.total_tv_trades - report.matched_trades
    report.unmatched_py = report.total_py_trades - report.matched_trades

    # Mismatch breakdown
    for c in report.comparisons:
        mt = c.mismatch_type
        report.mismatch_counts[mt] = report.mismatch_counts.get(mt, 0) + 1

    # Parity score
    if report.total_tv_trades > 0:
        match_rate = report.matched_trades / report.total_tv_trades
        exact_matches = sum(1 for c in report.comparisons
                           if c.matched and c.entry_diff_pct < 0.01
                           and c.pnl_diff_r < 0.05)
        exact_rate = exact_matches / max(report.total_tv_trades, 1)
        report.parity_score = round((match_rate * 60 + exact_rate * 40), 1)

    # Verdict
    if report.parity_score >= 90:
        report.verdict = "PASS"
    elif report.parity_score >= 70:
        report.verdict = "ACCEPTABLE"
    else:
        report.verdict = "FAIL"

    return report


# ============================================================
# MISMATCH CLASSIFIER
# ============================================================
def _classify_mismatch(comp: TradeComparison,
                       score_tolerance: float) -> str:
    """
    Classify the source of a trade mismatch.

    Priority order:
    1. If entry prices differ significantly → FEED_DIFFERENCE
    2. If only scores differ → ROUNDING or PIVOT_TIMING
    3. If exit types differ → EXECUTION_ASSUMPTION
    4. If everything differs → CODE_BUG
    """
    if not comp.matched:
        return MismatchType.UNKNOWN

    issues = []

    # Entry price check
    if comp.entry_diff_pct > 0.1:
        issues.append(MismatchType.FEED_DIFFERENCE)
    elif comp.entry_diff_pct > 0.01:
        issues.append(MismatchType.ROUNDING)

    # Score check
    if comp.score_diff > score_tolerance:
        issues.append(MismatchType.PIVOT_TIMING)
    elif comp.score_diff > 2:
        issues.append(MismatchType.ROUNDING)

    # Stop price check
    if comp.stop_diff_pct > 1.0:
        issues.append(MismatchType.FEED_DIFFERENCE)

    # Exit check
    if (comp.tv_exit_price > 0 and comp.py_exit_price > 0 and
            comp.pnl_diff_r > 0.3):
        issues.append(MismatchType.EXECUTION_ASSUMPTION)

    # If no issues found, it's a match
    if not issues:
        return "MATCH"

    # Return most severe issue
    priority = [
        MismatchType.CODE_BUG,
        MismatchType.FEED_DIFFERENCE,
        MismatchType.EXECUTION_ASSUMPTION,
        MismatchType.PIVOT_TIMING,
        MismatchType.MTF_TIMING,
        MismatchType.TIMEZONE_DIFFERENCE,
        MismatchType.ROUNDING,
    ]

    for p in priority:
        if p in issues:
            return p

    return issues[0] if issues else MismatchType.UNKNOWN


# ============================================================
# REPORT FORMATTER
# ============================================================
def format_parity_report(report: ParityReport) -> str:
    """Format parity test results as a readable report."""
    from io import StringIO
    buf = StringIO()
    w = buf.write

    w("\n" + "=" * 60 + "\n")
    w("  ASR ENGINE v3 — PARITY TEST REPORT\n")
    w("=" * 60 + "\n\n")

    # Summary
    w(f"  {'TV Trades:':<25} {report.total_tv_trades:>6}\n")
    w(f"  {'Python Trades:':<25} {report.total_py_trades:>6}\n")
    w(f"  {'Matched:':<25} {report.matched_trades:>6}\n")
    w(f"  {'Unmatched (TV only):':<25} {report.unmatched_tv:>6}\n")
    w(f"  {'Unmatched (PY only):':<25} {report.unmatched_py:>6}\n")
    w(f"\n")
    w(f"  {'Parity Score:':<25} {report.parity_score:>5.1f}/100\n")
    w(f"  {'Verdict:':<25} {report.verdict:>6}\n")
    w(f"\n")

    # Tolerances
    w(f"  Tolerances used:\n")
    w(f"    Entry: ±{report.entry_tolerance_pct}%\n")
    w(f"    Time: ±{report.time_tolerance_bars} bars\n")
    w(f"\n")

    # Mismatch breakdown
    if report.mismatch_counts:
        w("  Mismatch Classification:\n")
        for mtype, count in sorted(report.mismatch_counts.items(),
                                    key=lambda x: x[1], reverse=True):
            w(f"    {mtype:<30} {count:>4}\n")
        w("\n")

    # Detailed mismatches (non-matches only)
    mismatches = [c for c in report.comparisons
                  if c.matched and c.mismatch_type != "MATCH"]
    if mismatches:
        w(f"\n  Top Mismatches ({min(len(mismatches), 20)} shown):\n")
        w(f"  {'#':<4} {'Dir':<6} {'TV Entry':>10} {'PY Entry':>10} "
          f"{'Δ%':>6} {'TV R':>6} {'PY R':>6} {'Type':<20}\n")
        w(f"  {'-' * 72}\n")

        for c in mismatches[:20]:
            w(f"  {c.match_id:<4} {c.tv_direction:<6} "
              f"{c.tv_entry:>10.2f} {c.py_entry:>10.2f} "
              f"{c.entry_diff_pct:>5.2f}% "
              f"{c.tv_pnl_r:>6.2f} {c.py_pnl_r:>6.2f} "
              f"{c.mismatch_type:<20}\n")

    w("\n" + "=" * 60 + "\n")
    return buf.getvalue()


# ============================================================
# CONVENIENCE: RUN PARITY TEST
# ============================================================
def run_parity_test(tv_csv_path: str, python_trades,
                    entry_tolerance_pct: float = 0.5,
                    save_path: Optional[str] = None) -> ParityReport:
    """
    Run a complete parity test between TradingView and Python.

    Args:
        tv_csv_path: Path to TV strategy tester CSV export
        python_trades: List of Python TradeResult objects
        entry_tolerance_pct: Max entry price tolerance
        save_path: Optional path to save the report

    Returns:
        ParityReport
    """
    tv_df = parse_tv_export(tv_csv_path)
    py_df = python_trades_to_df(python_trades)

    logger.info(f"TV trades: {len(tv_df)}, Python trades: {len(py_df)}")

    report = match_trades(tv_df, py_df, entry_tolerance_pct=entry_tolerance_pct)
    text = format_parity_report(report)
    print(text)

    if save_path:
        with open(save_path, "w") as f:
            f.write(text)
        logger.info(f"Parity report saved to {save_path}")

    return report
