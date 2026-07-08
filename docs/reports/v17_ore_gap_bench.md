# v17 ORE + GAP — BENCH (Knowledge Version #2)

**Date:** 8 July 2026 | **Run:** `.superpowers/sdd/v17_run.log` (ORE+GAP ON; results
salvaged from console — the run's report block crashed on an unrelated environment
failure, Windows Defender quarantining the Python stdlib mid-run; engine verdicts printed
before the crash and are complete).

## Verdict: both engines FAIL. Zero promotions. Second Knowledge Version.

### ORE (Opening Range) — clear FAIL
6,346 trades, **PF 0.96, net −RM690.** The textbook "high frequency, no edge, spread eats
it" signature — huge signal count, negative expectancy.
- **Index rows** (US30, USTEC): net −RM83.61, PF 0.91.
- **FX rows** (11 majors — the cross-test invariant): net −RM606, PF 0.96.
- **Cross-test invariant CONFIRMED:** ORE fails on FX just as on indices — it is not
  secretly an FX engine; opening-range breakout carries no edge on either after costs.
- US500 and DE40 were skipped (they sit in ALL_SYMBOLS from v14's INDEX_CANDIDATES, so the
  dedicated ORE/GAP index fetch's `if sym not in data` guard skipped their M15). Does not
  change the verdict — ORE failed decisively on the other indices AND all 11 FX pairs.

### GAP (Overnight Gap-and-go) — FAIL / under-sampled (predicted)
Confirmed the pre-run gap probe (median overnight gap 0.03 ATR): these 24h CFDs barely gap,
so there is almost nothing to trade. 7–38 signals per symbol, tiny mixed samples, no
combo reaches a validatable edge. US30 13tr +RM9 / USTEC 7tr −RM2.5; FX mixed and small.

## The finding (evidence for v18+)
**Event-based engines don't fit continuous index CFDs on this broker.** The two discrete
events these engines need — the cash-market open (ORE) and the overnight gap (GAP) — are
both smeared away by 24-hour CFD trading: no clean open signature in the data (volume/
volatility track the broker's US-afternoon client peak, not home-market opens), and near-
zero gaps. The index opportunity, if pursued, needs **continuous-stream** engines (VWAP
reversion, trend-following, dip-buying) or a different data source — not opening-range/gap.

## Disposition
Both benched. `ore_logic.py` / `gap_logic.py` stay (tested, reusable); harness sections
stay flag-gated OFF. Realistic index-spread accounting (GVE-style) and the index data
pipeline are kept for future use. No live changes.
