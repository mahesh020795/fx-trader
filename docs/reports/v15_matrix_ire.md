# v15 IRE — First Results (Task 3, Run 2)

**Date:** 7 July 2026 | **Run:** `.superpowers/sdd/v15_task3_run2_ire_on.log` (IRE_ENABLED=True, all else OFF)
**Gates:** Run 1 (flags off) byte-stable vs corrected baseline (sole diff = MRE×EURGBP oldest
trade off the rolling window). Run 2 base rows vs Run 1: counts AND net RM identical to the
cent — IRE fully isolated, SCE flags-off no-op proven simultaneously.

## Matrix rows (mechanical bar: ≥10 trades, PF ≥ 1.3, pf_ex_best > 1.0)

| engine | symbol | variant | n_trades | wr | net_rm | pf | pf_ex_best | verdict |
|---|---|---|---|---|---|---|---|---|
| IRE | AUDUSD | base | 14 | 50.0 | 17.18 | 1.39 | 1.02 | PASS |
| IRE | CADJPY | base | 1 | 100.0 | 16.91 | 99.0 | 0.0 | INSUFFICIENT_DATA |
| IRE | DE40 | base | 3 | 33.3 | -2.94 | 0.67 | 0.0 | INSUFFICIENT_DATA |
| IRE | EURGBP | base | 10 | 70.0 | 51.13 | 3.48 | 2.63 | PASS |
| IRE | EURJPY | base | 4 | 25.0 | -24.46 | 0.36 | 0.0 | INSUFFICIENT_DATA |
| IRE | EURUSD | base | 11 | 63.6 | 55.53 | 3.1 | 2.47 | PASS |
| IRE | GBPUSD | base | 11 | 27.3 | -19.12 | 0.66 | 0.41 | FAIL |
| IRE | NZDUSD | base | 13 | 15.4 | -32.7 | 0.42 | 0.14 | FAIL |
| IRE | UK100 | base | 1 | 0.0 | -1.06 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| IRE | US30M | base | 4 | 25.0 | -0.75 | 0.57 | 0.0 | INSUFFICIENT_DATA |
| IRE | US500 | base | 3 | 0.0 | -2.25 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| IRE | USDCAD | base | 7 | 28.6 | -2.1 | 0.93 | 0.3 | INSUFFICIENT_DATA |
| IRE | USDCHF | base | 17 | 41.2 | 14.09 | 1.2 | 0.97 | FAIL |
| IRE | USDJPY | base | 2 | 50.0 | 10.25 | 3.52 | 0.0 | INSUFFICIENT_DATA |
| IRE | USTECH100M | base | 5 | 60.0 | 14.5 | 2.72 | 1.64 | INSUFFICIENT_DATA |

**3 PASS** (EURGBP 3.48 / EURUSD 3.10 / AUDUSD 1.39), 3 FAIL (GBPUSD, NZDUSD, USDCHF),
9 INSUFFICIENT_DATA (incl. all 5 indices and XAUUSD's 0 signals — the 70-pip metals
min_fvg is likely strict; recorded, not tuned this round). Aggregate 106 ≥ 30 ✓.

## Tag breakdowns (spec §3 "Measured, not assumed")

```
  IRE aggregate: 106 trades | net RM+94.21 | PF 1.25
  IRE BY SESSION:
    Asian    n=  13 net RM   +17.40 PF 1.36
    London   n=  19 net RM   +45.74 PF 1.77
    NY       n=  64 net RM   +26.06 PF 1.11
    Other    n=  10 net RM    +5.01 PF 1.15
  IRE BY PRE-COMPRESSION:
    False    n=  79 net RM   +29.68 PF 1.1
    True     n=  27 net RM   +64.53 PF 1.8
  IRE BY CBE OVERLAP:
    False    n=  98 net RM   +76.74 PF 1.22
    True     n=   8 net RM   +17.47 PF 1.97
```

Readings: (1) **Pre-compression hypothesis SUPPORTED** — compression-preceded displacements
run PF 1.80 vs 1.10 without (27 vs 79 trades). Tagged-not-required per spec; making it a
requirement is a calibration change needing its own A/B. (2) Session-agnostic claim holds
directionally (every session net-positive) but London (PF 1.77) >> NY (PF 1.11, 60% of
volume). (3) CBE cannibalization: 8/106 trades overlap — negligible, and those 8 did fine
(PF 1.97). IRE is finding setups CBE does not take.

## Next
Walk-forward OOS (Task 6) decides promotion for the 3 PASS combos.
