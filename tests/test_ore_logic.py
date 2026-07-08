# tests/test_ore_logic.py
"""ORE pure logic on synthetic index bars: opening-range construction with
ATR guards, close-through breakout classification, and levels (mid-range
stop + measured-move target, which self-selects early/clean breaks)."""
from ore_logic import ORE_DEFAULTS, opening_range, classify_or_breakout, ore_levels

PIP = 1.0   # 1 index point

def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}

def _window(hi, lo):
    # 6 M5 bars spanning [lo, hi]
    return [bar(lo, hi, lo, hi), bar(hi, hi, lo, lo)] * 3

def test_opening_range_basic():
    assert opening_range(_window(5010, 5000), atr=5.0) == (5010.0, 5000.0)

def test_opening_range_too_tight():
    # height 1 < 0.5 x ATR(5) = 2.5 -> junk, rejected
    assert opening_range(_window(5001, 5000), atr=5.0) is None

def test_opening_range_too_wide():
    # height 20 > 3 x ATR(5) = 15 -> gap-day blowout, rejected
    assert opening_range(_window(5020, 5000), atr=5.0) is None

def test_breakout_up():
    b = bar(5010, 5014, 5009, 5013)   # closes 3 pts beyond OR high 5010
    assert classify_or_breakout(b, 5010, 5000, PIP, 0.5, 0.6) == "BREAK_UP"

def test_breakout_down():
    b = bar(5000, 5001, 4996, 4997)
    assert classify_or_breakout(b, 5010, 5000, PIP, 0.5, 0.6) == "BREAK_DOWN"

def test_no_breakout_inside():
    b = bar(5005, 5009, 5004, 5008)   # closes inside the range
    assert classify_or_breakout(b, 5010, 5000, PIP, 0.5, 0.6) is None

def test_weak_body_rejected():
    b = bar(5006, 5015, 5005, 5013)   # closes beyond but body 7/10 < ... actually big; make doji
    b = bar(5012, 5015, 5005, 5013)   # body 1 / range 10 = 0.1 < 0.6
    assert classify_or_breakout(b, 5010, 5000, PIP, 0.5, 0.6) is None

def test_levels_early_break_passes():
    # entry 5013, OR 5000-5010, mid 5005; SL = mid - 0.5xATR; TP = 2x range
    out = ore_levels("BUY", 5013, 5010, 5000, PIP, atr=5.0, sl_cap_pips=60)
    assert out is not None
    sl, tp, sl_pips, tp_pips, rr = out
    assert sl < 5013 and tp > 5013
    assert ORE_DEFAULTS["rr_min"] <= rr <= ORE_DEFAULTS["rr_max"]

def test_levels_late_break_rejected():
    # entry 5020 (far beyond the 10-pt range) -> SL too big vs 2x-range TP -> RR < 1.5
    out = ore_levels("BUY", 5020, 5010, 5000, PIP, atr=5.0, sl_cap_pips=60)
    assert out is None
