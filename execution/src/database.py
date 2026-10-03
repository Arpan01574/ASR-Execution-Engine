from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
from src.config import settings

engine = create_engine(
    settings.DATABASE_URL, 
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==============================================================================
# DATABASE MODELS
# ==============================================================================

class SignalRecord(Base):
    """Stores every webhook or internal signal event."""
    __tablename__ = "signals"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, unique=True, index=True)
    signal_id = Column(String, index=True)
    timestamp = Column(DateTime(timezone=True), default=func.now())
    bar_time = Column(DateTime(timezone=True))
    
    symbol = Column(String, index=True)
    direction = Column(String)
    action = Column(String) # ENTRY, EXIT, etc.
    
    entry_price = Column(Float)
    stop_price = Column(Float)
    tp1_price = Column(Float)
    tp2_price = Column(Float)
    
    payload = Column(JSON)  # Store the raw request payload
    status = Column(String, default="RECEIVED") # RECEIVED, PROCESSED, REJECTED
    reject_reason = Column(String, nullable=True)

class OrderRecord(Base):
    """Tracks orders sent to the venue."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    internal_order_id = Column(String, unique=True, index=True)
    client_order_id = Column(String, unique=True, index=True)
    venue_order_id = Column(String, index=True, nullable=True)
    signal_id = Column(String, ForeignKey("signals.signal_id"))
    
    symbol = Column(String, index=True)
    order_type = Column(String)
    side = Column(String)
    
    price = Column(Float, nullable=True)
    quantity = Column(Float)
    
    state = Column(String) # NEW, SUBMITTING, OPEN, FILLED, etc.
    
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class FillRecord(Base):
    """Tracks actual fills from the venue."""
    __tablename__ = "fills"
    
    id = Column(Integer, primary_key=True, index=True)
    fill_id = Column(String, unique=True, index=True)
    venue_order_id = Column(String, index=True)
    internal_order_id = Column(String, ForeignKey("orders.internal_order_id"))
    
    symbol = Column(String, index=True)
    side = Column(String)
    price = Column(Float)
    quantity = Column(Float)
    fee = Column(Float)
    fee_asset = Column(String)
    
    timestamp = Column(DateTime(timezone=True))
    
class PositionRecord(Base):
    """Tracks aggregated positions."""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(String, unique=True, index=True)
    symbol = Column(String, index=True)
    
    side = Column(String)
    quantity = Column(Float)
    entry_price = Column(Float)
    
    state = Column(String) # OPEN, REDUCING, CLOSED
    
    realized_pnl = Column(Float, default=0.0)
    
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class RiskDecisionRecord(Base):
    __tablename__ = "risk_decisions"
    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(String, index=True)
    decision = Column(String) # ALLOW, REJECT, RESIZE
    reason = Column(String)
    timestamp = Column(DateTime(timezone=True), default=func.now())

class HealthEventRecord(Base):
    __tablename__ = "health_events"
    id = Column(Integer, primary_key=True, index=True)
    component = Column(String) # WEBSOCKET, BROKER, API
    status = Column(String)
    message = Column(String)
    timestamp = Column(DateTime(timezone=True), default=func.now())

# Initialize database
def init_db():
    Base.metadata.create_all(bind=engine)
