import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from src.database import SessionLocal, SignalRecord
from src.models.signals import TVWebhookPayload

logger = logging.getLogger(__name__)

class SignalQueue:
    """
    Async persistent signal queue with idempotency support.
    Follows exactly-once execution semantics by tracking event_ids.
    """
    
    def __init__(self):
        self._queue = asyncio.Queue()
    
    async def enqueue(self, payload: TVWebhookPayload):
        """
        Persists the signal to DB and adds it to the memory queue.
        Enforces idempotency using event_id.
        """
        # Run DB operation in a thread pool to avoid blocking async loop
        is_duplicate = await asyncio.to_thread(self._persist_signal, payload)
        
        if is_duplicate:
            logger.warning(f"Duplicate signal detected and dropped: {payload.event_id}")
            return
            
        await self._queue.put(payload)
        
    def _persist_signal(self, payload: TVWebhookPayload) -> bool:
        """
        Saves signal to SQLite. Returns True if it's a duplicate.
        """
        db = SessionLocal()
        try:
            # Check for exact duplicate event (Idempotency)
            existing = db.query(SignalRecord).filter(
                SignalRecord.event_id == payload.event_id
            ).first()
            
            if existing:
                return True
                
            # Convert TV ISO string to naive/aware UTC
            try:
                # Basic parsing, depends on exact TV output format
                bar_time = datetime.fromisoformat(payload.timestamp.replace('Z', '+00:00'))
            except Exception:
                bar_time = datetime.now(timezone.utc)
                
            record = SignalRecord(
                event_id=payload.event_id,
                signal_id=payload.signal_id,
                bar_time=bar_time,
                symbol=payload.symbol,
                direction=payload.direction.value,
                action=payload.action.value,
                entry_price=payload.price,
                stop_price=payload.stop,
                tp1_price=payload.tp1,
                tp2_price=payload.tp2,
                payload=payload.model_dump(mode='json'),
                status="RECEIVED"
            )
            
            db.add(record)
            db.commit()
            return False
            
        except Exception as e:
            db.rollback()
            logger.error(f"DB Error persisting signal: {e}")
            # If we fail to persist, we must raise an error to block processing 
            # and let the webhook return a 500 to the caller.
            raise RuntimeError(f"Cannot persist signal: {e}")
        finally:
            db.close()
            
    async def dequeue(self) -> TVWebhookPayload:
        """Wait for and return the next signal."""
        return await self._queue.get()
        
    def mark_done(self):
        """Mark task as done in the asyncio queue."""
        self._queue.task_done()
        
    def update_status(self, event_id: str, status: str, reason: str = None):
        """Update the processing status in the database."""
        db = SessionLocal()
        try:
            record = db.query(SignalRecord).filter(SignalRecord.event_id == event_id).first()
            if record:
                record.status = status
                if reason:
                    record.reject_reason = reason
                db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"DB Error updating status: {e}")
        finally:
            db.close()

# Global Singleton Instance
signal_queue = SignalQueue()
