# System v14 — SRE + RFE + Market Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the validated universe (gold crosses + indices), add SRE — the sixth signal engine (session stop-run reversals on FX) — and A/B-test the RFE currency-strength veto, promoting only what survives the v13 evidence bar.

**Architecture:** `backtest_master_v13.py` remains the living harness (extended in place — git tags provide revert). New pure-logic lives in tracked modules (`sre_logic.py`, `rfe_strength.py`) with pytest TDD; the harness imports them. Every phase is flag-gated with byte-stability regression proofs, exactly the v13 Task 7/8 pattern. Spec: `docs/specs/2026-07-06-v14-sre-rfe-market-sweep-design.md`.

**Tech Stack:** Python 3.11, MetaTrader5, pandas, numpy, pytest.

## Global Constraints

- `config.py` and `Archive/` are NEVER committed. New tunables default in tracked modules (`sre_logic.py` / `rfe_strength.py`), not config.py, so they are versioned.
- MT5 terminal must be open (demo 109166621). All harness runs: `$env:PYTHONIOENCODING='utf-8'; python -u backtest_master_v13.py` redirected to a distinct log in `.superpowers/sdd/`, background + poll for process exit (runs take 50–80 min; Task 4 lost a run to buffered output in v13 — never run unredirected).
- **Regression invariant (every harness-touching task):** with all new flags off, ALL existing matrix rows must be byte-stable versus a same-day flags-off run (compare the generated `docs/reports/v13_matrix_<date>.md`; live-data drift is only acceptable on weekends/market-closed and must be documented). Baseline-combo subtotal must reproduce the same-day base run exactly.
- **Iron pip rule:** every new symbol profile's pip/point value is derived from `mt5.symbol_info` (`tick_value × (pip/tick_size) × 0.01 lot × 3.98`), raw probe values recorded in the profile comment. If a symbol cannot pass the 0.25 sanity gate at min lot on RM500 → EXCLUDE it (report), never force-fit.
- Promotion bar (spec §8): ≥10 trades/combo, PF ≥ 1.3, PF>1.0 ex-best, walk-forward 5/5 OOS + majority-fold-positive per combo, Monte Carlo not worse than v13 ref (median DD 21.7% / P95 52.6% / ruin 3.83%). SRE additionally ≥30 trades engine-aggregate. RFE adoption: spec §5 bar verbatim.
- State isolation: SRE keeps its own spacing/monthly-loss state (v13 Task 7 lesson — never share gate state across engines/variants).
- Volume-based triggers are FORBIDDEN (demo tick volume unreliable — GVE precedent).
- Commit per task, push to origin main. Commit style: imperative + why + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Matrix .md files committed every run; .csv and trade JSONs stay git-ignored.

---

### Task 1: Profile probe + energies addendum

**Files:**
- Create: `profile_probe.py`
- Create: `docs/reports/v14_profile_probe_<date>.md` (output, committed)

**Interfaces:**
- Produces: the probe report — the single source of derived pip values, spreads, ATR ratios, and IN/OUT verdicts that Tasks 2–3 copy from. No harness changes here.

- [ ] **Step 1: Write the probe script**

```python
# profile_probe.py
"""v14 Task 1: derive tradability facts for every Phase A candidate from
broker truth (mt5.symbol_info + M15 history). Output feeds Tasks 2-3 profiles.
Iron rule: pip values from tick data, never contract-size assumptions."""
import MetaTrader5 as mt5
from datetime import date
from statistics import median

USD_MYR = 3.98
CANDIDATES = {
    "gold_cross": ["XAUEUR", "XAUGBP", "XAUAUD"],
    "index":      ["US500", "US30M", "USTECH100M", "UK100", "JPN225",
                   "AUS200", "EUSTX50", "DE40"],
    # energies discovered at runtime from path prefix Energies\\
}

def probe(sym):
    mt5.symbol_select(sym, True)
    si = mt5.symbol_info(sym)
    if si is None:
        return None
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 99999)
    bars = len(rates) if rates is not None else 0
    atr_m15 = (median(float(r["high"] - r["low"]) for r in rates[-5000:])
               if bars >= 5000 else 0.0)
    pip = si.point * 10 if "XAU" in sym else max(si.point, 1.0 if bars and rates[-1]["close"] > 500 else si.point * 10)
    # pip definition: gold crosses follow XAUUSD convention (point*10);
    # indices: 1 point if instrument trades in hundreds+ (index points), else point*10
    usd_per_pip_001 = si.trade_tick_value * (pip / si.trade_tick_size) * 0.01
    pip_val_rm = usd_per_pip_001 * USD_MYR
    spread_price = si.spread * si.point
    spread_pct_atr = (spread_price / atr_m15 * 100) if atr_m15 > 0 else 999
    return dict(sym=sym, path=si.path, contract=si.trade_contract_size,
                tick_value=si.trade_tick_value, tick_size=si.trade_tick_size,
                point=si.point, pip=pip, pip_val_rm=round(pip_val_rm, 5),
                bars=bars, atr_m15=round(atr_m15, 5),
                spread_pct_atr=round(spread_pct_atr, 1))

def main():
    if not mt5.initialize():
        raise SystemExit("MT5 initialize failed — open the terminal")
    from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
    mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)   # never print the password
    energies = [s.name for s in mt5.symbols_get() if s.path.startswith("Energies")]
    rows, lines = [], []
    for cls, syms in list(CANDIDATES.items()) + [("energy", energies)]:
        for s in syms:
            r = probe(s)
            if r: r["cls"] = cls; rows.append(r)
    mt5.shutdown()
    lines.append(f"# v14 Profile Probe — {date.today()}\n")
    lines.append("| sym | cls | contract | tick_val | tick_size | point | pip | pip_val_rm(0.01) | M15 bars | ATR_M15 | spread %ATR | verdict |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        # verdicts: sanity risk uses a conservative 100-point/pip SL scale proxy
        risk_ok = r["pip_val_rm"] * 100 < 0.25 * 500
        verdict = ("IN" if r["bars"] >= 20000 and r["spread_pct_atr"] <= 15
                   and risk_ok else
                   "OUT(bars)" if r["bars"] < 20000 else
                   "OUT(spread)" if r["spread_pct_atr"] > 15 else "OUT(risk)")
        lines.append(f"| {r['sym']} | {r['cls']} | {r['contract']} | {r['tick_value']} "
                     f"| {r['tick_size']} | {r['point']} | {r['pip']} | {r['pip_val_rm']} "
                     f"| {r['bars']} | {r['atr_m15']} | {r['spread_pct_atr']} | {verdict} |")
    out = f"docs/reports/v14_profile_probe_{date.today()}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Wrote", out, f"({len(rows)} symbols)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it** — `$env:PYTHONIOENCODING='utf-8'; python profile_probe.py` (MT5 open; a few minutes for the deep fetches). Expected: report with one row per candidate; DE40 gets its spread-vs-ATR verdict (spec: IN only if ≤15% of median M15 ATR); energies get IN/OUT verdicts. Review the pip definitions printed for indices — if any index's derived `pip_val_rm × 100` risks >25% of RM500, its verdict must be OUT(risk).

- [ ] **Step 3: Sanity-check two rows by hand** in the report (one gold cross, one index): recompute `tick_value × (pip/tick_size) × 0.01 × 3.98` manually and confirm the table matches. Record the hand-check in the task report.

- [ ] **Step 4: Commit**

```powershell
cd C:\fx_agents; git add profile_probe.py docs/reports/v14_profile_probe_*.md; git commit -m "v14: profile probe - tick-derived pip values and IN/OUT verdicts for Phase A candidates"; git push
```

---

### Task 2: GVE gold crosses (secondary-section generalization)

**Files:**
- Modify: `backtest_master_v13.py` (XAGUSD GVE section, ~line 997 region; `V13_CANDIDATES`; GVE profile data)

**Interfaces:**
- Consumes: Task 1 probe report (pip_val_rm etc. for XAUEUR/XAUGBP/XAUAUD — only IN-verdict symbols proceed).
- Produces: matrix rows `GVE | XAUEUR/XAUGBP/XAUAUD | base`.

- [ ] **Step 1: Read the XAGUSD GVE scan section fully** (search `XAGUSD GVE scan`). It is the single-symbol "secondary gold" scan (no variant machinery — that lives only in the XAUUSD section). Confirm its inputs: a profile-ish set of constants (pip, pip_val, SL cap) + M15/H1/D1 data fetch for `SILVER_SYMBOL`.

- [ ] **Step 2: Generalize it into a loop.** Introduce, next to `SILVER_SYMBOL`:

```python
# v14: GVE secondary symbols — gold-family instruments scanned with the
# same secondary-section logic as XAGUSD (no variant machinery).
# Profiles: pip values TICK-DERIVED (see docs/reports/v14_profile_probe_*.md).
GVE_SECONDARY = {
    "XAGUSD": dict(pip=0.001, pip_val_rm=<keep existing Task-5 value>, sl_cap=<existing>),
    "XAUEUR": dict(pip=0.1,   pip_val_rm=<probe>, sl_cap=<scale from XAUUSD's $35 by pip_val ratio>),
    "XAUGBP": dict(pip=0.1,   pip_val_rm=<probe>, sl_cap=<scaled>),
    "XAUAUD": dict(pip=0.1,   pip_val_rm=<probe>, sl_cap=<scaled>),
}
```

(`<probe>` values are copied from the Task 1 report — they are data, not placeholders; the implementer fills them from the committed report. Only IN-verdict symbols get entries.) Convert the XAGUSD section body to `for _gsym, _gprof in GVE_SECONDARY.items():` using `_gprof` fields where the section used silver constants. XAGUSD's own behavior must be unchanged (its dict entry reproduces the current constants exactly). Add the crosses to `V13_CANDIDATES["GVE"]` and ensure they reach `ALL_SYMBOLS` via the existing profiled-intersection guard (they need entries in a profile dict the guard scans — extend the guard's `_profiled` set with `set(GVE_SECONDARY)`).

- [ ] **Step 3: Regression + results run** — full run, background+poll. Gate: all pre-existing matrix rows byte-stable INCLUDING `GVE | XAGUSD`-related rows and `GVE | XAUUSD | base`; new rows appear for the crosses. If XAGUSD's row changed, the generalization broke silver — STOP and fix before commit.

- [ ] **Step 4: Commit** — `backtest_master_v13.py` + the run's matrix .md. Message: `v14: GVE generalized to gold crosses (XAUEUR/XAUGBP/XAUAUD) via secondary-section loop`.

---

### Task 3: Index (+ energies) profiles for CTE/MRE/CBE/HPE

**Files:**
- Modify: `backtest_master_v13.py` (the four `*_PROFILES` dicts + `V13_CANDIDATES`)

**Interfaces:**
- Consumes: Task 1 probe report (IN-verdict indices/energies only).
- Produces: matrix rows for every new engine×index combo.

- [ ] **Step 1: Add profile entries** for each IN symbol to all four dicts, modeled on the existing JPY-shape entries but with: `pip=<probe pip>`, `pip_val_rm=<probe>`, spread from probe (`spread_price/pip × pip_val_rm × 0.01` consistent with existing spread_rm convention), sessions `s_start/s_end` = the class cash window (US 13/20, EU 7/15, JP 0/6 UTC), `label="Index"` (or "Energy"), CTE fields `vp_prox_pct=0.5, vp_lookback=40, min_fvg=<2×median M15 ATR in pips, from probe>`, MRE `min_range=<10×ATR pips>`, CBE `min_range=<5×ATR pips>`, HPE `prox=<3×ATR pips>, sl_buf=<1×ATR pips>` — every derived number computed from the probe's ATR and written as a literal with a comment showing the derivation. Add symbols to `V13_CANDIDATES` for the four engines.

- [ ] **Step 2: Sanity gate dry-fire** — before the long run, run the harness just past the gate (start, watch log for `SANITY FAIL` vs preload, kill). Any gate failure = miscalibrated profile; fix using probe data, never by loosening the gate.

- [ ] **Step 3: Full run** — background+poll. Gate: pre-existing rows byte-stable; new index rows recorded (zeros and losers included). Portfolio-level shifts are expected/additive (v13 Task 4 precedent) — note MaxDD movement in the report.

- [ ] **Step 4: Commit** — harness + matrix .md. Message: `v14: index/energy candidate profiles (tick-derived) across CTE/MRE/CBE/HPE`.

---

### Task 4: sre_logic.py (pure TDD)

**Files:**
- Create: `sre_logic.py`
- Test: `tests/test_sre_logic.py`

**Interfaces:**
- Produces (Task 5 consumes verbatim):
  - `SRE_DEFAULTS: dict` — tunables
  - `asian_range(m15_bars, day_start_idx) -> (high, low) | None`
  - `classify_sweep(bar, pool_high, pool_low, pip, min_sweep_pips) -> "SWEPT_HIGH"|"SWEPT_LOW"|None`
  - `confirm_reversal(bars_after, direction) -> bool` (direction "SELL" after SWEPT_HIGH, "BUY" after SWEPT_LOW)
  - `sre_levels(direction, entry, sweep_extreme, asian_mid, opposite_pool, pip, atr_m15) -> (sl, tp, sl_pips, tp_pips, rr) | None`
  Bars are dicts with keys `open, high, low, close` (floats).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sre_logic.py
"""SRE pure logic: sweep-and-reject classification, reversal confirmation,
and level construction — all on synthetic candles, no MT5."""
from sre_logic import (SRE_DEFAULTS, classify_sweep, confirm_reversal,
                       sre_levels)

PIP = 0.0001

def bar(o, h, l, c):
    return {"open": o, "high": h, "low": l, "close": c}

def test_sweep_high_detected():
    # pool high 1.1000; wick to 1.1006 (6 pips through), close back inside
    b = bar(1.0995, 1.1006, 1.0993, 1.0996)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) == "SWEPT_HIGH"

def test_shallow_poke_not_a_sweep():
    # only 2 pips through the pool with min 3 -> not a sweep
    b = bar(1.0995, 1.1002, 1.0993, 1.0996)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) is None

def test_close_beyond_pool_is_breakout_not_sweep():
    # closes ABOVE the pool -> breakout, not a stop run
    b = bar(1.0995, 1.1010, 1.0994, 1.1008)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) is None

def test_sweep_low_detected():
    b = bar(1.0955, 1.0957, 1.0944, 1.0953)
    assert classify_sweep(b, 1.1000, 1.0950, PIP, 3.0) == "SWEPT_LOW"

def test_confirm_reversal_sell_rejection():
    # after SWEPT_HIGH we need a bar closing in its bottom third (rejection)
    rej = bar(1.0999, 1.1002, 1.0985, 1.0987)   # range 17 pips, close 2 from low
    assert confirm_reversal([rej], "SELL") is True

def test_confirm_reversal_fails_on_strength():
    bull = bar(1.0999, 1.1008, 1.0998, 1.1007)  # closes strong -> no reversal
    assert confirm_reversal([bull], "SELL") is False

def test_confirm_within_max_bars_only():
    bull = bar(1.0999, 1.1008, 1.0998, 1.1007)
    rej  = bar(1.1006, 1.1007, 1.0990, 1.0992)
    bars = [bull] * SRE_DEFAULTS["confirm_bars"] + [rej]   # rejection arrives too late
    assert confirm_reversal(bars, "SELL") is False

def test_levels_sell_shape_and_rr_clamp():
    out = sre_levels("SELL", entry=1.0990, sweep_extreme=1.1006,
                     asian_mid=1.0975, opposite_pool=1.0950,
                     pip=PIP, atr_m15=0.0008)
    assert out is not None
    sl, tp, sl_pips, tp_pips, rr = out
    assert sl > 1.1006            # beyond the sweep extreme + ATR buffer
    assert tp < 1.0990            # toward the mid/opposite pool
    assert SRE_DEFAULTS["rr_min"] <= rr <= SRE_DEFAULTS["rr_max"]

def test_levels_rejects_oversized_sl():
    # sweep extreme absurdly far -> SL beyond cap -> no trade
    out = sre_levels("SELL", entry=1.0990, sweep_extreme=1.1090,
                     asian_mid=1.0975, opposite_pool=1.0950,
                     pip=PIP, atr_m15=0.0008)
    assert out is None
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/test_sre_logic.py -q` → ImportError.

- [ ] **Step 3: Implement**

```python
# sre_logic.py
"""SRE — Stop Run Exhaustion Engine: pure logic (no MT5, no pandas).
Session stop-run REVERSALS: London/NY opens sweep the Asian extreme to run
stops, then reverse. GVE five-layer template with reversal semantics.
Tunables live HERE (tracked/versioned) — config.py is untracked.
Volume triggers deliberately absent (demo tick volume unreliable)."""

SRE_DEFAULTS = {
    "min_sweep_pips_fx":  3.0,   # spec §4: forex
    "min_sweep_pips_jpy": 5.0,   # spec §4: JPY crosses
    "confirm_bars":       3,     # reversal must confirm within N M15 bars
    "sl_atr_buffer":      0.5,   # SL = sweep extreme + 0.5*ATR(M15)
    "sl_max_pips_fx":     30,
    "sl_max_pips_jpy":    40,
    "rr_min":             1.5,
    "rr_max":             4.0,
    "atr_dead_ratio":     0.6,   # skip if ATR < 0.6x average (dead)
    "atr_hyper_ratio":    2.5,   # skip if ATR > 2.5x average (hyper)
}

def classify_sweep(bar, pool_high, pool_low, pip, min_sweep_pips):
    """A stop run: wick penetrates a pool by >= min_sweep_pips but the bar
    CLOSES back inside the range. Close beyond the pool = breakout, not sweep."""
    if (bar["high"] - pool_high) / pip >= min_sweep_pips and bar["close"] < pool_high:
        return "SWEPT_HIGH"
    if (pool_low - bar["low"]) / pip >= min_sweep_pips and bar["close"] > pool_low:
        return "SWEPT_LOW"
    return None

def confirm_reversal(bars_after, direction):
    """Within SRE_DEFAULTS['confirm_bars'] bars of the sweep, a rejection
    candle closing in the far third against the sweep confirms the reversal."""
    for b in bars_after[:SRE_DEFAULTS["confirm_bars"]]:
        rng = b["high"] - b["low"]
        if rng <= 0:
            continue
        pos = (b["close"] - b["low"]) / rng      # 0 = at low, 1 = at high
        if direction == "SELL" and pos <= 1/3:
            return True
        if direction == "BUY" and pos >= 2/3:
            return True
    return False

def sre_levels(direction, entry, sweep_extreme, asian_mid, opposite_pool,
               pip, atr_m15, is_jpy=False):
    """SL beyond the sweep extreme + ATR buffer (capped); TP toward the Asian
    mid, extended to the opposite pool only if RR stays inside the clamp."""
    d = SRE_DEFAULTS
    buf = d["sl_atr_buffer"] * atr_m15
    sl_cap = d["sl_max_pips_jpy"] if is_jpy else d["sl_max_pips_fx"]
    if direction == "SELL":
        sl = sweep_extreme + buf
        sl_pips = (sl - entry) / pip
        tp = asian_mid if asian_mid < entry else opposite_pool
        tp_pips = (entry - tp) / pip
    else:
        sl = sweep_extreme - buf
        sl_pips = (entry - sl) / pip
        tp = asian_mid if asian_mid > entry else opposite_pool
        tp_pips = (tp - entry) / pip
    if sl_pips <= 0 or sl_pips > sl_cap or tp_pips <= 0:
        return None
    rr = tp_pips / sl_pips
    if rr < d["rr_min"]:
        return None
    if rr > d["rr_max"]:                          # clamp TP to max RR
        tp_pips = sl_pips * d["rr_max"]
        tp = entry - tp_pips * pip if direction == "SELL" else entry + tp_pips * pip
        rr = d["rr_max"]
    return sl, tp, sl_pips, tp_pips, rr

def asian_range(m15_bars, day_start_idx):
    """High/low of the 00:00-07:00 UTC window = bars [day_start_idx,
    day_start_idx+28). Returns None if fewer than 20 bars present."""
    window = m15_bars[day_start_idx: day_start_idx + 28]
    if len(window) < 20:
        return None
    return max(b["high"] for b in window), min(b["low"] for b in window)
```

- [ ] **Step 4: Run to green** — `python -m pytest tests/test_sre_logic.py -q` → 9 passed. Then full suite: `python -m pytest tests/ -q` → all green.

- [ ] **Step 5: Commit** — `git add sre_logic.py tests/test_sre_logic.py` → `v14: SRE pure logic (sweep-reject, reversal confirm, levels) — TDD`.

---

### Task 5: SRE harness section (flag-gated) + runs

**Files:**
- Modify: `backtest_master_v13.py` (new SRE section AFTER the HPE section, BEFORE the final aggregation at ~line 1631; new flag)

**Interfaces:**
- Consumes: `sre_logic` functions exactly as defined in Task 4.
- Produces: `ALL_TRADES` entries with `engine="SRE"`, standard trade-dict fields (`symbol, direction, entry_dt, month, year, outcome, pnl_pips, pnl_rm, sl_pips, tp_pips, rr, session, regime="STOP_RUN", grade="B", dow, hold_hours` — copy the field set from the MRE section's dict literal so the matrix/JSON pipeline needs zero changes).

- [ ] **Step 1: Read the MRE harness section end-to-end** (it is the simplest complete engine section: per-symbol loop → signal detection on historical bars → outcome simulation → `ALL_TRADES.extend`). Your SRE section mirrors its skeleton.

- [ ] **Step 2: Implement the SRE section**, flag `SRE_ENABLED = False` at its top:
  - Symbols: the 11 FX pairs (spec §4) — iterate `[s for s in ALL_SYMBOLS if s not in ("XAUUSD","XAGUSD") and s in <fx set>]`, using each symbol's CTE profile for pip/pip_val_rm/spread (they exist for all 11).
  - Per day in the M15 history: build Asian range via `asian_range`; skip if ATR regime outside `[atr_dead_ratio, atr_hyper_ratio]` × rolling ATR average; within London KZ (07:00–09:00) and NY KZ (12:00–14:00) bars, `classify_sweep` against Asian high/low (+ prior-day high/low as secondary pools); on sweep, `confirm_reversal` on the following bars; on confirm, `sre_levels`; simulate outcome bar-by-bar exactly like MRE's sim loop (SL first, then TP, timeout after the session's remaining bars + 8h, spread cost deducted like other engines). One trade max per symbol per KZ window; SRE-private spacing/monthly state (own dicts).
  - Trades append to `ALL_TRADES` with `engine="SRE"`, `session="London_KZ"|"NY_KZ"`.
- [ ] **Step 3: Run 1 (flag OFF)** — full run; ALL existing rows byte-stable, zero SRE rows. **Step 4: Run 2 (flag ON)** — SRE rows appear per symbol; existing rows still byte-stable (isolation proof). Record every SRE row including zeros/losers; note engine-aggregate trade count vs the ≥30 bar. Archive matrix as `docs/reports/v14_matrix_sre.md`.
- [ ] **Step 5: Restore flag OFF, commit** harness + both matrices: `v14: SRE engine section (flag-gated) — session stop-run reversals on 11 FX pairs`.

---

### Task 6: rfe_strength.py (pure TDD)

**Files:**
- Create: `rfe_strength.py`
- Test: `tests/test_rfe_strength.py`

**Interfaces:**
- Produces (Task 7 consumes):
  - `RFE_DEFAULTS = {"lookback": 20, "min_gap": 3}`
  - `currency_strength(h4_closes: dict[str, list[float]], lookback: int) -> dict[str, float]` — pair name → close series; returns strength score per currency (mean sign-adjusted ROC across its pairs)
  - `strength_ranks(scores: dict) -> dict[str, int]` — 1 = strongest
  - `rfe_allows(direction: str, pair: str, ranks: dict, min_gap: int) -> bool`

- [ ] **Step 1: Failing tests**

```python
# tests/test_rfe_strength.py
from rfe_strength import (RFE_DEFAULTS, currency_strength, strength_ranks,
                          rfe_allows)

def rising(n=25, start=1.0, step=0.001):
    return [start + i * step for i in range(n)]

def falling(n=25, start=1.0, step=0.001):
    return [start - i * step for i in range(n)]

def test_strength_direction():
    # EURUSD rising + EURGBP rising => EUR strong; USD weak side of EURUSD
    closes = {"EURUSD": rising(), "EURGBP": rising(), "GBPUSD": falling()}
    s = currency_strength(closes, RFE_DEFAULTS["lookback"])
    assert s["EUR"] > s["USD"]
    assert s["EUR"] > s["GBP"]

def test_ranks_are_1_to_n():
    closes = {"EURUSD": rising(), "GBPUSD": falling(), "AUDUSD": rising()}
    ranks = strength_ranks(currency_strength(closes, 20))
    assert sorted(ranks.values()) == list(range(1, len(ranks) + 1))

def test_gate_allows_strong_vs_weak():
    ranks = {"EUR": 1, "GBP": 3, "USD": 7, "JPY": 8}
    assert rfe_allows("BUY", "EURUSD", ranks, 3) is True     # buy strong vs weak
    assert rfe_allows("SELL", "EURUSD", ranks, 3) is False   # sell strong vs weak

def test_gate_vetoes_close_ranks():
    ranks = {"EUR": 4, "GBP": 5}
    assert rfe_allows("BUY", "EURGBP", ranks, 3) is False    # gap 1 < 3

def test_gate_passes_unknown_pairs():
    # non-FX (gold/index) or missing currency -> filter does not apply
    assert rfe_allows("BUY", "XAUUSD", {"EUR": 1}, 3) is True
```

- [ ] **Step 2: RED** — pytest → ImportError. **Step 3: Implement**

```python
# rfe_strength.py
"""RFE — relative currency strength (pure logic). Strength score per currency
= mean sign-adjusted ROC over `lookback` H4 closes across every supplied pair
containing it. Veto layer only — never generates signals."""

RFE_DEFAULTS = {"lookback": 20, "min_gap": 3}
_CCYS = ("USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF")

def _split(pair):
    b, q = pair[:3], pair[3:6]
    return (b, q) if b in _CCYS and q in _CCYS else (None, None)

def currency_strength(h4_closes, lookback):
    acc = {c: [] for c in _CCYS}
    for pair, closes in h4_closes.items():
        base, quote = _split(pair)
        if base is None or len(closes) < lookback + 1:
            continue
        roc = (closes[-1] - closes[-1 - lookback]) / closes[-1 - lookback]
        acc[base].append(roc)      # pair up => base strong
        acc[quote].append(-roc)    # pair up => quote weak
    return {c: (sum(v) / len(v) if v else 0.0) for c, v in acc.items()}

def strength_ranks(scores):
    ordered = sorted(scores, key=lambda c: scores[c], reverse=True)
    return {c: i + 1 for i, c in enumerate(ordered)}

def rfe_allows(direction, pair, ranks, min_gap):
    base, quote = _split(pair)
    if base is None or base not in ranks or quote not in ranks:
        return True                       # filter only applies to known FX legs
    gap = ranks[quote] - ranks[base]      # positive when base stronger
    return gap >= min_gap if direction == "BUY" else -gap >= min_gap
```

- [ ] **Step 4: GREEN** — 5 passed; full suite green. **Step 5: Commit** — `v14: RFE currency-strength logic (pure) — TDD`.

---

### Task 7: RFE harness A/B

**Files:**
- Modify: `backtest_master_v13.py` (flag `RFE_FILTER = False`; strength table precompute after preload; veto hook in each FX engine section's signal-accept point)

**Interfaces:**
- Consumes: `rfe_strength` exactly as in Task 6.
- Produces: an A/B report section in the task report + `docs/reports/v14_matrix_rfe_on.md`.

- [ ] **Step 1: Precompute** — after all symbols preload, build `RFE_RANKS_BY_DAY: dict[date, ranks]` from the H4 data of the 11 FX pairs (for each day, feed each pair's H4 closes up to that day into `currency_strength` + `strength_ranks`). Pure lookup at scan time — no lookahead (use closes strictly BEFORE the signal day).
- [ ] **Step 2: Hook the veto** into CTE/MRE/CBE/HPE/SRE signal-accept points (immediately before each section appends a trade): `if RFE_FILTER and not rfe_allows(direction, sym, RFE_RANKS_BY_DAY.get(day, {}), RFE_DEFAULTS["min_gap"]): vetoed_count += 1; continue`. Gold/index symbols pass automatically (`rfe_allows` returns True for non-FX pairs). Count vetoes per engine.
- [ ] **Step 3: Run A (flag OFF)** — byte-stability proof. **Step 4: Run B (flag ON)** — collect: per-engine and portfolio WR/PF/net deltas, trade retention %, MRE's delta separately (spec §5 note). Evaluate the adoption bar mechanically: portfolio PF up AND net ≥ −10% of base AND retention ≥ 60%. Walk-forward check on the filtered JSON happens in Task 8.
- [ ] **Step 5: Restore flag OFF, commit** harness + matrix + A/B numbers in the report: `v14: RFE veto hook + A/B evidence (adoption decided at revalidation)`.

---

### Task 8: Revalidation (analysis only — no config changes)

**Files:**
- Uses: `walkforward_v13.py`, `montecarlo_v13.py` (unchanged — they read `backtest_master_v13.json`)

- [ ] **Step 1:** Fresh full run with ALL v14 additions enabled EXCEPT RFE (SRE_ENABLED=True; candidates all in) → regenerates `backtest_master_v13.json` with the full v14 universe. Run walk-forward + Monte Carlo; produce the per-candidate-combo OOS breakdown for every new PASS row (gold crosses, indices, energies, SRE combos) — the v13 Task 10A format.
- [ ] **Step 2:** If Task 7's A/B passed its mechanical bar: rerun with RFE on, regenerate JSON, run walk-forward on the filtered set (must stay 5/5). Report RFE's final verdict against the full spec §5 bar.
- [ ] **Step 3:** Write the full arbitration report (promote/hold/reject per combo + RFE adopt/reject + SRE engine-aggregate check vs ≥30) to `.superpowers/sdd/task-8-report.md`. Commit any script tweaks + report. **The controller adjudicates promotions — do not touch config.py.**

---

### Task 9: Promotion + bookkeeping (controller-driven)

**Files:**
- Modify: `config.py` (untracked), `VERSION_HISTORY.md`, `OPERATING_GUIDE.txt`; conditionally `agent_kira.py` + `agent_guard.py` (live ports)

- [ ] **Step 1:** Apply the controller's promotion list: routing table + whitelist + `PAIRS`/`JPY_PAIRS`(/new index list) + `PROBATION_COMBOS` entries. RFE: if adopted, `RFE_FILTER=True` equivalent goes into the live stack ONLY with its own port (see Step 3); otherwise recorded as tested-and-off.
- [ ] **Step 2:** Verify wiring exactly like v13: every promoted combo `whitelist=True routed=True in_scan=True`; rejected combos blocked; no legacy-route bypass; all live modules import clean.
- [ ] **Step 3 (conditional live ports, own reviewed commits each):** SRE promoted → port `sre_logic` consumption into `agent_kira.py` behind `SRE_LIVE=False`-default flag + routing entries; index combos promoted → live session handling + GUARD non-currency exposure bucket; RFE adopted → veto in KIRA's signal path behind a flag. Each port: `test_full_system.py` before/after + full pytest suite.
- [ ] **Step 4:** VERSION_HISTORY v14 row with measured numbers + promotions/holds/rejects + RFE verdict; OPERATING_GUIDE Market Watch list if new symbols promoted; `git tag v14`; push with tags.

---

## Plan Self-Review (completed)

- **Spec coverage:** §3 sweep = Tasks 1–3; §4 SRE = Tasks 4–5; §5 RFE = Tasks 6–7; §6 revalidation/promotion = Tasks 8–9; §7 ledger lives in the spec itself; §9 testing = TDD tasks + byte-stability gates throughout.
- **Placeholder scan:** Task 2's `<probe>` markers are data references to the committed Task 1 report (values cannot exist before the probe runs — same pattern as v13 Task 5's MT5-derived pip), not TBDs. All parameter defaults are concrete in `sre_logic.py`/`rfe_strength.py` code.
- **Type consistency:** `classify_sweep/confirm_reversal/sre_levels/asian_range` signatures match between Task 4 definitions and Task 5 consumption; `currency_strength/strength_ranks/rfe_allows` match between Tasks 6 and 7; SRE trade-dict fields copy the MRE literal so matrix/JSON contracts hold unchanged.
