# ════════════════════════════════════════════════════════════
#  MONTE CARLO RISK ENGINE v13 — Institutional stress testing
#  Bootstrap-resamples the actual trade distribution 10,000×
#  to answer the questions a single backtest equity curve can't:
#    • What's the DD distribution (median / P95 / worst-case)?
#    • Risk of ruin (hitting -50% from start)?
#    • 95% confidence interval on annual return?
#  A single backtest is ONE path. Live trading will be a DIFFERENT
#  path drawn from the same distribution. This shows the full range.
#
#  v13 delta vs v11 (Task 10A, ANALYSIS ONLY): reads
#  backtest_master_v13.json (expanded universe: baseline + matrix-PASS
#  candidate symbols/engines + XAGUSD) instead of the v10 baseline JSON.
#  No other methodology change — same bootstrap, same N_SIMS/START_BAL.
#
#  Usage: python montecarlo_v13.py   (needs backtest_master_v13.json)
# ════════════════════════════════════════════════════════════
import json, random, sys

N_SIMS        = 10_000
START_BAL     = 500.0
RUIN_LEVEL    = 0.50      # ruin = losing 50% of starting balance
TRADES_PER_YR = 72        # ~6.0/month from v10

def run():
    with open("backtest_master_v13.json") as f:
        trades = json.load(f)
    pnls = [t["pnl_rm"] for t in trades]
    n = len(pnls)
    print("=" * 70)
    print(f"  MONTE CARLO RISK ENGINE — {N_SIMS:,} bootstrap simulations")
    print(f"  Resampling {n} actual trades | 1-year horizon "
          f"({TRADES_PER_YR} trades/sim)")
    print("=" * 70)

    random.seed(42)
    max_dds, finals, ruins = [], [], 0
    for _ in range(N_SIMS):
        bal = peak = START_BAL
        mdd = 0.0
        ruined = False
        for _ in range(TRADES_PER_YR):
            bal += random.choice(pnls)
            peak = max(peak, bal)
            mdd = max(mdd, (peak - bal) / peak * 100)
            if bal <= START_BAL * RUIN_LEVEL:
                ruined = True
        max_dds.append(mdd)
        finals.append(bal)
        if ruined: ruins += 1

    max_dds.sort(); finals.sort()
    def pct(arr, p): return arr[int(len(arr) * p)]

    print(f"\n  1-YEAR RETURN DISTRIBUTION (start RM{START_BAL:.0f}):")
    print(f"    P5  (bad year):    RM{pct(finals,0.05):,.0f}  "
          f"({(pct(finals,0.05)/START_BAL-1)*100:+.0f}%)")
    print(f"    Median:            RM{pct(finals,0.50):,.0f}  "
          f"({(pct(finals,0.50)/START_BAL-1)*100:+.0f}%)")
    print(f"    P95 (good year):   RM{pct(finals,0.95):,.0f}  "
          f"({(pct(finals,0.95)/START_BAL-1)*100:+.0f}%)")
    losing_years = sum(1 for fb in finals if fb < START_BAL) / N_SIMS * 100
    print(f"    Probability of a losing year: {losing_years:.1f}%")

    print(f"\n  MAX DRAWDOWN DISTRIBUTION:")
    print(f"    Median DD:         {pct(max_dds,0.50):.1f}%")
    print(f"    P95 DD:            {pct(max_dds,0.95):.1f}%   ← plan capital for this")
    print(f"    P99 DD (severe):   {pct(max_dds,0.99):.1f}%")
    print(f"    Backtest showed:   12.6%  "
          f"({'below' if 12.6 < pct(max_dds,0.50) else 'near/above'} median path — "
          f"expect worse paths live)")

    print(f"\n  RISK OF RUIN (−{RUIN_LEVEL*100:.0f}% from start within 1yr): "
          f"{ruins/N_SIMS*100:.2f}%")
    verdict = ("🟢 INSTITUTIONAL GRADE" if ruins/N_SIMS < 0.01 and pct(max_dds,0.95) < 30
               else "🟡 ACCEPTABLE" if ruins/N_SIMS < 0.05
               else "🔴 TOO HOT — reduce risk per trade")
    print(f"\n  VERDICT: {verdict}")
    print("=" * 70)

def run_compounding():
    """v11.1 COMPOUNDING MODE — models live GUARD sizing (% of balance).
    The fixed-RM mode above overstates ruin: live, losses shrink as the
    balance shrinks (self-deleveraging). Here each trade is converted to an
    R-multiple and risk is 1% of CURRENT balance, exactly like live GUARD."""
    with open("backtest_master_v13.json") as f:
        trades = json.load(f)
    # R-multiple per trade: pnl relative to typical loss magnitude
    losses = [abs(t["pnl_rm"]) for t in trades if t["pnl_rm"] < 0]
    avg_loss = sum(losses) / len(losses)
    r_mults = [t["pnl_rm"] / avg_loss for t in trades]

    RISK_PCT = 0.01
    print("\n" + "=" * 70)
    print(f"  COMPOUNDING MODE — live %%-of-balance sizing ({RISK_PCT*100:.0f}%% risk/trade)")
    print("=" * 70)
    random.seed(7)
    max_dds, finals, ruins = [], [], 0
    for _ in range(N_SIMS):
        bal = peak = START_BAL
        mdd = 0.0; ruined = False
        for _ in range(TRADES_PER_YR):
            bal += bal * RISK_PCT * random.choice(r_mults)
            peak = max(peak, bal)
            mdd = max(mdd, (peak - bal) / peak * 100)
            if bal <= START_BAL * RUIN_LEVEL: ruined = True
        max_dds.append(mdd); finals.append(bal)
        if ruined: ruins += 1
    max_dds.sort(); finals.sort()
    def pct(a, p): return a[int(len(a) * p)]
    print(f"  1-yr return:  P5 {(pct(finals,0.05)/START_BAL-1)*100:+.0f}%% | "
          f"median {(pct(finals,0.50)/START_BAL-1)*100:+.0f}%% | "
          f"P95 {(pct(finals,0.95)/START_BAL-1)*100:+.0f}%%")
    print(f"  Max DD:       median {pct(max_dds,0.50):.1f}%% | "
          f"P95 {pct(max_dds,0.95):.1f}%% | P99 {pct(max_dds,0.99):.1f}%%")
    print(f"  Risk of ruin (−50%%): {ruins/N_SIMS*100:.2f}%%")
    verdict = ("🟢 INSTITUTIONAL GRADE" if ruins/N_SIMS < 0.01
               else "🟡 ACCEPTABLE" if ruins/N_SIMS < 0.05 else "🔴 TOO HOT")
    print(f"  VERDICT: {verdict}")
    print("=" * 70)

if __name__ == "__main__":
    try:
        run()
        run_compounding()
    except FileNotFoundError:
        print("backtest_master_v13.json not found — run backtest_master_v13.py first")
        sys.exit(1)
