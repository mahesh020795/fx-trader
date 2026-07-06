"""SRE — Stop Run Exhaustion Engine: pure logic (no MT5, no pandas).
Session stop-run REVERSALS: London/NY opens sweep the Asian extreme to run
stops, then reverse. GVE five-layer template with reversal semantics.
Tunables live HERE (tracked/versioned) — config.py is untracked.
Volume triggers deliberately absent (demo tick volume unreliable)."""

SRE_DEFAULTS = {
    "min_sweep_pips_fx":  3.0,   # spec §4: forex
    "min_sweep_pips_jpy": 5.0,   # spec §4: JPY crosses
    "confirm_bars":       3,     # reversal must confirm within N M15 bars
    "sl_atr_buffer":      0.5,   # SL = sweep extreme + 0.5*ATR(M15)
    "sl_max_pips_fx":     30,
    "sl_max_pips_jpy":    40,
    "rr_min":             1.5,
    "rr_max":             4.0,
    "atr_dead_ratio":     0.6,   # skip if ATR < 0.6x average (dead)
    "atr_hyper_ratio":    2.5,   # skip if ATR > 2.5x average (hyper)
}

def classify_sweep(bar, pool_high, pool_low, pip, min_sweep_pips):
    """A stop run: wick penetrates a pool by >= min_sweep_pips but the bar
    CLOSES back inside the range. Close beyond the pool = breakout, not sweep."""
    if (bar["high"] - pool_high) / pip >= min_sweep_pips and bar["close"] < pool_high:
        return "SWEPT_HIGH"
    if (pool_low - bar["low"]) / pip >= min_sweep_pips and bar["close"] > pool_low:
        return "SWEPT_LOW"
    return None

def confirm_reversal(bars_after, direction):
    """Within SRE_DEFAULTS['confirm_bars'] bars of the sweep, a rejection
    candle closing in the far third against the sweep confirms the reversal."""
    for b in bars_after[:SRE_DEFAULTS["confirm_bars"]]:
        rng = b["high"] - b["low"]
        if rng <= 0:
            continue
        pos = (b["close"] - b["low"]) / rng      # 0 = at low, 1 = at high
        if direction == "SELL" and pos <= 1/3:
            return True
        if direction == "BUY" and pos >= 2/3:
            return True
    return False

def sre_levels(direction, entry, sweep_extreme, asian_mid, opposite_pool,
               pip, atr_m15, is_jpy=False):
    """SL beyond the sweep extreme + ATR buffer (capped); TP toward the Asian
    mid, extended to the opposite pool only if RR stays inside the clamp."""
    d = SRE_DEFAULTS
    buf = d["sl_atr_buffer"] * atr_m15
    sl_cap = d["sl_max_pips_jpy"] if is_jpy else d["sl_max_pips_fx"]
    if direction == "SELL":
        sl = sweep_extreme + buf
        sl_pips = (sl - entry) / pip
        tp = asian_mid if asian_mid < entry else opposite_pool
        tp_pips = (entry - tp) / pip
    else:
        sl = sweep_extreme - buf
        sl_pips = (entry - sl) / pip
        tp = asian_mid if asian_mid > entry else opposite_pool
        tp_pips = (tp - entry) / pip
    if sl_pips <= 0 or sl_pips > sl_cap or tp_pips <= 0:
        return None
    rr = tp_pips / sl_pips
    if rr < d["rr_min"]:
        tp_pips = sl_pips * d["rr_min"]         # extend TP to meet min RR
        tp = entry - tp_pips * pip if direction == "SELL" else entry + tp_pips * pip
        rr = d["rr_min"]
    if rr > d["rr_max"]:                          # clamp TP to max RR
        tp_pips = sl_pips * d["rr_max"]
        tp = entry - tp_pips * pip if direction == "SELL" else entry + tp_pips * pip
        rr = d["rr_max"]
    return sl, tp, sl_pips, tp_pips, rr

def asian_range(m15_bars, day_start_idx):
    """High/low of the 00:00-07:00 UTC window = bars [day_start_idx,
    day_start_idx+28). Returns None if fewer than 20 bars present."""
    window = m15_bars[day_start_idx: day_start_idx + 28]
    if len(window) < 20:
        return None
    return max(b["high"] for b in window), min(b["low"] for b in window)
