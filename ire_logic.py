# ire_logic.py
"""IRE — Imbalance Rebalance Engine, pure logic (no MT5/pandas).
Mahesh's chain: compression -> displacement -> FVG -> partial rebalance ->
continuation, entered ON the rebalance. Session-agnostic by design;
session/compression/overlap tagging happens in the harness section.
Tunables live here (tracked) — config.py is untracked."""

IRE_DEFAULTS = {
    "disp_atr_mult":   2.0,   # displacement range >= 2x ATR(H1,14)
    "disp_body_min":   0.65,  # body/range of the displacement bar
    "structure_bars":  20,    # must close beyond this prior extreme
    "wait_bars":       12,    # H1 bars allowed for the rebalance to arrive
    "sl_atr_buffer":   0.5,   # SL = origin -/+ 0.5*ATR
    "rr_min":          1.5,
    "rr_max":          4.0,
}

def detect_displacement(bars, i, atr):
    """Bar i is a displacement if: range >= disp_atr_mult*atr, body ratio >=
    disp_body_min, and it CLOSES beyond the prior `structure_bars` extreme."""
    d = IRE_DEFAULTS
    if i < d["structure_bars"] or atr <= 0:
        return None
    b = bars[i]
    rng = b["high"] - b["low"]
    if rng < d["disp_atr_mult"] * atr or rng <= 0:
        return None
    if abs(b["close"] - b["open"]) / rng < d["disp_body_min"]:
        return None
    prior = bars[i - d["structure_bars"]: i]
    if b["close"] > b["open"]:
        if b["close"] <= max(p["high"] for p in prior):
            return None
        return {"direction": "BUY", "origin": b["low"], "extreme": b["high"]}
    else:
        if b["close"] >= min(p["low"] for p in prior):
            return None
        return {"direction": "SELL", "origin": b["high"], "extreme": b["low"]}

def find_fvg(bars, i, direction, pip, min_gap_pips):
    """3-candle fair value gap around displacement bar i (needs bar i+1).
    BUY: gap between bars[i-1].high and bars[i+1].low. SELL mirrored."""
    if i + 1 >= len(bars) or i < 1:
        return None
    if direction == "BUY":
        lo, hi = bars[i - 1]["high"], bars[i + 1]["low"]
    else:
        lo, hi = bars[i + 1]["high"], bars[i - 1]["low"]
    if (hi - lo) / pip < min_gap_pips:
        return None
    return round(lo, 6), round(hi, 6)

def rebalance_entry(bars_after, gap_lo, gap_hi, direction, origin, wait_bars):
    """Walk forward from the bar after FVG confirmation. Enter at the gap
    MIDPOINT when a bar's range touches it — unless the same or an earlier
    bar first trades through the displacement origin (structure failure).
    Returns (offset, entry_price) or None (missed window / invalidated)."""
    mid = (gap_lo + gap_hi) / 2.0
    for off, b in enumerate(bars_after[:wait_bars]):
        if direction == "BUY":
            if b["low"] <= origin:            # origin breached — invalid
                return None
            if b["low"] <= mid:
                return off, mid
        else:
            if b["high"] >= origin:
                return None
            if b["high"] >= mid:
                return off, mid
    return None

def ire_levels(direction, entry, origin, extreme, pip, atr, sl_cap_pips):
    """SL beyond the displacement origin + ATR buffer (capped); TP at the
    displacement extreme; RR clamped to [rr_min, rr_max]."""
    d = IRE_DEFAULTS
    buf = d["sl_atr_buffer"] * atr
    if direction == "BUY":
        sl = origin - buf
        sl_pips = (entry - sl) / pip
        tp = extreme
        tp_pips = (tp - entry) / pip
    else:
        sl = origin + buf
        sl_pips = (sl - entry) / pip
        tp = extreme
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
