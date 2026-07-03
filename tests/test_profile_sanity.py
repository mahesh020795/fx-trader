from profile_sanity import check_profile

GOOD = dict(pip=0.0001, pip_val_rm=0.398, sl_min=30, spread_rm=0.003)

def test_good_profile_passes():
    assert check_profile("USDCHF", GOOD) == []

def test_oversized_pip_value_fails():
    # The XAGUSD disaster: pip value so large that min-lot SL risk >> threshold
    bad = dict(GOOD, pip_val_rm=5.0, sl_min=100)   # 100 pips * RM5 = RM500 = 100% of RM500
    violations = check_profile("XAGUSD", bad)
    assert any("risk" in v.lower() for v in violations)

def test_missing_pip_fails():
    violations = check_profile("EURGBP", dict(pip_val_rm=0.4))
    assert any("pip" in v.lower() for v in violations)

def test_negative_spread_fails():
    bad = dict(GOOD, spread_rm=-0.1)
    assert any("spread" in v.lower() for v in check_profile("X", bad))

def test_mre_style_profile_is_risk_checked():
    # min_range acts as the SL-scale estimate for MRE/CBE profiles
    bad = dict(pip=0.001, pip_val_rm=2.0, min_range=75)   # 75 * RM2 = RM150 = 30% of RM500
    assert any("risk" in v.lower() for v in check_profile("XAGUSD", bad))

def test_hpe_style_profile_is_risk_checked():
    bad = dict(pip=0.0001, pip_val_rm=3.0, prox=50, sl_buf=25)  # 75 * RM3 = RM225 = 45%
    assert any("risk" in v.lower() for v in check_profile("EURUSD", bad))

def test_worst_legitimate_profile_passes():
    # HPE GBPJPY, the worst real v10 profile:
    # (prox 150 + sl_buf 80) * 0.091*3.98 = RM83.30 = 16.7% < 25%
    ok = dict(pip=0.01, pip_val_rm=0.091*3.98, prox=150, sl_buf=80, spread_rm=0.009)
    assert check_profile("GBPJPY", ok) == []
