"""
ASR Engine v3 — Resample 1m data to 10m
=========================================
Generates synthetic 10m OHLCV data from cached 1m data.
Produces both CSV and _meta.json (matching data_engine.py format)
for full cache consistency.

Usage:
    python -m backtester.resample_to_10m     (from project root)
    python resample_to_10m.py                (from backtester/)
"""
import pandas as pd
import numpy as np
from pathlib import Path
import json
from datetime import datetime, timezone

# Paths
CACHE_DIR = Path(__file__).resolve().parent / "data_cache"
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT"]
TARGET_TF = "10m"
SOURCE_TF = "1m"
TF_MINUTES = 10


def _assess_quality(df: pd.DataFrame, symbol: str) -> dict:
    """Compute data quality metrics matching data_engine.py format."""
    total_bars = len(df)
    start_ts = None
    end_ts = None

    if "datetime" in df.columns:
        start_ts = df["datetime"].iloc[0]
        end_ts = df["datetime"].iloc[-1]
    elif "timestamp" in df.columns:
        start_ts = pd.to_datetime(df["timestamp"].iloc[0], unit="ms", utc=True)
        end_ts = pd.to_datetime(df["timestamp"].iloc[-1], unit="ms", utc=True)

    expected_bars = total_bars
    missing_bars = 0
    if start_ts is not None and end_ts is not None:
        total_minutes = (end_ts - start_ts).total_seconds() / 60
        expected_bars = int(total_minutes / TF_MINUTES) + 1
        missing_bars = max(0, expected_bars - total_bars)

    dup_bars = int(df["timestamp"].duplicated().sum()) if "timestamp" in df.columns else 0
    zero_vol = int((df["volume"] == 0).sum()) if "volume" in df.columns else 0

    gap_count = 0
    max_gap_min = 0.0
    if "timestamp" in df.columns and len(df) > 1:
        tf_ms = TF_MINUTES * 60 * 1000
        diffs = df["timestamp"].diff().dropna()
        gaps = diffs[diffs > tf_ms * 1.5]
        gap_count = len(gaps)
        if len(gaps) > 0:
            max_gap_min = float(gaps.max()) / 60000

    score = 100.0
    if expected_bars > 0:
        score -= max(0, (1 - total_bars / expected_bars) * 40)
    score -= min(20, gap_count * 2)
    score -= min(10, dup_bars * 5)
    if total_bars > 0:
        score -= min(10, (zero_vol / total_bars) * 50)
    score = max(0.0, round(score, 1))

    return {
        "provider": "binance",
        "symbol": symbol,
        "timeframe": TARGET_TF,
        "timezone": "UTC",
        "start": start_ts.isoformat() if start_ts is not None else None,
        "end": end_ts.isoformat() if end_ts is not None else None,
        "download_time": datetime.now(timezone.utc).isoformat(),
        "total_bars": total_bars,
        "expected_bars": expected_bars,
        "missing_bars": missing_bars,
        "duplicate_bars": dup_bars,
        "zero_volume_bars": zero_vol,
        "gap_count": gap_count,
        "max_gap_minutes": max_gap_min,
        "quality_score": score,
        "synthetic": True,
        "source_timeframe": SOURCE_TF,
    }


def create_10m_data():
    print(f"Generating synthetic {TARGET_TF} data from {SOURCE_TF} data...")
    for sym in SYMBOLS:
        safe_sym = sym.replace("/", "_")

        file_src = CACHE_DIR / safe_sym / SOURCE_TF / f"binance_{safe_sym}_{SOURCE_TF}.csv"
        target_dir = CACHE_DIR / safe_sym / TARGET_TF
        target_dir.mkdir(parents=True, exist_ok=True)

        file_out = target_dir / f"binance_{safe_sym}_{TARGET_TF}.csv"
        meta_out = target_dir / f"binance_{safe_sym}_{TARGET_TF}_meta.json"

        if not file_src.exists():
            print(f"  Skipping {sym} ({SOURCE_TF} file not found at {file_src})")
            continue

        print(f"  Processing {sym}...")
        df = pd.read_csv(file_src)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df.set_index("datetime", inplace=True)

        # Resample logic
        resampled = df.resample(f"{TF_MINUTES}min").agg({
            "timestamp": "first",
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna()

        resampled.reset_index(inplace=True)
        resampled.to_csv(file_out, index=False)
        print(f"  Saved {len(resampled)} bars to {file_out.name}")

        # Generate _meta.json matching data_engine.py format
        meta = _assess_quality(resampled, sym)
        with open(meta_out, "w") as f:
            json.dump(meta, f, indent=2)
        print(f"  Saved meta: quality={meta['quality_score']}/100")

if __name__ == "__main__":
    create_10m_data()
