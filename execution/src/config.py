import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from src.models.enums import TradingMode

class Settings(BaseSettings):
    """
    Centralized configuration.
    Values are loaded from environment variables or .env file.
    """
    TRADING_MODE: TradingMode = TradingMode.PAPER
    
    # Webhook Security
    WEBHOOK_URL_TOKEN: str = "default_token_please_change"
    WEBHOOK_PASSPHRASE: str = "default_passphrase_please_change"
    
    # Binance (Primary Adapter)
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_USE_TESTNET: bool = True
    
    # Database
    DATABASE_URL: str = "sqlite:///./execution/data/asr_engine.db"
    
    # Risk
    RISK_PER_TRADE_PCT: float = 0.5  # Must match backtester config.yaml
    MAX_GLOBAL_DRAWDOWN_PCT: float = 20.0
    MAX_SLIPPAGE_PCT: float = 0.5
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Global settings instance
settings = Settings()

# Validation block
if settings.TRADING_MODE == TradingMode.LIVE:
    # Double check for LIVE mode to ensure it's not accidentally enabled
    if os.getenv("CONFIRM_LIVE_MODE", "false").lower() != "true":
        import sys
        import logging
        logging.getLogger(__name__).critical(
            "LIVE mode is disabled by default. "
            "To enable LIVE trading, you must explicitly set CONFIRM_LIVE_MODE=true in environment."
        )
        sys.exit(1)
