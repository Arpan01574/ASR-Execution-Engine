import os
import io
import time
import zipfile
import requests
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta

def download_binance_vision():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT"]
    timeframes = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"]
    
    # 3 years of months, starting 36 months ago
    now = datetime(2026, 9, 1) # up to last complete month
    start_date = now - relativedelta(months=36)
    
    # Generate list of YYYY-MM strings
    months = []
    current = start_date
    while current <= now:
        months.append(current.strftime("%Y-%m"))
        current += relativedelta(months=1)
        
    cache_dir = os.path.join("backtester", "data_cache")
    os.makedirs(cache_dir, exist_ok=True)
    
    # Column names in Binance Vision CSVs
    columns = [
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "count",
        "taker_buy_volume", "taker_buy_quote_volume", "ignore"
    ]
    
    for symbol in symbols:
        for tf in timeframes:
            print(f"\\nProcessing {symbol} - {tf}")
            all_dfs = []
            
            for month in months:
                url = f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/{tf}/{symbol}-{tf}-{month}.zip"
                try:
                    response = requests.get(url, timeout=15)
                    if response.status_code == 200:
                        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                            csv_filename = z.namelist()[0]
                            with z.open(csv_filename) as f:
                                # Binance CSVs don't have headers
                                df = pd.read_csv(f, names=columns)
                                all_dfs.append(df)
                                print(f"  [SUCCESS] {month}")
                    elif response.status_code == 404:
                        print(f"  [MISSING] {month} (404 Not Found)")
                    else:
                        print(f"  [ERROR] {month} (Status {response.status_code})")
                except Exception as e:
                    print(f"  [FAILED] {month} - {str(e)}")
            
            if all_dfs:
                combined_df = pd.concat(all_dfs, ignore_index=True)
                
                # Convert timestamp to numeric and drop invalid rows (like headers)
                combined_df["open_time"] = pd.to_numeric(combined_df["open_time"], errors="coerce")
                combined_df = combined_df.dropna(subset=["open_time"])
                
                # Normalize timestamps: Binance switched some dumps to microseconds
                # Any timestamp > 3 trillion is definitely in microseconds.
                mask = combined_df["open_time"] > 3000000000000
                if mask.any():
                    combined_df.loc[mask, "open_time"] = combined_df.loc[mask, "open_time"] / 1000
                
                # Format to match ASR data_engine requirements
                out_df = pd.DataFrame()
                out_df["timestamp"] = combined_df["open_time"]
                out_df["open"] = combined_df["open"]
                out_df["high"] = combined_df["high"]
                out_df["low"] = combined_df["low"]
                out_df["close"] = combined_df["close"]
                out_df["volume"] = combined_df["volume"]
                
                # Convert timestamp to UTC datetime string
                out_df["datetime"] = pd.to_datetime(out_df["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S+00:00")
                
                # Sort and drop duplicates just in case
                out_df = out_df.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
                
                base = symbol.replace("USDT", "")
                quote = "USDT"
                out_filename = f"binance_{base}_{quote}_{tf}.csv"
                out_path = os.path.join(cache_dir, out_filename)
                
                out_df.to_csv(out_path, index=False)
                print(f"Saved {len(out_df)} rows to {out_filename}")
            else:
                print(f"No data found for {symbol} {tf}")

if __name__ == "__main__":
    download_binance_vision()
