# System v18 — Lower-Timeframe Track (Design Spec)

**Date:** 8 July 2026
**Status:** Draft for review (direction approved in chat: lower-TF, kept SEPARATE, must not degrade current)
**Baseline:** v16 (tag `v16`) live. v17 (ORE/GAP) pending its run.

## 1. Goal & hard constraint

Materially increase **signal frequency** by running our two most timeframe-agnostic
engines (CBE compression-breakout, IRE imbalance-rebalance) on **lower timeframes**
(M15, and M5 for CBE) — potentially 3–4× the signals across the existing universe.

**HARD CONSTRAINT (Mahesh, explicit): the current H1/H4 system stays FROZEN and
untouched.** The lower-TF work is a SEPARATE, purely-additive track. It cannot alter,
reuse-in-place, or rebase the existing engines' behavior, config, live combos, or
validated results. If the LTF experiment fails, the current system is unaffected; if it
succeeds, it adds NEW distinct combos alongside — never replacing.

**Non-goals:** no changes to existing CBE/IRE/CTE/MRE/HPE/GVE/IRE live routing; no
lowering the promotion bar; no system-wide spread-convention change (see §4); no new
mean-reversion style (that's the separate v19 candidate).

## 2. Isolation architecture (the core of this spec)

- **New engine labels, distinct from the originals:** `CBE15`, `CBE5`, `IRE15`. Every
  LTF trade is tagged with its own label → its own matrix rows, its own candidate list,
  its own walk-forward combos. The strings `CBE`/`IRE` (H1/H4) never appear on an LTF row.
- **Existing rows byte-identical:** LTF harness sections are flag-gated (`LTF_ENABLED`
  default False); a flags-off run reproduces the v16/v17 baseline exactly. LTF is additive
  only.
- **Logic reuse WITHOUT modification:** `ire_logic.py` is pure and TF-agnostic — IRE15
  feeds it M15 bars, zero code change to the module. CBE's in-harness detectors
  (`cbe_detect_compression`, `cbe_h1_momentum`, `cbe_levels`) take dataframes + params —
  CBE15 calls them with (H1 compression-TF, M15 momentum/entry-TF); CBE5 with (M15, M5).
  The original CBE section (H4→H1) is not touched.
- **Live isolation (only on promotion):** promoted LTF combos get NEW methods
  (`_engine_cbe15` etc.) and their own routing/whitelist/probation entries under the LTF
  labels. The existing `_engine_cbe`/`_engine_ire` and their live combos are never edited.

## 3. Engines × timeframes

- **CBE15** — H1 compression → M15 momentum candle → M15 entry.
- **CBE5**  — M15 compression → M5 momentum candle → M5 entry.
- **IRE15** — M15 displacement → M15 FVG → M15 rebalance entry (ire_logic verbatim).
- Excluded: CTE (needs the HTF trend stack), MRE (D1-range native), HPE (W1/D1 native) —
  not cleanly timeframe-portable; kept out to hold scope.
- **Universe:** the existing candidate universe (majors + v16 crosses). Matrix decides fit.

## 4. Spread — the make-or-break at low TF

Lower TF = smaller moves = spread is a much larger fraction of edge. The harness's FX
profiles under-count spread ~100× (`spread_pips × pip_val × 0.01`), which is negligible at
H1 but **fatal to trust at M15/M5**. LTF sections therefore use **REALISTIC spread**
(`spread_pips × pip_val`, the full cost — same correction v17 applied to indices). The
existing engines' legacy convention is left UNCHANGED (per the freeze constraint — no
rebasing the current system). The 100×-under-count on legacy engines is logged as a known
issue for a future system-wide fix, not touched here.

## 5. Validation & promotion

- Flag-gated LTF sections; byte-stability regression (existing rows identical, flags off).
- Candidate mode → matrix (PASS/FAIL/INSUFFICIENT) → walk-forward (18m/6m) → Monte Carlo,
  all on the LTF labels only.
- Promotion bar UNCHANGED: ≥10 trades, PF ≥ 1.3, pf_ex_best > 1.0, OOS majority-fold-
  positive, aggregate ≥ 30. Passers → new live `_engine_*15/5` methods + LTF-labelled
  routing/whitelist/probation. `test_full_system.py` before/after. Failures benched.
- Benchmark: v16 live-36 vs v16 + promoted-LTF; frequency and OOS-profit delta recorded.

## 6. Honest expectations

Frequency WILL rise sharply (that's the mechanism — 4–12× the bars). The open question is
how many combos survive the bar **once spread is counted honestly** — and the honest prior
is that realistic spread eats a large share of low-TF edges (this is exactly why retail
scalping usually fails). Best odds: **CBE15** (compression breakout is a robust,
higher-conviction pattern that clears spread better than fine-grained signals); CBE5 and
IRE15 are more spread-exposed. A realistic outcome is a handful of CBE15 majors promoting
= a real, isolated frequency boost with the current system fully intact. A double-figure
promotion is possible but not the base case. Either way, the current system is untouched
and the result is honest.
