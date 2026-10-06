import logging
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from src.models.instruments import VenueInstrument

logger = logging.getLogger(__name__)

class PositionSizer:
    """
    Position sizing calculator using precise Decimal arithmetic.
    Never exceeds the risk budget merely due to rounding.
    """
    
    @staticmethod
    def calculate_size(
        account_equity: float,
        risk_pct_equity: float,
        entry_price: float,
        stop_price: float,
        instrument: VenueInstrument,
        max_leverage: float = 10.0,
    ) -> tuple[float, float, str]:
        """
        Calculate target quantity based on risk.
        Returns: (quantity, actual_risk_amount, error_reason)
        """
        if account_equity <= 0 or risk_pct_equity <= 0:
            return 0.0, 0.0, "Invalid equity or risk %"
            
        if entry_price <= 0 or stop_price <= 0 or entry_price == stop_price:
            return 0.0, 0.0, "Invalid entry/stop prices"
            
        # Convert all to Decimals for exact arithmetic
        eq = Decimal(str(account_equity))
        r_pct = Decimal(str(risk_pct_equity)) / Decimal('100')
        entry = Decimal(str(entry_price))
        stop = Decimal(str(stop_price))
        
        lot_size = Decimal(str(instrument.lot_size))
        min_qty = Decimal(str(instrument.min_qty))
        contract_size = Decimal(str(instrument.contract_size))
        
        # Risk amount in quote currency
        risk_amount = eq * r_pct
        
        # Price distance
        distance = abs(entry - stop)
        
        # Risk per contract
        risk_per_contract = distance * contract_size
        
        if risk_per_contract == Decimal('0'):
            return 0.0, 0.0, "Zero risk per contract"
            
        # Raw quantity
        raw_qty = risk_amount / risk_per_contract
        
        # Max notional based on leverage limits
        max_notional = eq * Decimal(str(max_leverage))
        max_qty_by_leverage = max_notional / (entry * contract_size)
        
        if raw_qty > max_qty_by_leverage:
            raw_qty = max_qty_by_leverage
            logger.debug(f"Position size capped by max leverage ({max_leverage}x)")
        
        # Round down to nearest lot size so we NEVER exceed risk
        # formula: floor(raw_qty / lot_size) * lot_size
        steps = (raw_qty / lot_size).quantize(Decimal('1'), rounding=ROUND_DOWN)
        final_qty = steps * lot_size
        
        if final_qty < min_qty:
            return 0.0, 0.0, f"Calculated size {final_qty} < min quantity {min_qty}"
            
        # Check min notional if applicable
        notional = final_qty * entry * contract_size
        if notional < Decimal(str(instrument.min_notional)):
            return 0.0, 0.0, f"Notional {notional} < min notional {instrument.min_notional}"
            
        actual_risk = final_qty * risk_per_contract
        
        return float(final_qty), float(actual_risk), ""
