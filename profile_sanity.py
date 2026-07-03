"""Symbol-profile sanity gate for backtest_master_v13.
Catches XAGUSD-disaster-class miscalibration (v8: pip value ~10x oversized
for the 5000oz contract -> PF 0.28, MaxDD 93.3%).
Check: at minimum lot (0.01), one stop-loss hit must risk < MAX_RISK_FRACTION
of the account. Threshold rationale: this gate is a miscalibration DETECTOR,
not a risk manager (GUARD owns risk). Two known populations: legitimate
profiles top out at 16.7% of RM500 at min lot (HPE GBPJPY: worst-case prox
150 + sl_buf 80 = 230 pips x RM0.362); the known miscalibration class starts
at ~50% (XAGUSD v8: pip value ~10x oversized, MaxDD 93.3%). 0.25 sits
between the two populations with ~50% margin to each side."""

MAX_RISK_FRACTION = 0.25

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
    # SL-scale estimate per engine profile shape:
    # CTE: sl_min | MRE/CBE: min_range (boundary distance proxy) | HPE: prox + sl_buf
    sl_est = (profile.get("sl_min")
              or profile.get("min_range")
              or ((profile.get("prox") or 0) + (profile.get("sl_buf") or 0))
              or None)
    if pip_val and pip_val > 0 and sl_est:
        worst_loss_rm = sl_est * pip_val          # min lot (0.01) SL hit
        if worst_loss_rm > balance_rm * MAX_RISK_FRACTION:
            violations.append(
                f"{symbol}: min-lot SL risk RM{worst_loss_rm:.0f} (SL-scale estimate "
                f"{sl_est}) exceeds {MAX_RISK_FRACTION:.0%} of RM{balance_rm:.0f} — "
                f"pip_val/SL-scale miscalibrated")
    return violations
