import hmac
import hashlib
from src.config import settings

def verify_token(token: str) -> bool:
    """
    Constant-time comparison for the URL path token.
    Prevents timing attacks on the webhook endpoint.
    
    Note: hmac.compare_digest already handles different-length strings safely.
    No early return on length mismatch — that would leak timing information.
    """
    expected_token = settings.WEBHOOK_URL_TOKEN.encode('utf-8')
    provided_token = token.encode('utf-8')
    return hmac.compare_digest(expected_token, provided_token)

def verify_passphrase(passphrase: str) -> bool:
    """
    Constant-time comparison for the JSON payload passphrase.
    
    Note: hmac.compare_digest already handles different-length strings safely.
    No early return on length mismatch — that would leak timing information.
    """
    expected_pass = settings.WEBHOOK_PASSPHRASE.encode('utf-8')
    provided_pass = passphrase.encode('utf-8')
    return hmac.compare_digest(expected_pass, provided_pass)
