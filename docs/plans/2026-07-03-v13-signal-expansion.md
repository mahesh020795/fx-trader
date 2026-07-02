# System v13 — Validated Signal Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the engine×symbol universe (5 new pairs + XAGUSD recalibration + GVE SELL/NY + HPE SELL + new-market scan) through a v13 backtest harness, promoting only combos that pass the v10 evidence bar.

**Architecture:** `backtest_master_v13.py` (copy of v10) gains candidate-mode symbol lists and variant flags; pure-python helper modules (`profile_sanity.py`, `matrix_report.py`) are unit-tested with pytest; every candidate is judged by the §7 promotion criteria from the spec before touching `config.py`.

**Tech Stack:** Python 3.11, MetaTrader5, pandas, numpy, pytest. Spec: `docs/specs/2026-07-03-v13-signal-expansion-design.md`.

## Global Constraints

- `config.py` and `Archive/` are NEVER committed (live secrets). Parameter promotions are recorded in `VERSION_HISTORY.md` notes instead.
- Harness runs require the MT5 terminal open and logged into demo 107377015. If `mt5.initialize()` fails, STOP and ask Mahesh to open MT5 — do not stub data.
- CBE×XAGUSD is permanently blocked (PF 0.28, MaxDD 93.3%). No task may re-enable it.
- Promotion bar (spec §7): ≥10 trades (≥30 for GVE variants), PF ≥ 1.3, PF > 1.0 with best trade removed, walk-forward 5/5 OOS with additions, Monte Carlo not worse than median DD 21.9% / P95 53.8% / ruin 4.09%.
- Regression invariant: with zero candidates and all variant flags off, `backtest_master_v13.py` must reproduce v10 baseline — **287 signals, WR 49.5%, +RM4,192, PF 2.19** (±rounding). Re-verify after EVERY harness-touching task.
- Commit after every task; push to `origin main`. Live agent files (`agent_*.py`, `main_agents.py`) are untouched in Tasks 1–9.
- All new-symbol profile entries model the existing dict shapes at `backtest_master_v10.py:109-259` exactly — same keys, same constant references.

---

### Task 1: v13 harness copy + regression gate

**Files:**
- Create: `backtest_master_v13.py` (copy of `backtest_master_v10.py`)
- Create: `docs/reports/.gitkeep`

**Interfaces:**
- Produces: `backtest_master_v13.py` — the only file later tasks modify for backtest logic. Run with `python backtest_master_v13.py`.

- [ ] **Step 1: Copy the file**

```powershell
Copy-Item C:\fx_agents\backtest_master_v10.py C:\fx_agents\backtest_master_v13.py
New-Item -ItemType Directory -Force C:\fx_agents\docs\reports | Out-Null
New-Item -ItemType File C:\fx_agents\docs\reports\.gitkeep
```

- [ ] **Step 2: Update the header banner**

In `backtest_master_v13.py` lines 1–17, change the version banner text to say `v13 — VALIDATED SIGNAL EXPANSION (built on v10 confirmed baseline)` and add one line: `# Regression invariant: candidates=[] + variants off => v10 numbers (287 / 49.5% / +RM4,192 / PF 2.19)`. Change nothing else.

- [ ] **Step 3: Run the regression gate (MT5 must be open)**

Run: `cd C:\fx_agents; python backtest_master_v13.py`
Expected: final portfolio section prints 287 trades, WR 49.5%, net ≈ +RM4,192, PF ≈ 2.19. If MT5 init fails, stop and request MT5 be opened. If numbers differ from v10's documented baseline, STOP — investigate before proceeding (likely broker data window drift; record actual numbers in the report and confirm they match a fresh `backtest_master_v10.py` run on the same day — the two files must agree exactly).

- [ ] **Step 4: Commit**

```powershell
cd C:\fx_agents; git add backtest_master_v13.py docs/reports/.gitkeep; git commit -m "v13: harness copy of v10, regression gate verified"; git push
```

---

### Task 2: Profile sanity checker (pure python, TDD)

**Files:**
- Create: `profile_sanity.py`
- Test: `tests/test_profile_sanity.py`

**Interfaces:**
- Produces: `check_profile(symbol: str, profile: dict, balance_rm: float = 500.0) -> list[str]` — returns list of violation strings, empty list = OK. Keys used: `pip` (float), `pip_val_rm` (RM per pip per 0.01 lot), `sl_min` (int pips, optional), `spread_rm` (float, optional).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_profile_sanity.py
from profile_sanity import check_profile

GOOD = dict(pip=0.0001, pip_val_rm=0.398, sl_min=30, spread_rm=0.003)

def test_good_profile_passes():
    assert check_profile("USDCHF", GOOD) == []

def test_oversized_pip_value_fails():
    # The XAGUSD disaster: pip value so large that min-lot SL risk > 2% of balance
    bad = dict(GOOD, pip_val_rm=5.0, sl_min=100)   # 100 pips * RM5 = RM500 = 100% of RM500
    violations = check_profile("XAGUSD", bad)
    assert any("risk" in v.lower() for v in violations)

def test_missing_pip_fails():
    violations = check_profile("EURGBP", dict(pip_val_rm=0.4))
    assert any("pip" in v.lower() for v in violations)

def test_negative_spread_fails():
    bad = dict(GOOD, spread_rm=-0.1)
    assert any("spread" in v.lower() for v in check_profile("X", bad))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\fx_agents; python -m pytest tests/test_profile_sanity.py -v`
Expected: FAIL / ERROR with "No module named 'profile_sanity'"

- [ ] **Step 3: Implement**

```python
# profile_sanity.py
"""Symbol-profile sanity gate for backtest_master_v13.
The check that would have caught the XAGUSD pip-value disaster (v8):
at minimum lot, one SL hit must risk < 2% of the account."""

MAX_RISK_FRACTION = 0.02

def check_profile(symbol, profile, balance_rm=500.0):
    violations = []
    pip = profile.get("pip")
    if not pip or pip <= 0:
        violations.append(f"{symbol}: 'pip' missing or non-positive ({pip})")
    pip_val = profile.get("pip_val_rm")
    if not pip_val or pip_val <= 0:
        violations.append(f"{symbol}: 'pip_val_rm' missing or non-positive ({pip_val})")
    spread = profile.get("spread_rm")
    if spread is not None and spread < 0:
        violations.append(f"{symbol}: negative spread_rm ({spread})")
    sl_min = profile.get("sl_min")
    if pip_val and pip_val > 0 and sl_min:
        worst_loss_rm = sl_min * pip_val          # min lot (0.01) SL hit
        if worst_loss_rm > balance_rm * MAX_RISK_FRACTION:
            violations.append(
                f"{symbol}: min-lot SL risk RM{worst_loss_rm:.0f} exceeds "
                f"{MAX_RISK_FRACTION:.0%} of RM{balance_rm:.0f} — pip_val/sl_min miscalibrated")
    return violations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\fx_agents; python -m pytest tests/test_profile_sanity.py -v`
Expected: 4 passed

- [ ] **Step 5: Wire into v13 harness**

In `backtest_master_v13.py`, directly after the last profile dict (`HPE_SYMS`, around line 261), add:

```python
# ── v13: PROFILE SANITY GATE ─────────────────────────────────
from profile_sanity import check_profile
_sanity_violations = []
for _name, _profiles in [("CTE", CTE_PROFILES), ("MRE", MRE_PROFILES),
                         ("CBE", CBE_PROFILES), ("HPE", HPE_PROFILES)]:
    for _sym, _prof in _profiles.items():
        for _v in check_profile(_sym, _prof):
            _sanity_violations.append(f"[{_name}] {_v}")
if _sanity_violations:
    for _v in _sanity_violations: print("SANITY FAIL:", _v)
    raise SystemExit("Profile sanity gate failed — fix profiles before running.")
```

- [ ] **Step 6: Re-run regression gate**

Run: `cd C:\fx_agents; python backtest_master_v13.py`
Expected: no sanity failures, baseline numbers unchanged (287 / 49.5% / PF 2.19).

- [ ] **Step 7: Commit**

```powershell
cd C:\fx_agents; git add profile_sanity.py tests/ backtest_master_v13.py; git commit -m "v13: profile sanity gate (XAGUSD-disaster check) wired into harness"; git push
```

---

### Task 3: Candidate-mode symbol lists

**Files:**
- Modify: `backtest_master_v13.py` (scan-list construction, lines ~169-261 region)

**Interfaces:**
- Produces: module-level `V13_CANDIDATES: dict[str, list[str]]` (engine → candidate symbols) and scan lists (`CONT_SYMBOLS`, `MRE_SYMS`, `CBE_SYMS`, `HPE_SYMS`, `ALL_SYMBOLS`) that include candidates. Tasks 4–5 add profile entries; a symbol only scans if it has BOTH a profile entry AND a candidate/whitelist entry.

- [ ] **Step 1: Add the candidate table**

In `backtest_master_v13.py`, immediately before `CONT_SYMBOLS` (line ~168), add:

```python
# ── v13 CANDIDATE MODE ───────────────────────────────────────
# Symbols under evaluation. NOT in the live whitelist — they scan in this
# harness only. Promotion to config.py requires spec §7 criteria.
V13_CANDIDATES = {
    "CTE": ["USDCHF", "EURGBP", "AUDJPY", "CADJPY", "NZDJPY", "XAGUSD"],
    "MRE": ["USDCHF", "EURGBP", "AUDJPY", "CADJPY", "NZDJPY", "XAGUSD"],
    "CBE": ["USDCHF", "EURGBP", "AUDJPY", "CADJPY", "NZDJPY"],   # XAGUSD: HARD BLOCKED
    "HPE": ["USDCHF", "EURGBP", "AUDJPY", "CADJPY", "NZDJPY", "XAGUSD"],
    "GVE": ["XAGUSD"],
}
def v13_allowed(engine, symbol):
    return engine_symbol_allowed(engine, symbol) or symbol in V13_CANDIDATES.get(engine, [])
```

- [ ] **Step 2: Switch scan lists to candidate-aware gate**

Replace the four scan-list constructions (v10 lines 169-170, 210-211, 236-237, 260-261). Each currently reads like:

```python
CONT_SYMBOLS = [s for s in CTE_PROFILES.keys()
                if s != "XAGUSD" and engine_symbol_allowed("CTE", s)]
```

Change all four to (respective engine names/profile dicts; note XAGUSD is no longer unconditionally excluded — profiles control it now):

```python
CONT_SYMBOLS = [s for s in CTE_PROFILES.keys() if v13_allowed("CTE", s)]
MRE_SYMS     = [s for s in MRE_PROFILES.keys() if v13_allowed("MRE", s)]
CBE_SYMS     = [s for s in CBE_PROFILES.keys() if v13_allowed("CBE", s)]
HPE_SYMS     = [s for s in HPE_PROFILES.keys() if v13_allowed("HPE", s)]
```

And extend `ALL_SYMBOLS` (v10 lines 176-179) to include candidates that have profiles — after the existing union loop add:

```python
for _eng, _syms in V13_CANDIDATES.items():
    _all_whitelisted.update(_syms)
ALL_SYMBOLS = sorted(_all_whitelisted | {GVE_SYMBOL})
```

(v9 lesson at lines 173-175: symbols missing from ALL_SYMBOLS silently never fetch — this is the exact bug class we must not reintroduce.)

- [ ] **Step 3: Regression gate still holds**

Candidates have no profile entries yet, so scan lists are unchanged except XAGUSD (still absent from all profile dicts). ALL_SYMBOLS now contains candidate names with no data — verify `fetch()`/`preload()` (lines 265-309) skip symbols with no profile gracefully; if preload errors on unknown symbols, guard the preload loop to only preload symbols appearing in at least one profile dict:

```python
_profiled = set(CTE_PROFILES) | set(MRE_PROFILES) | set(CBE_PROFILES) | set(HPE_PROFILES) | {GVE_SYMBOL}
ALL_SYMBOLS = sorted((_all_whitelisted | {GVE_SYMBOL}) & _profiled | {GVE_SYMBOL})
```

Run: `python backtest_master_v13.py`
Expected: 287 / 49.5% / PF 2.19 — identical.

- [ ] **Step 4: Commit**

```powershell
cd C:\fx_agents; git add backtest_master_v13.py; git commit -m "v13: candidate-mode scan lists (whitelist-union-candidates gate)"; git push
```

---

### Task 4: New-symbol profiles (USDCHF, EURGBP, AUDJPY, CADJPY, NZDJPY)

**Files:**
- Modify: `backtest_master_v13.py` (the four `*_PROFILES` dicts)

**Interfaces:**
- Consumes: `V13_CANDIDATES`, `check_profile` (Tasks 2–3).
- Produces: profile entries so the five candidates scan on CTE, MRE, CBE, HPE.

**Pip-value notes (RM per pip per 0.01 lot, USD_MYR_RATE = 3.98):**
USD-quoted pairs use `0.10*USD_MYR_RATE`. USDCHF (CHF-quoted, CHF≈1.11/USD): `0.111*USD_MYR_RATE`. EURGBP (GBP-quoted, GBP≈1.27 USD): `0.127*USD_MYR_RATE`. JPY crosses use the existing `0.091*USD_MYR_RATE` convention. These are approximations consistent with the harness's existing convention (it approximates 0.091 for all JPY crosses); exactness matters less than scale, which the sanity gate enforces.

- [ ] **Step 1: Add CTE profiles**

Append to `CTE_PROFILES` (before the XAGUSD comment block, v10 line ~163), modeled byte-for-byte on the existing entries:

```python
    # ── v13 CANDIDATES (spec 2026-07-03) ──
    "USDCHF": dict(pip=0.0001, pip_val_rm=0.111*USD_MYR_RATE, sl_min=SL_MIN_FOREX,
                   vp_prox_pct=None, vp_prox_fixed=VP_PROXIMITY_FOREX,
                   vp_lookback=VP_LOOKBACK_DEFAULT, min_fvg=MIN_FVG_PIPS_FOREX,
                   spread_rm=1.2*0.111*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=True, label="Forex",
                   block_sessions=["NY_PM"]),
    "EURGBP": dict(pip=0.0001, pip_val_rm=0.127*USD_MYR_RATE, sl_min=SL_MIN_FOREX,
                   vp_prox_pct=None, vp_prox_fixed=VP_PROXIMITY_FOREX,
                   vp_lookback=VP_LOOKBACK_DEFAULT, min_fvg=MIN_FVG_PIPS_FOREX,
                   spread_rm=1.0*0.127*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=True, label="Forex",
                   block_sessions=["NY_PM"]),
    "AUDJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE, sl_min=120,
                   vp_prox_pct=0.5, vp_prox_fixed=None, vp_lookback=40,
                   min_fvg=20.0, spread_rm=1.8*0.091*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=False, label="JPY-Cross",
                   block_sessions=["Other"]),
    "CADJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE, sl_min=120,
                   vp_prox_pct=0.5, vp_prox_fixed=None, vp_lookback=40,
                   min_fvg=20.0, spread_rm=2.0*0.091*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=False, label="JPY-Cross",
                   block_sessions=["Other"]),
    "NZDJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE, sl_min=120,
                   vp_prox_pct=0.5, vp_prox_fixed=None, vp_lookback=40,
                   min_fvg=20.0, spread_rm=2.0*0.091*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=False, label="JPY-Cross",
                   block_sessions=["Other"]),
```

- [ ] **Step 2: Add MRE, CBE, HPE profiles for the same five symbols**

Same pattern, modeled on each dict's existing forex/JPY entries (v10 lines 182-259): USDCHF/EURGBP copy the forex-shape entries (e.g. `MRE_MIN_RANGE_FOREX`, `CBE_MIN_RANGE_FOREX`, `prox=50`, `HPE_SL_BEYOND_FOREX`) with the pip values from Step 1; AUDJPY/CADJPY/NZDJPY copy the JPY-shape entries (`MRE_MIN_RANGE_JPY`, `CBE_MIN_RANGE_JPY`, `prox=120`, `HPE_SL_BEYOND_JPY`) with `pip=0.01, pip_val_rm=0.091*USD_MYR_RATE`. Spreads: USDCHF 1.2, EURGBP 1.0, AUDJPY 1.8, CADJPY 2.0, NZDJPY 2.0 (× respective pip_val × 0.01).

- [ ] **Step 3: Sanity gate + symbol availability**

Run: `cd C:\fx_agents; python -c "import MetaTrader5 as mt5; mt5.initialize(); [print(s, bool(mt5.symbol_select(s, True))) for s in ['USDCHF','EURGBP','AUDJPY','CADJPY','NZDJPY']]; mt5.shutdown()"`
Expected: all True. Any False = symbol unavailable on MetaQuotes-Demo → remove it from V13_CANDIDATES and profiles, note in report.

- [ ] **Step 4: Full candidate run**

Run: `python backtest_master_v13.py`
Expected: sanity gate passes; run completes; new combos appear in per-engine output. **The 20 baseline combos' stats must be unchanged** — new symbols add rows, they must not alter existing rows (shared account-level sims like GUARD clustering may shift portfolio-level numbers; per-combo engine stats must match. If portfolio sim mixes candidates into the baseline equity curve, add a `V13_SEPARATE_PORTFOLIO=True` mode that reports candidates in an isolated portfolio section).

- [ ] **Step 5: Commit**

```powershell
cd C:\fx_agents; git add backtest_master_v13.py; git commit -m "v13: profiles for USDCHF EURGBP AUDJPY CADJPY NZDJPY across CTE/MRE/CBE/HPE"; git push
```

---

### Task 5: XAGUSD recalibration profiles

**Files:**
- Modify: `backtest_master_v13.py` (profile dicts + GVE silver scan, lines ~776-883 region)

**Interfaces:**
- Consumes: candidate mode (Task 3). XAGUSD already in `V13_CANDIDATES` for CTE/MRE/HPE/GVE — NOT CBE.

**Documented fixes being applied (from v8 post-mortem):** CTE pip-value fix; MRE `min_range` 50–100 pips (was 500); GVE needs the full ~99,999-candle M15 window (was 3,000).

- [ ] **Step 1: Correct XAGUSD pip value, then add profiles**

Compute honestly before coding: MetaQuotes XAGUSD contract = 5,000 oz/lot. 0.01 lot = 50 oz. `pip=0.001` ($0.001 price move) → $0.05/pip → `pip_val_rm = 0.05*USD_MYR_RATE ≈ RM0.199`. Verify against MT5: `python -c "import MetaTrader5 as mt5; mt5.initialize(); mt5.symbol_select('XAGUSD', True); si = mt5.symbol_info('XAGUSD'); print(si.trade_contract_size, si.trade_tick_value, si.trade_tick_size); mt5.shutdown()"` and derive pip_val_rm from tick_value if it disagrees. Then add to CTE/MRE/HPE profile dicts (NOT CBE):

```python
    # v13: XAGUSD recalibration — pip_val from verified 5000oz contract
    "XAGUSD": dict(pip=0.001, pip_val_rm=0.05*USD_MYR_RATE, sl_min=SL_MIN_XAGUSD,  # CTE
                   vp_prox_pct=0.5, vp_prox_fixed=None, vp_lookback=40,
                   min_fvg=MIN_FVG_PIPS_XAGUSD, spread_rm=5.0*0.05*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=False, label="Silver",
                   block_sessions=["Other"]),
```

MRE entry: `min_range=75` (middle of the documented 50–100 band), `extreme_prox=MRE_EXTREME_PROX_JPY`, `sl_beyond=MRE_SL_BEYOND_JPY`. HPE entry: `prox=300, sl_buf=50` (Silver price scale ≈ 30.00, pivots need wide proximity). Constants `SL_MIN_XAGUSD`/`MIN_FVG_PIPS_XAGUSD` already exist in config.py:96-99.

- [ ] **Step 2: Extend GVE silver scan window**

In the XAGUSD GVE scan section (v10 line ~776), find the M15 fetch call and raise its candle count to 99999 (matching how line 269 fetches other data: `mt5.copy_rates_from(sym, tf, start, 99999)`). The v8 failure was 0 signals from a 3,000-candle window.

- [ ] **Step 3: Run and record**

Run: `python backtest_master_v13.py`
Expected: XAGUSD rows appear for CTE/MRE/HPE/GVE with sane risk numbers (sanity gate enforces). Record all XAGUSD combo stats — they go in the Task 6 report regardless of pass/fail.

- [ ] **Step 4: Commit**

```powershell
cd C:\fx_agents; git add backtest_master_v13.py; git commit -m "v13: XAGUSD recalibration - pip_val fix, MRE min_range 75, GVE full M15 window; CBE stays blocked"; git push
```

---

### Task 6: Matrix report generator (pure python, TDD)

**Files:**
- Create: `matrix_report.py`
- Test: `tests/test_matrix_report.py`
- Modify: `backtest_master_v13.py` (trade collection → report call at end, before `mt5.shutdown()` line ~882)

**Interfaces:**
- Consumes: harness's collected trade records. The harness already aggregates per-combo results for its printed report (section starting v10 line ~1583); adapt whatever list/dict it prints from.
- Produces: `build_matrix(trades: list[dict]) -> list[dict]` and `write_report(rows, path_md, path_csv)`. Each trade dict needs keys: `engine`, `symbol`, `variant` (default `"base"`), `pnl_rm` (float). Each output row: `engine, symbol, variant, n_trades, wr, net_rm, pf, pf_ex_best, verdict` where verdict ∈ `PASS | FAIL | INSUFFICIENT_DATA` per the promotion bar (≥10 trades, PF≥1.3, pf_ex_best>1.0 → PASS; <10 trades → INSUFFICIENT_DATA; else FAIL).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_matrix_report.py
from matrix_report import build_matrix

def T(engine="CTE", symbol="EURUSD", variant="base", pnl=10.0):
    return dict(engine=engine, symbol=symbol, variant=variant, pnl_rm=pnl)

def test_pass_verdict():
    trades = [T(pnl=30.0)] * 7 + [T(pnl=-10.0)] * 5   # 12 trades, PF 4.2
    row = build_matrix(trades)[0]
    assert row["n_trades"] == 12
    assert row["verdict"] == "PASS"

def test_insufficient_data():
    row = build_matrix([T(pnl=50.0)] * 5)[0]           # only 5 trades
    assert row["verdict"] == "INSUFFICIENT_DATA"

def test_single_trade_dependence_fails():
    # GBPJPY-MRE case: profitable ONLY because of one big winner
    trades = [T(pnl=200.0)] + [T(pnl=-12.0)] * 10 + [T(pnl=11.0)] * 4
    row = build_matrix(trades)[0]
    assert row["pf_ex_best"] < 1.0
    assert row["verdict"] == "FAIL"

def test_combos_grouped_separately():
    trades = [T(engine="CTE", pnl=10)] * 10 + [T(engine="MRE", pnl=-5)] * 10
    rows = build_matrix(trades)
    assert len(rows) == 2
```

- [ ] **Step 2: Run tests, verify fail**

Run: `python -m pytest tests/test_matrix_report.py -v` → Expected: import error.

- [ ] **Step 3: Implement**

```python
# matrix_report.py
"""Compatibility-matrix report for backtest_master_v13.
Verdicts implement spec 2026-07-03 §7 criteria 1-3 (walk-forward and
Monte Carlo, criteria 4-5, are separate whole-system runs)."""
from collections import defaultdict
import csv

MIN_TRADES, MIN_PF = 10, 1.3

def _pf(pnls):
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    return wins / losses if losses > 0 else float("inf")

def build_matrix(trades):
    groups = defaultdict(list)
    for t in trades:
        groups[(t["engine"], t["symbol"], t.get("variant", "base"))].append(t["pnl_rm"])
    rows = []
    for (engine, symbol, variant), pnls in sorted(groups.items()):
        n = len(pnls)
        pf = _pf(pnls)
        ex_best = sorted(pnls)[:-1] if n > 1 else []
        pf_ex_best = _pf(ex_best) if ex_best else 0.0
        wr = sum(1 for p in pnls if p > 0) / n * 100
        if n < MIN_TRADES:
            verdict = "INSUFFICIENT_DATA"
        elif pf >= MIN_PF and pf_ex_best > 1.0:
            verdict = "PASS"
        else:
            verdict = "FAIL"
        rows.append(dict(engine=engine, symbol=symbol, variant=variant,
                         n_trades=n, wr=round(wr, 1), net_rm=round(sum(pnls), 2),
                         pf=round(pf, 2) if pf != float("inf") else 99.0,
                         pf_ex_best=round(pf_ex_best, 2) if pf_ex_best != float("inf") else 99.0,
                         verdict=verdict))
    return rows

def write_report(rows, path_md, path_csv):
    cols = ["engine", "symbol", "variant", "n_trades", "wr", "net_rm",
            "pf", "pf_ex_best", "verdict"]
    with open(path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader(); w.writerows(rows)
    with open(path_md, "w", encoding="utf-8") as f:
        f.write("# v13 Compatibility Matrix\n\n")
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("|" + "---|" * len(cols) + "\n")
        for r in rows:
            f.write("| " + " | ".join(str(r[c]) for c in cols) + " |\n")
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_matrix_report.py -v` → Expected: 4 passed.

- [ ] **Step 5: Wire into harness**

Locate where the harness accumulates closed trades (the list feeding the per-combo report printed around line 1583 — each trade record already knows engine/symbol/pnl). Before `mt5.shutdown()` (line ~882 region), add:

```python
# ── v13: MATRIX REPORT ───────────────────────────────────────
from matrix_report import build_matrix, write_report
from datetime import date as _date
_rows = build_matrix([dict(engine=t["engine"], symbol=t["symbol"],
                           variant=t.get("variant", "base"), pnl_rm=t["pnl_rm"])
                      for t in all_trades])      # adapt name to actual trade list
write_report(_rows, f"docs/reports/v13_matrix_{_date.today()}.md",
             f"docs/reports/v13_matrix_{_date.today()}.csv")
print(f"Matrix report: docs/reports/v13_matrix_{_date.today()}.md")
```

Adapt field names to the actual trade-record structure (read the accumulation code first; pnl field may be named `pnl`, `net`, or similar).

- [ ] **Step 6: Full run + commit report**

Run: `python backtest_master_v13.py` → report file appears; verdicts match printed stats.

```powershell
cd C:\fx_agents; git add matrix_report.py tests/ backtest_master_v13.py docs/reports/*.md; git commit -m "v13: compatibility-matrix report with PASS/FAIL/INSUFFICIENT_DATA verdicts"; git push
```

---

### Task 7: GVE SELL + NY-window variants

**Files:**
- Modify: `backtest_master_v13.py` (GVE section: `gve_in_session` line ~481, GVE scan loop lines ~568-682)

**Interfaces:**
- Produces: module flags `GVE_SELL = False`, `GVE_NY_WINDOW = False` near the top of the GVE section. Trades generated under a variant carry `variant="GVE_SELL"` / `"GVE_NY"` so the matrix reports them as separate rows.

- [ ] **Step 1: Read the GVE scan loop (lines 568-682) and confirm the BUY restriction location**

`gve_sweep`, `gve_expansion`, `gve_levels` already take `direction` (lines 508/527/554). Find where the scan calls them with a hardcoded `"BUY"`.

- [ ] **Step 2: Add flags + parameterize direction**

```python
GVE_SELL      = False   # v13 variant: test SELL-side mirror
GVE_NY_WINDOW = False   # v13 variant: re-test NY 12:00-14:00 UTC with v12 filters
```

In the scan loop, replace the single BUY pass with `for _direction in (["BUY"] + (["SELL"] if GVE_SELL else [])):` and tag resulting trades `variant="GVE_SELL"` when direction is SELL. Verify sweep/pool logic is genuinely symmetric — SELL must sweep the HIGH-side liquidity pools (Asian high, prev-day high); if `gve_pools` returns pools without side labels, read it (line 488) and select the correct side per direction. If asymmetry runs deeper than pool selection, STOP and document rather than force a broken mirror.

- [ ] **Step 3: NY window**

In `gve_in_session` (line 481), add:

```python
    if GVE_NY_WINDOW and NY_KZ_START <= h < NY_KZ_END:   # 12:00-14:00 UTC
        return True, "NY_Open"
```

Tag trades entered in `NY_Open` with `variant="GVE_NY"` (SELL+NY combined → `"GVE_SELL_NY"`).

- [ ] **Step 4: Regression with flags OFF**

Run: `python backtest_master_v13.py` → baseline unchanged (287 / 49.5% / PF 2.19 for base rows).

- [ ] **Step 5: Variant runs (one flag at a time, then both)**

Three runs, flipping flags between runs: SELL only, NY only, both. Record matrix rows for each. Promotion needs ≥30 trades per GVE variant (Global Constraints).

- [ ] **Step 6: Commit**

```powershell
cd C:\fx_agents; git add backtest_master_v13.py docs/reports/; git commit -m "v13: GVE SELL-side and NY-window variants (flag-gated, base regression clean)"; git push
```

---

### Task 8: HPE SELL variant

**Files:**
- Modify: `backtest_master_v13.py` (HPE section lines ~1204-1378)

**Interfaces:**
- Produces: flag `HPE_SELL = False`; SELL trades tagged `variant="HPE_SELL"`.

- [ ] **Step 1: Read `hpe_w1_dir` (line 1212) and the HPE scan loop; locate the BUY-only filter**

`hpe_w1_dir(w1, d1)` derives direction from the weekly trend — check whether it can return "SELL" and gets filtered downstream, or returns BUY/None only.

- [ ] **Step 2: Parameterize**

Add `HPE_SELL = False`. Where the scan discards non-BUY directions, allow SELL when the flag is on. `hpe_pivots`/`hpe_find_level`/`hpe_lvls` already take direction-neutral inputs (line 1218-1257) — SELL pulls back UP to a pivot in a W1 downtrend: confirm `hpe_fib_ok` (line 1237) and `hpe_h4_mom` (line 1246) handle `direction="SELL"` by reading them; they take `direction` params, so they should. If any is BUY-hardcoded internally, mirror its comparison operators and document the change in the commit message.

- [ ] **Step 3: Regression (flag off) → variant run (flag on) → record matrix rows**

Run twice: `python backtest_master_v13.py`. Base rows identical; HPE_SELL rows appear in run 2.

- [ ] **Step 4: Commit**

```powershell
cd C:\fx_agents; git add backtest_master_v13.py docs/reports/; git commit -m "v13: HPE SELL-side variant (flag-gated)"; git push
```

---

### Task 9: New-market scan

**Files:**
- Create: `market_scan.py`
- Create: `docs/reports/market_scan_<date>.md` (output)

**Interfaces:**
- Consumes: MT5 terminal (open).
- Produces: report of every symbol class MetaQuotes-Demo offers (path, contract size, tick value, spread, M15 history depth) — the factual basis for deciding whether indices/crypto engines are worth designing (which would be a NEW spec, not this plan).

- [ ] **Step 1: Implement**

```python
# market_scan.py
"""Enumerate what MetaQuotes-Demo actually offers beyond the 9 traded
symbols. Output feeds the 'new markets' decision in spec 2026-07-03 §Phase 4.
Run with MT5 open: python market_scan.py"""
import MetaTrader5 as mt5
from datetime import date

def main():
    if not mt5.initialize():
        raise SystemExit("MT5 initialize failed — open the MT5 terminal first")
    syms = mt5.symbols_get()
    lines = ["# MetaQuotes-Demo Market Scan — " + str(date.today()), "",
             "| symbol | path | contract | tick_value | spread_pts | M15 bars |",
             "|---|---|---|---|---|---|"]
    for s in sorted(syms, key=lambda x: x.path):
        mt5.symbol_select(s.name, True)
        rates = mt5.copy_rates_from_pos(s.name, mt5.TIMEFRAME_M15, 0, 99999)
        depth = len(rates) if rates is not None else 0
        lines.append(f"| {s.name} | {s.path} | {s.trade_contract_size} "
                     f"| {s.trade_tick_value} | {s.spread} | {depth} |")
    mt5.shutdown()
    out = f"docs/reports/market_scan_{date.today()}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("Wrote", out, f"({len(syms)} symbols)")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run** — `python market_scan.py` → report written. Review: any index/metal/crypto CFDs with ≥20,000 M15 bars are viable future candidates; note them at the bottom of the report manually with a "requires new spec" marker.

- [ ] **Step 3: Commit**

```powershell
cd C:\fx_agents; git add market_scan.py docs/reports/; git commit -m "v13: broker market scan - factual basis for future new-market engines"; git push
```

---

### Task 10: System revalidation (walk-forward + Monte Carlo) and promotion

**Files:**
- Modify: `walkforward_v11.py` → save as `walkforward_v13.py` (universe = baseline + PASS combos)
- Modify: `config.py` (NOT committed — promotions recorded in VERSION_HISTORY.md)
- Modify: `VERSION_HISTORY.md`

**Interfaces:**
- Consumes: matrix reports from Tasks 4–8 (PASS rows only).

- [ ] **Step 1: Collect PASS rows** from the latest matrix report. If zero PASS rows: skip to Step 5 and record "no promotions — v13 is harness-infrastructure only" in VERSION_HISTORY.md. That is a legitimate outcome, not a failure.

- [ ] **Step 2: Walk-forward with additions**

Copy `walkforward_v11.py` → `walkforward_v13.py`; point it at the v13 harness/universe including PASS combos (read its structure first — it's 5.5KB). Run: `python walkforward_v13.py`. Requirement: 5/5 OOS folds profitable WITH additions. Any fold turning negative → remove the weakest addition (lowest OOS PF), re-run. Repeat until 5/5 or no additions remain.

- [ ] **Step 3: Monte Carlo with additions**

`montecarlo_v11.py` bootstraps from the trade list — feed it the v13 trade list (baseline + surviving additions). Requirement: median DD ≤ 21.9%, P95 ≤ 53.8%, ruin ≤ 4.09% (not worse than current). Worse → same removal loop as Step 2.

- [ ] **Step 4: Promote survivors to config.py**

For each surviving combo: add to `KIRA_ROUTING_TABLE` and `ENGINE_SYMBOL_WHITELIST` (config.py:33/65) with a `# v13 PROBATION 0.5x until 20 SIM signals` comment; new symbols also join `PAIRS`/`JPY_PAIRS` (config.py:23-26) and the MT5 Market Watch instruction list in OPERATING_GUIDE.txt. GVE/HPE SELL promotions additionally require porting the variant logic into `agent_kira.py` behind config flags default-off — **that port is its own reviewed commit** touching the live engine, with `test_full_system.py` run before and after.

- [ ] **Step 5: Version bookkeeping**

Update `VERSION_HISTORY.md` v13 row with measured numbers (from the walk-forward-approved run). List every promotion (or "none") in the notes. Then:

```powershell
cd C:\fx_agents; git add -A; git commit -m "v13: promotions + revalidation results (see VERSION_HISTORY.md)"; git tag v13; git push; git push --tags
```

- [ ] **Step 6: Update the Notion system-state page** (page `36cf0d18-b53f-81ee-8f7a-effc6f67c727`) with the v12 changelog (still missing) and the v13 results, so code and Notion stop drifting.

---

## Plan Self-Review (completed)

- **Spec coverage:** Phase 0 done pre-plan; Phase 1 = Tasks 1-3, 6; Phase 2 = Tasks 4-5; Phase 3 = Task 7; Phase 4 = Tasks 8-9 (new-engine design explicitly deferred to a future spec, per spec §Phase 4); Phase 5 = Task 10. Spec §8 harness self-test = Task 1 Step 3 + per-task regression gates.
- **Placeholder scan:** Tasks 4 Step 2, 7 Step 2, 8 Step 2 require reading harness internals before editing — these are read-then-edit instructions with defined invariants and STOP conditions, not TBDs; full mirrored code cannot be written before those reads without inventing line contents.
- **Type consistency:** `check_profile` and `build_matrix`/`write_report` signatures match between definition and call sites; trade-dict keys (`engine`, `symbol`, `variant`, `pnl_rm`) consistent across Tasks 6-8.
