from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from src.models.instruments import VenueInstrument

class BrokerAdapter(ABC):
    """
    Abstract interface for all broker/exchange connections.
    Separates market data, private account data, and order gateways.
    """
    
    @abstractmethod
    async def initialize(self):
        """Setup connection, auth, load markets."""
        pass
        
    @abstractmethod
    async def get_account(self) -> dict:
        """Get account details."""
        pass
        
    @abstractmethod
    async def get_balance(self, asset: str = "USDT") -> float:
        """Get available balance for trading."""
        pass
        
    @abstractmethod
    async def get_positions(self) -> List[dict]:
        """Get all open positions."""
        pass
        
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        """Get all open orders."""
        pass
        
    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> dict:
        """Get specific order details."""
        pass
        
    @abstractmethod
    async def place_order(self, symbol: str, side: str, order_type: str, 
                          quantity: float, price: Optional[float] = None,
                          client_order_id: Optional[str] = None) -> dict:
        """Submit a new order."""
        pass
        
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order."""
        pass
        
    @abstractmethod
    async def replace_order(self, order_id: str, symbol: str, 
                            quantity: float, price: float) -> dict:
        """Modify an existing order (cancel and replace if native unsupported)."""
        pass
        
    @abstractmethod
    async def close_position(self, symbol: str) -> dict:
        """Close an entire open position."""
        pass
        
    @abstractmethod
    async def get_symbol_metadata(self, symbol: str) -> VenueInstrument:
        """Get lot size, tick size, etc."""
        pass
        
    @abstractmethod
    async def get_quote(self, symbol: str) -> dict:
        """Get best bid/ask and last price."""
        pass
        
    @abstractmethod
    async def get_server_time(self) -> int:
        """Get exchange server time in ms."""
        pass
