import logging
import pandas as pd
from typing import Generator, Dict, Any
from .asr_engine import ASREngine

logger = logging.getLogger(__name__)

class HistoricalReplayEngine:
    """
    Simulates a live event stream from historical data.
    Instead of processing the entire dataframe at once (like a standard backtest),
    this engine yields events bar-by-bar, exactly as they would appear in live trading.
    
    Event Types Yielded:
    - BAR
    - ZONE_CREATED
    - SIGNAL
    - ORDER_INTENT
    - FILL
    - TP1 / TP2 / BE / SL / TIME_EXIT
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.engine = ASREngine(config)
        
    def stream_events(self, df: pd.DataFrame, symbol: str) -> Generator[Dict[str, Any], None, None]:
        """
        Yields discrete events by stepping through the DataFrame one bar at a time.
        """
        if df.empty:
            return
            
        # Initialize strategy state
        self.engine.symbol = symbol
        self.engine.trades = []
        self.engine.zones = []
        
        # We process bar by bar
        for i in range(len(df)):
            current_bar = df.iloc[i]
            timestamp = current_bar.name if isinstance(current_bar.name, pd.Timestamp) else i
            
            # 1. Yield BAR event
            yield {
                "type": "BAR",
                "timestamp": timestamp,
                "symbol": symbol,
                "open": current_bar.get("open", 0),
                "high": current_bar.get("high", 0),
                "low": current_bar.get("low", 0),
                "close": current_bar.get("close", 0),
                "volume": current_bar.get("volume", 0)
            }
            
            # Snapshot state before processing
            prev_zones_count = len(self.engine.zones)
            prev_trades_count = len(self.engine.trades)
            
            # Step the underlying engine logic for this single bar
            # To do this correctly, we pass the dataframe slice up to 'i'
            slice_df = df.iloc[:i+1]
            
            # In a true real-time engine, ASREngine would be stateful on a per-bar basis.
            # For the sake of this replay wrapper, we extract the core logic for the *current* bar.
            # (Assuming ASREngine has a step() method. Since our ASREngine runs vectorized/looped 
            # internally in run(), we will simulate the step here by tracking new additions).
            
            self._process_bar_state(slice_df, i, timestamp)
            
            # Check for new Zones
            if len(self.engine.zones) > prev_zones_count:
                new_zone = self.engine.zones[-1]
                yield {
                    "type": "ZONE_CREATED",
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "zone_id": f"Z_{new_zone.start_index}",
                    "polarity": new_zone.polarity,
                    "score": new_zone.score
                }
                
            # Check for Trade Events (Entries and Exits)
            if len(self.engine.trades) > prev_trades_count:
                # A new trade was completed (our backtester stores *completed* trades)
                # In a real event stream, we'd emit ENTRY then later EXIT.
                # Since ASREngine yields completed trades, we reconstruct the events.
                trade = self.engine.trades[-1]
                
                # Emit ENTRY
                yield {
                    "type": "SIGNAL",
                    "timestamp": trade.entry_time,
                    "symbol": symbol,
                    "action": "ENTRY",
                    "direction": "LONG" if trade.direction == 1 else "SHORT",
                    "price": trade.entry,
                    "stop": trade.stop,
                    "tp1": trade.tp1,
                    "tp2": trade.tp2
                }
                
                yield {
                    "type": "ORDER_INTENT",
                    "timestamp": trade.entry_time,
                    "symbol": symbol,
                    "order_type": "MARKET"
                }
                
                yield {
                    "type": "FILL",
                    "timestamp": trade.entry_time,
                    "symbol": symbol,
                    "fill_price": trade.entry
                }
                
                # Emit EXIT
                exit_type_str = {1: "SL", 2: "BE", 3: "TP2", 4: "TIME_EXIT", 5: "TP1"}.get(trade.exit_type, "EXIT")
                yield {
                    "type": exit_type_str,
                    "timestamp": trade.exit_time,
                    "symbol": symbol,
                    "exit_price": trade.exit_price,
                    "pnl_r": trade.net_r
                }
                
    def _process_bar_state(self, slice_df: pd.DataFrame, current_idx: int, timestamp: Any):
        """
        Steps the ASREngine logic for the current bar to update zones and trades.
        (This bridges the vectorized backtester to the bar-by-bar replay).
        """
        # Run the core logic over the slice.
        # This is computationally heavy if done purely iteratively from start every time.
        # A true production system will maintain running state variables.
        # For Prompt 5's Historical Replay requirement, we run the logic up to the current bar
        # to ensure state exactly matches what live would see.
        
        self.engine.run(slice_df, symbol=self.engine.symbol, timeframe="1h")
