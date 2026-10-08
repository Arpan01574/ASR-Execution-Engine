import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request, status
from src.models.signals import TVWebhookPayload
from src.webhook.security import verify_token, verify_passphrase

# We will inject the queue later, but for now we define the router structure
from src.queue.signal_queue import signal_queue

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
MAX_PAYLOAD_SIZE = 1024 * 10  # 10 KB limit per Prompt 4 requirement

@router.post("/webhook/tradingview/{token}", status_code=status.HTTP_202_ACCEPTED)
async def tradingview_webhook(token: str, payload: TVWebhookPayload, request: Request):
    """
    TradingView Webhook Entry Point.
    Validates token, passphrase, size, and queues for async processing.
    Must return quickly (202 Accepted).
    """
    # 1. Validate Token (URL Path)
    if not verify_token(token):
        logger.warning("Webhook rejected: Invalid URL token.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 2. Validate Request Size
    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > MAX_PAYLOAD_SIZE:
        logger.warning(f"Webhook rejected: Payload too large ({content_length} bytes)")
        raise HTTPException(status_code=413, detail="Payload Too Large")

    # 3. Validate Passphrase (Constant Time)
    if not verify_passphrase(payload.passphrase):
        logger.warning("Webhook rejected: Invalid passphrase in payload.")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # 4. Enqueue Event (Immediate Acknowledgment per Prompt 4)
    # The queue handles idempotency and persistence
    try:
        await signal_queue.enqueue(payload)
        logger.info(f"Signal {payload.signal_id} enqueued successfully.")
    except Exception as e:
        logger.error(f"Failed to enqueue signal: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
        
    return {"status": "accepted", "event_id": payload.event_id}
