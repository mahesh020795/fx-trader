# matrix_report.py
"""Compatibility-matrix report for backtest_master_v13.
Verdicts implement spec 2026-07-03 §7 criteria 1-3 (walk-forward and
Monte Carlo, criteria 4-5, are separate whole-system runs)."""
from collections import defaultdict
import csv

MIN_TRADES, MIN_PF = 10, 1.3

def _pf(pnls):
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    return wins / losses if losses > 0 else float("inf")

def build_matrix(trades):
    groups = defaultdict(list)
    for t in trades:
        groups[(t["engine"], t["symbol"], t.get("variant", "base"))].append(t["pnl_rm"])
    rows = []
    for (engine, symbol, variant), pnls in sorted(groups.items()):
        n = len(pnls)
        pf = _pf(pnls)
        ex_best = sorted(pnls)[:-1] if n > 1 else []
        pf_ex_best = _pf(ex_best) if ex_best else 0.0
        wr = sum(1 for p in pnls if p > 0) / n * 100
        if n < MIN_TRADES:
            verdict = "INSUFFICIENT_DATA"
        elif pf >= MIN_PF and pf_ex_best > 1.0:
            verdict = "PASS"
        else:
            verdict = "FAIL"
        rows.append(dict(engine=engine, symbol=symbol, variant=variant,
                         n_trades=n, wr=round(wr, 1), net_rm=round(sum(pnls), 2),
                         pf=round(pf, 2) if pf != float("inf") else 99.0,
                         pf_ex_best=round(pf_ex_best, 2) if pf_ex_best != float("inf") else 99.0,
                         verdict=verdict))
    return rows

def write_report(rows, path_md, path_csv):
    cols = ["engine", "symbol", "variant", "n_trades", "wr", "net_rm",
            "pf", "pf_ex_best", "verdict"]
    with open(path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("# v13 Compatibility Matrix\n\n")
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "---|" * len(cols) + "\n")
        for r in rows:
            f.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
