# System v16 — Universe Expansion (Design Spec)

**Date:** 8 July 2026
**Status:** Draft for Mahesh's review
**Baseline:** v15 (tag `v15`). Live universe = 27 combos (12 symbols). Corrected harness
(v15 Phase 0) is the reference. Live SIM running since 7 Jul on the new code.

## 1. Goal

Maximize trade frequency by expanding the **backtest candidate universe** with every
viable symbol the demo offers, then promote **only** the engine×symbol combos that clear
the standard bar (≥10 trades, PF ≥ 1.3, pf_ex_best > 1.0, out-of-sample positive). "Max
symbols in, only profit out" — the validation machinery judges, never a lowered bar.

**Non-goals:** no new engine build (ORE / volatility-breakout deferred to v17, own spec —
§6); no live-money changes (SIM gate still rules); no lowering the promotion bar; no
per-symbol parameter tuning (shared profiles by instrument class, whitelist decides fit).

## 2. The cross-test invariant (Mahesh's explicit requirement)

**No engine is fenced to a market class.** Candidate mode scans `engine × symbol` across
the *entire* pool. The compatibility matrix reports **every** engine on **every** symbol,
including a full set of FX-cross rows for each engine. Consequence, stated so it holds for
v17's non-FX engines too: when ORE (or any future "non-FX" engine) is added, it is
automatically run against all 17 FX crosses and its cross rows appear in the matrix
side-by-side — we are never "sure" an engine fails on crosses by assumption, only by its
matrix + walk-forward rows. Promotion is purely empirical and identical for every combo.

## 3. Candidate pool (~24 new symbols, backtest-only)

**Tier 1 — 17 FX crosses** (fit the existing FX-tuned engines; where promotions are
expected): AUDCAD, AUDCHF, AUDJPY, AUDNZD, CADCHF, CHFJPY, EURAUD, EURCAD, EURCHF,
EURNZD, GBPAUD, GBPCAD, GBPCHF, GBPNZD, NZDCAD, NZDCHF, NZDJPY. (AUDJPY + NZDJPY already
partial V13_CANDIDATES — fold into the full engine sweep.)

**Tier 2 — non-FX probes** (max-out breadth; honest prior = near-zero promotions with
FX-tuned engines, per v14's index/gold-cross findings — recorded as evidence, not a bet):
platinum XPTUSD, palladium XPDUSD, plus untested indices AUS200/HK50/USTEC. Crypto (BTC/
ETH) and oil (WTI) symbol identity + tradeability confirmed at the probe step before
inclusion; excluded if spread/contract specs are unviable.

## 4. Instrument handling (the iron pip rule)

- **Profiles by class, not by symbol.** Non-JPY crosses: pip 0.0001, forex profile
  template. JPY crosses: pip 0.01, JPY-cross template. Metals: GVE-style (extend GVE to
  XPTUSD/XPDUSD as probe). Indices: v14 index-profile template.
- **`pip_val_rm` derived STRICTLY from `mt5.symbol_info` tick data** (tick_value ×
  pip/tick_size × 0.01 lot × USD_MYR) — never assumed. The v13 XAGUSD lesson: a naive
  contract-size estimate silently 10×-oversized risk.
- **Profile sanity gate** (MAX_RISK_FRACTION 0.25, two-population discriminator) runs on
  every new profile before the backtest — a mis-derived pip_val fails the run, not live.
- **Spread viability**: London-hours spread probe per candidate; drop symbols whose spread
  is too large a fraction of ATR to trade (GBPNZD/EURNZD are historically wide). Documented
  OUT verdicts, same protocol as v14's gold-cross rejection.

## 5. Engines, validation, promotion

- **Engines run:** CTE, MRE, CBE, HPE, IRE across all Tier-1 crosses; GVE extended to
  Tier-2 metals; existing engines as probe on Tier-2 indices/crypto/oil. One shared
  parameter set per class.
- **Pipeline (unchanged v13→v15 machinery):** candidate mode → matrix (PASS/FAIL/
  INSUFFICIENT) → walk-forward (18m train / 6m test, whitelist re-derived per fold) →
  Monte Carlo. Byte-stability regression: existing 27-combo rows must reproduce the v15
  corrected baseline exactly (new symbols are additive).
- **Promotion bar (unchanged):** ≥10 trades/combo, PF ≥ 1.3, pf_ex_best > 1.0, OOS
  majority-fold-positive, engine-aggregate ≥ 30 respected. Passers → routing + whitelist +
  PROBATION_COMBOS (0.5× until 20 signals); live `agent_kira` unchanged (existing engines
  already ported — only config routing/whitelist grows). `test_full_system.py` before/after.
- **Benchmark:** same-day walk-forward OOS net, v15 live-27 universe vs v16 expanded live
  universe; delta + Monte Carlo side-by-side in VERSION_HISTORY (the v15 acceptance pattern).

## 6. Risk & scope notes

- **Correlation:** GUARD's per-currency cap (`MAX_PER_CURRENCY`=2) parses currency legs via
  `_split_currencies`, so it **auto-covers all 17 crosses** — the hard stacked-exposure
  protection needs no change. The softer half-size `CORRELATED_GROUPS` list is symbol-
  specific; add cross groups only for combos that actually promote. Verify `_split_currencies`
  degrades safely on non-FX tickers (BTC/WTI/US500) — task in the plan.
- **Compute:** ~36 symbols in one run pushes a full backtest past ~2h; run background +
  poll (v15 shepherding pattern), python -u + redirected log, PYTHONIOENCODING=utf-8.
- **New-engine deferral:** ORE (Opening Range Engine, indices) and a Donchian/volatility-
  breakout (crypto/commodities) are the archetypes that genuinely suit non-FX. They are
  *new engines* (multi-week TDD each, ~1-in-5 survival base rate), out of scope for v16, and
  each gets its own spec+plan starting v17 — inheriting §2's cross-test invariant.

## 7. Honest expectations

Tier 1 (17 crosses × ~5 engines): the real yield — expect a meaningful minority to pass,
plausibly growing the live universe from 27 toward ~40–55 combos = materially higher
frequency. Tier 2: near-zero with current engines (the point is to *prove* it on the
record and identify which markets justify a v17 engine). A double-digit Tier-1 promotion
count would be the biggest single-version frequency gain since v7.
