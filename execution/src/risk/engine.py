import logging
from typing import Dict, List, Optional
from src.config import settings
from src.database import SessionLocal, RiskDecisionRecord
from src.models.signals import TVWebhookPayload

logger = logging.getLogger(__name__)

class RiskEngine:
    """
    Central Authoritative Risk Engine.
    Pine Script risk is advisory. Python risk is authoritative.
    """
    
    def __init__(self):
        self.global_pause = False
        self.paused_symbols: set = set()
        
        # Current state tracked by execution engine
        self.open_positions: Dict[str, dict] = {}
        self.daily_pnl = 0.0
        self.peak_equity = 0.0
        self.current_equity = 0.0
        
    def evaluate_entry(self, payload: TVWebhookPayload) -> tuple[bool, str]:
        """
        Evaluate if a new entry signal should be allowed.
        Returns: (is_allowed, reason)
        """
        symbol = payload.symbol
        
        # 1. Kill Switches
        if self.global_pause:
            return self._reject(payload, "GLOBAL_PAUSE")
            
        if symbol in self.paused_symbols:
            return self._reject(payload, f"SYMBOL_PAUSED:{symbol}")
            
        # 2. Drawdown Check
        if self.peak_equity > 0:
            dd_pct = (self.peak_equity - self.current_equity) / self.peak_equity * 100
            if dd_pct >= settings.MAX_GLOBAL_DRAWDOWN_PCT:
                self.global_pause = True
                return self._reject(payload, f"MAX_DRAWDOWN_BREACH:{dd_pct:.1f}%")
                
        # 3. Per-Symbol Exposure
        if symbol in self.open_positions:
            pos = self.open_positions[symbol]
            if pos.get("quantity", 0) != 0:
                return self._reject(payload, "EXISTING_POSITION")
                
        # 4. Global Exposure Limits (e.g., max open trades)
        if len(self.open_positions) >= 5: # Configurable in full version
            return self._reject(payload, "MAX_OPEN_TRADES_REACHED")
            
        return self._allow(payload)
        
    def _reject(self, payload: TVWebhookPayload, reason: str) -> tuple[bool, str]:
        logger.warning(f"Risk Engine REJECT {payload.signal_id}: {reason}")
        self._record_decision(payload.signal_id, "REJECT", reason)
        return False, reason
        
    def _allow(self, payload: TVWebhookPayload) -> tuple[bool, str]:
        logger.info(f"Risk Engine ALLOW {payload.signal_id}")
        self._record_decision(payload.signal_id, "ALLOW", "")
        return True, ""
        
    def _record_decision(self, signal_id: str, decision: str, reason: str):
        db = SessionLocal()
        try:
            record = RiskDecisionRecord(
                signal_id=signal_id,
                decision=decision,
                reason=reason
            )
            db.add(record)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to record risk decision: {e}")
            db.rollback()
        finally:
            db.close()
            
    def update_state(self, current_equity: float, open_positions: dict):
        """Update internal state for risk calculations."""
        self.current_equity = current_equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        self.open_positions = open_positions
        
    def trigger_kill_switch(self, reason: str):
        """Manually trigger the global kill switch."""
        self.global_pause = True
        logger.critical(f"GLOBAL KILL SWITCH TRIGGERED: {reason}")
