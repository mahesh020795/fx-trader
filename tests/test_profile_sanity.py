from profile_sanity import check_profile

GOOD = dict(pip=0.0001, pip_val_rm=0.398, sl_min=30, spread_rm=0.003)

def test_good_profile_passes():
    assert check_profile("USDCHF", GOOD) == []

def test_oversized_pip_value_fails():
    # The XAGUSD disaster: pip value so large that min-lot SL risk > 2% of balance
    bad = dict(GOOD, pip_val_rm=5.0, sl_min=100)   # 100 pips * RM5 = RM500 = 100% of RM500
    violations = check_profile("XAGUSD", bad)
    assert any("risk" in v.lower() for v in violations)

def test_missing_pip_fails():
    violations = check_profile("EURGBP", dict(pip_val_rm=0.4))
    assert any("pip" in v.lower() for v in violations)

def test_negative_spread_fails():
    bad = dict(GOOD, spread_rm=-0.1)
    assert any("spread" in v.lower() for v in check_profile("X", bad))
