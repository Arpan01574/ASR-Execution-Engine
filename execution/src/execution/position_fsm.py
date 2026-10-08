import logging
from src.models.enums import PositionState

logger = logging.getLogger(__name__)

class PositionStateMachine:
    """
    Strict State Machine for Positions.
    Driven by actual authoritative exchange fills.
    """
    
    VALID_TRANSITIONS = {
        PositionState.FLAT: [PositionState.OPENING, PositionState.UNKNOWN],
        PositionState.OPENING: [PositionState.PARTIAL, PositionState.OPEN, PositionState.FLAT, PositionState.UNKNOWN],
        PositionState.PARTIAL: [PositionState.OPEN, PositionState.REDUCING, PositionState.CLOSING, PositionState.CLOSED],
        PositionState.OPEN: [PositionState.REDUCING, PositionState.CLOSING, PositionState.CLOSED, PositionState.UNKNOWN],
        PositionState.REDUCING: [PositionState.OPEN, PositionState.CLOSING, PositionState.CLOSED],
        PositionState.CLOSING: [PositionState.CLOSED, PositionState.FLAT, PositionState.PARTIAL],
        PositionState.UNKNOWN: [PositionState.RECONCILING],
        PositionState.RECONCILING: [PositionState.FLAT, PositionState.PARTIAL, PositionState.OPEN, PositionState.CLOSED],
        # Terminal
        PositionState.CLOSED: [PositionState.FLAT], # Can reset for a new trade
    }

    def __init__(self, symbol: str, initial_state: PositionState = PositionState.FLAT):
        self.symbol = symbol
        self._state = initial_state
        
    @property
    def state(self) -> PositionState:
        return self._state
        
    def transition_to(self, new_state: PositionState) -> bool:
        """Attempt to transition to a new position state."""
        if new_state in self.VALID_TRANSITIONS.get(self._state, []):
            logger.info(f"Position {self.symbol} transition: {self._state.name} -> {new_state.name}")
            self._state = new_state
            return True
        else:
            logger.error(f"Invalid position transition attempt for {self.symbol}: {self._state.name} -> {new_state.name}")
            return False
