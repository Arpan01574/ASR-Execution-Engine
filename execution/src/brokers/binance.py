import logging
from typing import Dict, List, Optional
from src.brokers.base import BrokerAdapter
from src.models.instruments import VenueInstrument, CanonicalInstrument
from src.config import settings

logger = logging.getLogger(__name__)

class BinanceAdapter(BrokerAdapter):
    """
    Binance implementation of BrokerAdapter using ccxt.async_support.
    Supports Testnet/Demo and Live via configuration.
    """
    
    def __init__(self, use_testnet: bool = None):
        try:
            import ccxt.async_support as ccxt
        except ImportError:
            raise ImportError("ccxt is required. pip install ccxt")
            
        self.use_testnet = use_testnet if use_testnet is not None else settings.BINANCE_USE_TESTNET
        
        # Determine base URL based on testnet
        self.exchange = ccxt.binanceusdm({
            'apiKey': settings.BINANCE_API_KEY,
            'secret': settings.BINANCE_API_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future', 
            }
        })
        
        if self.use_testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("BinanceAdapter initialized in TESTNET mode.")
        else:
            logger.warning("BinanceAdapter initialized in LIVE mode.")
            
        self._markets_loaded = False
        
    async def initialize(self):
        if not self._markets_loaded:
            await self.exchange.load_markets()
            self._markets_loaded = True
            
    async def get_account(self) -> dict:
        await self.initialize()
        return await self.exchange.fetch_account()
        
    async def get_balance(self, asset: str = "USDT") -> float:
        await self.initialize()
        balance = await self.exchange.fetch_balance()
        if asset in balance:
            return float(balance[asset]['free'])
        return 0.0
        
    async def get_positions(self) -> List[dict]:
        await self.initialize()
        positions = await self.exchange.fetch_positions()
        # Filter only open positions
        open_pos = [p for p in positions if float(p['info']['positionAmt']) != 0]
        return open_pos
        
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[dict]:
        await self.initialize()
        return await self.exchange.fetch_open_orders(symbol)
        
    async def get_order(self, order_id: str, symbol: str) -> dict:
        await self.initialize()
        return await self.exchange.fetch_order(order_id, symbol)
        
    async def place_order(self, symbol: str, side: str, order_type: str, 
                          quantity: float, price: Optional[float] = None,
                          client_order_id: Optional[str] = None) -> dict:
        await self.initialize()
        
        params = {}
        if client_order_id:
            params['newClientOrderId'] = client_order_id
            
        # Convert ASR order types to Binance compatible ones
        o_type = order_type.lower()
        
        return await self.exchange.create_order(
            symbol, o_type, side.lower(), quantity, price, params
        )
        
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        await self.initialize()
        try:
            await self.exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on {symbol}: {e}")
            return False
            
    async def replace_order(self, order_id: str, symbol: str, 
                            quantity: float, price: float) -> dict:
        # ccxt doesn't standardise replace_order well across all exchanges,
        # fallback is cancel and replace. For Binance, we can use edit_order
        await self.initialize()
        try:
            # Fetch original order to get the correct side
            old_order = await self.get_order(order_id, symbol)
            side = old_order.get('side', 'buy')
            return await self.exchange.edit_order(
                order_id, symbol, 'limit', side, quantity, price
            )
        except Exception:
            # Fallback: cancel and re-place with the correct side
            try:
                old_order = await self.get_order(order_id, symbol)
                side = old_order.get('side', 'buy')
                await self.cancel_order(order_id, symbol)
                return await self.place_order(
                    symbol, side, 'LIMIT', quantity, price
                )
            except Exception as e:
                logger.error(f"Failed to replace order {order_id}: {e}")
                raise
        
    async def close_position(self, symbol: str) -> dict:
        """
        Binance specific: close position using opposite market order
        or reduce-only order.
        """
        await self.initialize()
        positions = await self.get_positions()
        pos = next((p for p in positions if p['symbol'] == symbol), None)
        
        if not pos:
            return {}
            
        amt = float(pos['info']['positionAmt'])
        if amt == 0:
            return {}
            
        side = 'sell' if amt > 0 else 'buy'
        return await self.exchange.create_order(
            symbol, 'market', side, abs(amt), params={'reduceOnly': True}
        )
        
    async def get_symbol_metadata(self, symbol: str) -> VenueInstrument:
        await self.initialize()
        market = self.exchange.market(symbol)
        
        canonical = CanonicalInstrument(market['base'], market['quote'], 'PERP')
        
        return VenueInstrument(
            canonical=canonical,
            venue_symbol=market['id'],
            venue_id="BINANCE",
            tick_size=market['precision']['price'],
            lot_size=market['precision']['amount'],
            min_notional=market['limits']['cost']['min'] if 'cost' in market['limits'] else 5.0,
            min_qty=market['limits']['amount']['min'],
            contract_size=market.get('contractSize', 1.0)
        )
        
    async def get_quote(self, symbol: str) -> dict:
        await self.initialize()
        ticker = await self.exchange.fetch_ticker(symbol)
        return {
            "bid": ticker.get('bid'),
            "ask": ticker.get('ask'),
            "last": ticker.get('last')
        }
        
    async def get_server_time(self) -> int:
        await self.initialize()
        time_data = await self.exchange.fetch_time()
        return int(time_data)

    async def close(self):
        """Clean up resources."""
        await self.exchange.close()
