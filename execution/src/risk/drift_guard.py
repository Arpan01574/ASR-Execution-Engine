import logging
from src.models.enums import DriftPolicy

logger = logging.getLogger(__name__)

class DriftGuard:
    """
    Entry Drift Guard.
    Compares intended TradingView entry vs actual live market quote.
    """
    
    def __init__(self, policy: DriftPolicy = DriftPolicy.REJECT, max_slippage_pct: float = 0.5):
        self.policy = policy
        self.max_slippage_pct = max_slippage_pct
        
    def evaluate(self, intended_entry: float, current_quote: float, is_long: bool) -> tuple[bool, float, str]:
        """
        Calculates drift and applies the configured policy.
        Returns: (is_allowed, drift_pct, reason)
        """
        if intended_entry <= 0 or current_quote <= 0:
            return False, 0.0, "Invalid prices"
            
        # Calculate drift percentage (adverse movement)
        if is_long:
            # For longs, current quote > intended is adverse
            drift_pct = (current_quote - intended_entry) / intended_entry * 100
        else:
            # For shorts, current quote < intended is adverse
            drift_pct = (intended_entry - current_quote) / intended_entry * 100
            
        # If drift is favorable or within limit, allow it
        if drift_pct <= self.max_slippage_pct:
            return True, drift_pct, f"Drift {drift_pct:.3f}% within limit."
            
        # Drift exceeds limit, apply policy
        if self.policy == DriftPolicy.REJECT:
            logger.warning(f"DriftGuard REJECT: {drift_pct:.3f}% > {self.max_slippage_pct}%")
            return False, drift_pct, "Max slippage exceeded (REJECT)"
            
        elif self.policy == DriftPolicy.RESIZE:
            logger.info(f"DriftGuard RESIZE trigger: {drift_pct:.3f}% > {self.max_slippage_pct}%")
            return True, drift_pct, "Max slippage exceeded (RESIZE)"
            
        elif self.policy == DriftPolicy.ALLOW_WITH_WARNING:
            logger.warning(f"DriftGuard WARNING: {drift_pct:.3f}% > {self.max_slippage_pct}% (Allowed)")
            return True, drift_pct, "Max slippage exceeded (WARNING)"
            
        return False, drift_pct, "Unknown policy"
