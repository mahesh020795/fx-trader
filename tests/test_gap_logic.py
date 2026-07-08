# tests/test_gap_logic.py
"""GAP pure logic: overnight gap sizing, gap-and-go continuation
classification (gap beyond threshold + first-bar follow-through), and
measured-move levels. Continuation only — fill/fade is a v18 variant."""
from gap_logic import GAP_DEFAULTS, gap_size_atr, classify_gap_go, gap_levels

PIP = 1.0

def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}

def test_gap_size_signed():
    assert gap_size_atr(5000, 5015, 30.0) == 0.5     # +15 / 30
    assert gap_size_atr(5000, 4985, 30.0) == -0.5

def test_gap_up_go():
    fb = bar(5015, 5022, 5014, 5020)   # continues up from open 5015
    assert classify_gap_go(5000, 5015, fb, 30.0, 0.5, 0.6) == "GAP_UP_GO"

def test_gap_down_go():
    fb = bar(4985, 4986, 4978, 4980)
    assert classify_gap_go(5000, 4985, fb, 30.0, 0.5, 0.6) == "GAP_DOWN_GO"

def test_gap_up_but_reverses_rejected():
    fb = bar(5015, 5016, 5008, 5010)   # gap up but first bar closes below open -> no go
    assert classify_gap_go(5000, 5015, fb, 30.0, 0.5, 0.6) is None

def test_small_gap_rejected():
    fb = bar(5005, 5012, 5004, 5011)   # gap only +5 = 0.17 ATR < 0.5
    assert classify_gap_go(5000, 5005, fb, 30.0, 0.5, 0.6) is None

def test_weak_body_rejected():
    fb = bar(5015, 5025, 5014, 5017)   # continues but body 2/11 < 0.6
    assert classify_gap_go(5000, 5015, fb, 30.0, 0.5, 0.6) is None

def test_levels_gap_go():
    # entry 5020, stop_ref (open) 5015, gap 15; SL = 5015 - 0.5xATR(4); TP = 1x gap
    out = gap_levels("BUY", 5020, 5015, 15.0, PIP, atr=4.0, sl_cap_pips=80)
    assert out is not None
    sl, tp, sl_pips, tp_pips, rr = out
    assert sl < 5020 and tp > 5020
    assert GAP_DEFAULTS["rr_min"] <= rr <= GAP_DEFAULTS["rr_max"]

def test_levels_reject_when_stop_too_far():
    # entry barely above a far stop_ref with tiny gap -> RR < 1.5
    out = gap_levels("BUY", 5020, 5000, 3.0, PIP, atr=4.0, sl_cap_pips=80)
    assert out is None
