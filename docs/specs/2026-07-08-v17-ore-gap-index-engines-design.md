# System v17 — ORE + GAP Index Engines (Design Spec)

**Date:** 8 July 2026
**Status:** Draft for review (design approved in chat — "do pair now")
**Baseline:** v16 (tag `v16`). Live universe = 36 combos (19 symbols). Corrected harness.

## 1. Goal

Build the first two **index-native** engines — ORE (Opening Range) and GAP (Overnight
Gap continuation) — paired because they share all index infrastructure (data pipeline,
empirical session-open detection, one-trade-per-index-per-day structure) and fire on
complementary daily events (the intraday range break vs the overnight gap). Validate
through the standard machinery; promote only combos clearing the bar.

**Non-goals:** no reused FX engines on indices (v14 proved FX-tuned filters under-sample);
no VWAP / dip-buy engines (v18 candidates); no live-money changes (SIM gate); no lowering
the promotion bar. Both engines are continuation-side (our validated philosophy — GAP does
gap-and-go, NOT gap-fill; fill/fade is a tagged v18 variant).

## 2. Index universe (5 candidates)

US500, US30, USTEC, DE40, AUS200. **Dropped:** UK100 (broker M15 history ends 2026-05-15,
8-week gap), HK50 (spread 28 pts vs M5 ATR 15.5 = 180%, structurally untradeable). DE40 is
marginal (spread ~12% of M5 ATR) — kept as candidate; the matrix decides. pip = 1.0 index
point; pip_val_rm IRON-RULE tick-derived (probe 8 Jul: US500/US30/USTEC/AUS200 = RM0.0398,
DE40 = RM0.0454). Spread from tick data, conservative.

## 3. Shared infrastructure

**Empirical session-open detection** (the calibration foundation, DST-robust): for each
index, build an intraday volume-and-range profile from history and detect the daily cash
open as the (hour:minute, broker/UTC) of the sustained volume/volatility surge — NOT a
hardcoded clock time (which breaks on DST and broker-time quirks). Cached per index at
preload. One trade per index per day per engine; engine-private state; matrix rows tagged
`engine="ORE"/"GAP"`.

## 4. ORE — Opening Range Engine

Pure logic in `ore_logic.py` (TDD). Per index, per day:
1. **Opening range:** first 30 min after the detected open (6 × M5 bars) → OR high/low.
   Skip if OR height < 0.5× or > 3× M5-ATR(14) (junk/gap-day guard).
2. **Breakout:** the first M15 bar within the session to **close beyond** the OR by ≥
   `min_break` (index-native, ATR-scaled) with body ratio ≥ 0.6 (SCE/CBE convention).
3. **Entry** at that close; **SL** = opposite OR side + small ATR buffer (capped);
   **TP** = measured move (OR height projected) with RR clamp [1.5, 4.0].
4. One trade/index/day; skip after the session's first N hours (opening edge only).

## 5. GAP — Overnight Gap Continuation Engine

Pure logic in `gap_logic.py` (TDD). Per index, per day:
1. **Gap:** today's session-open price (first bar at the detected open) vs prior D1 close.
   Gap size in ATR units (D1-ATR(14)).
2. **Signal (gap-and-go):** gap ≥ `min_gap_atr` (e.g. 0.5× D1-ATR) AND the first M15 bar
   after the open **continues** in the gap direction (closes beyond the open, body ≥ 0.6)
   → enter continuation. Small gaps (< min) skipped (fill/fade = v18 variant, NOT here).
3. **Entry** at that close; **SL** = the day's pre-continuation extreme (gap origin side)
   + buffer, capped; **TP** = measured move (gap size × mult) with RR clamp [1.5, 4.0].
4. One trade/index/day.

## 6. Validation, cross-test invariant, promotion

- **Cross-test invariant (v16 §2):** ORE and GAP also run against the 17 FX crosses + 11
  majors. They should *fail* there (FX has no single cash open) — the matrix proving it is
  the guarantee. Index-native params mean FX rows will mostly be INSUFFICIENT/FAIL.
- **Pipeline:** flag-gated harness sections (`ORE_ENABLED`/`GAP_ENABLED` default False);
  byte-stability regression (flags off reproduce v16 baseline); candidate mode → matrix →
  walk-forward (18m/6m) → Monte Carlo. Needs M5 + M15 + D1 for the 5 indices (additive
  fetch, flag-gated).
- **Promotion bar (unchanged):** ≥10 trades, PF ≥ 1.3, pf_ex_best > 1.0, OOS majority-fold-
  positive, engine-aggregate ≥ 30. Passers → live `agent_kira` NEW `_engine_ore`/
  `_engine_gap` (own reviewed commits), routing/whitelist/probation, `CROSS_PIP_VAL_RM`-
  style index pip table, `test_full_system.py` before/after. Failures benched with evidence.
- **Benchmark:** same-day walk-forward OOS, v16 live-36 vs v17 expanded; VERSION_HISTORY
  three-liner + MC side-by-side.

## 7. Honest expectations

Indices resisted our FX engines (v14) and index spreads are wide — the tight-spread few
(US500, US30, USTEC, AUS200) are where any edge survives; DE40 is marginal. ORE and GAP
are real documented equity edges, but must clear OUR bar on THIS broker's data after
spread. Base rate ~1-in-5 per engine; a paired build means one run answers both. A double
failure still ships the index data pipeline + session-detection + the "indices need X"
evidence for v18 (VWAP / dip-buy). If either survives, it's your first non-FX profit source.
