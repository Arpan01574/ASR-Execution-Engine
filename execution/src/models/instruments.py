from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class CanonicalInstrument:
    """
    Abstract Canonical Instrument (e.g., BTC-USDT-PERP).
    Used internally by the execution system and risk engine.
    """
    base: str         # e.g., BTC
    quote: str        # e.g., USDT
    inst_type: str    # SPOT, PERP, FUTURE
    
    def __str__(self) -> str:
        return f"{self.base}-{self.quote}-{self.inst_type}"


@dataclass(frozen=True)
class VenueInstrument:
    """
    Venue-specific instrument implementation (e.g., BTCUSDT for Binance Perp).
    Used by specific broker adapters.
    """
    canonical: CanonicalInstrument
    venue_symbol: str
    venue_id: str
    
    # Metadata for sizing and execution
    tick_size: float
    lot_size: float
    min_notional: float
    min_qty: float
    contract_size: float = 1.0  # Usually 1.0 for crypto, varies for traditional
    
    def __str__(self) -> str:
        return f"{self.venue_id}:{self.venue_symbol}"
