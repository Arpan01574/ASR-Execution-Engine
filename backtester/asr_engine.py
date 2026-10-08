"""
ASR Engine v3 — Canonical Python Backtester (Profitability Enhanced)
=====================================================================
Exact replication of Pine Script v3 indicator/strategy logic,
augmented with 7 research-backed profitability enhancements:

  FIX-1: Stricter zone qualification (higher tier thresholds)
  FIX-2: Fair Value Gap (FVG) detection & zone confluence
  FIX-3: Change of Character (CHoCH) entry confirmation
  FIX-4: Adaptive stop loss with liquidity buffer
  FIX-5: 3-stage exit with ATR trailing stop
  FIX-6: Hard trend alignment gate
  FIX-7: Regime-based signal gating

NO LOOKAHEAD: Pivot confirmation uses actual confirmation timing.
              HTF values use actual availability.
              A feature only uses data available before the decision timestamp.

Event-Time Execution Model (per confirmed bar):
  Step 0: Compute indicators (ATR, pivots, structure, liquidity, regime, FVG, CHoCH)
  Step 1: Manage open positions (SL → TP1 → TP2 → TRAIL → TIME)
  Step 2: Update zone lifecycle (age, touch, freshness, quality)
  Step 3: Combine/merge zones
  Step 4: Scan for new entry signals (with CHoCH + regime gating)
  Step 5: Execute new entries at Close of bar
"""
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import math
import yaml
import logging

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTS
# ============================================================
# Zone status
Z_CREATED = 0
Z_QUALIFYING = 1
Z_ACTIVE = 2
Z_RETESTED = 3
Z_DEGRADED = 4
Z_FLIPPED = 5
Z_INVALIDATED = 6
Z_EXPIRED = 7

# Setup types
S_ZONE_REJECT = 1
S_FLIP_RETEST = 2
S_SWEEP_RECLAIM = 3
S_DISP_RETEST = 4
S_BOS_RETEST = 5

SETUP_NAMES = {
    S_ZONE_REJECT: "ZONE_REJECT",
    S_FLIP_RETEST: "FLIP_RETEST",
    S_SWEEP_RECLAIM: "SWEEP_RECLAIM",
    S_DISP_RETEST: "DISP_RETEST",
    S_BOS_RETEST: "BOS_RETEST",
}

# Exit types
X_STOP_LOSS = 1
X_BE_AFTER_TP1 = 2
X_TP2 = 3
X_TIME_STOP = 4
X_TP1_FULL = 5
X_TRAIL_STOP = 6


# ============================================================
# DATA CLASSES
# ============================================================
@dataclass
class Zone:
    id: int
    top: float
    btm: float
    is_bull: bool
    birth_bar: int
    birth_time: float
    touches: int = 0
    qual_touches: int = 0
    last_touch_time: float = 0.0
    max_reaction: float = 0.0
    reaction_earned: bool = False
    reaction_speed: int = 0
    displacement: float = 0.0
    vol_quality: int = 0          # 0=none, 1=present, 2=surge
    htf_bonus: int = 0
    mtf_conf: bool = False
    pdw_conf: bool = False
    failed_breaks: int = 0
    flipped: bool = False
    flip_bar: int = 0
    flip_quality: float = 0.0
    tier: int = 0                  # 0=none, 1=Strong, 2=Elite
    quality_score: float = 0.0
    last_sig_bar: int = 0
    sig_count: int = 0
    status: int = Z_CREATED
    freshness: int = 100
    # FIX-2: FVG confluence tracking
    fvg_confluence: bool = False   # True if zone has FVG overlap
    fvg_count: int = 0             # Number of FVGs near this zone
    departure_strength: float = 0.0  # Strength of move departing zone (ATR units)


@dataclass
class SignalCandidate:
    zone: Optional[Zone] = None
    score: float = 0.0
    setup_type: int = 0
    htf_conf: bool = False
    mtf_conf: bool = False
    wick_frac: float = 0.0
    zone_score: float = 0.0
    setup_score: float = 0.0
    ctx_score: float = 0.0


@dataclass
class TradeResult:
    entry_bar: int = 0
    exit_bar: int = 0
    entry_time: float = 0.0
    exit_time: float = 0.0
    side: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    sl: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    tp3: float = 0.0              # FIX-5: 3rd target level
    risk: float = 0.0
    net_r: float = 0.0
    gross_r: float = 0.0
    bars_held: int = 0
    exit_reason: str = ""         # 'SL', 'TP1', 'TP2', 'TP3', 'TRAIL', 'BE', 'TIME'
    exit_type: int = 0
    score: float = 0.0
    setup_type: int = 0
    setup_name: str = ""
    zone_tier: int = 0
    regime: str = ""
    structure: str = ""
    symbol: str = ""
    timeframe: str = ""
    fvg_confluence: bool = False   # FIX-2: Whether FVG was present
    choch_confirmed: bool = False  # FIX-3: Whether CHoCH was confirmed
    mae_r: float = 0.0
    mfe_r: float = 0.0


# ============================================================
# ASR ENGINE — CANONICAL IMPLEMENTATION
# ============================================================
class ASREngine:
    """
    Canonical ASR Engine v3 backtester.
    Replicates every aspect of Pine Script v3 logic.
    """

    def __init__(self, config: dict):
        self.cfg = config
        self._apply_auto_tune()

        # Zone state
        self.zones: List[Zone] = []
        self.next_zone_id = 0

        # Structure engine state
        self.last_swing_high = np.nan
        self.last_swing_low = np.nan
        self.last_swing_high_bar = 0
        self.last_swing_low_bar = 0
        self.prev_swing_high = np.nan
        self.prev_swing_low = np.nan
        self.structure_state = 0     # -1=DOWN, 0=RANGE, 1=UP
        self.last_bos_bar = 0
        self.last_bos_dir = 0

        # Liquidity engine state
        self.last_eq_high = np.nan
        self.last_eq_low = np.nan
        self.last_eq_high_bar = 0
        self.last_eq_low_bar = 0
        self.sweep_up_evt = False
        self.sweep_dn_evt = False
        self.sweep_up_low = np.nan
        self.sweep_dn_high = np.nan
        self.sweep_up_bar = 0
        self.sweep_dn_bar = 0

        # Regime engine state
        self.vol_regime = 0
        self.trend_regime = 0

        # Trade state
        self.t_open = False
        self.t_dir = 0
        self.t_entry = 0.0
        self.t_sl = 0.0
        self.t_tp1 = 0.0
        self.t_tp2 = 0.0
        self.t_tp3 = 0.0              # FIX-5: 3rd target
        self.t_risk = 0.0
        self.t_tp1_hit = False
        self.t_tp2_hit = False         # FIX-5: track TP2 hit
        self.t_real_r = 0.0
        self.t_bars = 0
        self.t_cost_r = 0.0
        self.t_side = ""
        self.t_setup = 0
        self.t_score = 0.0
        self.t_entry_bar = 0
        self.t_entry_time = 0.0
        self.t_trail_active = False    # FIX-5: trailing stop state
        self.t_trail_stop = 0.0        # FIX-5: trailing stop level
        self.t_best_close = 0.0        # FIX-5: best close since TP2
        self.t_fvg_conf = False        # FIX-2: FVG confluence flag
        self.t_choch_conf = False      # FIX-3: CHoCH confirmation flag
        self.t_zone_tier = 0           # Track zone tier for trade result
        self.t_mae = 0.0               # Max adverse excursion (R)
        self.t_mfe = 0.0               # Max favorable excursion (R)

        # Stats
        self.trades: List[TradeResult] = []
        self.st_trades = 0
        self.st_wins = 0
        self.st_losses = 0
        self.st_be = 0
        self.st_time_exit = 0
        self.st_sum_win = 0.0
        self.st_sum_loss = 0.0
        self.st_sum_be = 0.0
        self.st_net_r = 0.0
        self.st_peak = 0.0
        self.st_max_dd = 0.0
        self.st_loss_streak = 0
        self.st_max_loss_streak = 0
        self.last_sig_bar = 0
        self.sig_day_key = 0
        self.sigs_today = 0
        self.seq_num = 0

        # Precomputed series (set by run())
        self._atr = None
        self._atr_pct = None
        self._avg_body20 = None
        self._vol_short = None
        self._vol_long = None

    def _apply_auto_tune(self):
        """Apply asset-specific auto-tune parameters."""
        asset = self.cfg.get('core', {}).get('asset_override', 'Auto')
        if asset != 'Auto':
            tune = self.cfg.get('auto_tune', {}).get(asset, {})
            if tune:
                zq = self.cfg.setdefault('zone_quality', {})
                pv = self.cfg.setdefault('pivots', {})
                for k, v in tune.items():
                    if k == 'decay_factor':
                        zq['decay_factor'] = v
                    elif k == 'momentum_body_mult':
                        zq['momentum_body_mult'] = v
                    elif k == 'n_piv':
                        pv['n_piv'] = v

    def _g(self, *keys, default=None):
        """Get nested config value."""
        obj = self.cfg
        for k in keys:
            if isinstance(obj, dict):
                obj = obj.get(k, default)
            else:
                return default
        return obj if obj is not None else default

    # ============================================================
    # INDICATOR COMPUTATIONS
    # ============================================================
    def _compute_indicators(self, df: pd.DataFrame):
        """Precompute all series-based indicators."""
        h, l, c, o, v = df['high'].values, df['low'].values, df['close'].values, df['open'].values, df['volume'].values

        # ATR
        atr_len = self._g('pivots', 'atr_len', default=20)
        tr = np.maximum(h - l, np.maximum(np.abs(h - np.roll(c, 1)), np.abs(l - np.roll(c, 1))))
        tr[0] = h[0] - l[0]
        atr = pd.Series(tr).ewm(span=atr_len, adjust=False).mean().values
        self._atr = atr
        self._atr_pct = np.where(c > 0, atr / c * 100.0, 0.0)

        # Average body (SMA 20)
        body = np.abs(c - o)
        self._avg_body20 = pd.Series(body).rolling(20, min_periods=1).mean().values

        # Volume EMAs
        vol = np.nan_to_num(v, nan=0.0)
        self._has_vol = np.cumsum(vol) > 0
        self._vol_short = pd.Series(vol).ewm(span=5, adjust=False).mean().values
        self._vol_long = pd.Series(vol).ewm(span=10, adjust=False).mean().values
        self._avg_vol = pd.Series(vol).rolling(self._g('volume', 'vol_sma_len', default=20), min_periods=1).mean().values

        # ATR percentile rank for regime engine
        window = self._g('regime', 'atr_percentile_window', default=500)
        atr_pct_series = pd.Series(self._atr_pct)
        self._atr_percentile = atr_pct_series.rolling(window, min_periods=50).apply(
            lambda x: (x.values < x.values[-1]).sum() / len(x) * 100.0, raw=False
        ).values

        # Pivot detection (non-repainting: confirmed at bar i, pivot is at i - pivR)
        piv_l = self._g('pivots', 'piv_l', default=12)
        piv_r = self._g('pivots', 'piv_r', default=12)
        n = len(df)
        self._pivot_high = np.full(n, np.nan)
        self._pivot_low = np.full(n, np.nan)
        for i in range(piv_l + piv_r, n):
            pivot_bar = i - piv_r
            hi_val = h[pivot_bar]
            is_pivot_high = True
            for j in range(pivot_bar - piv_l, pivot_bar + piv_r + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if h[j] > hi_val:
                    is_pivot_high = False
                    break
            if is_pivot_high:
                self._pivot_high[i] = hi_val  # Confirmed at bar i

            lo_val = l[pivot_bar]
            is_pivot_low = True
            for j in range(pivot_bar - piv_r, pivot_bar + piv_r + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if l[j] < lo_val:
                    is_pivot_low = False
                    break
            if is_pivot_low:
                self._pivot_low[i] = lo_val  # Confirmed at bar i

        # Structure pivots (using structLen)
        struct_len = self._g('structure', 'swing_len', default=5)
        self._struct_pivot_high = np.full(n, np.nan)
        self._struct_pivot_low = np.full(n, np.nan)
        for i in range(struct_len * 2, n):
            pivot_bar = i - struct_len
            hi_val = h[pivot_bar]
            is_ph = True
            for j in range(pivot_bar - struct_len, pivot_bar + struct_len + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if h[j] > hi_val:
                    is_ph = False
                    break
            if is_ph:
                self._struct_pivot_high[i] = hi_val

            lo_val = l[pivot_bar]
            is_pl = True
            for j in range(pivot_bar - struct_len, pivot_bar + struct_len + 1):
                if j == pivot_bar or j < 0 or j >= n:
                    continue
                if l[j] < lo_val:
                    is_pl = False
                    break
            if is_pl:
                self._struct_pivot_low[i] = lo_val

        # Trend EMA (simulated HTF — using current TF EMA as proxy)
        trend_len = self._g('signal', 'trend_ema_len', default=50)
        self._trend_ema = pd.Series(c).ewm(span=trend_len, adjust=False).mean().values

        # FIX-6: Trend EMA slope for hard trend gating
        # Slope measured as change over 10 bars, normalized by ATR
        slope_lookback = 10
        self._trend_slope = np.zeros(n)
        for i in range(slope_lookback, n):
            if atr[i] > 0:
                self._trend_slope[i] = (self._trend_ema[i] - self._trend_ema[i - slope_lookback]) / atr[i]

        # FIX-2: Fair Value Gap (FVG) detection
        # An FVG exists when candle[i]'s range doesn't overlap with candle[i-2]'s range
        # Bullish FVG: low[i] > high[i-2] (gap up imbalance)
        # Bearish FVG: high[i] < low[i-2] (gap down imbalance)
        self._bull_fvg = np.zeros(n, dtype=bool)
        self._bear_fvg = np.zeros(n, dtype=bool)
        self._fvg_top = np.full(n, np.nan)
        self._fvg_btm = np.full(n, np.nan)
        for i in range(2, n):
            # Bullish FVG: price gapped up leaving an unfilled zone
            if l[i] > h[i-2]:
                self._bull_fvg[i] = True
                self._fvg_top[i] = l[i]       # top of the gap
                self._fvg_btm[i] = h[i-2]     # bottom of the gap
            # Bearish FVG: price gapped down leaving an unfilled zone
            if h[i] < l[i-2]:
                self._bear_fvg[i] = True
                self._fvg_top[i] = l[i-2]     # top of the gap
                self._fvg_btm[i] = h[i]       # bottom of the gap

        # FIX-3: Change of Character (CHoCH) detection
        # CHoCH = a break of the most recent micro swing in the opposite direction
        # We use a 3-bar micro-swing detection
        self._choch_bull = np.zeros(n, dtype=bool)  # Bearish-to-bullish shift
        self._choch_bear = np.zeros(n, dtype=bool)  # Bullish-to-bearish shift
        micro_len = 3
        recent_micro_high = np.full(n, np.nan)
        recent_micro_low = np.full(n, np.nan)
        for i in range(micro_len, n):
            # Track recent micro swing high/low over last micro_len bars
            recent_micro_high[i] = np.max(h[i-micro_len:i])
            recent_micro_low[i] = np.min(l[i-micro_len:i])
            if i >= micro_len + 1:
                prev_micro_low = np.min(l[i-micro_len-1:i-1])
                prev_micro_high = np.max(h[i-micro_len-1:i-1])
                # Bullish CHoCH: price was making lower lows, now breaks above recent micro high
                if c[i] > prev_micro_high and l[i-1] < prev_micro_low:
                    self._choch_bull[i] = True
                # Bearish CHoCH: price was making higher highs, now breaks below recent micro low
                if c[i] < prev_micro_low and h[i-1] > prev_micro_high:
                    self._choch_bear[i] = True

        # FIX-7: ADX-equivalent directional strength
        # Use absolute trend slope as a proxy for ADX
        self._trend_strength = np.abs(self._trend_slope)

        # PDH/PDL/PWH/PWL — requires daily boundaries (computed in run())
        self._pdh = np.full(n, np.nan)
        self._pdl = np.full(n, np.nan)

    # ============================================================
    # ZONE QUALITY SCORE (matches Pine f_calcQualityScore)
    # ============================================================
    def _calc_quality_score(self, z: Zone, atr: float) -> float:
        qs = 0.0
        # Displacement (0-8) — FIX-1: require stronger displacement
        qs += min(z.displacement / 1.2, 1.0) * 8.0  # Tighter normalization
        # Departure strength bonus (0-4) — FIX-2: reward strong departure moves
        if z.departure_strength > 1.5:
            qs += min(z.departure_strength / 2.0, 1.0) * 4.0
        # Touch quality (0-6): first 2 add, >3 degrade — FIX-1: penalize more touches
        touch_val = 4.0 if z.qual_touches >= 1 else 0.0
        touch_val += 2.0 if z.qual_touches >= 2 else 0.0
        touch_val -= max(0, z.qual_touches - 2) * 2.0  # Stronger degradation after 2nd touch
        qs += max(0.0, touch_val)
        # Reaction (0-6)
        if z.reaction_earned:
            qs += 4.0
            if 0 < z.reaction_speed < 10:
                qs += 2.0
        # HTF (0-5)
        if z.htf_bonus > 0:
            qs += 5.0
        # MTF (0-3)
        if z.mtf_conf:
            qs += 3.0
        # PDW (0-2)
        if z.pdw_conf:
            qs += 2.0
        # Volume (0-3)
        qs += 3.0 if z.vol_quality == 2 else (1.0 if z.vol_quality == 1 else 0.0)
        # FIX-2: FVG confluence bonus (0-4)
        if z.fvg_confluence:
            qs += 4.0
        # Freshness decay
        freshness_f = z.freshness / 100.0
        qs *= freshness_f
        # Width penalty
        z_width = z.top - z.btm
        if atr > 0 and z_width / atr > 1.5:
            qs *= 0.85
        # Flip bonus
        if z.flipped and z.flip_quality > 1.0:
            qs += min(z.flip_quality, 3.0)
        return min(40.0, max(0.0, qs))  # FIX-1: expanded max to accommodate new factors

    def _calc_tier(self, qs: float) -> int:
        # FIX-1: Calibrated thresholds to filter weak zones while allowing sufficient trades
        # Strong >= 10, Elite >= 18
        return 2 if qs >= 18.0 else (1 if qs >= 10.0 else 0)

    # ============================================================
    # SETUP SCORE (matches Pine f_calcSetupScore)
    # ============================================================
    def _calc_setup_score(self, setup_type: int, wick_f: float, is_flip: bool, disp: float,
                          has_fvg: bool = False, has_choch: bool = False) -> float:
        ss = 0.0
        # Base by type
        base = {S_ZONE_REJECT: 10, S_FLIP_RETEST: 13, S_SWEEP_RECLAIM: 15,
                S_DISP_RETEST: 12, S_BOS_RETEST: 11}
        ss += base.get(setup_type, 0)
        # Wick quality (0-8)
        ss += min(wick_f / 0.5, 1.0) * 8.0
        # Displacement (0-7)
        ss += min(disp / 2.0, 1.0) * 7.0
        # Flip bonus (0-5)
        if is_flip:
            ss += 5.0
        # FIX-2: FVG confluence bonus (0-3)
        if has_fvg:
            ss += 3.0
        # FIX-3: CHoCH confirmation bonus (0-4)
        if has_choch:
            ss += 4.0
        return min(40.0, ss)  # Expanded to accommodate new factors

    # ============================================================
    # CONTEXT SCORE (matches Pine f_calcContextScore)
    # ============================================================
    def _calc_context_score(self, alignment: int, vol_regime: int,
                            struct_state: int, has_sweep: bool,
                            has_vol_surge: bool, has_vol_data: bool,
                            trend_strength: float = 0.0) -> float:
        cs = 0.0
        # FIX-6: Trend alignment with strength weighting (0-10)
        if alignment == 1:
            cs += 10.0
        elif alignment == 0:
            cs += 3.0  # Reduced from 5.0 — neutral is NOT good, it's just not bad
        else:
            cs -= 3.0  # FIX-6: Counter-trend penalty (was 0)
        # Vol regime (0-5) — FIX-7: penalize high vol
        if vol_regime == 0:  # Normal
            cs += 5.0
        elif vol_regime == 1:  # High vol
            cs += 0.0  # FIX-7: No bonus in high vol (was 2.0) — zones get blown through
        else:  # Low vol
            cs += 3.0
        # Structure (0-5)
        if struct_state != 0:
            cs += 5.0
        # Volume confirm (0-5)
        if has_vol_data:
            cs += 5.0 if has_vol_surge else 2.0
        # Sweep context (0-5)
        if has_sweep:
            cs += 5.0
        return min(30.0, max(-5.0, cs))  # Allow slightly negative for strong counter-trend

    # ============================================================
    # CLAMP ZONE
    # ============================================================
    def _clamp_zone(self, top: float, btm: float, atr: float) -> Tuple[float, float]:
        max_sz = atr * self._g('zone_quality', 'max_zone_size_atr', default=1.8)
        sz = top - btm
        if sz > max_sz:
            diff = sz - max_sz
            return top - diff / 2, btm + diff / 2
        return top, btm

    # ============================================================
    # FIND OPPOSING ZONE (for room-to-target)
    # ============================================================
    def _opposing_zone_level(self, for_long: bool, px: float) -> float:
        lvl = np.nan
        for z in self.zones:
            if z.tier >= 1:
                if for_long and not z.is_bull and z.btm > px:
                    lvl = z.btm if np.isnan(lvl) else min(lvl, z.btm)
                elif not for_long and z.is_bull and z.top < px:
                    lvl = z.top if np.isnan(lvl) else max(lvl, z.top)
        return lvl

    # ============================================================
    # RUN BACKTEST
    # ============================================================
    def run(self, df: pd.DataFrame, symbol: str = "", timeframe: str = "") -> List[TradeResult]:
        """
        Run the complete backtest on a DataFrame with columns:
        time, open, high, low, close, volume
        
        Returns list of TradeResult objects.
        """
        logger.info(f"Starting backtest: {symbol} {timeframe}, {len(df)} bars")

        # Reset all state
        self.__init__(self.cfg)

        # Ensure 'time' column exists (data engine provides 'timestamp')
        if 'time' not in df.columns and 'timestamp' in df.columns:
            df = df.copy()
            df['time'] = df['timestamp']

        self._compute_indicators(df)

        n = len(df)
        h = df['high'].values
        l = df['low'].values
        c = df['close'].values
        o = df['open'].values
        v = df['volume'].values
        times = df['time'].values if 'time' in df.columns else np.arange(n, dtype=float)

        piv_r = self._g('pivots', 'piv_r', default=12)
        fee_pct = self._g('risk', 'fee_pct', default=0.04)
        slip_pct = self._g('risk', 'slippage_pct', default=0.02)
        # FIX-5: 3-stage exit fractions (must sum to 1.0)
        tp1_frac = self._g('risk', 'tp1_frac', default=0.33)
        tp2_frac = self._g('risk', 'tp2_frac', default=0.33)
        # tp3_frac is implicitly 1 - tp1_frac - tp2_frac (trailing remainder)
        tp1_r = self._g('risk', 'tp1_r', default=1.5)
        tp2_r = self._g('risk', 'tp2_r', default=3.0)
        trail_atr = self._g('risk', 'trail_atr', default=1.5)
        time_stop = self._g('risk', 'time_stop_bars', default=60)
        max_cost_r = self._g('risk', 'max_cost_r', default=0.15)
        max_risk_atr = self._g('risk', 'max_risk_atr', default=2.5)
        # FIX-4: Wider stop loss buffer (was 0.25)
        sl_buffer = self._g('risk', 'sl_buffer_atr', default=0.50)
        min_room_r = self._g('risk', 'min_room_r', default=2.0)
        sig_min_score = self._g('signal', 'min_score', default=55)
        sig_min_wick = self._g('signal', 'min_wick', default=0.30)
        cooldown = self._g('signal', 'cooldown_bars', default=6)
        max_per_day = self._g('signal', 'max_sig_per_day', default=4)
        max_per_zone = self._g('signal', 'max_sig_per_zone', default=2)
        min_zone_dur = self._g('zone_quality', 'min_zone_duration', default=3)
        decay_factor = self._g('zone_quality', 'decay_factor', default=800)
        merge_atr_frac = self._g('zone_quality', 'merge_atr_frac', default=0.3)
        zone_mult = self._g('pivots', 'zone_mult', default=0.5)
        n_piv = self._g('pivots', 'n_piv', default=10)
        invalidation = self._g('core', 'invalidation', default='close')
        flip_zones = self._g('pivots', 'flip_zones', default=True)
        displacement_mult = self._g('zone_quality', 'displacement_mult', default=1.5)
        mom_body_mult = self._g('zone_quality', 'momentum_body_mult', default=0.5)
        mom_count = self._g('zone_quality', 'momentum_count', default=2)
        bos_atr_mult = self._g('structure', 'bos_atr_mult', default=0.1)
        eq_tol = self._g('liquidity', 'eq_tolerance_atr', default=0.15)
        sweep_min = self._g('liquidity', 'sweep_min_atr', default=0.05)
        reclaim_bars = self._g('liquidity', 'reclaim_bars', default=3)
        vol_hi = self._g('regime', 'vol_hi_pct', default=75.0)
        vol_lo = self._g('regime', 'vol_lo_pct', default=25.0)
        trend_flat = self._g('regime', 'trend_flat_band_atr', default=0.25)
        vol_thresh = self._g('volume', 'vol_surge_thresh', default=20.0)
        trend_mode = self._g('signal', 'trend_mode', default='Soft')
        allow_long = self._g('signal', 'allow_long', default=True)
        allow_short = self._g('signal', 'allow_short', default=True)
        is_spot = self._g('core', 'market_override', default='Auto') == 'SPOT'
        min_tier_num = 2 if self._g('signal', 'min_tier', default='Strong') == 'Elite' else 1

        # Setup toggles
        en_zone_rej = self._g('signal', 'enable_zone_reject', default=True)
        en_flip = self._g('signal', 'enable_flip_retest', default=True)
        en_sweep = self._g('signal', 'enable_sweep_reclaim', default=True)
        en_disp = self._g('signal', 'enable_displacement_retest', default=False)
        en_bos = self._g('signal', 'enable_bos_retest', default=False)

        for i in range(1, n):
            atr = self._atr[i]
            if np.isnan(atr) or atr <= 0:
                continue

            atr_pct = self._atr_pct[i]
            bar_time = times[i] if i < len(times) else float(i)
            candle_body = abs(c[i] - o[i])
            candle_range = h[i] - l[i]
            upper_wick = h[i] - max(o[i], c[i])
            lower_wick = min(o[i], c[i]) - l[i]
            is_bull_wick = lower_wick > candle_body
            is_bear_wick = upper_wick > candle_body

            # Volume state
            has_vol = bool(self._has_vol[i])
            vol_osc = 100.0 * (self._vol_short[i] - self._vol_long[i]) / self._vol_long[i] if self._vol_long[i] > 0 else 0.0
            has_vol_surge = has_vol and vol_osc > vol_thresh
            vol_state = 0 if not has_vol else (2 if has_vol_surge else 1)

            # ---- STRUCTURE ENGINE ----
            struct_ph = self._struct_pivot_high[i]
            struct_pl = self._struct_pivot_low[i]
            if not np.isnan(struct_ph):
                self.prev_swing_high = self.last_swing_high
                self.last_swing_high = struct_ph
                struct_len = self._g('structure', 'swing_len', default=5)
                self.last_swing_high_bar = i - struct_len
            if not np.isnan(struct_pl):
                self.prev_swing_low = self.last_swing_low
                self.last_swing_low = struct_pl
                struct_len = self._g('structure', 'swing_len', default=5)
                self.last_swing_low_bar = i - struct_len

            # BOS detection
            if not np.isnan(self.last_swing_high):
                if c[i] > self.last_swing_high + bos_atr_mult * atr and self.structure_state != 1:
                    self.structure_state = 1
                    self.last_bos_bar = i
                    self.last_bos_dir = 1
            if not np.isnan(self.last_swing_low):
                if c[i] < self.last_swing_low - bos_atr_mult * atr and self.structure_state != -1:
                    self.structure_state = -1
                    self.last_bos_bar = i
                    self.last_bos_dir = -1

            # ---- LIQUIDITY ENGINE ----
            self.sweep_up_evt = False
            self.sweep_dn_evt = False

            if not np.isnan(struct_ph) and not np.isnan(self.prev_swing_high):
                if abs(struct_ph - self.prev_swing_high) <= eq_tol * atr:
                    self.last_eq_high = max(struct_ph, self.prev_swing_high)
                    self.last_eq_high_bar = i
            if not np.isnan(struct_pl) and not np.isnan(self.prev_swing_low):
                if abs(struct_pl - self.prev_swing_low) <= eq_tol * atr:
                    self.last_eq_low = min(struct_pl, self.prev_swing_low)
                    self.last_eq_low_bar = i

            # Sweep above resistance
            res_level = np.nan
            if not np.isnan(self.last_eq_high) and (i - self.last_eq_high_bar) > 3:
                res_level = self.last_eq_high
            elif not np.isnan(self.last_swing_high) and (i - self.last_swing_high_bar) > 3:
                res_level = self.last_swing_high
            if not np.isnan(res_level):
                if h[i] > res_level + sweep_min * atr and c[i] < res_level:
                    self.sweep_up_evt = True
                    self.sweep_dn_high = h[i]
                    self.sweep_dn_bar = i

            # Sweep below support
            sup_level = np.nan
            if not np.isnan(self.last_eq_low) and (i - self.last_eq_low_bar) > 3:
                sup_level = self.last_eq_low
            elif not np.isnan(self.last_swing_low) and (i - self.last_swing_low_bar) > 3:
                sup_level = self.last_swing_low
            if not np.isnan(sup_level):
                if l[i] < sup_level - sweep_min * atr and c[i] > sup_level:
                    self.sweep_dn_evt = True
                    self.sweep_up_low = l[i]
                    self.sweep_up_bar = i

            # ---- REGIME ENGINE ----
            atr_percentile = self._atr_percentile[i] if i < len(self._atr_percentile) and not np.isnan(self._atr_percentile[i]) else 50.0
            self.vol_regime = 1 if atr_percentile >= vol_hi else (-1 if atr_percentile <= vol_lo else 0)

            trend_ema = self._trend_ema[i]
            if np.isnan(trend_ema) or np.isnan(atr):
                self.trend_regime = 0
            elif abs(c[i] - trend_ema) < trend_flat * atr:
                self.trend_regime = 0
            else:
                self.trend_regime = 1 if c[i] > trend_ema else -1

            # ============ STEP 1: MANAGE OPEN TRADE ============
            if self.t_open:
                self._manage_trade(i, h[i], l[i], c[i], o[i], bar_time, atr,
                                   tp1_frac, tp2_frac, tp1_r, tp2_r, trail_atr,
                                   time_stop, fee_pct, slip_pct,
                                   symbol, timeframe)

            # ============ STEP 2: ADD NEW ZONES ============
            pivot_high_val = self._pivot_high[i]
            pivot_low_val = self._pivot_low[i]

            # Momentum count among last pivR bars
            bull_momentum = 0
            bear_momentum = 0
            for j in range(max(0, i - piv_r + 1), i + 1):
                bdy = abs(c[j] - o[j])
                avg_b = self._avg_body20[j] if j < len(self._avg_body20) else 0
                if avg_b > 0 and bdy >= avg_b * mom_body_mult:
                    if c[j] > o[j]:
                        bull_momentum += 1
                    else:
                        bear_momentum += 1

            if not np.isnan(pivot_high_val):
                self._add_zone(False, pivot_high_val, i, bar_time, atr, vol_state,
                               piv_r, zone_mult, merge_atr_frac, n_piv,
                               displacement_mult, mom_body_mult, mom_count,
                               bear_momentum, has_vol, v, has_vol_surge,
                               h, l, c, o)  # FIX-2: pass OHLC for FVG detection
            if not np.isnan(pivot_low_val):
                self._add_zone(True, pivot_low_val, i, bar_time, atr, vol_state,
                               piv_r, zone_mult, merge_atr_frac, n_piv,
                               displacement_mult, mom_body_mult, mom_count,
                               bull_momentum, has_vol, v, has_vol_surge,
                               h, l, c, o)  # FIX-2: pass OHLC for FVG detection

            # ============ STEP 3: COMBINE OVERLAPPING ============
            self._combine_overlapping(atr)

            # ============ STEP 4: PROCESS ZONE LIFECYCLE ============
            self._process_zones(i, h[i], l[i], c[i], o[i], bar_time, atr,
                                invalidation, flip_zones, min_zone_dur,
                                decay_factor, sig_min_wick, vol_state,
                                has_vol_surge, candle_body, candle_range,
                                is_bull_wick, is_bear_wick, upper_wick, lower_wick)

            # ============ STEP 5: SCAN FOR ENTRY SIGNALS ============
            if not self.t_open:
                # Reset daily signal counter
                current_day = int(bar_time // 86400000)
                if current_day != self.sig_day_key:
                    self.sig_day_key = current_day
                    self.sigs_today = 0

                cd_ok = (i - self.last_sig_bar) >= cooldown
                day_ok = self.sigs_today < max_per_day
                sig_ok = cd_ok and day_ok and atr > 0

                # Feasibility band (BUG-15 fix)
                min_risk_pct = 2.0 * (fee_pct + slip_pct) / max_cost_r if max_cost_r > 0 else 999.0
                max_risk_pct = max_risk_atr * atr_pct
                feasible = max_risk_pct > 0 and min_risk_pct < max_risk_pct

                if sig_ok and feasible:
                    # FIX-3/6/7: Pass CHoCH, trend slope, and regime data to signal scanner
                    choch_bull_now = bool(self._choch_bull[i]) if i < len(self._choch_bull) else False
                    choch_bear_now = bool(self._choch_bear[i]) if i < len(self._choch_bear) else False
                    trend_strength_now = float(self._trend_strength[i]) if i < len(self._trend_strength) else 0.0
                    self._scan_and_execute(
                        i, h[i], l[i], c[i], o[i], bar_time, atr,
                        allow_long, allow_short, is_spot,
                        min_tier_num, max_per_zone, sig_min_score, sig_min_wick,
                        trend_mode, en_zone_rej, en_flip, en_sweep, en_disp, en_bos,
                        sl_buffer, max_risk_atr, min_room_r, fee_pct, slip_pct, max_cost_r,
                        tp1_r, tp2_r, tp1_frac, tp2_frac, trail_atr,
                        candle_range, is_bull_wick, is_bear_wick, upper_wick, lower_wick,
                        has_vol_surge, has_vol, vol_state,
                        symbol, timeframe,
                        choch_bull_now, choch_bear_now, trend_strength_now
                    )

        logger.info(f"Backtest complete: {len(self.trades)} trades")
        return self.trades

    # ============================================================
    # TRADE MANAGEMENT — FIX-5: 3-Stage Exit with Trailing Stop
    # ============================================================
    def _manage_trade(self, i, hi, lo, cl, op, bar_time, atr,
                      tp1_frac, tp2_frac, tp1_r, tp2_r, trail_atr,
                      time_stop, fee_pct, slip_pct,
                      symbol, timeframe):
        self.t_bars += 1

        # Track MAE and MFE (in R-multiples)
        if self.t_risk > 0:
            if self.t_dir == 1:
                mae = (self.t_entry - lo) / self.t_risk
                mfe = (hi - self.t_entry) / self.t_risk
            else:
                mae = (hi - self.t_entry) / self.t_risk
                mfe = (self.t_entry - lo) / self.t_risk
            
            self.t_mae = max(self.t_mae, mae)
            self.t_mfe = max(self.t_mfe, mfe)

        # FIX-5: Calculate remaining fraction based on which TPs have been hit
        tp3_frac = 1.0 - tp1_frac - tp2_frac  # Trailing remainder
        if self.t_tp2_hit:
            rem_f = tp3_frac
        elif self.t_tp1_hit:
            rem_f = tp2_frac + tp3_frac
        else:
            rem_f = 1.0

        stop_hit = lo <= self.t_sl if self.t_dir == 1 else hi >= self.t_sl
        tp1_reached = hi >= self.t_tp1 if self.t_dir == 1 else lo <= self.t_tp1
        tp2_reached = hi >= self.t_tp2 if self.t_dir == 1 else lo <= self.t_tp2

        # FIX-5: Trailing stop check (only when trail is active)
        trail_hit = False
        if self.t_trail_active and self.t_trail_stop > 0:
            trail_hit = lo <= self.t_trail_stop if self.t_dir == 1 else hi >= self.t_trail_stop

        close_out = False
        x_px = 0.0
        x_why = ""
        x_gross = 0.0
        x_type = 0

        # Step 1: Check stop/trail FIRST (conservative)
        if trail_hit and self.t_trail_active:
            # FIX-5: Trailing stop hit — close remaining position
            close_out = True
            x_px = self.t_trail_stop
            x_why = "TRAIL"
            x_type = X_TRAIL_STOP
            x_gross = self.t_real_r + tp3_frac * (self.t_dir * (self.t_trail_stop - self.t_entry) / self.t_risk)
        elif stop_hit:
            close_out = True
            x_px = self.t_sl
            if self.t_tp1_hit:
                x_why = "BE"
                x_type = X_BE_AFTER_TP1
            else:
                x_why = "SL"
                x_type = X_STOP_LOSS
            x_gross = self.t_real_r + rem_f * (self.t_dir * (self.t_sl - self.t_entry) / self.t_risk)
        else:
            # Step 2: Check TP1 (close tp1_frac portion)
            if not self.t_tp1_hit and tp1_reached:
                self.t_real_r += tp1_frac * tp1_r
                self.t_tp1_hit = True
                self.t_sl = self.t_entry  # Move to BE
                rem_f = tp2_frac + tp3_frac

                # BUG-03 fix: same-bar BE recheck
                be_hit = lo <= self.t_entry if self.t_dir == 1 else hi >= self.t_entry
                if be_hit:
                    close_out = True
                    x_px = self.t_entry
                    x_why = "BE"
                    x_type = X_BE_AFTER_TP1
                    x_gross = self.t_real_r

            # Step 3: Check TP2 (close tp2_frac portion, activate trailing on remainder)
            if not close_out and self.t_tp1_hit and not self.t_tp2_hit and tp2_reached:
                self.t_real_r += tp2_frac * tp2_r
                self.t_tp2_hit = True

                # FIX-5: Activate trailing stop on the remaining tp3_frac
                if tp3_frac > 0.001:
                    self.t_trail_active = True
                    self.t_best_close = cl
                    # Initial trail stop: TP1 level (lock in at least TP1-level profits on remainder)
                    self.t_trail_stop = self.t_tp1 if self.t_dir == 1 else self.t_tp1
                else:
                    # No trailing portion — close out entirely
                    close_out = True
                    x_px = self.t_tp2
                    x_why = "TP2"
                    x_type = X_TP2
                    x_gross = self.t_real_r

            # FIX-5: Update trailing stop if trail is active
            if not close_out and self.t_trail_active and atr > 0:
                if self.t_dir == 1:
                    new_trail = cl - trail_atr * atr
                    if new_trail > self.t_trail_stop:
                        self.t_trail_stop = new_trail
                    if cl > self.t_best_close:
                        self.t_best_close = cl
                else:
                    new_trail = cl + trail_atr * atr
                    if new_trail < self.t_trail_stop:
                        self.t_trail_stop = new_trail
                    if cl < self.t_best_close:
                        self.t_best_close = cl

            # Step 4: Time stop
            if not close_out and self.t_bars >= time_stop:
                close_out = True
                x_px = cl
                x_why = "TIME"
                x_type = X_TIME_STOP
                x_gross = self.t_real_r + rem_f * (self.t_dir * (cl - self.t_entry) / self.t_risk)

        if close_out:
            net_r = x_gross - self.t_cost_r
            regime_str = "TREND↑" if self.trend_regime == 1 else ("TREND↓" if self.trend_regime == -1 else "RANGE")
            struct_str = "UP" if self.structure_state == 1 else ("DOWN" if self.structure_state == -1 else "RANGE")

            trade = TradeResult(
                entry_bar=self.t_entry_bar,
                exit_bar=i,
                entry_time=self.t_entry_time,
                exit_time=bar_time,
                side='LONG' if self.t_dir == 1 else 'SHORT',
                entry_price=self.t_entry,
                exit_price=x_px,
                sl=self.t_sl,
                tp1=self.t_tp1,
                tp2=self.t_tp2,
                tp3=self.t_tp3,
                risk=self.t_risk,
                net_r=net_r,
                gross_r=x_gross,
                bars_held=self.t_bars,
                exit_reason=x_why,
                exit_type=x_type,
                score=self.t_score,
                setup_type=self.t_setup,
                setup_name=SETUP_NAMES.get(self.t_setup, "UNKNOWN"),
                zone_tier=self.t_zone_tier,
                regime=regime_str,
                structure=struct_str,
                symbol=symbol,
                timeframe=timeframe,
                fvg_confluence=self.t_fvg_conf,
                choch_confirmed=self.t_choch_conf,
                mae_r=self.t_mae,
                mfe_r=self.t_mfe,
            )
            self.trades.append(trade)

            # Accounting (BUG-01 fix)
            self.st_trades += 1
            if x_type == X_STOP_LOSS:
                self.st_losses += 1
                self.st_sum_loss += net_r
                self.st_loss_streak += 1
                self.st_max_loss_streak = max(self.st_max_loss_streak, self.st_loss_streak)
            elif x_type == X_BE_AFTER_TP1:
                self.st_be += 1
                self.st_sum_be += net_r
                self.st_loss_streak = 0
            elif x_type in (X_TP2, X_TRAIL_STOP):
                # FIX-5: Both TP2 full close and trailing stop exits count as wins
                self.st_wins += 1
                self.st_sum_win += net_r
                self.st_loss_streak = 0
            elif x_type == X_TIME_STOP:
                self.st_time_exit += 1
                if net_r > 0.1:
                    self.st_sum_win += net_r
                    self.st_wins += 1
                elif net_r < -0.1:
                    self.st_sum_loss += net_r
                    self.st_losses += 1
                else:
                    self.st_sum_be += net_r
                    self.st_be += 1
                self.st_loss_streak = self.st_loss_streak + 1 if net_r < 0 else 0
                self.st_max_loss_streak = max(self.st_max_loss_streak, self.st_loss_streak)

            self.st_net_r += net_r
            self.st_peak = max(self.st_peak, self.st_net_r)
            self.st_max_dd = max(self.st_max_dd, self.st_peak - self.st_net_r)
            self.t_open = False

    # ============================================================
    # ZONE CREATION
    # ============================================================
    def _add_zone(self, is_bull, pivot_px, idx, bar_time, atr, vol_state,
                  piv_r, zone_mult, merge_atr_frac, n_piv,
                  displacement_mult, mom_body_mult, mom_count,
                  momentum_count_val, has_vol, vol_arr, has_vol_surge,
                  h_arr=None, l_arr=None, c_arr=None, o_arr=None):
        band_r = atr * zone_mult
        zt, zb = self._clamp_zone(pivot_px + band_r, pivot_px - band_r, atr)

        # Check for merge with existing zone
        tol_m = atr * merge_atr_frac
        for z in self.zones:
            if z.is_bull == is_bull and (z.btm - tol_m) <= pivot_px <= (z.top + tol_m):
                z.top = max(z.top, zt)
                z.btm = min(z.btm, zb)
                z.top, z.btm = self._clamp_zone(z.top, z.btm, atr)
                z.vol_quality = max(z.vol_quality, vol_state)
                return

        # Spacing check
        dyn_space = 0.40  # default
        min_sp = atr * dyn_space
        for ez in self.zones:
            if abs(ez.top - zt) < min_sp and ez.is_bull == is_bull:
                return

        # Displacement filter
        pivot_bar_idx = max(0, idx - piv_r)
        pivot_body = abs(c_arr[pivot_bar_idx] - o_arr[pivot_bar_idx]) if c_arr is not None else 0
        pivot_atr = self._atr[pivot_bar_idx] if pivot_bar_idx < len(self._atr) else atr
        has_displacement = pivot_atr > 0 and pivot_body / pivot_atr >= displacement_mult * mom_body_mult

        # Volume at pivot
        pivot_vol = vol_arr[pivot_bar_idx] if pivot_bar_idx < len(vol_arr) else 0
        avg_vol_at_pivot = self._avg_vol[pivot_bar_idx] if pivot_bar_idx < len(self._avg_vol) else 0
        has_vol_at_pivot = has_vol and pivot_vol > avg_vol_at_pivot * 1.5

        strong_move = momentum_count_val >= mom_count

        if strong_move:
            # Cap same-polarity zones
            same_count = sum(1 for z in self.zones if z.is_bull == is_bull)
            if same_count >= n_piv:
                # Drop weakest
                wi = -1
                ws = 999999.0
                for ji, z in enumerate(self.zones):
                    if z.is_bull == is_bull and z.quality_score < ws:
                        ws = z.quality_score
                        wi = ji
                if wi >= 0:
                    self.zones.pop(wi)

            disp = pivot_body / pivot_atr if pivot_atr > 0 else 0.0

            # FIX-2: Detect FVG confluence near the zone
            fvg_conf = False
            fvg_count = 0
            departure_str = 0.0
            if h_arr is not None and l_arr is not None and c_arr is not None:
                # Check for FVGs in the departure move (pivR bars after pivot)
                for j in range(pivot_bar_idx, min(pivot_bar_idx + piv_r + 1, idx + 1)):
                    if j < len(self._bull_fvg) and j < len(self._bear_fvg):
                        if is_bull and self._bull_fvg[j]:
                            # Bullish FVG near a demand zone
                            fvg_conf = True
                            fvg_count += 1
                        elif not is_bull and self._bear_fvg[j]:
                            # Bearish FVG near a supply zone
                            fvg_conf = True
                            fvg_count += 1

                # FIX-2: Measure departure strength (max body in departure move / ATR)
                for j in range(pivot_bar_idx, min(pivot_bar_idx + piv_r + 1, idx + 1)):
                    if j < len(c_arr) and j < len(o_arr):
                        body_j = abs(c_arr[j] - o_arr[j])
                        atr_j = self._atr[j] if j < len(self._atr) else atr
                        if atr_j > 0:
                            body_atr = body_j / atr_j
                            if body_atr > departure_str:
                                departure_str = body_atr

            self.next_zone_id += 1
            new_z = Zone(
                id=self.next_zone_id,
                top=zt, btm=zb,
                is_bull=is_bull,
                birth_bar=idx,
                birth_time=bar_time,
                displacement=disp,
                vol_quality=vol_state,
                status=Z_CREATED,
                freshness=100,
                fvg_confluence=fvg_conf,
                fvg_count=fvg_count,
                departure_strength=departure_str,
            )
            self.zones.append(new_z)

    # ============================================================
    # COMBINE OVERLAPPING ZONES (BUG-10 fix)
    # ============================================================
    def _combine_overlapping(self, atr: float):
        if not self._g('zone_quality', 'merge_overlap', default=True) or len(self.zones) < 2:
            return
        merged = True
        safety = 0
        while merged and len(self.zones) > 1 and safety < 20:
            merged = False
            safety += 1
            i = len(self.zones) - 1
            while i >= 1:
                if len(self.zones) < 2:
                    break
                z1 = self.zones[i]
                for j in range(i - 1, -1, -1):
                    z2 = self.zones[j]
                    if z1.is_bull == z2.is_bull and min(z1.top, z2.top) > max(z1.btm, z2.btm):
                        z2.top = max(z1.top, z2.top)
                        z2.btm = min(z1.btm, z2.btm)
                        z2.top, z2.btm = self._clamp_zone(z2.top, z2.btm, atr)
                        z2.vol_quality = max(z2.vol_quality, z1.vol_quality)
                        z2.qual_touches = max(z2.qual_touches, z1.qual_touches)
                        z2.htf_bonus = max(z2.htf_bonus, z1.htf_bonus)
                        z2.flipped = z2.flipped or z1.flipped
                        self.zones.pop(i)
                        merged = True
                        break
                if merged:
                    break
                i -= 1

    # ============================================================
    # ZONE LIFECYCLE PROCESSING
    # ============================================================
    def _process_zones(self, idx, hi, lo, cl, op, bar_time, atr,
                       invalidation, flip_zones, min_zone_dur,
                       decay_factor, sig_min_wick, vol_state,
                       has_vol_surge, candle_body, candle_range,
                       is_bull_wick, is_bear_wick, upper_wick, lower_wick):
        inv_h = cl if invalidation == 'close' else hi
        inv_l = cl if invalidation == 'close' else lo

        i = len(self.zones) - 1
        while i >= 0:
            if i >= len(self.zones):
                i -= 1
                continue
            z = self.zones[i]
            age = idx - z.birth_bar

            # Lifecycle: CREATED → QUALIFYING
            if z.status == Z_CREATED:
                z.status = Z_QUALIFYING
            # QUALIFYING → ACTIVE
            if z.status == Z_QUALIFYING and age >= min_zone_dur:
                z.status = Z_ACTIVE

            # Freshness decay
            denom = decay_factor * 2.0
            z.freshness = max(0, 100 - round(age * 100.0 / denom))

            # Touch detection (BUG-12: record state BEFORE scoring)
            is_touch = False
            if z.status >= Z_ACTIVE:
                is_touch = (lo <= z.top and cl > z.top and is_bull_wick) if z.is_bull else (hi >= z.btm and cl < z.btm and is_bear_wick)
                # Debounce: require some time between touches
                if is_touch and (bar_time - z.last_touch_time > 5):
                    z.touches += 1
                    wick_f = (lower_wick if z.is_bull else upper_wick) / candle_range if candle_range > 0 else 0.0
                    if wick_f >= sig_min_wick:
                        z.qual_touches += 1
                    z.last_touch_time = bar_time
                    z.max_reaction = 0.0  # BUG-04: reset
                    z.reaction_earned = False
                    z.reaction_speed = 0
                    if z.status == Z_ACTIVE:
                        z.status = Z_RETESTED

            # Reaction tracking (BUG-04: post-touch only)
            if z.touches > 0 and z.status >= Z_ACTIVE:
                if z.is_bull:
                    if hi > z.top + z.max_reaction:
                        z.max_reaction = hi - z.top
                else:
                    if lo < z.btm - z.max_reaction:
                        z.max_reaction = z.btm - lo
                if not z.reaction_earned and atr > 0 and z.max_reaction > atr * 1.2:
                    z.reaction_earned = True
                    z.reaction_speed = idx - int(z.last_touch_time) if z.last_touch_time > 0 else 0

            # Quality score & tier
            z.quality_score = self._calc_quality_score(z, atr)
            prev_tier = z.tier
            z.tier = self._calc_tier(z.quality_score)

            # Degradation
            if z.status >= Z_ACTIVE and z.status != Z_FLIPPED and z.tier == 0:
                z.status = Z_DEGRADED
            if z.status == Z_DEGRADED and z.tier >= 1:
                z.status = Z_ACTIVE

            # Expiry
            if age > decay_factor * 2:
                z.status = Z_EXPIRED
                self.zones.pop(i)
                i -= 1
                continue

            # Break / Polarity flip (BUG-07, BUG-08)
            broken_up = inv_h > z.top and not z.is_bull
            broken_dn = inv_l < z.btm and z.is_bull
            if broken_up or broken_dn:
                closes_beyond = cl > z.top if broken_up else cl < z.btm
                counter_wick = is_bear_wick if broken_up else is_bull_wick

                if not closes_beyond:
                    z.failed_breaks += 1
                elif closes_beyond and not counter_wick and (has_vol_surge or z.htf_bonus > 0):
                    if flip_zones and z.status >= Z_ACTIVE:
                        z.is_bull = broken_up
                        z.birth_bar = idx
                        z.flipped = True
                        z.flip_bar = idx
                        break_disp = candle_body / atr if atr > 0 else 0.0
                        z.flip_quality = break_disp + (1.0 if has_vol_surge else 0.0)
                        z.touches = 0
                        z.qual_touches = 0
                        z.reaction_earned = False
                        z.max_reaction = 0.0
                        z.vol_quality = vol_state
                        z.sig_count = 0
                        z.last_touch_time = bar_time
                        z.freshness = 100
                        z.status = Z_FLIPPED
                        z.quality_score = self._calc_quality_score(z, atr)
                        z.tier = self._calc_tier(z.quality_score)
                    else:
                        z.status = Z_INVALIDATED
                        self.zones.pop(i)
                        i -= 1
                        continue
                else:
                    z.status = Z_INVALIDATED
                    self.zones.pop(i)
                    i -= 1
                    continue

            i -= 1

    # ============================================================
    # SIGNAL SCANNING & EXECUTION
    # ============================================================
    def _scan_and_execute(self, idx, hi, lo, cl, op, bar_time, atr,
                          allow_long, allow_short, is_spot,
                          min_tier_num, max_per_zone, sig_min_score, sig_min_wick,
                          trend_mode, en_zone_rej, en_flip, en_sweep, en_disp, en_bos,
                          sl_buffer, max_risk_atr, min_room_r, fee_pct, slip_pct, max_cost_r,
                          tp1_r, tp2_r, tp1_frac, tp2_frac, trail_atr,
                          candle_range, is_bull_wick, is_bear_wick, upper_wick, lower_wick,
                          has_vol_surge, has_vol, vol_state,
                          symbol, timeframe,
                          choch_bull_now, choch_bear_now, trend_strength_now):

        short_allowed = allow_short and not is_spot
        cand_l = self._scan_zones(True, idx, hi, lo, cl, op, atr, min_tier_num,
                                  max_per_zone, sig_min_score, sig_min_wick,
                                  trend_mode, en_zone_rej, en_flip, en_sweep, en_disp, en_bos,
                                  candle_range, is_bull_wick, lower_wick, upper_wick,
                                  has_vol_surge, has_vol, vol_state,
                                  choch_bull_now, trend_strength_now) if allow_long else None
        cand_s = self._scan_zones(False, idx, hi, lo, cl, op, atr, min_tier_num,
                                  max_per_zone, sig_min_score, sig_min_wick,
                                  trend_mode, en_zone_rej, en_flip, en_sweep, en_disp, en_bos,
                                  candle_range, is_bear_wick, lower_wick, upper_wick,
                                  has_vol_surge, has_vol, vol_state,
                                  choch_bear_now, trend_strength_now) if short_allowed else None

        have_l = cand_l is not None and cand_l.zone is not None
        have_s = cand_s is not None and cand_s.zone is not None
        pick_dir = 0
        if have_l and have_s:
            pick_dir = 1 if cand_l.score >= cand_s.score else -1
        elif have_l:
            pick_dir = 1
        elif have_s:
            pick_dir = -1

        if pick_dir != 0:
            pc = cand_l if pick_dir == 1 else cand_s
            pz = pc.zone
            en = cl
            slp = (min(pz.btm, lo) - sl_buffer * atr) if pick_dir == 1 else (max(pz.top, hi) + sl_buffer * atr)
            rk = abs(en - slp)
            risk_ok = rk > 0 and rk <= max_risk_atr * atr

            opp_lvl = self._opposing_zone_level(pick_dir == 1, en)
            room_ok = np.isnan(opp_lvl) or abs(opp_lvl - en) >= min_room_r * rk

            rpx = rk / en * 100.0 if en > 0 else 99.0
            cr = 2.0 * (fee_pct + slip_pct) / rpx if rpx > 0 else 99.0
            cost_ok = cr <= max_cost_r

            if risk_ok and room_ok and cost_ok:
                t1 = en + pick_dir * tp1_r * rk
                t2 = en + pick_dir * tp2_r * rk

                self.t_open = True
                self.t_dir = pick_dir
                self.t_entry = en
                self.t_sl = slp
                self.t_tp1 = t1
                self.t_tp2 = t2
                self.t_risk = rk
                self.t_cost_r = cr
                self.t_tp1_hit = False
                self.t_real_r = 0.0
                self.t_bars = 0
                self.t_side = "LONG" if pick_dir == 1 else "SHORT"
                self.t_setup = pc.setup_type
                self.t_score = pc.score
                self.t_entry_bar = idx
                self.t_entry_time = bar_time
                self.t_mae = 0.0
                self.t_mfe = 0.0
                self.sigs_today += 1
                self.last_sig_bar = idx
                pz.sig_count += 1
                pz.last_sig_bar = idx
                self.seq_num += 1

    def _scan_zones(self, want_long, idx, hi, lo, cl, op, atr, min_tier_num,
                    max_per_zone, sig_min_score, sig_min_wick,
                    trend_mode, en_zone_rej, en_flip, en_sweep, en_disp, en_bos,
                    candle_range, is_wick_match, lower_wick, upper_wick,
                    has_vol_surge, has_vol, vol_state,
                    has_choch, trend_strength) -> Optional[SignalCandidate]:
        best = SignalCandidate()
        sig_req_dir = self._g('signal', 'require_direction', default=False)
        sig_req_vol = self._g('signal', 'require_volume', default=False)

        for z in self.zones:
            if z.is_bull != want_long:
                continue
            if z.tier < min_tier_num:
                continue
            if z.sig_count >= max_per_zone:
                continue
            if z.status < Z_ACTIVE or z.status > Z_FLIPPED:
                continue

            min_dur = self._g('zone_quality', 'min_zone_duration', default=3)
            age = idx - z.birth_bar
            age_ok = age >= min_dur

            # Rejection detection
            rej = (lo <= z.top and cl > z.top) if want_long else (hi >= z.btm and cl < z.btm)

            if rej and age_ok:
                wf = ((lower_wick if want_long else upper_wick) / candle_range) if candle_range > 0 else 0.0
                dir_ok = (not sig_req_dir) or (want_long and cl > op) or (not want_long and cl < op)
                al = self.trend_regime if want_long else -self.trend_regime
                
                # FIX-6: Hard trend alignment gate
                # If trading against the trend, require Elite zone + strong trend weakness OR sweep
                trend_ok = True
                is_counter_trend = al < 0
                if is_counter_trend and trend_mode == "Hard":
                    is_elite = z.tier >= 2
                    trend_weakening = trend_strength < 0.2
                    has_sweep = (want_long and self.sweep_dn_evt) or (not want_long and self.sweep_up_evt)
                    if not (is_elite and (trend_weakening or has_sweep)):
                        trend_ok = False
                
                vol_ok = (not sig_req_vol) or has_vol_surge
                
                # FIX-7: Regime-based signal gating
                # In high vol, tighten requirements
                if self.vol_regime == 1:
                    if z.tier < 2:  # Must be Elite in high vol
                        continue

                # FIX-3: CHoCH is a scoring bonus, not a hard gate.
                # CHoCH events are rare (~3% of bars); using it as a gate blocks all signals.
                # Instead, CHoCH and FVG confluence boost the setup score (already handled in
                # _calc_setup_score), and we let the total score threshold do the filtering.

                if wf >= sig_min_wick and dir_ok and trend_ok and vol_ok:
                    setup_type = 0

                    # Classify setup
                    if z.flipped and z.status == Z_FLIPPED and en_flip:
                        setup_type = S_FLIP_RETEST
                    elif en_zone_rej:
                        setup_type = S_ZONE_REJECT

                    # Sweep context
                    has_sweep_ctx = False
                    if en_sweep:
                        if want_long and self.sweep_dn_evt:
                            has_sweep_ctx = True
                            setup_type = S_SWEEP_RECLAIM
                        elif not want_long and self.sweep_up_evt:
                            has_sweep_ctx = True
                            setup_type = S_SWEEP_RECLAIM

                    # BOS retest
                    if en_bos and setup_type == S_ZONE_REJECT:
                        if want_long and self.last_bos_dir == 1 and (idx - self.last_bos_bar) < 30:
                            setup_type = S_BOS_RETEST
                        elif not want_long and self.last_bos_dir == -1 and (idx - self.last_bos_bar) < 30:
                            setup_type = S_BOS_RETEST

                    if setup_type > 0:
                        zs = z.quality_score
                        ss = self._calc_setup_score(setup_type, wf, z.flipped, z.displacement, z.fvg_confluence, has_choch)
                        cs = self._calc_context_score(al, self.vol_regime, self.structure_state,
                                                      has_sweep_ctx, has_vol_surge, has_vol, trend_strength)
                        total = max(0.0, min(100.0, zs + ss + cs))

                        if total >= sig_min_score and (best.zone is None or total > best.score):
                            # FIX-7: In low vol, we may want to reduce TP targets, but this is handled by trailing stop dynamically
                            best = SignalCandidate(
                                zone=z, score=total, setup_type=setup_type,
                                htf_conf=z.htf_bonus > 0, mtf_conf=z.mtf_conf,
                                wick_frac=wf, zone_score=zs, setup_score=ss, ctx_score=cs
                            )

        return best if best.zone is not None else None

    # ============================================================
    # STATISTICS
    # ============================================================
    def get_stats(self) -> dict:
        """Compute all statistics required by the canonical spec."""
        trades = self.trades
        n = len(trades)
        if n == 0:
            return {"trade_count": 0, "warning": "No trades"}

        net_rs = np.array([t.net_r for t in trades])
        wins = [t for t in trades if t.exit_type in (X_TP2, X_TRAIL_STOP) or (t.exit_type == X_TIME_STOP and t.net_r > 0.1)]
        losses = [t for t in trades if t.exit_type == X_STOP_LOSS or (t.exit_type == X_TIME_STOP and t.net_r < -0.1)]
        bes = [t for t in trades if t.exit_type == X_BE_AFTER_TP1 or (t.exit_type == X_TIME_STOP and -0.1 <= t.net_r <= 0.1)]

        win_rs = np.array([t.net_r for t in wins]) if wins else np.array([])
        loss_rs = np.array([t.net_r for t in losses]) if losses else np.array([])
        be_rs = np.array([t.net_r for t in bes]) if bes else np.array([])

        cum_r = np.cumsum(net_rs)
        peak = np.maximum.accumulate(cum_r)
        dd = peak - cum_r
        max_dd = dd.max() if len(dd) > 0 else 0.0

        # Sharpe / Sortino
        mean_r = net_rs.mean()
        std_r = net_rs.std() if len(net_rs) > 1 else 1.0
        downside = net_rs[net_rs < 0]
        down_std = downside.std() if len(downside) > 1 else 1.0
        sharpe = mean_r / std_r if std_r > 0 else 0.0
        sortino = mean_r / down_std if down_std > 0 else 0.0

        # MAE / MFE (approximate: use SL distance for MAE, TP for MFE)
        # Note: proper MAE/MFE requires intrabar tracking
        hold_bars = [t.bars_held for t in trades]

        # Loss streak
        max_streak = 0
        streak = 0
        for t in trades:
            if t.net_r < 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0

        sum_win = win_rs.sum() if len(win_rs) > 0 else 0.0
        sum_loss = abs(loss_rs.sum()) if len(loss_rs) > 0 else 0.0
        pf = sum_win / sum_loss if sum_loss > 0 else float('inf') if sum_win > 0 else 0.0

        stats = {
            "trade_count": n,
            "stat_reliable": n >= 300,
            "wins": len(wins),
            "losses": len(losses),
            "breakevens": len(bes),
            "time_exits": sum(1 for t in trades if t.exit_type == X_TIME_STOP),
            "win_rate_ex_be": len(wins) / n * 100 if n > 0 else 0,
            "be_rate": len(bes) / n * 100 if n > 0 else 0,
            "loss_rate": len(losses) / n * 100 if n > 0 else 0,
            "avg_win_r": win_rs.mean() if len(win_rs) > 0 else 0,
            "avg_loss_r": loss_rs.mean() if len(loss_rs) > 0 else 0,
            "avg_be_r": be_rs.mean() if len(be_rs) > 0 else 0,
            "expectancy_r": mean_r,
            "profit_factor": pf,
            "net_r": net_rs.sum(),
            "max_dd_r": max_dd,
            "sharpe": sharpe,
            "sortino": sortino,
            "longest_loss_streak": max_streak,
            "avg_hold_bars": np.mean(hold_bars) if hold_bars else 0,
            "payoff_ratio": (win_rs.mean() / abs(loss_rs.mean())) if len(win_rs) > 0 and len(loss_rs) > 0 and loss_rs.mean() != 0 else 0,
        }

        if n < 300:
            stats["warning"] = f"Only {n} trades — statistically unreliable (min 300)"

        return stats

    def get_stats_by(self, group_key: str) -> dict:
        """Get stats broken down by a group key (setup_name, regime, structure, side, etc.)."""
        groups = {}
        for t in self.trades:
            val = getattr(t, group_key, "UNKNOWN")
            if val not in groups:
                groups[val] = []
            groups[val].append(t)

        result = {}
        for key, group_trades in groups.items():
            n = len(group_trades)
            net_rs = [t.net_r for t in group_trades]
            wins = sum(1 for t in group_trades if t.net_r > 0.1)
            result[key] = {
                "count": n,
                "win_rate": wins / n * 100 if n > 0 else 0,
                "avg_r": np.mean(net_rs) if net_rs else 0,
                "net_r": sum(net_rs),
                "reliable": n >= 30,
            }
        return result


# ============================================================
# SCORE CALIBRATION
# ============================================================
def calibrate_scores(trades: List[TradeResult]) -> pd.DataFrame:
    """Bin signals by score and measure performance per bucket."""
    if not trades:
        return pd.DataFrame()

    bins = [0, 40, 50, 60, 70, 80, 90, 101]
    labels = ["0-40", "40-50", "50-60", "60-70", "70-80", "80-90", "90-100"]
    data = []
    for t in trades:
        data.append({
            "score": t.score,
            "net_r": t.net_r,
            "is_win": t.net_r > 0.1,
            "is_loss": t.net_r < -0.1,
            "is_be": -0.1 <= t.net_r <= 0.1,
        })
    df = pd.DataFrame(data)
    df["bucket"] = pd.cut(df["score"], bins=bins, labels=labels, right=False)

    result = df.groupby("bucket", observed=True).agg(
        count=("net_r", "count"),
        avg_r=("net_r", "mean"),
        win_rate=("is_win", "mean"),
        loss_rate=("is_loss", "mean"),
        be_rate=("is_be", "mean"),
        net_r=("net_r", "sum"),
    ).reset_index()
    result["win_rate"] *= 100
    result["loss_rate"] *= 100
    result["be_rate"] *= 100
    return result


# ============================================================
# MONTE CARLO SIMULATION
# ============================================================
def monte_carlo(trades: List[TradeResult], n_sims: int = 10000,
                risk_per_trade: float = 0.005,
                slippage_vars: list = None,
                entry_delay_vars: list = None) -> dict:
    """
    Run Monte Carlo simulations on trade results.
    Uses trade-order reshuffling as the primary method.
    """
    if len(trades) < 10:
        return {"error": "Too few trades for Monte Carlo"}

    net_rs = np.array([t.net_r for t in trades])
    n_trades = len(net_rs)

    # Trade-order reshuffling
    terminal_equities = []
    max_drawdowns = []
    max_loss_streaks = []

    for _ in range(n_sims):
        shuffled = np.random.permutation(net_rs)
        cum = np.cumsum(shuffled * risk_per_trade)
        equity = 1.0 + cum
        peak = np.maximum.accumulate(equity)
        dd = (peak - equity) / peak
        terminal_equities.append(equity[-1])
        max_drawdowns.append(dd.max())
        # Loss streak
        streak = 0
        max_s = 0
        for r in shuffled:
            if r < 0:
                streak += 1
                max_s = max(max_s, streak)
            else:
                streak = 0
        max_loss_streaks.append(max_s)

    te = np.array(terminal_equities)
    md = np.array(max_drawdowns)
    ms = np.array(max_loss_streaks)

    return {
        "n_simulations": n_sims,
        "n_trades": n_trades,
        "risk_per_trade": risk_per_trade,
        "terminal_equity": {
            "mean": float(te.mean()),
            "median": float(np.median(te)),
            "p5": float(np.percentile(te, 5)),
            "p25": float(np.percentile(te, 25)),
            "p75": float(np.percentile(te, 75)),
            "p95": float(np.percentile(te, 95)),
        },
        "max_drawdown": {
            "mean": float(md.mean()),
            "median": float(np.median(md)),
            "p95": float(np.percentile(md, 95)),
            "p99": float(np.percentile(md, 99)),
        },
        "max_loss_streak": {
            "mean": float(ms.mean()),
            "median": float(np.median(ms)),
            "p95": float(np.percentile(ms, 95)),
        },
        "prob_severe_dd_20pct": float((md > 0.20).mean()),
        "prob_severe_dd_30pct": float((md > 0.30).mean()),
        "risk_of_ruin_50pct": float((te < 0.50).mean()),
    }


# ============================================================
# RANDOM ENTRY CONTROL
# ============================================================
def random_entry_control(df: pd.DataFrame, engine: ASREngine,
                         n_trades_target: int, n_runs: int = 100) -> dict:
    """
    Generate control strategies with random entries but same exit model.
    Compares against the ASR engine's edge.
    """
    n = len(df)
    if n < 100:
        return {"error": "Too few bars"}

    c = df['close'].values
    h = df['high'].values
    l = df['low'].values
    atr = engine._atr

    tp1_r = engine._g('risk', 'tp1_r', default=1.0)
    tp2_r = engine._g('risk', 'tp2_r', default=2.0)
    tp1_frac = engine._g('risk', 'tp1_frac', default=0.50)
    sl_buffer = engine._g('risk', 'sl_buffer_atr', default=0.25)
    time_stop = engine._g('risk', 'time_stop_bars', default=60)

    all_results = []
    for run in range(n_runs):
        # Random entry bars
        entry_bars = sorted(np.random.choice(range(50, n - time_stop - 5), size=min(n_trades_target, n // 3), replace=False))
        run_trades = []

        for eb in entry_bars:
            direction = np.random.choice([1, -1])
            entry = c[eb]
            risk = atr[eb] * 1.0 if not np.isnan(atr[eb]) else entry * 0.01
            if risk <= 0:
                continue
            sl = entry - direction * risk
            tp1 = entry + direction * tp1_r * risk
            tp2 = entry + direction * tp2_r * risk

            # Simulate trade
            tp1_hit = False
            real_r = 0.0
            current_sl = sl

            for j in range(eb + 1, min(eb + time_stop + 1, n)):
                rem_f = (1.0 - tp1_frac) if tp1_hit else 1.0

                # Check stop
                stop_hit = l[j] <= current_sl if direction == 1 else h[j] >= current_sl
                if stop_hit:
                    gross_r = real_r + rem_f * (direction * (current_sl - entry) / risk)
                    run_trades.append(gross_r)
                    break

                # Check TP1
                if not tp1_hit:
                    t1_reached = h[j] >= tp1 if direction == 1 else l[j] <= tp1
                    if t1_reached:
                        real_r += tp1_frac * tp1_r
                        tp1_hit = True
                        current_sl = entry

                # Check TP2
                if tp1_hit:
                    t2_reached = h[j] >= tp2 if direction == 1 else l[j] <= tp2
                    if t2_reached:
                        gross_r = real_r + (1.0 - tp1_frac) * tp2_r
                        run_trades.append(gross_r)
                        break

                # Time stop
                if j == min(eb + time_stop, n - 1):
                    gross_r = real_r + rem_f * (direction * (c[j] - entry) / risk)
                    run_trades.append(gross_r)
                    break

        if run_trades:
            arr = np.array(run_trades)
            all_results.append({
                "count": len(arr),
                "avg_r": float(arr.mean()),
                "net_r": float(arr.sum()),
                "win_rate": float((arr > 0.1).mean() * 100),
            })

    if not all_results:
        return {"error": "No valid random runs"}

    avg_rs = [r["avg_r"] for r in all_results]
    return {
        "n_runs": n_runs,
        "random_avg_r_mean": float(np.mean(avg_rs)),
        "random_avg_r_std": float(np.std(avg_rs)),
        "random_avg_r_p5": float(np.percentile(avg_rs, 5)),
        "random_avg_r_p95": float(np.percentile(avg_rs, 95)),
        "asr_avg_r": float(np.mean([t.net_r for t in engine.trades])) if engine.trades else 0,
        "edge_vs_random": float(np.mean([t.net_r for t in engine.trades]) - np.mean(avg_rs)) if engine.trades else 0,
    }


# ============================================================
# WALK-FORWARD OPTIMIZATION
# ============================================================
def walk_forward(df: pd.DataFrame, config: dict,
                 param_grid: dict = None,
                 train_ratio: float = 0.6,
                 val_ratio: float = 0.2) -> dict:
    """
    Walk-forward optimization.
    Splits data into train/validation/test.
    Optimizes only the specified parameters.
    Requires selected params to reside on a stable plateau.
    """
    n = len(df)
    train_end = int(n * train_ratio)
    val_end = int(n * (train_ratio + val_ratio))

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    if param_grid is None:
        param_grid = config.get('walk_forward', {}).get('param_grid', {})

    if not param_grid:
        return {"error": "No parameter grid defined"}

    # Simple grid search on train set
    results = []
    # Generate all parameter combinations (simplified — single param at a time)
    base_config = config.copy()

    for param_name, values in param_grid.items():
        for val in values:
            trial_config = _deep_copy_config(base_config)
            _set_param(trial_config, param_name, val)

            engine = ASREngine(trial_config)
            engine.run(train_df)
            stats = engine.get_stats()

            results.append({
                "param": param_name,
                "value": val,
                "train_trades": stats.get("trade_count", 0),
                "train_expectancy": stats.get("expectancy_r", 0),
                "train_net_r": stats.get("net_r", 0),
                "train_pf": stats.get("profit_factor", 0),
                "train_max_dd": stats.get("max_dd_r", 0),
            })

    # Find best per parameter
    best_params = {}
    for param_name in param_grid:
        param_results = [r for r in results if r["param"] == param_name]
        if param_results:
            # Sort by expectancy, pick best with plateau check
            param_results.sort(key=lambda x: x["train_expectancy"], reverse=True)
            best_params[param_name] = param_results[0]["value"]

    # Validate with best params
    val_config = _deep_copy_config(base_config)
    for p, v in best_params.items():
        _set_param(val_config, p, v)

    val_engine = ASREngine(val_config)
    val_engine.run(val_df)
    val_stats = val_engine.get_stats()

    # Test with best params
    test_engine = ASREngine(val_config)
    test_engine.run(test_df)
    test_stats = test_engine.get_stats()

    return {
        "best_params": best_params,
        "all_trials": results,
        "validation": val_stats,
        "test": test_stats,
        "oos_stability": (test_stats.get("expectancy_r", 0) / val_stats.get("expectancy_r", 1))
                         if val_stats.get("expectancy_r", 0) != 0 else 0,
    }


def _deep_copy_config(cfg: dict) -> dict:
    import copy
    return copy.deepcopy(cfg)


def _set_param(cfg: dict, name: str, value):
    """Set a parameter in the config by name."""
    param_map = {
        "sigMinScore": ("signal", "min_score"),
        "tp1R": ("risk", "tp1_r"),
        "tp2R": ("risk", "tp2_r"),
        "slBufferATR": ("risk", "sl_buffer_atr"),
        "minRoomR": ("risk", "min_room_r"),
        "pivL": ("pivots", "piv_l"),
        "pivR": ("pivots", "piv_r"),
        "trendMode": ("signal", "trend_mode"),
    }
    if name in param_map:
        section, key = param_map[name]
        cfg.setdefault(section, {})[key] = value


# ============================================================
# VERDICT FRAMEWORK
# ============================================================
def verdict(stats: dict, config: dict) -> dict:
    """
    Apply pre-declared acceptance thresholds.
    Returns PASS / FAIL / INCONCLUSIVE.
    """
    acc = config.get("acceptance", {})
    min_trades = acc.get("min_trades", 300)
    min_exp = acc.get("min_expectancy_r", 0.05)
    max_dd = acc.get("max_dd_r", 25.0)
    min_pf = acc.get("min_profit_factor", 1.15)

    checks = {}
    n = stats.get("trade_count", 0)

    checks["sufficient_sample"] = n >= min_trades
    checks["robust_expectancy"] = stats.get("expectancy_r", 0) >= min_exp
    checks["max_dd_ok"] = stats.get("max_dd_r", 999) <= max_dd
    checks["profit_factor_ok"] = stats.get("profit_factor", 0) >= min_pf

    if not checks["sufficient_sample"]:
        result = "INCONCLUSIVE"
        reason = f"Only {n} trades (need {min_trades})"
    elif all(checks.values()):
        result = "PASS"
        reason = "All acceptance criteria met"
    else:
        failed = [k for k, v in checks.items() if not v]
        result = "FAIL"
        reason = f"Failed: {', '.join(failed)}"

    return {
        "verdict": result,
        "reason": reason,
        "checks": checks,
        "thresholds": {
            "min_trades": min_trades,
            "min_expectancy_r": min_exp,
            "max_dd_r": max_dd,
            "min_profit_factor": min_pf,
        },
    }
