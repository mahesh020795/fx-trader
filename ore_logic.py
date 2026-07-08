# ore_logic.py
"""ORE — Opening Range Engine, pure logic (no MT5/pandas). Index-native
continuation: the first 30 min after the cash open form a range; a decisive
close beyond it early in the session tends to trend. Confirmed entry (close-
through) + mid-range stop + measured-move target — the RR clamp self-selects
early/clean breaks (late breaks are far from the range, fail RR, get skipped).
Tunables here (tracked); session-open detection + tagging live in the harness."""

ORE_DEFAULTS = {
    "or_bars_m5":     6,     # 30 min opening range = 6 x M5 bars
    "or_min_atr":     0.5,   # OR height >= 0.5x M5-ATR (not junk-tight)
    "or_max_atr":     3.0,   # OR height <= 3x M5-ATR (not a gap-day blowout)
    "min_break_atr":  0.1,   # close beyond OR by >= 0.1x M5-ATR (index-native)
    "min_body":       0.6,
    "sl_atr_buffer":  0.5,   # SL = OR midpoint -/+ 0.5x ATR
    "tp_range_mult":  2.0,   # TP = 2x OR height (measured move)
    "rr_min":         1.5,
    "rr_max":         4.0,
}

def opening_range(window_bars, atr):
    """First-N-M5-bar high/low, gated by ATR (reject junk-tight and gap-day
    blowout ranges). Returns (or_high, or_low) or None."""
    d = ORE_DEFAULTS
    if not window_bars or atr <= 0:
        return None
    hi = max(b["high"] for b in window_bars)
    lo = min(b["low"] for b in window_bars)
    h = hi - lo
    if h < d["or_min_atr"] * atr or h > d["or_max_atr"] * atr:
        return None
    return round(hi, 5), round(lo, 5)

def classify_or_breakout(bar, or_high, or_low, pip, min_break_pips, min_body):
    """Close beyond the OR by >= min_break_pips with body >= min_body.
    Same close-through convention as sce_logic.classify_breakout."""
    rng = bar["high"] - bar["low"]
    if rng <= 0:
        return None
    if abs(bar["close"] - bar["open"]) / rng < min_body:
        return None
    if (bar["close"] - or_high) / pip >= min_break_pips:
        return "BREAK_UP"
    if (or_low - bar["close"]) / pip >= min_break_pips:
        return "BREAK_DOWN"
    return None

def ore_levels(direction, entry, or_high, or_low, pip, atr, sl_cap_pips):
    """SL = OR midpoint -/+ ATR buffer; TP = tp_range_mult x OR height
    (measured move from entry); RR clamped [rr_min, rr_max]."""
    d = ORE_DEFAULTS
    height = or_high - or_low
    if height <= 0:
        return None
    mid = (or_high + or_low) / 2.0
    buf = d["sl_atr_buffer"] * atr
    tp_dist = d["tp_range_mult"] * height
    if direction == "BUY":
        sl = mid - buf
        sl_pips = (entry - sl) / pip
        tp = entry + tp_dist
        tp_pips = (tp - entry) / pip
    else:
        sl = mid + buf
        sl_pips = (sl - entry) / pip
        tp = entry - tp_dist
        tp_pips = (entry - tp) / pip
    if sl_pips <= 0 or sl_pips > sl_cap_pips or tp_pips <= 0:
        return None
    rr = tp_pips / sl_pips
    if rr < d["rr_min"]:
        return None
    if rr > d["rr_max"]:
        tp_pips = sl_pips * d["rr_max"]
        tp = entry + tp_pips * pip if direction == "BUY" else entry - tp_pips * pip
        rr = d["rr_max"]
    return sl, tp, sl_pips, tp_pips, rr
