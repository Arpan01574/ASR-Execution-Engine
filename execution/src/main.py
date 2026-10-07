import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

from src.database import init_db
from src.webhook.router import router as webhook_router
from src.queue.processor import SignalProcessor
from src.execution.engine import ExecutionEngine

logger = logging.getLogger(__name__)

# Global instances
execution_engine = ExecutionEngine()
signal_processor = SignalProcessor(execution_engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management.
    Initializes database, brokers, and starts background processors.
    """
    logger.info("Starting ASR Execution Engine...")
    
    # 1. Init Database
    init_db()
    
    # 2. Init Execution Engine (connects to broker)
    await execution_engine.initialize()
    
    # 3. Start Background Signal Processor
    await signal_processor.start()
    
    logger.info("Application is ready to receive webhooks.")
    yield
    
    # Shutdown sequence
    logger.info("Shutting down...")
    await signal_processor.stop()
    if execution_engine.broker:
        # Some brokers require closing connections
        close_func = getattr(execution_engine.broker, "close", None)
        if callable(close_func):
            await close_func()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="ASR Execution Engine",
    version="0.1.0",
    lifespan=lifespan
)

# Include webhook routes
app.include_router(webhook_router)

@app.get("/health")
async def health_check():
    """Simple Liveness Probe."""
    return {"status": "healthy", "mode": execution_engine.mode.name}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
