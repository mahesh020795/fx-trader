# System v15 — IRE + SCE (Design Spec)

**Date:** 7 July 2026
**Status:** Approved by Mahesh (chat, 7 Jul 2026)
**Baseline:** v14 (tag `v14`, commit de2c0ed). Live universe = v13's 24 combos, unchanged by v14. Live SIM accumulating since 6 Jul.

## 1. Goal

Two continuation-side signal engines — the side every v13/v14 result favors — validated
through the standard machinery, then benchmarked: **same-day walk-forward OOS profit,
v12 core (original 20 combos) vs full v15, delta recorded in VERSION_HISTORY** with
Monte Carlo side-by-side (Mahesh's mandated acceptance test).

**Non-goals:** no reversal logic (SRE settled that), no new markets (v14 settled gold
crosses/indices for now — though IRE covers the 5 profiled indices for free as
candidates), no RFE (rejected; CTE-scoped variant stays a parked hypothesis), no
auto-tuning, no live-money changes (SIM gate still rules).

## 2. Phase 0 — Harness label fix (prerequisite, rebases numbers)

Audit every `kira_dynamic_risk(engine=, regime=, …)` call site in
`backtest_master_v13.py` (lines ~981, 1399, 1564, 1802; 1214 and 2055 are literal and
correct-by-inspection but re-verify) against the engine section each sits in; fix
wrong labels (known: MRE's loop passes "GVE"). Consequence: risk multipliers shift →
**all harness RM numbers rebase**. One full run establishes the corrected reference
matrix + subtotals; before/after totals documented in VERSION_HISTORY. All v15
comparisons (including the v12-core benchmark) run on the corrected harness only.

## 3. IRE — Imbalance Rebalance Engine

Session-agnostic, instrument-agnostic, H1-based. Mahesh's causal chain: compression →
displacement → inefficient pricing → partial rebalance → continuation. Entry ON the
rebalance — the gap between CBE (enters displacement) and CTE (FVG only inside full
HTF-trend stack).

1. **Displacement:** H1 candle or 2-candle burst with range ≥ IRE_DISP_ATR_MULT (2.0)
   × ATR(H1,14), aggregate body ratio ≥ 0.65, close beyond the prior 20-bar extreme.
   Direction = displacement direction.
2. **Imbalance:** the 3-candle FVG inside the displacement (existing `fvg_h1` pattern,
   adapted to return gap bounds [lo, hi]); min gap per instrument-class MIN_FVG
   convention. No FVG ⇒ no setup.
3. **Rebalance entry:** within IRE_WAIT_BARS (12) H1 bars, price trades into the gap
   ⇒ enter at gap midpoint in displacement direction. Invalidations: no retrace within
   the window (missed — never chase), or retrace through the displacement origin
   (structure failed).
4. **Levels:** SL beyond displacement origin + 0.5×ATR buffer, capped per class
   (forex 30 / JPY 40 / index 4×ATR-points / gold $35-convention); TP = displacement
   extreme; RR clamp [1.5, 4.0].

**Measured, not assumed:** every trade tagged with `session` (Asian/London/NY/Other),
`pre_compressed` (CBE-style H4 compression preceded — tagged, NOT required, so the
matrix can test Mahesh's stage-1 hypothesis without restricting IRE to CBE's own
signals), and `cbe_overlap` (a CBE trade on the same symbol within ±2 days). The
report must break out PF by session and by overlap status — cannibalization becomes
a number.

**Universe:** all 17 profiled symbols (11 FX + XAUUSD + 5 indices). One shared
parameter set, no per-symbol tuning (whitelist decides fit — v14 SRE convention).
One open position per symbol (engine-local, backtest-side).

## 4. SCE — Session Continuation Engine

Joins the move SRE's 2,290-trade failure proved shouldn't be faded. Reuses SRE's
audited scaffolding verbatim: Asian range (00:00–07:00 UTC via
`sre_logic.asian_range`), London/NY KZ gates, ATR regime filter [0.6, 2.5]×, one
trade per symbol per KZ per day, engine-private state.

- **Signal:** M15 candle **closes beyond** the Asian high/low by ≥ SCE_MIN_BREAK
  (3 pips forex / 5 JPY) with body ratio ≥ 0.60 — the exact case SRE's
  `classify_sweep` excludes (close-back-inside = sweep, faded, lost; close-through =
  breakout, joined here). Complementarity is by construction, zero signal overlap
  with the benched SRE.
- **Entry** at breakout close. **SL** 1×ATR(M15) behind entry, capped 30/40 pips.
  **TP** measured move: Asian range height projected from the breakout level.
  RR clamp [1.5, 4.0]; skip if clamped RR < 1.5.
- Both directions; the 11 FX pairs; trades tagged with KZ window.

## 5. Validation, benchmark, promotion

- Pure logic in tracked TDD modules: `ire_logic.py`, `sce_logic.py` (tunables live in
  the modules — versioned; config.py stays untracked). Suite additive to the existing
  30 tests.
- Harness sections flag-gated (`IRE_ENABLED`/`SCE_ENABLED` default False); byte-
  stability regression with flags off; base rows byte-identical with flags on
  (isolation, v14 pattern); trades tagged `engine="IRE"/"SCE"` → matrix rows automatic.
- **Benchmark protocol (the acceptance test):** one same-day run with both engines on
  (corrected harness) → trades JSON → walk-forward on (a) the v12-core-combo subset
  and (b) the full v15-eligible set → VERSION_HISTORY three-liner: v12-core OOS net /
  full-v15 OOS net / delta, + Monte Carlo side-by-side.
- Promotion bar unchanged (v13 §7 / v14 §8): ≥10 trades/combo, PF ≥ 1.3, ex-best
  > 1.0, OOS majority-fold-positive, ≥30 engine-aggregate, MC not worse, probation
  0.5×/20 via PROBATION_COMBOS. Live `agent_kira` ports only on promotion, flag-gated,
  own reviewed commits, `test_full_system.py` before/after. Failures go to the bench
  with evidence — expected base rate: ~1 of 2 engines survives.

## 6. Testing

TDD for both logic modules (synthetic candles: displacement/FVG/rebalance/invalidation
paths for IRE; close-through vs sweep discrimination + measured-move levels for SCE).
Fairness-audit review for any engine producing a decisive negative (v14 Task 5
precedent). Every run's matrix committed.

## 7. Honest expectations

SCE: moderate prior (direction evidenced by SRE's failure, but spread + entry-at-close
must still clear the bar). IRE: the conceptual flagship; FVG-retrace is heavily traded
retail lore — the test tells us if it's real on these instruments after costs. A double
failure would still ship the corrected harness + the v12-vs-current benchmark table.
