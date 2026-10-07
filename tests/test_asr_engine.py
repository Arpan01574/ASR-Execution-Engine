import pytest
import pandas as pd
import numpy as np
from backtester.asr_engine import ASREngine, Zone, TradeResult

def generate_sample_data(n=100) -> pd.DataFrame:
    """Generate basic OHLCV data for testing."""
    dates = pd.date_range("2026-01-01", periods=n, freq="1H")
    
    # Create a simple sine wave price pattern to generate pivots
    x = np.linspace(0, 4 * np.pi, n)
    base_price = 1000 + 100 * np.sin(x)
    
    df = pd.DataFrame({
        "timestamp": dates,
        "open": base_price,
        "high": base_price + 10,
        "low": base_price - 10,
        "close": base_price + 5,
        "volume": np.random.randint(100, 1000, size=n)
    })
    df.set_index("timestamp", inplace=True)
    return df

@pytest.fixture
def base_config():
    return {
        "core": {"invalidation": "close"},
        "pivots": {"piv_l": 5, "piv_r": 5, "n_piv": 5}, # Short pivots for faster testing
        "zone_quality": {"min_zone_duration": 1, "decay_factor": 800},
        "signal": {"min_score": 10, "min_tier": "None", "cooldown_bars": 1, "max_sig_per_day": 4, "enable": True},
        "risk": {"sl_buffer_atr": 0.5, "tp1_r": 1.0, "tp2_r": 2.0, "risk_pct_equity": 1.0},
        "regime": {"atr_percentile_window": 10}
    }

def test_zone_creation(base_config):
    df = generate_sample_data(100)
    engine = ASREngine(base_config)
    engine.run(df)
    
    assert len(engine.zones) > 0
    # Check if zones have expected attributes
    z = engine.zones[0]
    assert z.top >= z.btm
    assert z.status in [0, 1, 2, 3, 4, 5, 6, 7]

def test_zone_scoring(base_config):
    df = generate_sample_data(100)
    engine = ASREngine(base_config)
    engine.run(df)
    
    if len(engine.zones) > 0:
        z = engine.zones[-1]
        assert z.tier in [0, 1, 2] # None, Strong, Elite
        assert z.quality_score >= 0.0

def test_signal_generation(base_config):
    df = generate_sample_data(200)
    engine = ASREngine(base_config)
    trades = engine.run(df)
    
    if len(trades) > 0:
        t = trades[0]
        assert t.setup_name != ""
        assert t.entry_price > 0
        assert t.sl > 0

def test_trade_management(base_config):
    df = generate_sample_data(200)
    engine = ASREngine(base_config)
    trades = engine.run(df)
    
    for t in trades:
        # If trade closed, it should have an exit reason
        if t.exit_reason != "":
            assert t.exit_reason in ['SL', 'TP1', 'TP2', 'TP3', 'TRAIL', 'BE', 'TIME']
            assert t.exit_price > 0

def test_daily_signal_limit(base_config):
    # Set limit to 1 per day
    base_config['signal']['max_sig_per_day'] = 1
    df = generate_sample_data(300) # Covers multiple days
    engine = ASREngine(base_config)
    
    trades = engine.run(df)
    
    # Map trades to days
    trades_per_day = {}
    for t in trades:
        day = pd.Timestamp(t.entry_time, unit='ms').floor('D')
        trades_per_day[day] = trades_per_day.get(day, 0) + 1
        
    for day, count in trades_per_day.items():
        assert count <= 1, f"Found {count} trades on {day}, max allowed is 1"

def test_choch_gating(base_config):
    # A true test would inject a specific price sequence for CHoCH
    # Here we just verify the flag exists and doesn't crash
    df = generate_sample_data(50)
    engine = ASREngine(base_config)
    engine.run(df)
    assert hasattr(engine, 't_choch_conf')

def test_regime_gating(base_config):
    df = generate_sample_data(100)
    engine = ASREngine(base_config)
    engine.run(df)
    assert hasattr(engine, 'vol_regime')
    assert hasattr(engine, 'trend_regime')

def test_walk_forward():
    # Placeholder for walk_forward test if method is in another module
    pass

def test_monte_carlo():
    # Placeholder for monte_carlo test if method is in another module
    pass

def test_verdict():
    # Placeholder for verdict test if method is in another module
    pass
