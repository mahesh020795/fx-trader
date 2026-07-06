# System v14 — SRE + RFE + Market Sweep (Design Spec)

**Date:** 6 July 2026
**Status:** Approved by Mahesh (chat, 6 Jul 2026)
**Baseline:** system v13 (git tag `v13` + probation commit `09d6a97`). Live universe 12 symbols / 24 combos, SIM_MODE=True. Same-day regression convention: v13 harness must reproduce a same-day v10-family baseline run (v13 era reference: 286 baseline-combo trades / WR 50.0% / +RM4399.46 — expect data-window drift; the invariant is internal consistency, not the June figures).

## 1. Goal

Three validated additions in one version, all through the v13 evidence machinery
(sanity gate → compatibility matrix → walk-forward → Monte Carlo → probation):

- **Phase A — Market sweep:** existing engines on gold crosses + tight-spread index CFDs.
- **Phase B — SRE (Stop Run Exhaustion Engine):** the sixth signal engine — session
  stop-run *reversals* on FX, built on GVE's five-layer architecture.
- **Phase C — RFE (Relative FX Strength filter):** a veto layer tested strictly A/B,
  adopted only if it measurably improves the portfolio.

**Non-goals:** IOE (Index Open Engine) — deferred to v15, informed by Phase A's index
results. No live-money changes; SIM gate still rules. No orderflow/volume triggers
(MetaQuotes demo tick volume unreliable — same reason GVE's rel-vol filter is off).
No auto-parameter-tuning of any kind (AOE rejected; SAGE proposes, humans approve).

## 2. Governing principle (unchanged from v13)

`backtest_master_v13.py` (extended in place — it is the living harness; a v14 copy is
NOT needed since v13 established the regression convention and git tags provide revert)
is the sole gatekeeper. Every candidate is a harness run producing matrix rows. Only
rows passing §8 enter `config.py`, at probation 0.5× until 20 closed signals
(the v13 probation mechanism generalizes — add combos to `PROBATION_COMBOS`).

**Iron rule (XAGUSD lesson, now mandatory):** every new symbol profile's pip/point
value is derived from `mt5.symbol_info` tick data (`tick_value × pip/tick_size ×
lot_fraction × USD_MYR`), never assumed from contract size. Raw probe values recorded
in the profile comment. The 0.25 sanity gate remains the enforcement backstop —
extend `check_profile` if index point-scales require it, with the same
two-population rationale documented.

## 3. Phase A — Market sweep

### Candidates
| Class | Symbols | Engines |
|---|---|---|
| Gold crosses | XAUEUR, XAUGBP, XAUAUD | GVE only (gold session logic; XAUUSD precedent) |
| Indices | US500, US30M, USTECH100M, UK100, JPN225, AUS200, EUSTX50 | CTE, MRE, CBE, HPE |
| Indices (conditional) | DE40 | in only if spread ≤ 15% of median M15 ATR at profile time |
| Energies | the 5 `Energies\` symbols (addendum deep-fetch first) | CTE, MRE, CBE, HPE — only if specs sane + ≥20k M15 bars |

### Exclusions (recorded, closed)
Single stocks (scan noise = alphabetical sample; session gaps/earnings break engine
assumptions; poor fit for RM500), leveraged ETFs (structural decay), XPDUSD/XPTUSD
(spreads ~8,000–9,750 points), IT40/CHINA50/CHINAH/ESP35/FRA40 (spreads 114–1,000),
XAUCHF/XAGAUD (spread + spec anomalies: contract sizes 100,000 with implausible
tick values — the XAGUSD trap class).

### Index-specific requirements
- Sessions: index profiles carry their liquid cash-session windows (US 13:30–20:00 UTC,
  EU 07:00–15:30 UTC, JP 00:00–06:00 UTC) in the existing `s_start`/`s_end` fields;
  D1/H4 logic runs on the CFD's full candles (accepted dilution, documented).
- Point definition: 1 "pip" = 1 index point (pip=1.0) unless tick data dictates otherwise;
  sanity gate must pass at min lot on RM500 or the symbol is excluded (not force-fitted).

## 4. Phase B — SRE (Stop Run Exhaustion Engine)

**Thesis:** London (07:00–09:00 UTC) and NY (12:00–14:00 UTC) opens frequently sweep
the Asian-session extreme to run stops, then reverse. GVE trades gold sweeps as
continuation; SRE fades FX sweeps as reversal.

### Architecture (GVE five-layer template — proven portable in v13 Tasks 7–8)
1. **Volatility filter** — ATR regime: skip DEAD (< 0.6× avg) and HYPER (> 2.5× avg) days.
2. **Session gate** — `LONDON_KZ_START/END` and `NY_KZ_START/END` (existing config constants).
   Trades tagged with their window for per-session matrix analysis.
3. **Liquidity pools** — Asian range high/low (00:00–07:00 UTC) + prior-day high/low,
   built per-day from M15 (the `gve_pools` pattern).
4. **Sweep-and-reject** — M15 wick penetrates pool by ≥ SRE_MIN_SWEEP_PIPS (defaults:
   forex 3 pips, JPY crosses 5 — mirroring the MIN_FVG class conventions), closes back
   inside (the `gve_sweep` pattern with reversal semantics).
5. **Reclaim confirmation** — rejection candle (close in top/bottom third against the
   sweep) or structure reclaim within SRE_CONFIRM_BARS (≤3) M15 bars → entry at reclaim
   close. Swept HIGH ⇒ SELL, swept LOW ⇒ BUY. Both directions from day one.

### Levels
SL beyond sweep extreme + 0.5×ATR(M15) buffer, capped at SRE_SL_MAX pips per class
(forex 30 / JPY 40). TP1 = Asian mid-range; TP2 = opposite pool; RR clamped
[1.5, 4.0]. One trade per symbol per session window (per-day spacing like GVE).

### Scope & discipline
- Candidates: the 11 FX pairs of the live universe (AUDUSD, EURUSD, GBPUSD, NZDUSD,
  USDCAD, USDCHF, EURGBP, EURJPY, GBPJPY, USDJPY, CADJPY). XAUUSD excluded (GVE owns it).
- Implemented in the HARNESS ONLY (own engine section, `engine="SRE"` trade tags —
  matrix rows automatic). Live `agent_kira.py` port happens only on promotion, as its
  own reviewed commit, flag-gated default-off, `test_full_system.py` before/after.
- Per-variant/base state isolation rules from v13 Task 7 apply (no shared spacing or
  monthly-loss state with other engines; SRE keeps its own).
- Parameters get defaults from GVE analogues; NO per-symbol tuning in v1 (one shared
  parameter set — per-symbol tuning is a curve-fitting door; the whitelist decides
  which symbols suit the shared logic).

## 5. Phase C — RFE (Relative FX Strength filter)

**Mechanism:** for the 8 currencies (USD, EUR, GBP, JPY, AUD, NZD, CAD, CHF), compute a
rolling strength score from H4 closes of the pairs already fetched: currency strength =
mean normalized ROC (RFE_LOOKBACK=20 H4 bars) across every fetched pair containing the
currency, sign-adjusted for base/quote. Rank 1–8 daily.

**Gate (flag `RFE_FILTER=False`):** when on, a BUY on pair BASE/QUOTE requires
strength(BASE) − strength(QUOTE) ≥ RFE_MIN_GAP (default: ranks ≥ 3 apart); SELL mirrored.
Signals failing the gap are vetoed (logged with both ranks). Applies to FX engines only
(CTE/MRE/CBE/HPE/SRE); never to gold/indices (no meaningful two-currency legs).

**Adoption bar (strict A/B — the anti-v9-double-filter protocol):**
1. Base run (flag off) and filtered run (flag on), same day.
2. Adopt only if ALL hold: portfolio PF improves; net RM within −10% of base or better
   (a filter that costs >10% of profit to raise PF is starving winners); trade count
   retained ≥ 60%; walk-forward on the filtered trade set stays 5/5 OOS-positive.
3. Ambiguous or failing ⇒ RFE stays off, results recorded, revisit with live data later.
MRE note: mean-reversion logically trades AGAINST strength alignment — report MRE's
A/B delta separately; if RFE helps trend engines but hurts MRE, the adoption decision
may exempt MRE (recorded as a scoped adoption, not a silent carve-out).

## 6. Phase D — Revalidation + promotion

Identical to v13 Task 10: expanded trades JSON → `walkforward_v13.py` (5/5 OOS folds
required, per-combo OOS breakdown arbitrates each candidate) → `montecarlo_v13.py`
(median DD / P95 / ruin not worse than the v13 run: 21.7% / 52.6% / 3.83%) →
survivors into `config.py` (routing + whitelist + PROBATION_COMBOS at 0.5×/20).
SRE additionally requires ≥30 trades engine-aggregate. Index promotions carry their
live-stack prerequisites in the same reviewed commit: live session handling for the
index symbols + a GUARD exposure bucket for non-currency instruments. Tag `v14`,
VERSION_HISTORY row with measured numbers, matrices committed.

## 7. Roadmap ledger (dispositions of the full next-gen roadmap)

| Item | Disposition |
|---|---|
| RFE | **v14 Phase C** (as filter, not engine) |
| SRE | **v14 Phase B** |
| TVE | Parked — contradicts v10 evidence (EXPANDING regime 0% WR; CTE-TRENDING systematic loser). Unblock: new OOS evidence only. |
| VAE | Parked — duplicate of CBE's expansion exit. |
| BOE | Parked — needs orderflow delta + reliable volume; MT5 retail feed lacks both. |
| LQE | Absorbed — pool-targeting lives inside SRE/GVE level logic. |
| FAE | Exists — NOVA. |
| CME | Exists — GUARD exposure shield + KIRA correlation. |
| ECE | Exists — GUARD DD tiers + capital adequacy + clustering. |
| SAE | Reframed — session-expectancy table as a SAGE weekly-report feature (future small task, not an engine). |
| MCE | Exists — KIRA regime classifier. |
| PRE | Mostly exists (grades/confidence/ORACLE score); sharpening = future ATLAS expectancy-ranking task. |
| ARE | Exists — GUARD (user-confirmed). |
| AOE | Rejected as designed (auto-tuning = overfitting machine; violates SAGE human-approval principle). Reframed: scheduled re-validation runs, human-approved. |
| PAE | Deferred — needs live per-engine track records; probation + combo-health are the current crude form. |
| DSE | Exists — KIRA routing + ATLAS alpha-decay demotion. "Self-learning" variant rejected for the AOE reason. |
| IOE (from v14 draft) | Deferred to v15, informed by Phase A index results. |

## 8. Promotion criteria (all must hold — v13 §7 carried forward)

1. ≥10 backtest trades per combo (SRE: also ≥30 engine-aggregate)
2. PF ≥ 1.3; PF > 1.0 with best trade removed
3. Walk-forward stays 5/5 OOS-positive with additions; per-combo OOS net-positive in
   a majority of appearing folds (the NZDJPY rule)
4. Monte Carlo not worse than v13 reference
5. Probation 0.5× until 20 closed signals (PROBATION_COMBOS)
6. RFE adoption: §5 bar exactly

## 9. Testing

- Harness regression before/after every phase: baseline combos reproduce the same-day
  base run; all existing matrix rows byte-stable when new flags are off.
- SRE/RFE logic: pure-python unit tests where extractable (strength ranking, gap gate,
  sweep-reject classifier on synthetic candles) in tests/ alongside existing suites.
- Every run's matrix committed to docs/reports/ (audit trail).

## 10. Honest expectations

Gold crosses: decent prior (same underlying edge). Indices on FX engines: unknown —
that's the test. SRE: the flagship experiment; reversal engines fail more often than
continuation in backtests, and a clean failure is a valid, recorded answer. RFE: even
a null result is valuable (it closes the "should we route by strength" question with
data). Signal frequency — not WR vanity — remains the lever; on RM500 the payoff is a
broader proven edge for the prop-firm path.
