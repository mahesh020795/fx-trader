# tests/test_sce_logic.py
"""SCE pure logic: close-through breakout classification (the exact
complement of sre_logic.classify_sweep) and measured-move levels."""
from sce_logic import SCE_DEFAULTS, classify_breakout, sce_levels
from sre_logic import classify_sweep

PIP = 0.0001

def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}

def test_close_through_is_breakout():
    b = bar(1.0995, 1.1010, 1.0994, 1.1008)   # closes 8 pips beyond pool high
    assert classify_breakout(b, 1.1000, 1.0950, PIP, 3.0, 0.60) == "BREAK_UP"

def test_sweep_is_not_breakout_and_vice_versa():
    # the SRE sweep case (wick through, close back inside) must NOT break out
    sweep = bar(1.0995, 1.1006, 1.0993, 1.0996)
    assert classify_breakout(sweep, 1.1000, 1.0950, PIP, 3.0, 0.60) is None
    assert classify_sweep(sweep, 1.1000, 1.0950, PIP, 3.0) == "SWEPT_HIGH"
    # and the breakout case must NOT be a sweep — zero signal overlap
    brk = bar(1.0995, 1.1010, 1.0994, 1.1008)
    assert classify_sweep(brk, 1.1000, 1.0950, PIP, 3.0) is None

def test_weak_body_rejected():
    b = bar(1.1004, 1.1010, 1.0985, 1.1006)   # closes beyond but body 2/25
    assert classify_breakout(b, 1.1000, 1.0950, PIP, 3.0, 0.60) is None

def test_break_down():
    b = bar(1.0955, 1.0956, 1.0940, 1.0942)
    assert classify_breakout(b, 1.1000, 1.0950, PIP, 3.0, 0.60) == "BREAK_DOWN"

def test_levels_measured_move():
    # asian range 50 pips; BUY from 1.1008 -> TP = entry + 50 pips.
    # (plan's original atr=0.0004 gave SL 4 pips -> RR 12.5, which the spec's
    # rr_max clamp correctly pulls to 4.0; atr=0.0015 keeps RR 3.33 unclamped
    # so the full measured-move projection is what's asserted.)
    out = sce_levels("BUY", 1.1008, 1.1000, 1.0950, PIP,
                     atr=0.0015, sl_cap_pips=30)
    assert out is not None
    sl, tp, sl_pips, tp_pips, rr = out
    assert abs(tp - 1.1058) < 1e-9
    assert sl_pips <= 30 and rr >= SCE_DEFAULTS["rr_min"]

def test_levels_reject_low_rr():
    # tiny range (8 pips) vs ATR SL (10 pips) -> RR < 1.5 -> None
    out = sce_levels("BUY", 1.1002, 1.1000, 1.0992, PIP,
                     atr=0.0010, sl_cap_pips=30)
    assert out is None
