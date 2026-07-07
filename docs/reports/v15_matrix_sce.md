# v15 SCE — First Results: FAIL 0/11 (Task 5, Run 3)

**Date:** 7 July 2026 | **Run:** `.superpowers/sdd/v15_task5_run3_sce_on.log` (SCE_ENABLED=True, all else OFF)
**Gates:** base rows vs Run 1 — counts AND net RM identical to the cent (isolation clean).

## Matrix rows

| engine | symbol | variant | n_trades | wr | net_rm | pf | pf_ex_best | verdict |
|---|---|---|---|---|---|---|---|---|
| SCE | AUDUSD | base | 524 | 22.7 | 62.02 | 1.09 | 1.06 | FAIL |
| SCE | CADJPY | base | 476 | 24.6 | 67.25 | 1.07 | 1.05 | FAIL |
| SCE | EURGBP | base | 486 | 23.5 | 12.88 | 1.02 | 0.99 | FAIL |
| SCE | EURJPY | base | 587 | 25.2 | 107.01 | 1.09 | 1.06 | FAIL |
| SCE | EURUSD | base | 658 | 23.3 | -9.16 | 0.99 | 0.96 | FAIL |
| SCE | GBPJPY | base | 643 | 22.7 | -60.29 | 0.95 | 0.92 | FAIL |
| SCE | GBPUSD | base | 731 | 22.2 | -13.86 | 0.99 | 0.97 | FAIL |
| SCE | NZDUSD | base | 508 | 22.2 | 11.85 | 1.02 | 1.0 | FAIL |
| SCE | USDCAD | base | 563 | 20.4 | -57.04 | 0.86 | 0.81 | FAIL |
| SCE | USDCHF | base | 582 | 23.9 | 61.23 | 1.11 | 1.06 | FAIL |
| SCE | USDJPY | base | 526 | 19.8 | -82.21 | 0.83 | 0.78 | FAIL |

**0/11 PASS.** Aggregate: 6,284 trades, net +RM99.68, PF 1.01.

## Edge anatomy — why it fails

Avg RR 3.58 (measured-move TP vs 1xATR SL, avg 8.9 pips) needs WR 21.8% to break even;
SCE delivers 22.8% — one point of gross edge, consumed by spread. Splits: London_KZ
PF 1.07 vs NY_KZ 0.99 (74% of volume); BUY 1.07 vs SELL 0.94. Best post-hoc subgroup
(London-only on the 4 net-positive symbols) = PF 1.24, still under the 1.3 bar, and
subgroup adoption is barred anyway (v9/v14 lesson).

## Fairness notes (inline audit)

No-lookahead: entry at the classifying bar's close, sim starts next bar (SRE's audited
pattern). Spread deducted once per trade (house convention). Zero signal overlap with
SRE by construction (in-suite complementarity proof). Scaffolding (Asian range, KZ
gates, ATR regime filter, one-per-KZ-per-day) reused verbatim from the audited SRE
section. Sample: 6,284 trades across 11 symbols x 4.5 years — the verdict is not a
small-sample artifact.

## The completed SRE+SCE story

SRE faded the Asian-range M15 event: PF 0.92 over 2,290 trades. SCE joined it: PF 1.01
over 6,284. **The Asian-range break at M15 granularity is efficiently priced — neither
side pays after costs.** This closes the Asian-range-event question with evidence on
both sides; future session engines must find a different event or timeframe.

## Verdict
BENCHED. No promotion candidates. sce_logic.py stays (tested, reusable); harness
section stays flag-gated OFF.
