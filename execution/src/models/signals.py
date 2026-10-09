from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from src.models.enums import SignalType, Direction

class TVWebhookPayload(BaseModel):
    """
    Strict validation schema for incoming TradingView webhooks.
    Follows Prompt 4 requirement for strict schema and validation.
    """
    passphrase: str = Field(..., description="Authentication passphrase")
    timestamp: str = Field(..., description="ISO8601 string from TV")
    event_id: str = Field(..., description="Unique event ID from TV")
    signal_id: str = Field(..., description="Unique signal ID per setup")
    
    symbol: str = Field(..., description="Trading pair, e.g. BTCUSDT")
    action: SignalType = Field(..., description="ENTRY or EXIT")
    direction: Direction = Field(..., description="LONG or SHORT")
    
    # Entry data
    price: float = Field(..., description="Current close price of the alert bar")
    stop: Optional[float] = Field(None, description="Stop loss price")
    tp1: Optional[float] = Field(None, description="Take profit 1 price")
    tp2: Optional[float] = Field(None, description="Take profit 2 price")
    
    # Additional ASR context
    score: Optional[float] = Field(None, description="ASR Zone Quality Score (0-100)")
    setup: Optional[str] = Field(None, description="Setup type, e.g., ZONE_REJECT")
    
    class Config:
        json_schema_extra = {
            "example": {
                "passphrase": "your_secure_passphrase",
                "timestamp": "2026-10-03T05:00:00Z",
                "event_id": "evt_12345",
                "signal_id": "sig_09876",
                "symbol": "BTCUSDT",
                "action": "ENTRY",
                "direction": "LONG",
                "price": 60000.50,
                "stop": 59000.00,
                "tp1": 61500.00,
                "tp2": 63000.00,
                "score": 85.5,
                "setup": "ZONE_REJECT"
            }
        }
