import asyncio
import logging
import uuid
import time
from typing import Dict, List, Optional
from src.brokers.base import BrokerAdapter
from src.models.instruments import VenueInstrument, CanonicalInstrument

logger = logging.getLogger(__name__)

class PaperBroker(BrokerAdapter):
    """
    Local Paper Trading Broker.
    Simulates market, limit, and stop orders with realistic 
    fees, spread, and latency.
    """
    
    def __init__(self, initial_balance: float = 10000.0, 
                 fee_pct: float = 0.0004, latency_ms: int = 50):
        self.balance = initial_balance
        self.fee_pct = fee_pct
        self.latency_ms = latency_ms
        
        self.positions: Dict[str, dict] = {}
        self.orders: Dict[str, dict] = {}
        self.last_quotes: Dict[str, float] = {} # Mocks current price
        
    async def _simulate_latency(self):
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)
            
    async def initialize(self):
        logger.info("PaperBroker initialized.")
        
    async def get_account(self) -> dict:
        return {"id": "paper_acc_1", "type": "PAPER"}
        
    async def get_balance(self, asset: str = "USDT") -> float:
        return self.balance
        
    async def get_positions(self) -> List[dict]:
        return list(self.positions.values())
        
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        return [o for o in self.orders.values() if o["status"] == "OPEN"]
        
    async def get_order(self, order_id: str, symbol: str) -> dict:
        if order_id in self.orders:
            return self.orders[order_id]
        raise ValueError(f"Order {order_id} not found")
        
    async def place_order(self, symbol: str, side: str, order_type: str, 
                          quantity: float, price: Optional[float] = None,
                          client_order_id: Optional[str] = None) -> dict:
        await self._simulate_latency()
        
        order_id = f"paper_{uuid.uuid4().hex[:8]}"
        
        # Determine execution price based on mock quote and spread
        quote = self.last_quotes.get(symbol, price if price else 100.0)
        spread_penalty = quote * 0.0001
        
        exec_price = quote
        if order_type == "MARKET":
            exec_price = quote + spread_penalty if side == "BUY" else quote - spread_penalty
        elif order_type in ["LIMIT", "STOP"]:
            exec_price = price
            
        order = {
            "order_id": order_id,
            "client_order_id": client_order_id or order_id,
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "price": exec_price,
            "status": "OPEN", # In reality, MARKET fills instantly, but we mock it
            "timestamp": int(time.time() * 1000)
        }
        
        self.orders[order_id] = order
        
        # Auto-fill market orders for testing
        if order_type == "MARKET":
            await self._execute_fill(order_id, exec_price, quantity)
            
        logger.info(f"Paper order placed: {order_id} {side} {quantity} {symbol} @ {exec_price}")
        return order
        
    async def _execute_fill(self, order_id: str, price: float, quantity: float):
        """Internal mock for executing an order."""
        if order_id not in self.orders:
            return
            
        order = self.orders[order_id]
        order["status"] = "FILLED"
        order["filled_qty"] = quantity
        order["avg_price"] = price
        
        fee = (price * quantity) * self.fee_pct
        self.balance -= fee
        
        symbol = order["symbol"]
        side = order["side"]
        
        # Simple position tracking
        if symbol not in self.positions:
            self.positions[symbol] = {"symbol": symbol, "qty": 0.0, "avg_entry": 0.0}
            
        pos = self.positions[symbol]
        
        if side == "BUY":
            # VWAP for buying: weighted average of old position + new fill
            old_qty = pos["qty"]
            old_avg = pos["avg_entry"]
            pos["qty"] += quantity
            if pos["qty"] != 0:
                pos["avg_entry"] = (old_avg * old_qty + price * quantity) / pos["qty"]
            else:
                pos["avg_entry"] = price
        else:
            # Selling reduces position; keep avg_entry as-is (realized PnL is on exit)
            pos["qty"] -= quantity
            
        if pos["qty"] == 0:
            del self.positions[symbol]
            
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        await self._simulate_latency()
        if order_id in self.orders and self.orders[order_id]["status"] == "OPEN":
            self.orders[order_id]["status"] = "CANCELLED"
            return True
        return False
        
    async def replace_order(self, order_id: str, symbol: str, 
                            quantity: float, price: float) -> dict:
        await self.cancel_order(order_id, symbol)
        order = self.orders.get(order_id)
        if not order:
            raise ValueError("Order not found")
        return await self.place_order(
            symbol, order["side"], order["type"], quantity, price, order.get("client_order_id")
        )
        
    async def close_position(self, symbol: str) -> dict:
        await self._simulate_latency()
        if symbol in self.positions:
            pos = self.positions[symbol]
            side = "SELL" if pos["qty"] > 0 else "BUY"
            return await self.place_order(symbol, side, "MARKET", abs(pos["qty"]))
        return {}
        
    async def get_symbol_metadata(self, symbol: str) -> VenueInstrument:
        canonical = CanonicalInstrument("MOCK", "USDT", "PERP")
        return VenueInstrument(canonical, symbol, "PAPER", 0.01, 0.001, 5.0, 0.001, 1.0)
        
    async def get_quote(self, symbol: str) -> dict:
        price = self.last_quotes.get(symbol, 100.0)
        return {"bid": price * 0.9999, "ask": price * 1.0001, "last": price}
        
    async def get_server_time(self) -> int:
        return int(time.time() * 1000)
        
    # Helper for testing
    def update_mock_price(self, symbol: str, price: float):
        self.last_quotes[symbol] = price
