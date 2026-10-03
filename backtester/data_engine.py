"""
ASR Engine v3 — Data Engine
============================
OHLCV data downloader with multi-timeframe support, quality tracking,
and caching. Uses ccxt for exchange data (free, no subscription).

Supports:
  - Multiple exchanges (Binance, Bybit, OKX, etc.)
  - Multi-timeframe (1h, 4h, 1D, etc.)
  - Timezone handling
  - Session filtering
  - Volume data
  - Optional funding rate data
  - Data quality metadata
  - Local CSV caching
  - Rate limit compliance
"""
import os
import time
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTS
# ============================================================
DEFAULT_TEST_UNIVERSE = [
    {"symbol": "BTC/USDT", "name": "Bitcoin"},
    {"symbol": "ETH/USDT", "name": "Ethereum"},
    {"symbol": "SOL/USDT", "name": "Solana"},
    {"symbol": "XRP/USDT", "name": "XRP"},
    {"symbol": "BNB/USDT", "name": "BNB"},
]

DEFAULT_TIMEFRAMES = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"]

# Minimum data requirements
MIN_BARS = 500
PREFERRED_BARS = 5000
MIN_YEARS = 2

CACHE_DIR = Path(__file__).parent / "data_cache"


# ============================================================
# DATA QUALITY METADATA
# ============================================================
class DataQualityReport:
    """Track data quality for every downloaded dataset."""

    def __init__(self):
        self.provider: str = ""
        self.symbol: str = ""
        self.timeframe: str = ""
        self.timezone_info: str = "UTC"
        self.start_ts: Optional[datetime] = None
        self.end_ts: Optional[datetime] = None
        self.download_time: Optional[datetime] = None
        self.total_bars: int = 0
        self.expected_bars: int = 0
        self.missing_bars: int = 0
        self.duplicate_bars: int = 0
        self.zero_volume_bars: int = 0
        self.gap_count: int = 0
        self.max_gap_minutes: float = 0.0
        self.quality_score: float = 0.0  # 0-100

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timezone": self.timezone_info,
            "start": self.start_ts.isoformat() if self.start_ts else None,
            "end": self.end_ts.isoformat() if self.end_ts else None,
            "download_time": self.download_time.isoformat() if self.download_time else None,
            "total_bars": self.total_bars,
            "expected_bars": self.expected_bars,
            "missing_bars": self.missing_bars,
            "duplicate_bars": self.duplicate_bars,
            "zero_volume_bars": self.zero_volume_bars,
            "gap_count": self.gap_count,
            "max_gap_minutes": self.max_gap_minutes,
            "quality_score": self.quality_score,
        }


# ============================================================
# TIMEFRAME HELPERS
# ============================================================
TF_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480,
    "12h": 720, "1d": 1440, "3d": 4320, "1w": 10080, "1M": 43200,
}


def tf_to_minutes(tf: str) -> int:
    """Convert timeframe string to minutes."""
    return TF_MINUTES.get(tf, 60)


def estimate_bars_for_period(tf: str, days: int) -> int:
    """Estimate number of bars for a given period."""
    minutes = tf_to_minutes(tf)
    return int((days * 1440) / minutes)


# ============================================================
# CCXT DATA FETCHER
# ============================================================
class CCXTFetcher:
    """
    Fetch OHLCV data from exchanges via ccxt.
    Handles pagination, rate limits, and error recovery.
    """

    def __init__(self, exchange_id: str = "binance", market_type: str = "spot"):
        try:
            import ccxt
        except ImportError:
            raise ImportError(
                "ccxt is required for data fetching. Install with: pip install ccxt"
            )

        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unknown exchange: {exchange_id}")

        options = {}
        if market_type == "futures":
            options["defaultType"] = "future"
        elif market_type == "swap":
            options["defaultType"] = "swap"

        self.exchange = exchange_class({
            "enableRateLimit": True,
            "options": options,
        })
        self.exchange_id = exchange_id
        self.market_type = market_type
        self._markets_loaded = False

    def _ensure_markets(self):
        if not self._markets_loaded:
            self.exchange.load_markets()
            self._markets_loaded = True

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data with automatic pagination.

        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframe: Candle timeframe (e.g., "1h", "4h", "1d")
            since: Start datetime (UTC)
            until: End datetime (UTC), defaults to now
            limit: Batch size per request

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        self._ensure_markets()

        if symbol not in self.exchange.markets:
            # Try with :USDT suffix for futures
            alt = f"{symbol}:USDT"
            if alt in self.exchange.markets:
                symbol = alt
            else:
                raise ValueError(
                    f"Symbol {symbol} not found on {self.exchange_id}. "
                    f"Available: {list(self.exchange.markets.keys())[:10]}..."
                )

        if since is None:
            # Default: 2 years ago
            since = datetime.now(timezone.utc) - timedelta(days=730)

        if until is None:
            until = datetime.now(timezone.utc)

        since_ms = int(since.timestamp() * 1000)
        until_ms = int(until.timestamp() * 1000)

        all_data = []
        current_since = since_ms
        request_count = 0
        max_requests = 500  # Safety limit

        logger.info(
            f"Fetching {symbol} {timeframe} from {since.isoformat()} "
            f"to {until.isoformat()} on {self.exchange_id}"
        )

        while current_since < until_ms and request_count < max_requests:
            try:
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=current_since, limit=limit
                )
            except Exception as e:
                logger.warning(f"Fetch error at offset {request_count}: {e}")
                time.sleep(2)
                request_count += 1
                continue

            if not ohlcv:
                break

            all_data.extend(ohlcv)

            # Move cursor past last candle
            last_ts = ohlcv[-1][0]
            if last_ts <= current_since:
                break  # No progress
            current_since = last_ts + 1

            request_count += 1

            if request_count % 50 == 0:
                logger.info(
                    f"  ... fetched {len(all_data)} bars "
                    f"({request_count} requests)"
                )

        if not all_data:
            logger.warning(f"No data returned for {symbol} {timeframe}")
            return pd.DataFrame()

        df = pd.DataFrame(
            all_data,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        # Remove duplicates
        df = df.drop_duplicates(subset="timestamp", keep="last")

        # Filter to requested range
        df = df[(df["timestamp"] >= since_ms) & (df["timestamp"] <= until_ms)]

        # Convert timestamp to datetime
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)

        logger.info(f"Fetched {len(df)} bars for {symbol} {timeframe}")
        return df

    def fetch_funding_rate(
        self, symbol: str, since: Optional[datetime] = None, limit: int = 500
    ) -> pd.DataFrame:
        """Fetch historical funding rates (perpetual contracts only)."""
        self._ensure_markets()

        try:
            if not hasattr(self.exchange, "fetch_funding_rate_history"):
                logger.warning(
                    f"{self.exchange_id} does not support funding rate history"
                )
                return pd.DataFrame()

            since_ms = int(since.timestamp() * 1000) if since else None
            data = self.exchange.fetch_funding_rate_history(
                symbol, since=since_ms, limit=limit
            )
        except Exception as e:
            logger.warning(f"Funding rate fetch error: {e}")
            return pd.DataFrame()

        if not data:
            return pd.DataFrame()

        records = []
        for entry in data:
            records.append({
                "timestamp": entry.get("timestamp"),
                "datetime": entry.get("datetime"),
                "funding_rate": entry.get("fundingRate"),
                "symbol": symbol,
            })

        return pd.DataFrame(records)

    def get_available_symbols(self, quote: str = "USDT") -> List[str]:
        """List available trading pairs for a given quote currency."""
        self._ensure_markets()
        return [
            s for s in self.exchange.markets
            if s.endswith(f"/{quote}") and self.exchange.markets[s].get("active", True)
        ]


# ============================================================
# DATA QUALITY ASSESSMENT
# ============================================================
def assess_quality(df: pd.DataFrame, symbol: str, timeframe: str,
                   provider: str = "ccxt") -> DataQualityReport:
    """
    Assess data quality and return a detailed report.
    """
    report = DataQualityReport()
    report.provider = provider
    report.symbol = symbol
    report.timeframe = timeframe
    report.download_time = datetime.now(timezone.utc)

    if df.empty:
        report.quality_score = 0.0
        return report

    report.total_bars = len(df)

    if "datetime" in df.columns:
        report.start_ts = df["datetime"].iloc[0].to_pydatetime()
        report.end_ts = df["datetime"].iloc[-1].to_pydatetime()
    elif "timestamp" in df.columns:
        report.start_ts = datetime.fromtimestamp(
            df["timestamp"].iloc[0] / 1000, tz=timezone.utc
        )
        report.end_ts = datetime.fromtimestamp(
            df["timestamp"].iloc[-1] / 1000, tz=timezone.utc
        )

    # Expected bars
    if report.start_ts and report.end_ts:
        total_minutes = (report.end_ts - report.start_ts).total_seconds() / 60
        tf_mins = tf_to_minutes(timeframe)
        report.expected_bars = int(total_minutes / tf_mins) + 1
        report.missing_bars = max(0, report.expected_bars - report.total_bars)

    # Duplicates
    if "timestamp" in df.columns:
        report.duplicate_bars = int(df["timestamp"].duplicated().sum())

    # Zero volume
    if "volume" in df.columns:
        report.zero_volume_bars = int((df["volume"] == 0).sum())

    # Gaps
    if "timestamp" in df.columns and len(df) > 1:
        tf_ms = tf_to_minutes(timeframe) * 60 * 1000
        diffs = df["timestamp"].diff().dropna()
        gaps = diffs[diffs > tf_ms * 1.5]  # 50% tolerance
        report.gap_count = len(gaps)
        if len(gaps) > 0:
            report.max_gap_minutes = float(gaps.max()) / 60000

    # Quality score (0-100)
    score = 100.0
    if report.expected_bars > 0:
        completeness = report.total_bars / report.expected_bars
        score -= max(0, (1 - completeness) * 40)  # Up to -40 for missing data
    score -= min(20, report.gap_count * 2)  # Up to -20 for gaps
    score -= min(10, report.duplicate_bars * 5)  # Up to -10 for duplicates
    if report.total_bars > 0:
        zvr = report.zero_volume_bars / report.total_bars
        score -= min(10, zvr * 50)  # Up to -10 for zero volume
    if report.total_bars < MIN_BARS:
        score -= 20  # Penalty for too few bars
    report.quality_score = max(0.0, round(score, 1))

    return report


# ============================================================
# LOCAL CSV CACHE
# ============================================================
def _cache_key(symbol: str, timeframe: str, exchange: str) -> str:
    """Generate a deterministic cache filename."""
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    return f"{exchange}_{safe_symbol}_{timeframe}"


def save_to_cache(df: pd.DataFrame, symbol: str, timeframe: str,
                  exchange: str = "binance", quality: Optional[DataQualityReport] = None):
    """Save OHLCV data to local CSV cache."""
    key = _cache_key(symbol, timeframe, exchange)
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    target_dir = CACHE_DIR / safe_symbol / timeframe
    target_dir.mkdir(parents=True, exist_ok=True)
    
    csv_path = target_dir / f"{key}.csv"
    meta_path = target_dir / f"{key}_meta.json"

    df.to_csv(csv_path, index=False)
    logger.info(f"Cached {len(df)} bars to {csv_path}")

    if quality:
        with open(meta_path, "w") as f:
            json.dump(quality.to_dict(), f, indent=2, default=str)


def load_from_cache(symbol: str, timeframe: str,
                    exchange: str = "binance",
                    max_age_hours: float = 24.0) -> Optional[pd.DataFrame]:
    """Load OHLCV data from local cache if fresh enough."""
    key = _cache_key(symbol, timeframe, exchange)
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    csv_path = CACHE_DIR / safe_symbol / timeframe / f"{key}.csv"

    if not csv_path.exists():
        return None

    # Check freshness
    mtime = datetime.fromtimestamp(csv_path.stat().st_mtime, tz=timezone.utc)
    age = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
    if age > max_age_hours:
        logger.info(f"Cache expired ({age:.1f}h old): {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    logger.info(f"Loaded {len(df)} bars from cache: {csv_path}")
    return df


# ============================================================
# MULTI-TIMEFRAME DATA BUNDLE
# ============================================================
class DataBundle:
    """
    Container for multi-timeframe OHLCV data for a single symbol.
    Provides aligned access for HTF confluence calculations.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.frames: Dict[str, pd.DataFrame] = {}
        self.quality: Dict[str, DataQualityReport] = {}

    def add(self, timeframe: str, df: pd.DataFrame,
            quality: Optional[DataQualityReport] = None):
        self.frames[timeframe] = df
        if quality:
            self.quality[timeframe] = quality

    def get(self, timeframe: str) -> Optional[pd.DataFrame]:
        return self.frames.get(timeframe)

    @property
    def primary_tf(self) -> Optional[str]:
        """Return the smallest timeframe available."""
        available = sorted(self.frames.keys(), key=lambda t: tf_to_minutes(t))
        return available[0] if available else None

    def summary(self) -> dict:
        """Quick summary of all loaded data."""
        result = {"symbol": self.symbol, "timeframes": {}}
        for tf, df in self.frames.items():
            q = self.quality.get(tf)
            result["timeframes"][tf] = {
                "bars": len(df),
                "start": str(df["datetime"].iloc[0]) if "datetime" in df.columns and len(df) > 0 else None,
                "end": str(df["datetime"].iloc[-1]) if "datetime" in df.columns and len(df) > 0 else None,
                "quality_score": q.quality_score if q else None,
            }
        return result


# ============================================================
# TEST UNIVERSE MANAGER
# ============================================================
class TestUniverse:
    """
    Manages downloading and caching data for the full test universe.

    Test Universe (Prompt 3 requirement):
      - BTC, ETH, SOL, XRP, BNB
      - 2-3 timeframes (1h, 4h, 1d)
      - At least 2 years of data
      - Cover bull, bear, sideways, high/low volatility
    """

    def __init__(self, exchange_id: str = "binance",
                 market_type: str = "spot",
                 symbols: Optional[List[dict]] = None,
                 timeframes: Optional[List[str]] = None):
        self.exchange_id = exchange_id
        self.market_type = market_type
        self.symbols = symbols or DEFAULT_TEST_UNIVERSE
        self.timeframes = timeframes or DEFAULT_TIMEFRAMES
        self.bundles: Dict[str, DataBundle] = {}
        self._fetcher: Optional[CCXTFetcher] = None

    def _get_fetcher(self) -> CCXTFetcher:
        if self._fetcher is None:
            self._fetcher = CCXTFetcher(self.exchange_id, self.market_type)
        return self._fetcher

    def download_all(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        use_cache: bool = True,
        cache_max_age_hours: float = 48.0,
    ) -> Dict[str, DataBundle]:
        """
        Download OHLCV data for the entire test universe.

        Args:
            since: Start date (default: 2 years ago)
            until: End date (default: now)
            use_cache: Whether to use local cache
            cache_max_age_hours: Max cache age before re-download

        Returns:
            Dict mapping symbol to DataBundle
        """
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=730)
        if until is None:
            until = datetime.now(timezone.utc)

        fetcher = self._get_fetcher()
        total = len(self.symbols) * len(self.timeframes)
        done = 0

        for sym_info in self.symbols:
            symbol = sym_info["symbol"]
            name = sym_info.get("name", symbol)
            bundle = DataBundle(symbol)

            for tf in self.timeframes:
                done += 1
                logger.info(
                    f"[{done}/{total}] Fetching {name} ({symbol}) {tf}..."
                )

                # Try cache first
                df = None
                if use_cache:
                    df = load_from_cache(
                        symbol, tf, self.exchange_id, cache_max_age_hours
                    )

                if df is None:
                    try:
                        df = fetcher.fetch_ohlcv(
                            symbol, tf, since=since, until=until
                        )
                        if not df.empty:
                            quality = assess_quality(
                                df, symbol, tf, self.exchange_id
                            )
                            save_to_cache(
                                df, symbol, tf, self.exchange_id, quality
                            )
                            bundle.add(tf, df, quality)
                        else:
                            logger.warning(f"No data for {symbol} {tf}")
                    except Exception as e:
                        logger.error(f"Failed to fetch {symbol} {tf}: {e}")
                else:
                    quality = assess_quality(df, symbol, tf, self.exchange_id)
                    bundle.add(tf, df, quality)

                # Small delay between requests
                time.sleep(0.5)

            self.bundles[symbol] = bundle

        return self.bundles

    def get_bundle(self, symbol: str) -> Optional[DataBundle]:
        return self.bundles.get(symbol)

    def summary(self) -> dict:
        """Summary of all downloaded data."""
        return {
            symbol: bundle.summary()
            for symbol, bundle in self.bundles.items()
        }

    def quality_report(self) -> pd.DataFrame:
        """Generate a quality report for all downloaded data."""
        rows = []
        for symbol, bundle in self.bundles.items():
            for tf, quality in bundle.quality.items():
                row = quality.to_dict()
                rows.append(row)
        return pd.DataFrame(rows) if rows else pd.DataFrame()


# ============================================================
# SESSION FILTER
# ============================================================
def filter_session(df: pd.DataFrame, session: str = "0000-2359",
                   skip_weekends: bool = False) -> pd.DataFrame:
    """
    Filter data to trading session hours.

    Args:
        df: DataFrame with 'datetime' column
        session: Session string like "0930-1600"
        skip_weekends: If True, exclude Saturday/Sunday

    Returns:
        Filtered DataFrame
    """
    if "datetime" not in df.columns:
        return df

    result = df.copy()

    if session != "0000-2359":
        parts = session.split("-")
        if len(parts) == 2:
            start_h = int(parts[0][:2])
            start_m = int(parts[0][2:])
            end_h = int(parts[1][:2])
            end_m = int(parts[1][2:])

            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            bar_minutes = (
                result["datetime"].dt.hour * 60 + result["datetime"].dt.minute
            )

            if start_minutes <= end_minutes:
                mask = (bar_minutes >= start_minutes) & (bar_minutes <= end_minutes)
            else:
                # Overnight session
                mask = (bar_minutes >= start_minutes) | (bar_minutes <= end_minutes)

            result = result[mask]

    if skip_weekends:
        result = result[result["datetime"].dt.weekday < 5]

    return result.reset_index(drop=True)


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================
def quick_download(symbol: str = "BTC/USDT", timeframe: str = "1h",
                   days: int = 730, exchange: str = "binance") -> pd.DataFrame:
    """
    Quick one-liner to download OHLCV data.

    Usage:
        df = quick_download("BTC/USDT", "4h", days=365)
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    fetcher = CCXTFetcher(exchange)
    df = fetcher.fetch_ohlcv(symbol, timeframe, since=since)
    if not df.empty:
        quality = assess_quality(df, symbol, timeframe, exchange)
        save_to_cache(df, symbol, timeframe, exchange, quality)
        logger.info(f"Quality: {quality.quality_score}/100")
    return df


# ============================================================
# MAIN (CLI usage)
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=" * 60)
    print("ASR Engine v3 — Data Engine")
    print("=" * 60)

    # Download full test universe
    universe = TestUniverse(exchange_id="binance", timeframes=["2h"])
    bundles = universe.download_all(use_cache=True)

    # Print summary
    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)

    for symbol, bundle in bundles.items():
        s = bundle.summary()
        print(f"\n{symbol}:")
        for tf, info in s["timeframes"].items():
            q = info.get("quality_score", "N/A")
            print(f"  {tf}: {info['bars']} bars | Quality: {q}/100")
            print(f"        {info['start']} → {info['end']}")

    # Quality report
    qr = universe.quality_report()
    if not qr.empty:
        print("\n" + "=" * 60)
        print("QUALITY REPORT")
        print("=" * 60)
        print(qr.to_string(index=False))
