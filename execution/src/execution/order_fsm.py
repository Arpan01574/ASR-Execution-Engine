import logging
from typing import Optional
from src.models.enums import OrderState

logger = logging.getLogger(__name__)

class OrderStateMachine:
    """
    Strict State Machine for Orders.
    Validates all state transitions to prevent invalid routing.
    """
    
    VALID_TRANSITIONS = {
        OrderState.NEW: [OrderState.VALIDATING, OrderState.REJECTED, OrderState.CANCELLED],
        OrderState.VALIDATING: [OrderState.RISK_CHECK, OrderState.REJECTED],
        OrderState.RISK_CHECK: [OrderState.SUBMITTING, OrderState.REJECTED],
        OrderState.SUBMITTING: [OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.UNKNOWN],
        OrderState.ACKNOWLEDGED: [OrderState.OPEN, OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED],
        OrderState.OPEN: [OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCEL_REQUESTED, OrderState.CANCELLED],
        OrderState.PARTIAL: [OrderState.FILLED, OrderState.CANCEL_REQUESTED, OrderState.CANCELLED],
        OrderState.CANCEL_REQUESTED: [OrderState.CANCELLED, OrderState.FILLED, OrderState.PARTIAL, OrderState.OPEN], # Might reject cancel
        OrderState.UNKNOWN: [OrderState.RECONCILING],
        OrderState.RECONCILING: [OrderState.OPEN, OrderState.PARTIAL, OrderState.FILLED, OrderState.CANCELLED, OrderState.CLOSED],
        # Terminal States
        OrderState.FILLED: [],
        OrderState.CANCELLED: [],
        OrderState.REJECTED: [],
        OrderState.CLOSED: [],
    }

    def __init__(self, order_id: str, initial_state: OrderState = OrderState.NEW):
        self.order_id = order_id
        self._state = initial_state
        
    @property
    def state(self) -> OrderState:
        return self._state
        
    def transition_to(self, new_state: OrderState) -> bool:
        """Attempt to transition to a new state."""
        if new_state in self.VALID_TRANSITIONS.get(self._state, []):
            logger.debug(f"Order {self.order_id} transition: {self._state.name} -> {new_state.name}")
            self._state = new_state
            return True
        else:
            logger.error(f"Invalid order transition attempt for {self.order_id}: {self._state.name} -> {new_state.name}")
            return False
            
    def is_terminal(self) -> bool:
        """Check if the order is in a terminal state."""
        return len(self.VALID_TRANSITIONS.get(self._state, [])) == 0
