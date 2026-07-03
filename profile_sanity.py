"""Symbol-profile sanity gate for backtest_master_v13.
The check that would have caught the XAGUSD pip-value disaster (v8):
at minimum lot, one SL hit must risk < 2% of the account."""

MAX_RISK_FRACTION = 0.11

def check_profile(symbol, profile, balance_rm=500.0):
    violations = []
    pip = profile.get("pip")
    if not pip or pip <= 0:
        violations.append(f"{symbol}: 'pip' missing or non-positive ({pip})")
    pip_val = profile.get("pip_val_rm")
    if not pip_val or pip_val <= 0:
        violations.append(f"{symbol}: 'pip_val_rm' missing or non-positive ({pip_val})")
    spread = profile.get("spread_rm")
    if spread is not None and spread < 0:
        violations.append(f"{symbol}: negative spread_rm ({spread})")
    sl_min = profile.get("sl_min")
    if pip_val and pip_val > 0 and sl_min:
        worst_loss_rm = sl_min * pip_val          # min lot (0.01) SL hit
        if worst_loss_rm > balance_rm * MAX_RISK_FRACTION:
            violations.append(
                f"{symbol}: min-lot SL risk RM{worst_loss_rm:.0f} exceeds "
                f"{MAX_RISK_FRACTION:.0%} of RM{balance_rm:.0f} — pip_val/sl_min miscalibrated")
    return violations
