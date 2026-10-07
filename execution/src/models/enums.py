from enum import Enum

class TradingMode(str, Enum):
    PAPER = "PAPER"
    DEMO = "DEMO"
    LIVE = "LIVE"

class SignalType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"

class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

class OrderState(str, Enum):
    """Order state machine (14 states per Prompt 4)."""
    NEW = "NEW"
    VALIDATING = "VALIDATING"
    RISK_CHECK = "RISK_CHECK"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"
    CLOSED = "CLOSED"

class PositionState(str, Enum):
    """Position state machine (9 states per Prompt 4)."""
    FLAT = "FLAT"
    OPENING = "OPENING"
    PARTIAL = "PARTIAL"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"
    RECONCILING = "RECONCILING"

class DriftPolicy(str, Enum):
    """Policy for entry drift guard."""
    REJECT = "REJECT"
    RESIZE = "RESIZE"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
