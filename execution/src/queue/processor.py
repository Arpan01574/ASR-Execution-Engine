import asyncio
import logging
from datetime import datetime, timezone
from src.queue.signal_queue import signal_queue
from src.models.signals import TVWebhookPayload

logger = logging.getLogger(__name__)

# TTL constant from Prompt 4 (Signal TTL)
SIGNAL_TTL_SECONDS = 60 * 5  # Reject if signal is older than 5 minutes

class SignalProcessor:
    """
    Consumes signals from the queue, applies TTL checks,
    and routes valid signals to the Execution Engine.
    """
    def __init__(self, execution_engine):
        self.execution_engine = execution_engine
        self._running = False
        self._task = None
        
    async def start(self):
        """Start the background processing loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Signal Processor started.")
        
    async def stop(self):
        """Stop the processing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Signal Processor stopped.")
        
    async def _process_loop(self):
        while self._running:
            try:
                payload = await signal_queue.dequeue()
                await self._process_signal(payload)
                signal_queue.mark_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing signal: {e}")
                
    async def _process_signal(self, payload: TVWebhookPayload):
        """Validate TTL and route to execution."""
        
        # 1. Check Signal TTL (Prompt 4 Requirement)
        try:
            bar_time = datetime.fromisoformat(payload.timestamp.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age_seconds = (now - bar_time).total_seconds()
            
            if age_seconds > SIGNAL_TTL_SECONDS:
                logger.warning(
                    f"Signal {payload.signal_id} rejected: Stale TTL. "
                    f"Age: {age_seconds:.1f}s > {SIGNAL_TTL_SECONDS}s"
                )
                signal_queue.update_status(payload.event_id, "REJECTED", "STALE_TTL")
                return
                
        except Exception as e:
            logger.warning(f"Could not parse signal timestamp for TTL check: {e}")
            # Continue processing, but maybe flag it
            
        # 2. Route to Execution Engine
        logger.info(f"Routing valid signal {payload.signal_id} to Execution Engine.")
        success = await self.execution_engine.handle_signal(payload)
        
        if success:
            signal_queue.update_status(payload.event_id, "PROCESSED")
        else:
            signal_queue.update_status(payload.event_id, "REJECTED", "EXECUTION_REJECTED")
