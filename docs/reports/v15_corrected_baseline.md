# v15 Corrected Baseline — Harness Risk-Label Fix (Task 1)

**Date:** 7 July 2026 | **Run:** `.superpowers/sdd/v15_task1_run.log` (full run, corrected harness)
**Fix commit:** see git log (backtest_master_v13.py)

## What was fixed

`kira_dynamic_risk(engine=, regime=)` call sites carried a copy-paste chain shifted
one engine over, present since ~v10. Labels select risk multipliers via the SCORES
tables, so three engines were sized under the wrong engine's risk profile:

| Section (line) | Passed before | Passed after | Status |
|---|---|---|---|
| CTE (~981) | `"CTE"`, `regime` var | unchanged | already correct |
| XAGUSD-GVE (~1214) | `"GVE","GVE"` literal | unchanged | verified correct |
| MRE (~1399) | **`"GVE"`**, `regime` var | `"MRE"`, `"RANGING"` | FIXED |
| CBE (~1564) | **`"MRE"`**, `regime` var | `"CBE"`, `"COMPRESSING"` | FIXED |
| HPE (~1802) | **`"CBE"`**, `regime` var | `"HPE"`, `regime` var | FIXED |
| SRE (~2055) | `"SRE","STOP_RUN"` literal | unchanged | verified correct |

`kira_dynamic_risk` itself and the SCORES tables were NOT changed.

## Count-identity gate: PASS

`risk_mult` is used only in `pnl_rm = (pips × pipval − spread) × risk_mult`, applied
after signal detection and outcome simulation — labels cannot change trade counts.
Verified against the pre-fix trade list (`.superpowers/sdd/task7_runA_trades.json`,
v14 Task 7 Run A): 606 → 605 trades, the ONLY difference being CBE×AUDUSD's oldest
trade (2022-09-06) falling off the count-capped H1 rolling window between run times
(same effect as the documented v14 CBE×NZDJPY 18→17 drift). Zero other count changes
across all 55 engine×symbol rows.

## The rebase — how much the label bug distorted history

Per-engine (all trades incl. XAGUSD analysis rows):

| Engine | n (pre→post) | Net RM pre | Net RM post | Delta | Cause |
|---|---|---|---|---|---|
| CBE | 305→304 | 3,021.92 | 3,615.63 | **+593.71** | was billed as MRE (under-sized) |
| CTE | 101 | 445.56 | 445.56 | 0.00 | label was correct |
| GVE | 42 | 1,011.40 | 1,011.40 | 0.00 | label was correct |
| HPE | 15 | 181.28 | 167.74 | −13.54 | was billed as CBE |
| MRE | 143 | 642.71 | 436.67 | **−206.04** | was billed as GVE (over-sized) |
| **Total** | 606→605 | **5,302.87** | **5,677.00** | **+374.13** | |

Clean portfolio (XAGUSD excluded): 592→591 signals, WR 44.9%→45.0%,
net **RM+5,282.48 → RM+5,655.69**, PF **1.94 → 2.00**, Sharpe **2.27 → 2.33**,
max DD **21.4% → 16.3%**.

Interpretation: the bug systematically under-sized CBE (the strongest engine) and
over-sized MRE. All historical per-engine RM comparisons v10–v14 carry this skew;
verdicts stand (PF/count-based), but RM magnitudes rebase from here. **All v15
comparisons — including the v12-core benchmark — use this corrected harness only.**

## Corrected compatibility matrix

| engine | symbol | variant | n_trades | wr | net_rm | pf | pf_ex_best | verdict |
|---|---|---|---|---|---|---|---|---|
| CBE | AUDJPY | base | 22 | 40.9 | 141.89 | 1.72 | 1.15 | PASS |
| CBE | AUDUSD | base | 34 | 52.9 | 324.08 | 1.95 | 1.62 | PASS |
| CBE | CADJPY | base | 20 | 55.0 | 533.95 | 3.38 | 2.77 | PASS |
| CBE | DE40 | base | 15 | 33.3 | 7.85 | 1.1 | 0.66 | FAIL |
| CBE | EURGBP | base | 32 | 46.9 | 149.47 | 1.72 | 1.31 | PASS |
| CBE | EURJPY | base | 24 | 58.3 | 1205.12 | 3.96 | 3.37 | PASS |
| CBE | GBPJPY | base | 24 | 58.3 | 801.32 | 2.69 | 2.21 | PASS |
| CBE | GBPUSD | base | 15 | 40.0 | 142.34 | 1.77 | 1.16 | PASS |
| CBE | NZDJPY | base | 17 | 47.1 | 79.94 | 1.38 | 1.08 | PASS |
| CBE | NZDUSD | base | 17 | 35.3 | 18.47 | 1.15 | 0.76 | FAIL |
| CBE | UK100 | base | 17 | 52.9 | 20.91 | 2.08 | 1.56 | PASS |
| CBE | US30M | base | 14 | 42.9 | 2.25 | 1.18 | 0.58 | FAIL |
| CBE | US500 | base | 10 | 30.0 | -0.95 | 0.92 | 0.21 | FAIL |
| CBE | USDCAD | base | 20 | 45.0 | 228.39 | 2.01 | 1.47 | PASS |
| CBE | USDCHF | base | 19 | 36.8 | -5.33 | 0.97 | 0.68 | FAIL |
| CBE | USTECH100M | base | 4 | 0.0 | -34.07 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| CTE | AUDJPY | base | 4 | 50.0 | -31.64 | 0.53 | 0.19 | INSUFFICIENT_DATA |
| CTE | AUDUSD | base | 15 | 40.0 | 52.04 | 1.7 | 1.2 | PASS |
| CTE | CADJPY | base | 4 | 50.0 | 0.86 | 1.01 | 0.39 | INSUFFICIENT_DATA |
| CTE | EURGBP | base | 13 | 23.1 | -2.67 | 0.95 | 0.48 | FAIL |
| CTE | EURJPY | base | 4 | 75.0 | 152.77 | 3.51 | 1.68 | INSUFFICIENT_DATA |
| CTE | EURUSD | base | 6 | 33.3 | 18.33 | 1.48 | 0.47 | INSUFFICIENT_DATA |
| CTE | GBPJPY | base | 3 | 66.7 | 113.69 | 2.49 | 0.55 | INSUFFICIENT_DATA |
| CTE | NZDJPY | base | 2 | 50.0 | 3.19 | 1.1 | 0.0 | INSUFFICIENT_DATA |
| CTE | NZDUSD | base | 17 | 29.4 | 13.2 | 1.18 | 0.68 | FAIL |
| CTE | US30M | base | 2 | 100.0 | 4.69 | 99.0 | 99.0 | INSUFFICIENT_DATA |
| CTE | US500 | base | 2 | 50.0 | 5.3 | 7.88 | 0.0 | INSUFFICIENT_DATA |
| CTE | USDCHF | base | 15 | 40.0 | 55.7 | 2.19 | 1.64 | PASS |
| CTE | USTECH100M | base | 1 | 100.0 | 26.12 | 99.0 | 0.0 | INSUFFICIENT_DATA |
| CTE | XAGUSD | base | 13 | 38.5 | 33.98 | 1.95 | 1.45 | PASS |
| GVE | XAUUSD | base | 42 | 64.3 | 1011.4 | 1.8 | 1.67 | PASS |
| HPE | AUDJPY | base | 1 | 0.0 | -16.77 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| HPE | DE40 | base | 1 | 0.0 | -6.11 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| HPE | EURGBP | base | 1 | 0.0 | -4.63 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| HPE | EURUSD | base | 3 | 66.7 | 76.12 | 5.3 | 2.1 | INSUFFICIENT_DATA |
| HPE | UK100 | base | 1 | 0.0 | -1.74 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| HPE | US500 | base | 1 | 0.0 | -0.92 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| HPE | USDCAD | base | 1 | 100.0 | 18.54 | 99.0 | 0.0 | INSUFFICIENT_DATA |
| HPE | USDJPY | base | 2 | 100.0 | 129.91 | 99.0 | 99.0 | INSUFFICIENT_DATA |
| HPE | USTECH100M | base | 3 | 0.0 | -13.99 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| HPE | XAGUSD | base | 1 | 0.0 | -12.67 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| MRE | AUDJPY | base | 15 | 33.3 | -10.56 | 0.92 | 0.6 | FAIL |
| MRE | AUDUSD | base | 15 | 46.7 | 103.13 | 2.82 | 2.21 | PASS |
| MRE | CADJPY | base | 17 | 17.6 | -78.7 | 0.36 | 0.11 | FAIL |
| MRE | DE40 | base | 2 | 100.0 | 10.94 | 99.0 | 99.0 | INSUFFICIENT_DATA |
| MRE | EURGBP | base | 19 | 47.4 | 119.01 | 2.38 | 1.93 | PASS |
| MRE | EURUSD | base | 11 | 54.5 | 104.11 | 3.46 | 2.74 | PASS |
| MRE | GBPUSD | base | 6 | 33.3 | 26.26 | 1.92 | 0.85 | INSUFFICIENT_DATA |
| MRE | NZDJPY | base | 18 | 50.0 | 96.68 | 1.64 | 1.26 | PASS |
| MRE | NZDUSD | base | 21 | 38.1 | 81.8 | 1.91 | 1.57 | PASS |
| MRE | UK100 | base | 1 | 100.0 | 2.1 | 99.0 | 0.0 | INSUFFICIENT_DATA |
| MRE | US30M | base | 1 | 0.0 | -0.26 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| MRE | US500 | base | 3 | 100.0 | 2.84 | 99.0 | 99.0 | INSUFFICIENT_DATA |
| MRE | USDCHF | base | 8 | 0.0 | -53.1 | 0.0 | 0.0 | INSUFFICIENT_DATA |
| MRE | USDJPY | base | 6 | 33.3 | 32.42 | 1.79 | 0.85 | INSUFFICIENT_DATA |
