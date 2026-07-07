# tests/test_ire_logic.py
"""IRE pure logic on synthetic H1 candles: displacement detection, FVG
identification, rebalance entry with both invalidation paths, levels."""
from ire_logic import (IRE_DEFAULTS, detect_displacement, find_fvg,
                       rebalance_entry, ire_levels)

PIP = 0.0001

def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}

def flat(n, px=1.1000, rng=0.0008):
    return [bar(px, px + rng/2, px - rng/2, px) for _ in range(n)]

def _disp_bars():
    """20 flat bars then a huge bullish displacement bar."""
    bars = flat(20)
    bars.append(bar(1.1000, 1.1042, 1.0999, 1.1040))   # range 43 pips, body ~40/43
    return bars

def test_displacement_detected():
    bars = _disp_bars()
    d = detect_displacement(bars, 20, atr=0.0010)       # range 4.3x ATR, body .93
    assert d is not None and d["direction"] == "BUY"
    assert d["origin"] == 1.0999                        # displacement bar's low
    assert d["extreme"] == 1.1042                       # its high

def test_small_or_weak_body_rejected():
    bars = flat(20) + [bar(1.1000, 1.1015, 1.0999, 1.1013)]   # only 1.6x ATR
    assert detect_displacement(bars, 20, atr=0.0010) is None
    bars2 = flat(20) + [bar(1.1000, 1.1042, 1.0958, 1.1002)]  # huge range, tiny body
    assert detect_displacement(bars2, 20, atr=0.0010) is None

def test_no_structure_break_rejected():
    # big candle but closes below the prior 20-bar high -> not institutional break
    bars = [bar(1.1000, 1.1080, 1.0990, 1.1005) for _ in range(20)]
    bars.append(bar(1.1000, 1.1042, 1.0999, 1.1040))    # 1.1040 < prior high 1.1080
    assert detect_displacement(bars, 20, atr=0.0010) is None

def test_fvg_found_and_bounds_correct():
    bars = _disp_bars()
    bars.append(bar(1.1040, 1.1055, 1.1031, 1.1050))    # bar i+1: low 1.1031
    # bull FVG = gap between bar[i-1].high (1.1004) and bar[i+1].low (1.1031)
    g = find_fvg(bars, 20, "BUY", PIP, min_gap_pips=3.0)
    assert g == (1.1004, 1.1031)

def test_fvg_too_small_rejected():
    bars = _disp_bars()
    bars.append(bar(1.1040, 1.1055, 1.1005, 1.1050))    # i+1 low nearly fills gap
    assert find_fvg(bars, 20, "BUY", PIP, min_gap_pips=3.0) is None

def test_rebalance_entry_on_gap_touch():
    after = [bar(1.1050, 1.1052, 1.1035, 1.1040),       # holds above gap
             bar(1.1040, 1.1041, 1.1015, 1.1022)]       # dips into gap (mid 1.10175)
    hit = rebalance_entry(after, 1.1004, 1.1031, "BUY",
                          origin=1.0999, wait_bars=12)
    assert hit is not None
    off, px = hit
    assert off == 1 and abs(px - 1.10175) < 1e-9        # gap midpoint

def test_rebalance_invalidated_through_origin():
    after = [bar(1.1050, 1.1051, 1.0990, 1.0995)]        # crashes through origin first
    assert rebalance_entry(after, 1.1004, 1.1031, "BUY",
                           origin=1.0999, wait_bars=12) is None

def test_rebalance_missed_window():
    after = [bar(1.1050, 1.1060, 1.1045, 1.1058)] * 12   # never retraces
    assert rebalance_entry(after, 1.1004, 1.1031, "BUY",
                           origin=1.0999, wait_bars=12) is None

def test_levels_buy_shape_and_clamp():
    # entry deep in the gap: SL 16 pips (origin-buffer), TP 32 pips -> RR 2.0
    # (plan's original entry=1.10175 gave RR 1.04 < rr_min -> correctly rejected)
    out = ire_levels("BUY", entry=1.1010, origin=1.0999, extreme=1.1042,
                     pip=PIP, atr=0.0010, sl_cap_pips=30)
    assert out is not None
    sl, tp, sl_pips, tp_pips, rr = out
    assert sl < 1.0999                                   # beyond origin - buffer
    assert tp <= 1.1042                                  # at/below extreme (clamp)
    assert IRE_DEFAULTS["rr_min"] <= rr <= IRE_DEFAULTS["rr_max"]

def test_levels_reject_oversized_sl():
    out = ire_levels("BUY", entry=1.10175, origin=1.0940, extreme=1.1042,
                     pip=PIP, atr=0.0010, sl_cap_pips=30)   # SL ~82 pips > cap
    assert out is None
