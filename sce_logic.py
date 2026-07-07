# sce_logic.py
"""SCE — Session Continuation Engine, pure logic. Joins the Asian-range
CLOSE-THROUGH that SRE's 2,290-trade fade experiment proved shouldn't be
faded. classify_breakout is the exact complement of sre_logic.classify_sweep:
sweep = wick through + close back inside (faded, failed); breakout = close
beyond (joined here). Zero signal overlap by construction."""

SCE_DEFAULTS = {
    "min_break_pips_fx":  3.0,
    "min_break_pips_jpy": 5.0,
    "min_body":           0.60,
    "sl_atr_mult":        1.0,
    "sl_max_pips_fx":     30,
    "sl_max_pips_jpy":    40,
    "rr_min":             1.5,
    "rr_max":             4.0,
}

def classify_breakout(bar, pool_high, pool_low, pip, min_break_pips, min_body):
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return None
    if abs(bar["close"] - bar["open"]) / rng < min_body:
        return None
    if (bar["close"] - pool_high) / pip >= min_break_pips:
        return "BREAK_UP"
    if (pool_low - bar["close"]) / pip >= min_break_pips:
        return "BREAK_DOWN"
    return None

def sce_levels(direction, entry, asian_high, asian_low, pip, atr, sl_cap_pips):
    """SL = 1xATR behind entry (capped); TP = measured move (Asian range
    height projected from the entry); RR clamped [rr_min, rr_max]."""
    d = SCE_DEFAULTS
    height = asian_high - asian_low
    if height <= 0:
        return None
    sl_dist = d["sl_atr_mult"] * atr
    sl_pips = sl_dist / pip
    if sl_pips <= 0 or sl_pips > sl_cap_pips:
        return None
    if direction == "BUY":
        sl, tp = entry - sl_dist, entry + height
        tp_pips = (tp - entry) / pip
    else:
        sl, tp = entry + sl_dist, entry - height
        tp_pips = (entry - tp) / pip
    rr = tp_pips / sl_pips
    if rr < d["rr_min"]:
        return None
    if rr > d["rr_max"]:
        tp_pips = sl_pips * d["rr_max"]
        tp = entry + tp_pips * pip if direction == "BUY" else entry - tp_pips * pip
        rr = d["rr_max"]
    return sl, tp, sl_pips, tp_pips, rr
