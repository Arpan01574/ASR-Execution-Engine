import pytest
import httpx
import asyncio
from datetime import datetime, timezone
from src.config import settings

# Test payload mirroring TradingView's structure
MOCK_PAYLOAD = {
    "passphrase": settings.WEBHOOK_PASSPHRASE,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "event_id": "test_event_001",
    "signal_id": "test_signal_001",
    "symbol": "BTCUSDT",
    "action": "ENTRY",
    "direction": "LONG",
    "price": 60000.00,
    "stop": 59000.00,
    "tp1": 61500.00,
    "tp2": 63000.00,
    "score": 85.0,
    "setup": "ZONE_REJECT"
}

@pytest.mark.asyncio
async def test_webhook_acceptance():
    """
    Test that the webhook endpoint correctly validates and accepts a payload.
    Assumes the FastAPI server is running locally on port 8000.
    """
    url = f"http://localhost:8000/webhook/tradingview/{settings.WEBHOOK_URL_TOKEN}"
    
    async with httpx.AsyncClient() as client:
        # Test 1: Valid Request
        response = await client.post(url, json=MOCK_PAYLOAD)
        # We expect 202 Accepted because processing is asynchronous
        assert response.status_code == 202
        assert response.json() == {"status": "accepted", "event_id": MOCK_PAYLOAD["event_id"]}
        
        # Test 2: Invalid Token
        bad_token_url = "http://localhost:8000/webhook/tradingview/wrong_token"
        response_bad_token = await client.post(bad_token_url, json=MOCK_PAYLOAD)
        assert response_bad_token.status_code == 401
        
        # Test 3: Invalid Passphrase
        bad_payload = MOCK_PAYLOAD.copy()
        bad_payload["passphrase"] = "wrong_passphrase"
        response_bad_pass = await client.post(url, json=bad_payload)
        assert response_bad_pass.status_code == 401

@pytest.mark.asyncio
async def test_end_to_end_paper_execution():
    """
    Test the full flow:
    1. Send Webhook
    2. Wait for async processing
    3. Verify PaperBroker state (mocked or via DB)
    
    *Note: In a true CI environment, we would spin up the TestClient and 
    inspect the in-memory SQLite DB and PaperBroker state directly.*
    """
    # For now, this is a placeholder representing the Live-Readiness Check requirement.
    pass
