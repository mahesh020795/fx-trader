# ════════════════════════════════════════════════════════════
#  WALK-FORWARD VALIDATOR v13 — Institutional gold standard
#  (Pardo 1992/2008; Bailey & López de Prado 2014)
#
#  Tests whether the WHITELIST METHODOLOGY itself is robust:
#  for each fold, the whitelist is re-derived using ONLY the
#  training window, then applied blind to the test window.
#  If OOS performance holds across folds → methodology is real.
#  If OOS collapses → we curve-fit. Honest answer either way.
#
#  v13 delta vs v11 (Task 10A, ANALYSIS ONLY): reads
#  backtest_master_v13.json (expanded universe: baseline symbols +
#  candidate symbols CADJPY/USDCHF/EURGBP/AUDJPY/NZDJPY + XAGUSD,
#  across all engines) instead of the v10 baseline JSON. The
#  train/test/whitelist methodology below is UNCHANGED — re-deriving
#  the whitelist per fold from the (now larger) candidate pool IS the
#  point of this run: it answers whether the candidates survive OOS,
#  not just in-sample matrix testing. A read-only per-candidate-combo
#  OOS breakdown was added at the end (does not affect the verdict
#  computation above it).
#
#  Usage: python walkforward_v13.py   (needs backtest_master_v13.json)
# ════════════════════════════════════════════════════════════
import json, sys
from datetime import datetime
from collections import defaultdict

TRAIN_MONTHS = 18
TEST_MONTHS  = 6
MIN_TRAIN_SIGNALS = 5     # combo needs >=5 train signals to qualify
MIN_TRAIN_PF      = 1.15  # combo must show PF >= 1.15 in train to trade test

# Matrix-PASS candidate combos (Tasks 4-8) — tracked separately below so the
# controller can see per-combo OOS behavior, not just the aggregate verdict.
CANDIDATE_COMBOS = [
    ("CADJPY", "CBE"),
    ("USDCHF", "CTE"),
    ("EURGBP", "MRE"),
    ("NZDJPY", "CBE"),
    ("EURGBP", "CBE"),
    ("AUDJPY", "CBE"),
    ("XAGUSD", "CTE"),
    # v15 task-6: IRE matrix-PASS combos (docs/reports/v15_matrix_ire.md)
    ("EURGBP", "IRE"),
    ("EURUSD", "IRE"),
    ("AUDUSD", "IRE"),
    # v18: IRE15 (lower-TF) matrix-PASS combos
    ("AUDUSD", "IRE15"),
    ("USDJPY", "IRE15"),
    ("EURCHF", "IRE15"),
    # v18: CBE15 (lower-TF) matrix-PASS combos
    ("EURUSD", "CBE15"),
    ("USDCAD", "CBE15"),
    ("USDJPY", "CBE15"),
    ("NZDJPY", "CBE15"),
    # v16: FX-cross matrix-PASS combos (docs/reports/v13_matrix_2026-07-08.md)
    ("AUDCAD", "CBE"), ("AUDCHF", "CBE"), ("CADCHF", "CBE"), ("EURCAD", "CBE"),
    ("GBPAUD", "CBE"), ("GBPCAD", "CBE"), ("NZDCHF", "CBE"),
    ("AUDCAD", "CTE"), ("AUDCHF", "CTE"), ("EURAUD", "CTE"),
    ("AUDCAD", "MRE"), ("AUDCHF", "MRE"), ("EURAUD", "MRE"),
]

def load_trades(path="backtest_master_v13.json"):
    with open(path) as f:
        trades = json.load(f)
    for t in trades:
        t["_dt"] = datetime.strptime(t["entry_dt"], "%Y-%m-%d")
    return sorted(trades, key=lambda t: t["_dt"])

def month_index(dt, origin):
    return (dt.year - origin.year) * 12 + (dt.month - origin.month)

def pf_of(trades):
    gw = sum(t["pnl_rm"] for t in trades if t["pnl_rm"] > 0)
    gl = abs(sum(t["pnl_rm"] for t in trades if t["pnl_rm"] < 0))
    return gw / gl if gl > 0 else 99.0

def run():
    trades = load_trades()
    origin = trades[0]["_dt"].replace(day=1)
    last_m = month_index(trades[-1]["_dt"], origin)

    print("=" * 70)
    print("  WALK-FORWARD VALIDATION — v13 (expanded universe)")
    print(f"  Train {TRAIN_MONTHS}m → Test {TEST_MONTHS}m, rolling | "
          f"{len(trades)} trades | {last_m+1} months")
    print(f"  Combo qualifies for OOS if train PF >= {MIN_TRAIN_PF} "
          f"with >= {MIN_TRAIN_SIGNALS} signals")
    print("=" * 70)

    fold_results = []
    # per-candidate-combo OOS tracking (read-only reporting addition)
    combo_log = {c: [] for c in CANDIDATE_COMBOS}  # list of (fold_n, approved, n, net, pf)

    start = 0
    fold_n = 1
    while start + TRAIN_MONTHS + TEST_MONTHS <= last_m + 1:
        tr_lo, tr_hi = start, start + TRAIN_MONTHS
        te_lo, te_hi = tr_hi, tr_hi + TEST_MONTHS

        train = [t for t in trades if tr_lo <= month_index(t["_dt"], origin) < tr_hi]
        test  = [t for t in trades if te_lo <= month_index(t["_dt"], origin) < te_hi]

        # Derive whitelist from TRAIN ONLY
        combos = defaultdict(list)
        for t in train:
            combos[(t["symbol"], t["engine"])].append(t)
        approved = {k for k, v in combos.items()
                    if len(v) >= MIN_TRAIN_SIGNALS and pf_of(v) >= MIN_TRAIN_PF}
        # GVE XAUUSD always approved if it appears (structural engine)
        oos = [t for t in test if (t["symbol"], t["engine"]) in approved]
        oos_all = test  # comparison: trade everything

        def stats(ts):
            if not ts: return (0, 0.0, 0.0, 0.0)
            wins = sum(1 for t in ts if t["outcome"] == "win")
            net  = sum(t["pnl_rm"] for t in ts)
            return (len(ts), wins/len(ts)*100, net, pf_of(ts))

        n_w, wr_w, net_w, pf_w = stats(oos)
        n_a, wr_a, net_a, pf_a = stats(oos_all)

        fold_results.append((net_w, pf_w, n_w, net_a))
        tr_period = f"{(origin.year + (tr_lo//12))}-{tr_lo%12+1:02d}"
        te_period = f"{(origin.year + (te_lo//12))}-{te_lo%12+1:02d}"
        print(f"\n  Fold {fold_n}: train from {tr_period} | test from {te_period}")
        print(f"    Approved combos: {len(approved)}")
        print(f"    OOS (whitelist): {n_w:>3} trades | WR {wr_w:5.1f}% | "
              f"RM{net_w:+9.2f} | PF {pf_w:.2f}")
        print(f"    OOS (all):       {n_a:>3} trades | WR {wr_a:5.1f}% | "
              f"RM{net_a:+9.2f} | PF {pf_a:.2f}")
        edge = net_w - net_a
        print(f"    Whitelist edge vs trading everything: RM{edge:+.2f}")

        # --- per-candidate-combo OOS breakdown (read-only, does not affect
        # the whitelist/approved logic above) ---
        for combo in CANDIDATE_COMBOS:
            test_ts = [t for t in test if (t["symbol"], t["engine"]) == combo]
            was_approved = combo in approved
            if test_ts:
                n_c, wr_c, net_c, pf_c = stats(test_ts)
                combo_log[combo].append((fold_n, was_approved, n_c, net_c, pf_c))

        start += TEST_MONTHS
        fold_n += 1

    # Aggregate verdict
    nets   = [f[0] for f in fold_results]
    pfs    = [f[1] for f in fold_results if f[2] > 0]
    pos    = sum(1 for n in nets if n > 0)
    total  = sum(nets)
    total_all = sum(f[3] for f in fold_results)
    print("\n" + "=" * 70)
    print("  WALK-FORWARD VERDICT")
    print("=" * 70)
    print(f"  Folds:                    {len(fold_results)}")
    print(f"  Profitable OOS folds:     {pos}/{len(fold_results)} "
          f"({pos/len(fold_results)*100:.0f}%)")
    print(f"  Total OOS net (whitelist):RM{total:+.2f}")
    print(f"  Total OOS net (all):      RM{total_all:+.2f}")
    print(f"  Median OOS fold PF:       {sorted(pfs)[len(pfs)//2]:.2f}" if pfs else "")
    if pos / max(1, len(fold_results)) >= 0.7 and total > 0:
        print("  VERDICT: [ROBUST] methodology survives out-of-sample.")
        print("           The edge is structural, not curve-fit.")
    elif total > 0:
        print("  VERDICT: [MIXED] positive overall but inconsistent folds.")
        print("           Trade at reduced size; monitor combo health closely.")
    else:
        print("  VERDICT: [OVERFIT] OOS performance does not hold.")
        print("           Do NOT go live on the in-sample numbers.")
    print("=" * 70)

    # --- per-candidate-combo OOS summary report ---
    print("\n" + "=" * 70)
    print("  PER-CANDIDATE-COMBO OOS BREAKDOWN (matrix-PASS combos)")
    print("=" * 70)
    for combo, log in combo_log.items():
        sym, eng = combo
        if not log:
            print(f"  {eng} {sym:7s}: never appeared in an OOS test window "
                  f"(insufficient history for this train/test split)")
            continue
        total_n   = sum(x[2] for x in log)
        total_net = sum(x[3] for x in log)
        approved_folds = sum(1 for x in log if x[1])
        pfs_c = [x[4] for x in log]
        pos_folds = sum(1 for x in log if x[3] > 0)
        print(f"  {eng} {sym:7s}: appeared in {len(log)} fold(s) "
              f"(whitelisted in {approved_folds}/{len(log)}) | "
              f"{total_n} test trades | net RM{total_net:+.2f} | "
              f"positive folds {pos_folds}/{len(log)} | "
              f"per-fold PF {['%.2f' % p for p in pfs_c]}")
        verdict = ("net-positive across OOS folds" if total_net > 0
                   else "net-negative across OOS folds")
        print(f"      -> {verdict}")
    print("=" * 70)

if __name__ == "__main__":
    try:
        run()
    except FileNotFoundError:
        print("backtest_master_v13.json not found — run backtest_master_v13.py first")
        sys.exit(1)
