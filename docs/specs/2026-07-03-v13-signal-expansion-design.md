# System v13 — Validated Signal Expansion (Design Spec)

**Date:** 3 July 2026
**Status:** Approved by Mahesh (chat, 3 Jul 2026)
**Baseline:** system v12 (git tag `v12`), trading core = v10 (287 signals, WR 49.5%, +RM4,192, Sharpe 2.53, DD 12.6%, PF 2.19, walk-forward 5/5 OOS folds)

## 1. Goal

Increase the number of **validated** signals per month — the only lever that
raises profit without raising risk-of-ruin. Secondary goal (user request):
extend coverage to markets the system currently ignores, and add sell-side
coverage where engines are BUY-only — all behind the same evidence bar.

**Non-goals:**
- No changes to the live v10 trading core until promotion criteria pass.
- No NIE (News Impact Engine) this version — parked until historical news
  data is sourced; candles-only validation is impossible for it.
- No re-enabling the EXPANDING regime (0% WR in backtest — evidence says no).
- No live-money changes of any kind; SIM gate (30 signals, WR>50%) still rules.

## 2. Governing principle

`backtest_master_v13.py` (a copy of v10's harness, extended) is the sole
gatekeeper. Every candidate — new symbol, new session, new direction, new
engine — is expressed as a harness run that outputs a compatibility-matrix
row. Only rows that pass §7 enter `config.py`, and then only at 0.5×
probationary sizing. This is the identical process that produced the v10
whitelist, which is the most profitable configuration the project has had.

## 3. Phase structure

### Phase 0 — Versioning infrastructure (DONE, this session)
Git repo at `C:\fx_agents`, remote `github.com/mahesh020795/fx-trader`,
tag `v12` = baseline. `VERSION_HISTORY.md` = version table + revert
procedure. `config.py`/`Archive/` untracked (secrets).

### Phase 1 — v13 harness
Copy `backtest_master_v10.py` → `backtest_master_v13.py`. Changes:
- **Symbol profiles as data, not code:** one profile dict per symbol (pip
  size, pip value/lot, typical spread, session hours, contract notes),
  validated by an automated sanity check (computed risk per trade at min lot
  must be < 2% of balance — the check that would have caught the XAGUSD
  pip-value disaster).
- **Variant flags:** `GVE_SELL`, `GVE_NY_WINDOW`, `HPE_SELL` — off by
  default, each run toggles one.
- **Report output:** per engine×symbol×variant: trades, WR, net RM, PF,
  max DD, PF-with-best-trade-removed. Written to
  `docs/reports/v13_matrix_<date>.md` (+ CSV, git-ignored).
- Harness requires MT5 terminal open (pulls candles via `copy_rates_from`).

### Phase 2 — Stream A: universe expansion + XAGUSD
- New candidates: **USDCHF, EURGBP, AUDJPY, CADJPY, NZDJPY** across all 5
  engines (minus documented hard blocks).
- **XAGUSD recalibration** per the documented fix list:
  GVE with full ~99,999-candle M15 window; MRE `min_range` 50–100 pips;
  CTE pip-value fix. **CBE permanently blocked on XAGUSD** (PF 0.28,
  MaxDD 93.3% — code comment says "DO NOT re-enable without full
  investigation" and this spec honors it).

### Phase 3 — Stream B: GVE capacity
- SELL-side mirror of sweep→expansion logic (harness variant, not live code).
- NY window (12:00–14:00 UTC) re-test with current v12 GVE filters — the
  original block was measured on older GVE versions. Promotion of either
  needs ≥30 backtest signals (gold is session-sensitive; small samples lie).

### Phase 4 — Structural gaps: sell-side mirrors + new markets
- **HPE SELL mirror** (HPE is BUY-only today; TRENDING-down is uncovered).
- **New-market scan:** enumerate what MetaQuotes-Demo actually offers
  (indices, metals, crypto CFDs) via `mt5.symbols_get()`; build profiles for
  viable candidates; run the existing engines over them. No new engine code
  unless the scan proves a market class where no current engine fits — in
  that case, design of the new engine goes back through brainstorming as
  its own mini-spec appended here.

### Phase 5 — Promotion + system revalidation
- Combos passing §7 → `KIRA_ROUTING_TABLE` + `ENGINE_SYMBOL_WHITELIST`
  with `PROBATION` 0.5× sizing (existing HPE mechanism) until 20 SIM signals.
- Full-system **walk-forward** re-run (extend `walkforward_v11.py` to the
  new universe): must remain 5/5 OOS folds profitable *with additions*.
- **Monte Carlo** re-run: median DD / P95 DD / risk-of-ruin must not worsen
  vs current (21.9% / 53.8% / 4.09% fixed-mode).
- Tag `v13`, update `VERSION_HISTORY.md` with measured numbers.

## 4. Explicitly parked

| Item | Why parked | Unblock condition |
|---|---|---|
| NIE news engine | No historical news data in harness | Source archived FF calendar, align to candles |
| EXPANDING regime | 0% WR in v10 backtest | New evidence only |
| GVE rel-volume filter | MetaQuotes demo tick volume unreliable | 30+ trades on real broker |
| Live deployment | SIM gate 0/30 | 30 SIM signals, WR>50% (start system now — parallel to all of this) |

## 5. Interfaces

- Harness → report files (`docs/reports/`) → human review → `config.py` edit.
- Live agents are consumers of `config.py` only; no agent file changes in
  Phases 1–4 except adding the HPE/GVE SELL code paths **gated off** behind
  config flags defaulting to disabled.

## 6. Error handling

- Profile sanity check hard-fails a symbol before any backtest runs on it.
- Harness runs that produce <10 trades for a combo mark it INSUFFICIENT_DATA,
  never PASS.
- MT5 fetch failures skip the symbol with a logged reason, never silently
  return partial candles (the v9 lesson: silent drops cost RM+563).

## 7. Promotion criteria (all must hold)

1. ≥10 backtest trades (≥30 for GVE session/direction variants)
2. PF ≥ 1.3
3. Stability: PF > 1.0 with single best trade removed (the GBPJPY-MRE test)
4. Full-system walk-forward stays 5/5 OOS profitable with the combo included
5. Monte Carlo risk metrics not worse than current baseline
6. Enters live config at 0.5× probation until 20 SIM signals

## 8. Testing

- Harness self-test: run v13 harness with zero new symbols/variants → output
  must reproduce v10 baseline numbers (287 signals, WR 49.5%, ±rounding).
  This is the regression gate proving the copy didn't drift.
- Each phase's runs are committed as report files so results are auditable.

## 9. Honest expectations (recorded so the version table stays honest)

More validated combos raise signal frequency and compounding speed; they do
not guarantee higher WR. On RM500 capital the absolute RM impact is small —
the real payoff is a broader proven edge for the prop-firm path ($100k
funded), where the same expectancy is ~200× the capital. "Best AI FX trader"
is earned through this validation discipline, not through engine count.
