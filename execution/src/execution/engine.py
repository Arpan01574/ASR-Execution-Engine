import logging
import asyncio
from typing import Dict, Optional
from src.models.signals import TVWebhookPayload
from src.models.enums import TradingMode, OrderState, PositionState
from src.models.instruments import VenueInstrument
from src.config import settings
from src.risk.engine import RiskEngine
from src.risk.drift_guard import DriftGuard
from src.risk.sizing import PositionSizer
from src.brokers.base import BrokerAdapter
from src.brokers.paper import PaperBroker
from src.brokers.binance import BinanceAdapter
from src.execution.order_fsm import OrderStateMachine
from src.execution.position_fsm import PositionStateMachine
from src.database import SessionLocal, OrderRecord

logger = logging.getLogger(__name__)

class ExecutionEngine:
    """
    Central Execution Engine.
    Maps validated signals to broker orders, enforcing state machines and risk limits.
    """
    
    def __init__(self):
        self.risk_engine = RiskEngine()
        self.drift_guard = DriftGuard()
        self.sizer = PositionSizer()
        self.broker: Optional[BrokerAdapter] = None
        self.mode = settings.TRADING_MODE
        
        # FSM tracking: per-symbol position FSMs
        self._position_fsms: Dict[str, PositionStateMachine] = {}
        
    async def initialize(self):
        if self.mode == TradingMode.PAPER:
            self.broker = PaperBroker()
        elif self.mode in [TradingMode.DEMO, TradingMode.LIVE]:
            # Binance Adapter uses testnet based on config
            self.broker = BinanceAdapter()
        else:
            raise ValueError(f"Unknown Trading Mode: {self.mode}")
            
        await self.broker.initialize()
        logger.info(f"Execution Engine initialized in {self.mode.name} mode.")
        
    async def _sync_risk_state(self):
        """
        Synchronize risk engine state from broker before every signal evaluation.
        Ensures drawdown circuit breaker and open position limits use live data.
        """
        if not self.broker:
            return
        try:
            balance = await self.broker.get_balance("USDT")
            positions_raw = await self.broker.get_positions()
            pos_dict = {p['symbol']: p for p in positions_raw} if isinstance(positions_raw, list) else {}
            self.risk_engine.update_state(balance, pos_dict)
        except Exception as e:
            logger.error(f"Failed to sync risk state from broker: {e}")
        
    async def handle_signal(self, payload: TVWebhookPayload) -> bool:
        """
        Process a verified, non-stale signal.
        """
        if not self.broker:
            logger.error("Execution Engine not initialized.")
            return False
        
        # 0. Sync risk state from broker (LOGIC-1 fix)
        await self._sync_risk_state()
            
        # 1. Risk Check
        allowed, reason = self.risk_engine.evaluate_entry(payload)
        if not allowed:
            logger.info(f"Signal {payload.signal_id} blocked by risk: {reason}")
            return False
            
        # 2. Get Live Quote and Symbol Metadata
        try:
            quote = await self.broker.get_quote(payload.symbol)
            metadata = await self.broker.get_symbol_metadata(payload.symbol)
        except Exception as e:
            logger.error(f"Failed to fetch market data for {payload.symbol}: {e}")
            return False
            
        # 3. Drift Guard
        is_allowed, drift_pct, drift_reason = self.drift_guard.evaluate(
            intended_entry=payload.price,
            current_quote=quote['last'],
            is_long=(payload.direction.value == "LONG")
        )
        
        if not is_allowed:
            logger.warning(f"Signal {payload.signal_id} rejected by Drift Guard: {drift_reason}")
            return False
            
        # 4. Sizing — use config-driven risk % (LOGIC-3 fix)
        try:
            balance = await self.broker.get_balance("USDT")
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return False
            
        risk_pct = settings.RISK_PER_TRADE_PCT
        qty, actual_risk, size_err = self.sizer.calculate_size(
            account_equity=balance,
            risk_pct_equity=risk_pct,
            entry_price=quote['last'],
            stop_price=payload.stop if payload.stop else (quote['last'] * 0.99 if payload.direction.value == "LONG" else quote['last'] * 1.01),
            instrument=metadata
        )
        
        if qty <= 0:
            logger.warning(f"Signal {payload.signal_id} sizing failed: {size_err}")
            return False
            
        # 5. Order Construction & Submission with FSMs (LOGIC-4 fix)
        client_order_id = f"asr_{payload.event_id}"
        side = "BUY" if payload.direction.value == "LONG" else "SELL"
        
        # Initialize Order FSM
        order_fsm = OrderStateMachine(client_order_id)
        order_fsm.transition_to(OrderState.VALIDATING)
        order_fsm.transition_to(OrderState.RISK_CHECK)
        order_fsm.transition_to(OrderState.SUBMITTING)
        
        # Initialize/get Position FSM for this symbol
        if payload.symbol not in self._position_fsms:
            self._position_fsms[payload.symbol] = PositionStateMachine(payload.symbol)
        pos_fsm = self._position_fsms[payload.symbol]
        pos_fsm.transition_to(PositionState.OPENING)
        
        self._record_order_intent(payload, client_order_id, side, qty)
        
        try:
            logger.info(f"Submitting {side} order for {qty} {payload.symbol}...")
            order_res = await self.broker.place_order(
                symbol=payload.symbol,
                side=side,
                order_type="MARKET",
                quantity=qty,
                client_order_id=client_order_id
            )
            
            # Transition FSMs on success
            order_fsm.transition_to(OrderState.ACKNOWLEDGED)
            order_fsm.transition_to(OrderState.FILLED)
            pos_fsm.transition_to(PositionState.OPEN)
            
            logger.info(f"Order successful! Venue ID: {order_res.get('id', 'N/A')} | "
                        f"Order FSM: {order_fsm.state.name} | Position FSM: {pos_fsm.state.name}")
            
            # Place Stop Loss and Take Profits
            await self._place_bracket_orders(payload, qty, metadata)
            
            return True
            
        except Exception as e:
            # Transition FSM to REJECTED on failure
            order_fsm.transition_to(OrderState.REJECTED)
            pos_fsm.transition_to(PositionState.FLAT)
            logger.error(f"Failed to execute order for {payload.signal_id}: {e} | "
                         f"Order FSM: {order_fsm.state.name}")
            return False
            
    async def _place_bracket_orders(self, payload: TVWebhookPayload, qty: float, metadata: VenueInstrument):
        """Simplistic bracket placement."""
        opp_side = "SELL" if payload.direction.value == "LONG" else "BUY"
        
        if payload.stop:
            try:
                await self.broker.place_order(
                    symbol=payload.symbol, side=opp_side, order_type="STOP_MARKET",
                    quantity=qty, price=payload.stop, client_order_id=f"sl_{payload.event_id}"
                )
            except Exception as e:
                logger.error(f"Failed to place SL: {e}")
                
        # TP1 (assuming 33% scale out as per strategy)
        if payload.tp1:
            tp1_qty = round(qty * 0.33 / metadata.lot_size) * metadata.lot_size
            if tp1_qty >= metadata.min_qty:
                try:
                    await self.broker.place_order(
                        symbol=payload.symbol, side=opp_side, order_type="TAKE_PROFIT_MARKET",
                        quantity=tp1_qty, price=payload.tp1, client_order_id=f"tp1_{payload.event_id}"
                    )
                    # Transition position FSM to REDUCING on TP1 placement
                    if payload.symbol in self._position_fsms:
                        self._position_fsms[payload.symbol].transition_to(PositionState.REDUCING)
                except Exception as e:
                    logger.error(f"Failed to place TP1: {e}")
            
    def _record_order_intent(self, payload: TVWebhookPayload, client_id: str, side: str, qty: float):
        db = SessionLocal()
        try:
            rec = OrderRecord(
                internal_order_id=client_id,
                client_order_id=client_id,
                signal_id=payload.signal_id,
                symbol=payload.symbol,
                order_type="MARKET",
                side=side,
                quantity=qty,
                state="NEW"
            )
            db.add(rec)
            db.commit()
        except Exception as e:
            logger.error(f"DB Error recording order intent: {e}")
            db.rollback()
        finally:
            db.close()
