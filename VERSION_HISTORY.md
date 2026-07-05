# FX Command Agents — Version History

Every system version, what changed, and how to revert. From v13 onward each
version is a **git tag** — revert with `git checkout <tag>` (or
`git checkout -b rollback-<tag> <tag>` to branch from it). Versions v3–v12
predate git; their snapshots live in `Archive/` (not in git — old configs
contain secrets).

**Rule: `config.py` is never committed** (live Telegram + Anthropic keys).
Parameter changes are recorded in this file's notes instead.

## Version Table

| Version | Date | What changed | Signals | WR | Net P&L | Sharpe | Max DD | PF | Revert via |
|---|---|---|---|---|---|---|---|---|---|
| v3 | May 2026 | Original 2-engine system | 79 | 55.7% | +RM1,214 | 1.15 | 13.9% | 1.77 | `Archive/v3` |
| v7 | Jun 2026 | Full 8-symbol universe, no filtering | 396 | 43.4% | +RM3,863 | 2.27 | 19.8% | 1.85 | `Archive/` + fx_agents_v11.zip lineage |
| v8 | Jun 2026 | KIRA adaptive routing, GUARD clustering, XAGUSD fix attempt | 396 | 43.4% | +RM3,927 | 2.30 | 18.1% | 1.86 | — |
| v9 | Jun 2026 | Engine×symbol whitelist (had ALL_SYMBOLS bug, dropped RM+563) | — | — | — | — | — | — | — |
| **v10** | Jun 2026 | **CONFIRMED BASELINE** — fixed v9 bug, dropped GBPJPY-MRE, removed CTE double-filter | **287** | **49.5%** | **+RM4,192** | **2.53** | **12.6%** | **2.19** | `backtest_master_v10.py` is the reference |
| v11 | Jun 2026 | Walk-forward validator, Monte Carlo (fixed mode) | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 | — |
| v11.1 | Jun 2026 | Monte Carlo compounding mode, GUARD capital-adequacy rule | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 | — |
| v12 | 14 Jun 2026 | SAGE self-review agent, Prop Firm Mode in GUARD | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 | git tag `v12` (initial commit) |
| **v13** | 6 Jul 2026 | **Validated Signal Expansion** — promoted 4 new engine×symbol combos (see notes). Walk-forward ROBUST 5/5 OOS folds (+RM1,839.85 whitelist net, median PF 1.87); Monte Carlo median DD 21.7% / P95 52.6% / ruin 3.83% (all slightly better than v10 baseline via diversification). v10 core unchanged — v13 adds to it. | 287+4 combos | — | — | — | 21.7% (MC med) | — | git tag `v13` |

### v13 promotions (config.py — untracked; recorded here per the config-is-never-committed rule)
Added to `KIRA_ROUTING_TABLE`, `ENGINE_SYMBOL_WHITELIST`, and `PAIRS`/`JPY_PAIRS`:
- **CBE × CADJPY** — matrix PF 3.40, OOS +RM298 (4/5 folds). Strongest.
- **CTE × USDCHF** — matrix PF 2.19, OOS +RM68 (4/5 folds).
- **MRE × EURGBP** — matrix PF 2.17, OOS +RM81 (4/5 folds).
- **CBE × EURGBP** — matrix PF 1.76, OOS +RM51 (3/5 folds).

Held (net-positive but not promoted this round): CBE×AUDJPY (OOS 2/4 folds), CTE×XAGUSD (unstable PF 1.26→1.95 across runs, whitelisted only 1/4 OOS folds, unresolved Silver pip-value uncertainty). Rejected: CBE×NZDJPY (in-sample PF 1.79 but OOS-NEGATIVE −RM18.73 — the walk-forward curve-fit catch). No GVE/HPE variant promoted (SELL/NY all failed). **Probation sizing (added post-promotion):** the 4 combos trade at 0.5× size (`config.PROBATION_COMBOS`/`PROBATION_MULT`) until each accumulates `PROBATION_GRADUATION`=20 closed signals, then auto-graduate to 1.0×. Applied in `main_agents._execute` as one more factor in the existing exposure×combo-health multiplier chain; logic in `AgentATLAS.get_probation_mult` (tested, tests/test_probation.py). To revert: remove the four `# v13` entries + the PROBATION block from config.py and `git checkout v12` for tracked files.

**Open items for a future session:** (1) two currently-live combos now FAIL the matrix — CBE×NZDUSD (PF 1.20) and CTE×NZDUSD (PF 1.18); NOT auto-demoted (v10 lesson: don't re-filter on one window; ATLAS alpha-decay brake is the designed mechanism) — monitor in SIM. (2) XAGUSD GVE-scan and config.py still carry the naive pip_val (10× oversized) — fix before any Silver retry. (3) 51 non-FX markets surfaced by the scan await a new-engine spec.

## Naming note

"GVE v12" is the Gold Volatility Engine's **internal** version number (39
signals, WR 69.2%, PF 1.90) and is unrelated to system v12. Always say
"system vN" or "GVE vN".

## Changelog discipline (from v13 onward)

1. Every meaningful change = a git commit with a message explaining *why*.
2. Every completed system version = a git tag `vN` + a row in the table above.
3. Performance numbers in the table come from `backtest_master_v13.py` (or
   its successor) runs — never estimates.
4. Live-config promotions (whitelist/routing changes) are listed explicitly
   in the version's notes, since `config.py` itself is untracked.
