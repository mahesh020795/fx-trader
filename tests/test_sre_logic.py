"""SRE pure logic: sweep-and-reject classification, reversal confirmation,
and level construction — all on synthetic candles, no MT5."""
from sre_logic import (SRE_DEFAULTS, classify_sweep, confirm_reversal,
                       sre_levels)

PIP = 0.0001

def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}

def test_sweep_high_detected():
    # pool high 1.1000; wick to 1.1006 (6 pips through), close back inside
    b = bar(1.0995, 1.1006, 1.0993, 1.0996)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) == "SWEPT_HIGH"

def test_shallow_poke_not_a_sweep():
    # only 2 pips through the pool with min 3 -> not a sweep
    b = bar(1.0995, 1.1002, 1.0993, 1.0996)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) is None

def test_close_beyond_pool_is_breakout_not_sweep():
    # closes ABOVE the pool -> breakout, not a stop run
    b = bar(1.0995, 1.1010, 1.0994, 1.1008)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) is None

def test_sweep_low_detected():
    b = bar(1.0955, 1.0957, 1.0944, 1.0953)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) == "SWEPT_LOW"

def test_confirm_reversal_sell_rejection():
    # after SWEPT_HIGH we need a bar closing in its bottom third (rejection)
    rej = bar(1.0999, 1.1002, 1.0985, 1.0987)   # range 17 pips, close 2 from low
    assert confirm_reversal([rej], "SELL") is True

def test_confirm_reversal_fails_on_strength():
    bull = bar(1.0999, 1.1008, 1.0998, 1.1007)  # closes strong -> no reversal
    assert confirm_reversal([bull], "SELL") is False

def test_confirm_within_max_bars_only():
    bull = bar(1.0999, 1.1008, 1.0998, 1.1007)
    rej  = bar(1.1006, 1.1007, 1.0990, 1.0992)
    bars = [bull] * SRE_DEFAULTS["confirm_bars"] + [rej]   # rejection arrives too late
    assert confirm_reversal(bars, "SELL") is False

def test_levels_sell_shape_and_rr_clamp():
    out = sre_levels("SELL", entry=1.0990, sweep_extreme=1.1006,
                     asian_mid=1.0975, opposite_pool=1.0950,
                     pip=PIP, atr_m15=0.0008)
    assert out is not None
    sl, tp, sl_pips, tp_pips, rr = out
    assert sl > 1.1006            # beyond the sweep extreme + ATR buffer
    assert tp < 1.0990            # toward the mid/opposite pool
    assert SRE_DEFAULTS["rr_min"] <= rr <= SRE_DEFAULTS["rr_max"]

def test_levels_rejects_oversized_sl():
    # sweep extreme absurdly far -> SL beyond cap -> no trade
    out = sre_levels("SELL", entry=1.0990, sweep_extreme=1.1090,
                     asian_mid=1.0975, opposite_pool=1.0950,
                     pip=PIP, atr_m15=0.0008)
    assert out is None
