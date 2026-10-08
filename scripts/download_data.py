import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backtester.data_engine import TestUniverse

def main():
    print("Initializing Data Engine for 3-year historical download...")
    
    # 5 assets requested by user
    symbols = [
        {"symbol": "BTC/USDT", "name": "Bitcoin"},
        {"symbol": "ETH/USDT", "name": "Ethereum"},
        {"symbol": "SOL/USDT", "name": "Solana"},
        {"symbol": "XRP/USDT", "name": "XRP"},
        {"symbol": "BNB/USDT", "name": "BNB"},
    ]
    
    # Timeframes requested
    timeframes = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"]
    
    universe = TestUniverse(
        exchange_id="binance",
        symbols=symbols,
        timeframes=timeframes
    )
    
    # Last 3 years
    since = datetime.now(timezone.utc) - timedelta(days=1095)
    
    # Force use_cache=False to ensure we fetch missing bars and go back 3 years,
    # or use_cache=True but let it fetch the whole range if not cached. 
    # data_engine's download_all doesn't merge old and new, it just uses cache if exists. 
    # To get 3 years, we should probably force download.
    print(f"Downloading data since {since.strftime('%Y-%m-%d')}...")
    bundles = universe.download_all(since=since, use_cache=False)
    
    print("\nDownload complete. Quality Report:")
    qr = universe.quality_report()
    if not qr.empty:
        print(qr[["symbol", "timeframe", "total_bars", "quality_score", "start", "end"]].to_string(index=False))

if __name__ == "__main__":
    main()
