# gap_logic.py
"""GAP — Overnight Gap continuation engine, pure logic (no MT5/pandas).
Index-native: the session opens with a gap vs the prior close; a large gap
that FOLLOWS THROUGH in the gap direction tends to run (gap-and-go). This is
a continuation edge — consistent with our validated "continuation pays,
fading loses" finding. Gap-FILL (fade small gaps) is deliberately NOT here;
it's a tagged v18 variant. Tunables tracked here; session-open detection and
prior-close wiring live in the harness."""

GAP_DEFAULTS = {
    "min_gap_atr":   0.5,   # gap >= 0.5x D1-ATR to qualify
    "min_body":      0.6,   # first-bar follow-through body ratio
    "sl_atr_buffer": 0.5,   # SL = stop_ref -/+ 0.5x (intraday) ATR
    "tp_gap_mult":   1.0,   # TP = 1x gap size (measured move) from entry
    "rr_min":        1.5,
    "rr_max":        4.0,
}

def gap_size_atr(prior_close, open_price, atr_d1):
    """Signed overnight gap in D1-ATR units."""
    if atr_d1 <= 0:
        return 0.0
    return round((open_price - prior_close) / atr_d1, 4)

def classify_gap_go(prior_close, open_price, first_bar, atr_d1,
                    min_gap_atr, min_body):
    """Gap beyond +/- min_gap_atr AND the first post-open bar continues in the
    gap direction (closes beyond the open, body >= min_body). Returns
    'GAP_UP_GO' / 'GAP_DOWN_GO' / None."""
    g = gap_size_atr(prior_close, open_price, atr_d1)
    rng = first_bar["high"] - first_bar["low"]
    if rng <= 0:
        return None
    if abs(first_bar["close"] - first_bar["open"]) / rng < min_body:
        return None
    if g >= min_gap_atr and first_bar["close"] > open_price:
        return "GAP_UP_GO"
    if g <= -min_gap_atr and first_bar["close"] < open_price:
        return "GAP_DOWN_GO"
    return None

def gap_levels(direction, entry, stop_ref, gap_price, pip, atr, sl_cap_pips):
    """SL = stop_ref -/+ ATR buffer (stop_ref = the session open, the level
    whose loss means the go failed); TP = tp_gap_mult x |gap| measured move
    from entry; RR clamped [rr_min, rr_max]."""
    d = GAP_DEFAULTS
    if gap_price <= 0:
        return None
    buf = d["sl_atr_buffer"] * atr
    tp_dist = d["tp_gap_mult"] * gap_price
    if direction == "BUY":
        sl = stop_ref - buf
        sl_pips = (entry - sl) / pip
        tp = entry + tp_dist
        tp_pips = (tp - entry) / pip
    else:
        sl = stop_ref + buf
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
