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

| **v14** | 7 Jul 2026 | **The Knowledge Version** — four experiments run, four rejections, ZERO promotions (live universe unchanged from v13). SRE (stop-run reversal engine): FAIL, PF 0.92 over 2,290 trades, fairness-audited. Gold crosses (GVE): untradeable, spreads structural at London liquidity. Indices (5 × 4 engines): one PASS on truncated data (CBE UK100), 12/16 combos under-sampled — FX-tuned filters too strict, calibration follow-up recorded. RFE strength filter: FAIL 0/3 (PF 1.94→1.75, net −62%) — rejected globally; CTE-scoped variant (PF 1.71→2.42 subgroup) recorded as future hypothesis requiring its own A/B. Revalidation for the record: walk-forward ROBUST 7/8 OOS folds (median PF 1.91), MC median DD 21.5% / ruin 3.72%. Also: live SIM system started 6 Jul (first time since 11 Jun) on the 12-symbol universe; three latent live bugs fixed (LOT_SIZE NameError, 4 undefined HPE_W1_* constants, false-passing weekly-loss test); live-HPE-vs-backtest-HPE algorithm divergence discovered and ticketed; duplicate-process launch hazard in start_agents.bat documented. | — | — | — | — | — | — | git tag `v14` |

| **v15** | 7 Jul 2026 | **IRE + SCE + harness label fix** — first net promotion since v13. **Phase 0 (label fix):** `kira_dynamic_risk` engine labels wrong since ~v10 (copy-paste chain: MRE billed "GVE", CBE "MRE", HPE "CBE") — fixed; count-identity gate PASS (606→605, sole diff = window-drift trade). Rebase: CBE +RM594 (was under-sized), MRE −RM206 (over-sized); corrected clean portfolio RM+5,282→+5,656, PF 1.94→2.00, DD 21.4%→16.3%. **All v15 numbers use the corrected harness.** **IRE (Imbalance Rebalance Engine):** 106 trades, PF 1.25 agg; 3 combos PASS + walk-forward OOS-validated → **PROMOTED: IRE×EURGBP (PF 3.48, OOS 5/6), IRE×EURUSD (3.10, 4/6), IRE×AUDUSD (1.39, 5/8)**, all on 0.5× probation. Pre-compression tag PF 1.80 vs 1.10 (Mahesh's stage-1 hypothesis supported); CBE cannibalization negligible (8/106). **SCE (Session Continuation Engine):** FAIL 0/11, benched — 6,284 trades PF 1.01, WR 22.8% vs 21.8% breakeven, edge eaten by spread. Completes the Asian-range-M15 question: efficiently priced both ways (SRE fade 0.92 + SCE join 1.01). **Benchmark (mandated):** full-v15 OOS RM+2,243 vs v12-core RM+1,475 = **+52%**, both ROBUST; decision MC (live24 vs +IRE3): DD 20.5→20.1%, ruin 3.43→2.90% (every risk metric improves). Live universe 24→27 combos. | +3 combos | — | — | — | 20.1% (MC med) | — | git tag `v15` |

### v15 promotions (config.py — untracked; recorded here per the config-is-never-committed rule)
Added to `KIRA_ROUTING_TABLE` (`("IRE", None)` appended), `ENGINE_SYMBOL_WHITELIST["IRE"]`, and `PROBATION_COMBOS`:
- **IRE × EURGBP** — matrix PF 3.48 (70% WR), OOS +RM51.13 (5/6 folds). Strongest.
- **IRE × EURUSD** — matrix PF 3.10, OOS +RM55.53 (4/6 folds).
- **IRE × AUDUSD** — matrix PF 1.39, OOS +RM17.18 (5/8 folds). Marginal on pf_ex_best (1.02) — probation covers it.

Rejected this round: IRE×GBPUSD (PF 0.66), IRE×NZDUSD (0.42), IRE×USDCHF (1.20 < 1.3 bar). Indices + XAUUSD under-sampled (XAUUSD 0 signals — 70-pip metals FVG floor likely too strict; recorded, not tuned). Live constants added to config.py: `IRE_BASE_CONFIDENCE=62`, `IRE_MIN_FVG_JPY=20.0`, `IRE_SL_CAP_FOREX=30`, `IRE_SL_CAP_JPY=40` (all validated — signal tunables live in tracked `ire_logic.py`). Live port: `agent_kira._engine_ire` (stateless), wired into `_dispatch_engine`; `test_full_system.py` 24/24 before and after. **To revert:** remove the 3 `# v15` routing/whitelist/probation entries + 4 IRE_* constants from config.py, remove the ire_logic import + `_engine_ire` + dispatch branch from agent_kira.py, and `git checkout v14` for tracked files.

### v15 open tickets (carried forward)
5. **IRE gold/index coverage**: XAUUSD produced 0 signals (70-pip FVG floor); indices under-sampled. IRE's session-agnostic design was meant to cover indices "for free" — it needs a metals/index-native min_fvg calibration before those markets yield tradeable IRE signals.
6. **IRE pre-compression variant**: compression-preceded displacements ran PF 1.80 vs 1.10. A "compression-required" IRE variant is a future A/B (do not adopt from this run's subgroup — v9/v14 lesson).
7. **v14 tickets 1, 3, 4 still open** (live-HPE divergence; index calibration; CTE-scoped RFE). Ticket 2 (harness label mismatch) CLOSED by v15 Phase 0.

### v14 open tickets (carried forward)
1. **Live HPE ≠ backtested HPE**: live `agent_kira._engine_hpe` uses a never-backtested W1-swing design; the validated backtest version uses D1 pivots. Its 4 new config constants are UNVALIDATED placeholders. Either backtest the live design or port the validated one. Until then, live HPE signals are unvalidated.
2. **Harness engine-label mismatch** (since ~v10): `kira_dynamic_risk(engine=...)` receives wrong engine labels in some loops (e.g. MRE loop passes "GVE") — consistent across all versions so comparisons hold, but fix before v15 harness work.
3. **Index profile calibration**: CTE/MRE/HPE produced <10 trades on all indices — filters need index-native calibration (or wait for v15 IRE's session-agnostic coverage). UK100 broker history gap (ends 15 May) is broker-side.
4. **CTE-scoped RFE**: dedicated A/B experiment (do not adopt from the v14 aggregate subgroup).

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
