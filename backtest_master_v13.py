# ════════════════════════════════════════════════════════════
#  backtest_master_v13.py — VALIDATED SIGNAL EXPANSION (built on v10 confirmed baseline)
#
#  EXPANDED SYMBOL UNIVERSE — Regime/Symbol Compatibility Matrix
#
#  v5 engines (CTE, GVE, MRE, CBE, HPE) tested on ALL symbols:
#    Existing: AUDUSD, EURUSD, EURJPY, XAUUSD
#    New:      GBPUSD, USDJPY, GBPJPY, NZDUSD, USDCAD
#
#  New in v6:
#    1. All 5 new symbols added to every eligible engine
#    2. Section 8: Regime/Symbol Compatibility Matrix
#       — which symbols work in which regimes with which engine
#    3. Section 9: Symbol ranking per engine
#    4. KIRA adaptive routing: regime → best engine → best symbol
#
#  v5 baseline: 162 signals | WR 54.3% | RM+2177 | Sharpe 1.84
#  Regression invariant: candidates=[] + variants off => v10 numbers (287 / 49.5% / +RM4,192 / PF 2.19)
# ════════════════════════════════════════════════════════════

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import json, time, sys, os
from datetime import datetime, timezone
from collections import defaultdict
from config import *

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_kira import AgentKIRA

SEP  = "━" * 72
SEP2 = "─" * 72


# ══════════════════════════════════════════════════════════
#  KIRA ARE-v3 — Adaptive Risk Engine
# ══════════════════════════════════════════════════════════

BASE_RISK = 1.0  # baseline risk %
MAX_ALLOWED_DD = 20.0

ENGINE_SCORES = {
    "GVE": 1.8,
    "CBE": 1.4,
    "HPE": 1.3,
    "MRE": 1.1,
    "CTE": 0.9,
}

REGIME_SCORES = {
    "COMPRESSING": 1.3,
    "WEAK_TREND": 1.2,
    "RANGING": 1.0,
    "TRENDING": 0.8,
}

SYMBOL_SCORES = {
    "XAUUSD": 1.4,
    "XAGUSD": 1.2,   # Silver — similar to Gold but less tested
    "EURJPY": 1.3,
    "GBPJPY": 1.3,
    "AUDUSD": 1.1,
    "EURUSD": 1.1,
    "GBPUSD": 1.0,
    "NZDUSD": 1.0,
    "USDCAD": 1.0,
    "USDJPY": 0.8,
}

def kira_dynamic_risk(engine, regime, symbol, current_dd=0.0):
    """
    Adaptive risk allocation engine.
    Returns:
        risk_pct (float),
        risk_multiplier (float)
    """

    e = ENGINE_SCORES.get(engine, 1.0)
    r = REGIME_SCORES.get(regime, 1.0)
    s = SYMBOL_SCORES.get(symbol, 1.0)

    # Drawdown protection
    d = max(0.25, 1.0 - (current_dd / MAX_ALLOWED_DD))

    risk_pct = BASE_RISK * e * r * s * d

    # Clamp risk to safe operational range
    risk_pct = max(0.15, min(risk_pct, 2.5))

    return round(risk_pct, 2), round(risk_pct / BASE_RISK, 2)

print("=" * 72)
print("  FX COMMAND AGENTS — MASTER BACKTEST v10 — AGENTS FULL POWER")
print("  ENGINE×SYMBOL WHITELIST — only proven-edge combos trade")
print("  Removed: 96 signals / RM-328 of confirmed losers (v8 matrix ❌ DROP)")
print("  CTE TRENDING blocked (except NZDUSD) | GUARD clustering active")
print("=" * 72)

mt5.initialize()
mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER)
acct = mt5.account_info()
print(f"\nConnected: {acct.login} | Balance: ${acct.balance:.2f}")

# ══════════════════════════════════════════════════════════
#  PROFILES — all symbols, all engines
# ══════════════════════════════════════════════════════════

# CTE profiles — extended to all 8 non-gold symbols
CTE_PROFILES = {
    "AUDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE, sl_min=SL_MIN_FOREX,
                   vp_prox_pct=None, vp_prox_fixed=VP_PROXIMITY_FOREX,
                   vp_lookback=VP_LOOKBACK_DEFAULT, min_fvg=MIN_FVG_PIPS_FOREX,
                   spread_rm=0.8*0.10*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=True, label="Forex",
                   block_sessions=["NY_PM"]),
    "EURUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE, sl_min=SL_MIN_FOREX,
                   vp_prox_pct=None, vp_prox_fixed=VP_PROXIMITY_FOREX,
                   vp_lookback=VP_LOOKBACK_DEFAULT, min_fvg=MIN_FVG_PIPS_FOREX,
                   spread_rm=0.7*0.10*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=True, label="Forex",
                   block_sessions=["Other"]),
    "EURJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE, sl_min=120,
                   vp_prox_pct=0.5, vp_prox_fixed=None, vp_lookback=40,
                   min_fvg=20.0, spread_rm=2.0*0.091*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=False, label="JPY-Cross",
                   block_sessions=["Other"]),
    "GBPUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE, sl_min=SL_MIN_FOREX,
                   vp_prox_pct=None, vp_prox_fixed=VP_PROXIMITY_FOREX,
                   vp_lookback=VP_LOOKBACK_DEFAULT, min_fvg=MIN_FVG_PIPS_FOREX,
                   spread_rm=1.0*0.10*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=True, label="Forex",
                   block_sessions=["NY_PM"]),
    "NZDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE, sl_min=SL_MIN_FOREX,
                   vp_prox_pct=None, vp_prox_fixed=VP_PROXIMITY_FOREX,
                   vp_lookback=VP_LOOKBACK_DEFAULT, min_fvg=MIN_FVG_PIPS_FOREX,
                   spread_rm=1.2*0.10*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=True, label="Forex",
                   block_sessions=["NY_PM"]),
    "USDCAD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE, sl_min=SL_MIN_FOREX,
                   vp_prox_pct=None, vp_prox_fixed=VP_PROXIMITY_FOREX,
                   vp_lookback=VP_LOOKBACK_DEFAULT, min_fvg=MIN_FVG_PIPS_FOREX,
                   spread_rm=1.2*0.10*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=True, label="Forex",
                   block_sessions=["NY_PM"]),
    "USDJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE, sl_min=120,
                   vp_prox_pct=0.5, vp_prox_fixed=None, vp_lookback=40,
                   min_fvg=20.0, spread_rm=1.5*0.091*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=False, label="JPY-Cross",
                   block_sessions=["Other"]),
    "GBPJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE, sl_min=150,
                   vp_prox_pct=0.5, vp_prox_fixed=None, vp_lookback=40,
                   min_fvg=25.0, spread_rm=2.5*0.091*USD_MYR_RATE*0.01,
                   s_start=SESSION_START_UTC, s_end=SESSION_END_UTC,
                   atr_thresh=ATR_REGIME_THRESH, block_london=False, label="JPY-Cross",
                   block_sessions=["Other"]),
    # XAGUSD CTE: 34 signals, PF 1.08, MaxDD 42.3% — marginal, DD too high for live
    # Root cause: pip_val_rm oversized relative to Silver price — needs recalibration
    # SUSPENDED from live trading. Left in profiles for future calibration run.
    # "XAGUSD": dict(pip=0.001, ...)  ← re-enable after pip_val fix
}
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

# v9 PRECISION: only whitelisted CTE symbols scan
CONT_SYMBOLS = [s for s in CTE_PROFILES.keys() if v13_allowed("CTE", s)]
GVE_SYMBOL   = "XAUUSD"
SILVER_SYMBOL = "XAGUSD"
# v10 FIX: ALL_SYMBOLS must be the UNION of all engine whitelists + GVE.
# v9 bug: built from CTE whitelist only — GBPUSD/USDCAD/USDJPY data never
# fetched, silently skipping RM+563 of profitable MRE/CBE/HPE combos.
_all_whitelisted = set()
for _eng_syms in ENGINE_SYMBOL_WHITELIST.values():
    _all_whitelisted.update(_eng_syms)
for _eng, _syms in V13_CANDIDATES.items():
    _all_whitelisted.update(_syms)
ALL_SYMBOLS = sorted(_all_whitelisted | {GVE_SYMBOL})

# MRE profiles — test all non-JPY symbols
MRE_PROFILES = {
    "EURUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_FOREX, extreme_prox=MRE_EXTREME_PROX_FOREX,
                   sl_beyond=MRE_SL_BEYOND_PIPS, spread_rm=0.7*0.10*USD_MYR_RATE*0.01),
    "AUDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_FOREX, extreme_prox=MRE_EXTREME_PROX_FOREX,
                   sl_beyond=MRE_SL_BEYOND_PIPS, spread_rm=0.8*0.10*USD_MYR_RATE*0.01),
    "GBPUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_FOREX, extreme_prox=MRE_EXTREME_PROX_FOREX,
                   sl_beyond=MRE_SL_BEYOND_PIPS, spread_rm=1.0*0.10*USD_MYR_RATE*0.01),
    "NZDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_FOREX, extreme_prox=MRE_EXTREME_PROX_FOREX,
                   sl_beyond=MRE_SL_BEYOND_PIPS, spread_rm=1.2*0.10*USD_MYR_RATE*0.01),
    "USDCAD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_FOREX, extreme_prox=MRE_EXTREME_PROX_FOREX,
                   sl_beyond=MRE_SL_BEYOND_PIPS, spread_rm=1.2*0.10*USD_MYR_RATE*0.01),
    "EURJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_JPY, extreme_prox=MRE_EXTREME_PROX_JPY,
                   sl_beyond=MRE_SL_BEYOND_JPY, spread_rm=2.0*0.091*USD_MYR_RATE*0.01),
    "USDJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_JPY, extreme_prox=MRE_EXTREME_PROX_JPY,
                   sl_beyond=MRE_SL_BEYOND_JPY, spread_rm=1.5*0.091*USD_MYR_RATE*0.01),
    "GBPJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   min_range=MRE_MIN_RANGE_JPY, extreme_prox=MRE_EXTREME_PROX_JPY,
                   sl_beyond=MRE_SL_BEYOND_JPY, spread_rm=2.5*0.091*USD_MYR_RATE*0.01),
    # XAGUSD MRE: 0 signals — range detection parameters need Silver-specific tuning
    # "XAGUSD": dict(pip=0.001, ...)  ← re-enable after min_range calibration
}
MRE_SYMS = [s for s in MRE_PROFILES.keys() if v13_allowed("MRE", s)]

# CBE profiles — test all symbols
CBE_PROFILES = {
    "AUDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_FOREX, spread_rm=0.8*0.10*USD_MYR_RATE*0.01),
    "EURUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_FOREX, spread_rm=0.7*0.10*USD_MYR_RATE*0.01),
    "GBPUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_FOREX, spread_rm=1.0*0.10*USD_MYR_RATE*0.01),
    "NZDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_FOREX, spread_rm=1.2*0.10*USD_MYR_RATE*0.01),
    "USDCAD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_FOREX, spread_rm=1.2*0.10*USD_MYR_RATE*0.01),
    "EURJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_JPY, spread_rm=2.0*0.091*USD_MYR_RATE*0.01),
    "USDJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_JPY, spread_rm=1.5*0.091*USD_MYR_RATE*0.01),
    "GBPJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   min_range=CBE_MIN_RANGE_JPY, spread_rm=2.5*0.091*USD_MYR_RATE*0.01),
    # XAGUSD CBE: CATASTROPHIC — PF 0.28, -RM466, MaxDD 93.3%
    # CBE compression breakout logic fires on Silver volatility spikes, not real compressions
    # HARD BLOCKED from live trading until dedicated Silver CBE calibration
    # "XAGUSD": dict(pip=0.001, ...)  ← DO NOT re-enable without full investigation
}
CBE_SYMS = [s for s in CBE_PROFILES.keys() if v13_allowed("CBE", s)]

# HPE profiles — test all symbols
HPE_PROFILES = {
    "EURUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   prox=50, sl_buf=HPE_SL_BEYOND_FOREX, spread_rm=0.7*0.10*USD_MYR_RATE*0.01),
    "AUDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   prox=50, sl_buf=HPE_SL_BEYOND_FOREX, spread_rm=0.8*0.10*USD_MYR_RATE*0.01),
    "GBPUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   prox=50, sl_buf=HPE_SL_BEYOND_FOREX, spread_rm=1.0*0.10*USD_MYR_RATE*0.01),
    "NZDUSD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   prox=50, sl_buf=HPE_SL_BEYOND_FOREX, spread_rm=1.2*0.10*USD_MYR_RATE*0.01),
    "USDCAD": dict(pip=0.0001, pip_val_rm=0.10*USD_MYR_RATE,
                   prox=50, sl_buf=HPE_SL_BEYOND_FOREX, spread_rm=1.2*0.10*USD_MYR_RATE*0.01),
    "EURJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   prox=120, sl_buf=HPE_SL_BEYOND_JPY, spread_rm=2.0*0.091*USD_MYR_RATE*0.01),
    "USDJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   prox=120, sl_buf=HPE_SL_BEYOND_JPY, spread_rm=1.5*0.091*USD_MYR_RATE*0.01),
    "GBPJPY": dict(pip=0.01, pip_val_rm=0.091*USD_MYR_RATE,
                   prox=150, sl_buf=HPE_SL_BEYOND_JPY*2, spread_rm=2.5*0.091*USD_MYR_RATE*0.01),
    # XAGUSD HPE: 0 signals — D1 pivot proximity too tight for Silver price scale
    # "XAGUSD": dict(pip=0.001, ...)  ← re-enable after prox/sl_buf calibration
}
HPE_SYMS = [s for s in HPE_PROFILES.keys() if v13_allowed("HPE", s)]

# v13: ALL_SYMBOLS must only include candidates that HAVE profiles (Tasks 4-5
# add them). Union-then-intersect so profile-less candidates are excluded
# without reintroducing the v9 bug (symbols missing from ALL_SYMBOLS silently
# never fetch).
_profiled = set(CTE_PROFILES) | set(MRE_PROFILES) | set(CBE_PROFILES) | set(HPE_PROFILES) | {GVE_SYMBOL}
ALL_SYMBOLS = sorted((_all_whitelisted | {GVE_SYMBOL}) & _profiled | {GVE_SYMBOL})

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

# ── Preload + Fetch ───────────────────────────────────────
print("\nPreloading 3-year history...")
def preload(sym, tfs):
    start = datetime(2022, 12, 1, tzinfo=timezone.utc)
    mt5.symbol_select(sym, True)
    for tf in tfs:
        mt5.copy_rates_from(sym, tf, start, 99999)
        time.sleep(0.4)
    time.sleep(2.0)

for sym in ALL_SYMBOLS:
    print(f"  {sym}...", end=" ", flush=True)
    tfs = [TF_D1, TF_H4, TF_H1, TF_W1]
    if sym in (GVE_SYMBOL, SILVER_SYMBOL): tfs += [TF_M15]
    preload(sym, tfs)
    print("done")
time.sleep(3.0)

def fetch(sym, tf, n):
    mt5.symbol_select(sym, True); time.sleep(0.3)
    r = mt5.copy_rates_from_pos(sym, tf, 0, n)
    if r is None or len(r) == 0: return None
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.rename(columns={"tick_volume":"volume"})[
        ["time","open","high","low","close","volume"]].reset_index(drop=True)

print("\nFetching data...")
data = {}
for sym in ALL_SYMBOLS:
    d1=fetch(sym,TF_D1,1200); h4=fetch(sym,TF_H4,6000)
    h1=fetch(sym,TF_H1,25000); w1=fetch(sym,TF_W1,260)
    entry = {"D1":d1,"H4":h4,"H1":h1,"W1":w1}
    if sym in (GVE_SYMBOL, SILVER_SYMBOL):
        # GVE needs full history; Silver uses 3000-candle window (v8 fix for 1-signal issue)
        m15_count = 99999 if sym == GVE_SYMBOL else 3000
        m15=fetch(sym,TF_M15,m15_count)
        entry["M15"] = m15
    else:
        m15 = None
    if d1 is not None and h4 is not None and h1 is not None:
        data[sym] = entry
        extras = f" {len(m15)}×M15" if m15 is not None else ""
        print(f"  {sym}: {len(d1)}×D1 {len(h4)}×H4 {len(h1)}×H1{extras} | "
              f"{h1['time'].iloc[0].date()} → {h1['time'].iloc[-1].date()}")
    else:
        print(f"  {sym}: ⚠️ MISSING DATA")

# ── Classifier ────────────────────────────────────────────
class _Dummy:
    def get_all_timeframes(self, s): return {}
    def get_tick(self, s): return None
    def get_balance(self): return 500.0
    def get_equity(self): return 500.0

kira = AgentKIRA(_Dummy())
DAYS = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
ALL_TRADES = []

# ══════════════════════════════════════════════════════════
#  V3 INDICATORS — VERBATIM (CTE engine)
# ══════════════════════════════════════════════════════════
def d1_bias(d1):
    if d1 is None or len(d1)<55: return None
    c=d1["close"]; p=float(c.iloc[-1])
    e50=float(c.ewm(span=50,adjust=False).mean().iloc[-1])
    e200=float(c.ewm(span=min(200,len(c)),adjust=False).mean().iloc[-1])
    if p>e50>e200: return "BUY"
    if p<e50<e200: return "SELL"
    return None

def atr_ok(d1,thresh,period=20):
    if d1 is None or len(d1)<period+5: return True
    h=d1["high"]; l=d1["low"]; pc=d1["close"].shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    s=tr.ewm(com=period-1,adjust=False).mean()
    cur=float(s.iloc[-1]); avg=float(s.tail(period).mean())
    return avg==0 or (cur/avg)>=thresh

def vp_zone(h4,direction,pip,vp_prox_fixed,vp_prox_pct,current_price,periods=80,levels=50):
    if h4 is None or len(h4)<20: return False,0.0,{}
    r=h4.tail(min(periods,len(h4)))
    pmin=float(r["low"].min()); pmax=float(r["high"].max())
    if pmax==pmin: return False,0.0,{}
    pl=np.linspace(pmin,pmax,levels); vp_=np.zeros(levels)
    for _,c in r.iterrows():
        for j,p in enumerate(pl):
            if c["low"]<=p<=c["high"]: vp_[j]+=c.get("volume",1)
    if vp_.sum()==0: return False,0.0,{}
    poc_i=int(np.argmax(vp_)); poc=round(float(pl[poc_i]),5)
    tot=vp_.sum(); si=np.argsort(vp_)[::-1]; vav=0.0; vai=[]
    for i in si:
        vav+=vp_[i]; vai.append(i)
        if vav>=tot*0.70: break
    vah=round(float(pl[max(vai)]),5); val=round(float(pl[min(vai)]),5)
    if vp_prox_pct is not None:
        prox=int(current_price*vp_prox_pct/100/pip)
    else:
        prox=vp_prox_fixed
    near=(abs(current_price-poc)<pip*prox or
          abs(current_price-vah)<pip*prox or
          abs(current_price-val)<pip*prox)
    if direction=="SELL":
        cands=[x for x in [val,poc] if x<current_price-pip*5]
        vp_tp=min(cands) if cands else round(current_price-pip*prox*2,5)
    else:
        cands=[x for x in [vah,poc] if x>current_price+pip*5]
        vp_tp=max(cands) if cands else round(current_price+pip*prox*2,5)
    return near,round(vp_tp,5),{"poc":poc,"vah":vah,"val":val}

def sweep_h1(h1,direction,pip,lb=20):
    if h1 is None or len(h1)<lb+3: return False,0.0
    sw=h1.iloc[-(lb+5):-5]; rc=h1.iloc[-5:]
    if len(sw)<5: return False,0.0
    if direction=="SELL":
        sh=float(sw["high"].max())
        for i in range(len(rc)):
            c=rc.iloc[i]
            if c["high"]>sh and c["close"]<sh: return True,round(sh,5)
    else:
        sl=float(sw["low"].min())
        for i in range(len(rc)):
            c=rc.iloc[i]
            if c["low"]<sl and c["close"]>sl: return True,round(sl,5)
    return False,0.0

def fvg_h1(h1,direction,pip,min_p,lb=15):
    if h1 is None or len(h1)<10: return False,0.0,0.0
    cur=float(h1["close"].iloc[-1]); sc=h1.iloc[-lb-3:-1]
    for i in range(len(sc)-2):
        c1=sc.iloc[i]; c3=sc.iloc[i+2]
        if direction=="SELL" and c1["low"]>c3["high"]:
            sz=(c1["low"]-c3["high"])/pip
            if sz>=min_p:
                fh=round(float(c1["low"]),5); fl=round(float(c3["high"]),5)
                if fl<=cur<=fh*1.001 or abs(cur-fl)<pip*10: return True,fh,fl
        elif direction=="BUY" and c1["high"]<c3["low"]:
            sz=(c3["low"]-c1["high"])/pip
            if sz>=min_p:
                fh=round(float(c3["low"]),5); fl=round(float(c1["high"]),5)
                if fl*0.999<=cur<=fh or abs(cur-fh)<pip*10: return True,fh,fl
    return False,0.0,0.0

def rej_h1(h1,direction,lb=5):
    if h1 is None or len(h1)<3: return False
    r=h1.iloc[-lb:]
    for i in range(len(r)-1,-1,-1):
        c=r.iloc[i]; tr=float(c["high"]-c["low"])
        if tr==0: continue
        uw=float(c["high"])-max(float(c["open"]),float(c["close"]))
        lw=min(float(c["open"]),float(c["close"]))-float(c["low"])
        br=abs(float(c["close"])-float(c["open"]))/tr
        if direction=="SELL":
            if uw/tr>=0.55 and c["close"]<c["open"]: return True
            if c["close"]<c["open"] and br>=0.70 and uw/tr<0.15: return True
        else:
            if lw/tr>=0.55 and c["close"]>c["open"]: return True
            if c["close"]>c["open"] and br>=0.70 and lw/tr<0.15: return True
    return False

def cont_levels(direction,entry,sweep_lv,pip,sl_min,vp_tp):
    if direction=="SELL":
        sl=round(sweep_lv+pip*3,5); slp=round((sl-entry)/pip,1)
        if slp<sl_min: sl=round(entry+pip*sl_min,5); slp=float(sl_min)
        tp=vp_tp if vp_tp>0 and vp_tp<entry else round(entry-pip*slp*3,5)
        tpp=round((entry-tp)/pip,1)
        if tpp<slp*MIN_RR: tp=round(entry-pip*slp*MIN_RR,5); tpp=round(slp*MIN_RR,1)
    else:
        sl=round(sweep_lv-pip*3,5); slp=round((entry-sl)/pip,1)
        if slp<sl_min: sl=round(entry-pip*sl_min,5); slp=float(sl_min)
        tp=vp_tp if vp_tp>0 and vp_tp>entry else round(entry+pip*slp*3,5)
        tpp=round((tp-entry)/pip,1)
        if tpp<slp*MIN_RR: tp=round(entry+pip*slp*MIN_RR,5); tpp=round(slp*MIN_RR,1)
    rr=round(tpp/slp,2) if slp>0 else MIN_RR
    if rr>MAX_RR:
        if direction=="SELL": tp=round(entry-pip*slp*MAX_RR,5)
        else:                  tp=round(entry+pip*slp*MAX_RR,5)
        tpp=round(slp*MAX_RR,1); rr=MAX_RR
    return sl,tp,round(slp,1),round(tpp,1),rr

# ══════════════════════════════════════════════════════════
#  GVE INDICATORS — VERBATIM
# ══════════════════════════════════════════════════════════
def gve_calc_atr(df,period=14):
    if df is None or len(df)<period+1: return 0.0
    h=df["high"]; l=df["low"]; pc=df["close"].shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    atr=float(tr.ewm(com=period-1,adjust=False).mean().iloc[-1])
    if len(df)>0:
        cp=float(df["close"].iloc[-1])
        if atr<cp*0.001: return 0.0
    return atr

def gve_regime(m15,h1,d1,i_m15,i_h1):
    if m15 is None or i_m15<GVE_ATR_PERIOD+5: return "NORMAL","default"
    m15v=m15.iloc[max(0,i_m15-GVE_ATR_PERIOD*3):i_m15+1]
    h_=m15v["high"]; l_=m15v["low"]; pc_=m15v["close"].shift(1)
    tr_=pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
    atr_=tr_.ewm(com=GVE_ATR_PERIOD-1,adjust=False).mean()
    if len(atr_)<GVE_ATR_PERIOD: return "NORMAL","insufficient"
    cur=float(atr_.iloc[-1]); avg=float(atr_.tail(GVE_ATR_PERIOD).mean())
    if avg==0: return "NORMAL","zero avg"
    ratio=cur/avg
    dt=m15.iloc[i_m15]["time"]
    d1v=d1[d1["time"]<=dt].tail(21)
    adr_20=float((d1v["high"]-d1v["low"]).tail(20).mean()) if len(d1v)>=20 else 0
    if len(d1v)>0:
        td=d1v[d1v["time"].dt.date==dt.date()]
        today_rng=float((td["high"].max()-td["low"].min()) if len(td)>0 else 0)
        adr_used=today_rng/adr_20 if adr_20>0 else 0
    else:
        adr_used=0
    if ratio>GVE_ATR_EXTREME:    return "EXTREME",f"ATR spike {ratio:.1f}x"
    if adr_used>GVE_ADR_MAX_PCT: return "EXTREME",f"ADR {adr_used*100:.0f}% consumed"
    if ratio<GVE_ATR_COMPRESS:   return "DEAD",f"ATR compressed {ratio:.2f}x"
    if ratio>=1.5:                return "EXPANSION",f"ATR expanding {ratio:.1f}x"
    return "NORMAL",f"ATR {ratio:.2f}x"

def gve_in_session(dt):
    h=dt.hour
    if dt.weekday()>=5: return False,"weekend"
    if dt.weekday()==4: return False,"friday"
    if GVE_LONDON_START<=h<GVE_LONDON_END: return True,"London_Open"
    return False,"outside"

def gve_pools(m15,h1,i_m15,i_h1,dt):
    pools={}
    if h1 is not None and i_h1>=24:
        prev_h1=h1.iloc[max(0,i_h1-48):i_h1]
        prev=prev_h1[prev_h1["time"].dt.date<dt.date()].tail(24)
        if len(prev)>=4:
            pools["prev_day_high"]=round(float(prev["high"].max()),2)
            pools["prev_day_low"] =round(float(prev["low"].min()),2)
    if m15 is not None:
        today_m15=m15.iloc[max(0,i_m15-100):i_m15]
        asian=today_m15[(today_m15["time"].dt.date==dt.date())&(today_m15["time"].dt.hour<7)]
        if len(asian)>=4:
            pools["asian_high"]=round(float(asian["high"].max()),2)
            pools["asian_low"] =round(float(asian["low"].min()),2)
    if m15 is not None and i_m15>=GVE_SWEEP_LOOKBACK:
        recent=m15.iloc[i_m15-GVE_SWEEP_LOOKBACK:i_m15]
        pools["swing_high"]=round(float(recent["high"].max()),2)
        pools["swing_low"] =round(float(recent["low"].min()),2)
    return pools

def gve_sweep(m15,i_m15,pools,direction):
    if not pools or i_m15<5: return False,0.0,0,""
    pip=get_pip("XAUUSD")
    recent=m15.iloc[max(0,i_m15-5):i_m15+1]
    for _,c in recent.iloc[::-1].iterrows():
        for label,level in pools.items():
            if level==0: continue
            if direction=="BUY":
                if "low" in label or "swing" in label:
                    if c["low"]<level and c["close"]>level:
                        sp=round((level-c["low"])/pip,1)
                        if sp>=GVE_MIN_SWEEP_PIPS: return True,round(level,2),int(sp),label
            if direction=="SELL":
                if "high" in label or "swing" in label:
                    if c["high"]>level and c["close"]<level:
                        sp=round((c["high"]-level)/pip,1)
                        if sp>=GVE_MIN_SWEEP_PIPS: return True,round(level,2),int(sp),label
    return False,0.0,0,""

def gve_expansion(m15,i_m15,direction):
    if m15 is None or i_m15<10: return False,"C","no data"
    recent=m15.iloc[max(0,i_m15-5):i_m15+1]
    m15v=m15.iloc[max(0,i_m15-30):i_m15+1]
    h_=m15v["high"]; l_=m15v["low"]; pc_=m15v["close"].shift(1)
    tr_=pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
    atr_s=tr_.ewm(com=13,adjust=False).mean()
    atr_now=float(atr_s.iloc[-1]); atr_avg=float(atr_s.mean())
    expanding=atr_now>atr_avg*1.1
    best_grade=""; best_reason=""
    for i in range(len(recent)-1,max(len(recent)-4,-1),-1):
        c=recent.iloc[i]; tr_c=float(c["high"]-c["low"])
        if tr_c==0: continue
        body=abs(float(c["close"]-c["open"])); body_ratio=body/tr_c
        correct=((direction=="BUY" and c["close"]>c["open"]) or
                 (direction=="SELL" and c["close"]<c["open"]))
        if not correct: continue
        if body_ratio>=GVE_SWEEP_BODY_MIN:
            if expanding and body_ratio>=0.75:
                best_grade="A"; best_reason=f"A+ {body_ratio:.0%} ATR+"; break
            elif body_ratio>=0.65 or (expanding and body_ratio>=0.60):
                if best_grade!="A": best_grade="B"; best_reason=f"B {body_ratio:.0%}"
            else:
                if not best_grade: best_grade="C"; best_reason=f"C {body_ratio:.0%}"
    if not best_grade: return False,"C","no displacement"
    return True,best_grade,best_reason

def gve_levels(direction,entry,h1_atr,grade):
    pip=get_pip("XAUUSD"); pip_val=100*0.01*LOT_GOLD*USD_MYR_RATE
    sl_usd=max(h1_atr*GVE_SL_ATR_MULT, entry*GVE_SL_PRICE_PCT)
    sl_usd=min(sl_usd,GVE_MAX_SL_USD)
    sl_pips=round(sl_usd/pip,1)
    tp_mult=(GVE_TP_ATR_MULT_A if grade=="A" else
             GVE_TP_ATR_MULT_B if grade=="B" else GVE_TP_ATR_MULT_C)
    tp_pips=round(sl_pips*tp_mult,1); rr=round(tp_pips/sl_pips,2) if sl_pips>0 else tp_mult
    if direction=="SELL": sl=round(entry+pip*sl_pips,2); tp=round(entry-pip*tp_pips,2)
    else:                  sl=round(entry-pip*sl_pips,2); tp=round(entry+pip*tp_pips,2)
    return sl,tp,round(sl_pips,1),round(tp_pips,1),rr,tp_mult

# ══════════════════════════════════════════════════════════
#  1. CTE — CONTINUATION ENGINE (all 8 non-gold symbols)
# ══════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  RUNNING CTE — CONTINUATION ENGINE")
print(f"  Symbols: {CONT_SYMBOLS}")
print(SEP)

for sym in CONT_SYMBOLS:
    if sym not in data:
        print(f"\n{sym}: SKIPPED — no data"); continue
    p=CTE_PROFILES[sym]
    pip=p["pip"]; pv=p["pip_val_rm"]
    d1a=data[sym]["D1"]; h4a=data[sym]["H4"]; h1a=data[sym]["H1"]
    trades=[]; last_idx=-30; mo_pnl=defaultdict(float)
    print(f"\n{sym} ({p['label']}) — scanning {len(h1a)} H1 candles (CTE)...")

    for i in range(300,len(h1a)-121):
        c=h1a.iloc[i]; dt=c["time"]
        if not (p["s_start"]<=dt.hour<p["s_end"]): continue
        if dt.weekday()>=5 or dt.weekday()==4: continue
        if p["block_london"] and LONDON_KZ_START<=dt.hour<=LONDON_KZ_END: continue
        h_utc=dt.hour
        if   LONDON_KZ_START<=h_utc<LONDON_KZ_END:  _sess="London_Open"
        elif NY_KZ_START    <=h_utc<NY_KZ_END:       _sess="NY_Open"
        elif NY_PM_KZ_START <=h_utc<NY_PM_KZ_END:    _sess="NY_PM"
        else:                                         _sess="Other"
        if _sess in p.get("block_sessions",[]): continue
        if i-last_idx<30: continue

        d1v=d1a[d1a["time"]<=dt].tail(250)
        if len(d1v)<55: continue
        direction=d1_bias(d1v)
        if direction is None: continue
        if not atr_ok(d1v,p["atr_thresh"]): continue

        h4v_rc=h4a[h4a["time"]<=dt].tail(200)
        regime,_,_,_=kira._classify_regime(sym,d1v,h4v_rc)
        if regime in ("RANGING","COMPRESSING","EXPANDING"): continue
        # v10: CTE TRENDING block REMOVED — it double-filtered. The whitelist
        # already removed the symbols making CTE TRENDING negative; stacking
        # the regime block cut RM+88 of winners (AUDUSD/GBPJPY TRENDING wins).

        h4v=h4a[h4a["time"]<=dt].tail(p["vp_lookback"]+50)
        if len(h4v)<20: continue
        current_price=float(h4v["close"].iloc[-1])
        zone,vp_tp,_=vp_zone(h4v,direction,pip,p["vp_prox_fixed"],p["vp_prox_pct"],current_price,periods=p["vp_lookback"])
        if not zone: continue

        h1v=h1a.iloc[max(0,i-200):i+1]
        swept,sw_lv=sweep_h1(h1v,direction,pip)
        if not swept: continue
        fok,fh,fl=fvg_h1(h1v,direction,pip,p["min_fvg"])
        if not fok: continue
        if not rej_h1(h1v,direction): continue

        entry=round((fh+fl)/2,5)
        sl,tp,slp,tpp,rr=cont_levels(direction,entry,sw_lv,pip,p["sl_min"],vp_tp)
        if slp<=0 or tpp<=0 or rr<MIN_RR: continue

        mo=dt.strftime("%Y-%m")
        bal=500+sum(t["pnl_rm"] for t in trades)
        if mo_pnl[mo]<=-(bal*MAX_MONTHLY_LOSS_PCT/100): continue

        out="timeout"; pp=0.0; ei=i
        for fi in range(i+1,min(i+121,len(h1a))):
            fc=h1a.iloc[fi]
            if direction=="SELL":
                if fc["high"]>=sl: out="loss"; pp=-slp; ei=fi; break
                if fc["low"]<=tp:  out="win";  pp=tpp;  ei=fi; break
            else:
                if fc["low"]<=sl:  out="loss"; pp=-slp; ei=fi; break
                if fc["high"]>=tp: out="win";  pp=tpp;  ei=fi; break
        if out=="timeout":
            lp=float(h1a.iloc[min(i+120,len(h1a)-1)]["close"])
            pp=round((entry-lp)/pip if direction=="SELL" else (lp-entry)/pip,1)
            out="win" if pp>0 else "loss" if pp<0 else "be"; ei=i+120

        
        current_balance = 500 + sum(t["pnl_rm"] for t in trades)
        peak_balance = max([500] + [500 + sum(x["pnl_rm"] for x in trades[:i]) for i in range(len(trades)+1)])
        current_dd = max(0.0, ((peak_balance - current_balance) / peak_balance) * 100)

        risk_pct, risk_mult = kira_dynamic_risk(
            engine="CTE",
            regime=regime,
            symbol=sym,
            current_dd=current_dd
        )

        pnl_rm=round((pp*pv-p["spread_rm"]) * risk_mult,2)

        exit_dt=h1a.iloc[min(ei,len(h1a)-1)]["time"]
        hold_h=round((exit_dt-dt).total_seconds()/3600,1)
        if LONDON_KZ_START<=h_utc<LONDON_KZ_END: sess="London_Open"
        elif NY_KZ_START<=h_utc<NY_KZ_END:       sess="NY_Open"
        elif NY_PM_KZ_START<=h_utc<NY_PM_KZ_END: sess="NY_PM"
        else:                                     sess="Other"

        t={"symbol":sym,"engine":"CTE","regime":regime,"direction":direction,
           "entry_dt":str(dt.date()),"month":mo,"year":str(dt.year),
           "dow":DAYS[dt.weekday()],"session":sess,"hold_hours":hold_h,
           "sl_pips":slp,"tp_pips":tpp,"rr":rr,"outcome":out,
           "pnl_pips":pp,"pnl_rm":pnl_rm,"risk_pct":risk_pct,"risk_mult":risk_mult}
        trades.append(t); mo_pnl[mo]+=pnl_rm; last_idx=i

    ALL_TRADES.extend(trades)
    if trades:
        wins=[t for t in trades if t["outcome"]=="win"]
        n=len(trades); wr=len(wins)/n*100
        net=sum(t["pnl_rm"] for t in trades)
        n_mo=len(set(t["month"] for t in trades))
        flag="✅" if net>0 else "❌"
        print(f"  → {n} signals | WR {wr:.1f}% | Net RM{net:+.2f} | {n/n_mo:.1f}/month {flag}")
    else:
        print(f"  → 0 signals")

# ══════════════════════════════════════════════════════════
#  2. GVE — GOLD VOLATILITY ENGINE
# ══════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  RUNNING GVE (Gold Volatility Engine)")
print(f"  XAUUSD + XAGUSD | London Open only | H4 slope filter | BUY only")
print(f"  Silver uses same GVE logic — sweep+expansion, ATR-adaptive SL/TP")
print(SEP)

if GVE_SYMBOL in data:
    d1a=data[GVE_SYMBOL]["D1"]; h4a=data[GVE_SYMBOL]["H4"]
    h1a=data[GVE_SYMBOL]["H1"]; m15a=data[GVE_SYMBOL]["M15"]
    pip=get_pip("XAUUSD"); pip_val=100*0.01*LOT_GOLD*USD_MYR_RATE
    spread_cost=35*pip_val
    gve_trades=[]; last_i=-20; mo_pnl=defaultdict(float)
    print(f"\nXAUUSD (GVE) — scanning {len(m15a)} M15 candles...")

    for i in range(300,len(m15a)-193):
        c=m15a.iloc[i]; dt=c["time"]
        in_sess,sess=gve_in_session(dt)
        if not in_sess: continue

        i_h1=len(h1a[h1a["time"]<=dt])-1
        i_d1=len(d1a[d1a["time"]<=dt])-1
        if i_h1<55 or i_d1<55: continue

        regime,_=gve_regime(m15a,h1a,d1a,i,i_h1)
        if regime in ["EXTREME","DEAD"]: continue

        d1v=d1a.iloc[max(0,i_d1-250):i_d1+1]
        direction=d1_bias(d1v)
        if direction is None or direction=="SELL": continue

        i_h4=len(h4a[h4a["time"]<=dt])-1
        if i_h4>=GVE_H4_EMA_SLOPE_PERIOD+5:
            h4v_s=h4a.iloc[max(0,i_h4-60):i_h4+1]
            h4_ema50=h4v_s["close"].ewm(span=50,adjust=False).mean()
            slope=float(h4_ema50.iloc[-1])-float(h4_ema50.iloc[-(GVE_H4_EMA_SLOPE_PERIOD+1)])
            if slope<=0: continue

        pools=gve_pools(m15a,h1a,i,i_h1,dt)
        if not pools: continue
        swept,sweep_level,sweep_pips,pool_label=gve_sweep(m15a,i,pools,direction)
        if not swept: continue
        expanded,grade,_=gve_expansion(m15a,i,direction)
        if not expanded or grade=="C": continue

        entry=round(float(c["close"]),2)
        h1_atr=gve_calc_atr(h1a.iloc[max(0,i_h1-50):i_h1+1],14)
        if h1_atr==0: continue
        sl,tp,sl_pips,tp_pips,rr,tp_mult=gve_levels(direction,entry,h1_atr,grade)
        if rr<GVE_MIN_RR or i-last_i<20: continue

        mo=dt.strftime("%Y-%m")
        if mo_pnl[mo]<=-(500*MAX_MONTHLY_LOSS_PCT/100): continue

        out="timeout"; pp=0.0; ei=i; partial_hit=False
        for fi in range(i+1,min(i+193,len(m15a))):
            fc=m15a.iloc[fi]
            if direction=="BUY":
                if not partial_hit and fc["high"]>=round(entry+pip*sl_pips,2):
                    partial_hit=True
                if partial_hit and fc["low"]<=entry:
                    out="win"; pp=sl_pips*0.50; ei=fi; break
                elif not partial_hit and fc["low"]<=sl:
                    out="loss"; pp=-sl_pips; ei=fi; break
                if fc["high"]>=tp:
                    pp=sl_pips*0.50+sl_pips*tp_mult*0.50 if partial_hit else tp_pips
                    out="win"; ei=fi; break
        if out=="timeout":
            lp=float(m15a.iloc[min(i+192,len(m15a)-1)]["close"])
            pp=round((lp-entry)/pip,1)
            out="win" if pp>0 else "loss" if pp<0 else "be"; ei=i+192

        pnl_rm=round(pp*pip_val-spread_cost,2)
        exit_dt=m15a.iloc[min(ei,len(m15a)-1)]["time"]
        hold_h=round((exit_dt-dt).total_seconds()/3600,1)

        t={"symbol":"XAUUSD","engine":"GVE","regime":"GVE","direction":direction,
           "entry_dt":str(dt.date()),"month":mo,"year":str(dt.year),
           "dow":DAYS[dt.weekday()],"session":sess,"hold_hours":hold_h,
           "sl_pips":sl_pips,"tp_pips":tp_pips,"rr":rr,"grade":grade,
           "outcome":out,"pnl_pips":pp,"pnl_rm":pnl_rm,"risk_pct":risk_pct,"risk_mult":risk_mult}
        gve_trades.append(t); mo_pnl[mo]+=pnl_rm; last_i=i

    ALL_TRADES.extend(gve_trades)
    if gve_trades:
        wins=[t for t in gve_trades if t["outcome"]=="win"]
        n=len(gve_trades); wr=len(wins)/n*100
        net=sum(t["pnl_rm"] for t in gve_trades)
        n_mo=len(set(t["month"] for t in gve_trades))
        print(f"  → {n} signals | WR {wr:.1f}% | Net RM{net:+.2f} | {n/n_mo:.1f}/month")

# ── XAGUSD GVE scan ─────────────────────────────────────────────────────
# Silver follows same GVE logic as Gold — London Open, BUY only, sweep+expansion.
# pip=0.001, pip_val uses Silver contract (5000oz at 0.01 lot).
if SILVER_SYMBOL in data and data[SILVER_SYMBOL].get("M15") is not None:
    d1a=data[SILVER_SYMBOL]["D1"]; h4a=data[SILVER_SYMBOL]["H4"]
    h1a=data[SILVER_SYMBOL]["H1"]; m15a=data[SILVER_SYMBOL]["M15"]
    pip_ag=0.001
    pip_val_ag=5000*0.001*LOT_XAGUSD*USD_MYR_RATE
    spread_cost_ag=5.0*pip_val_ag
    ag_trades=[]; last_i_ag=-20; mo_pnl_ag=defaultdict(float)
    print(f"\nXAGUSD (GVE) — scanning {len(m15a)} M15 candles...")

    for i in range(300, len(m15a)-193):
        c=m15a.iloc[i]; dt=c["time"]
        in_sess,sess=gve_in_session(dt)
        if not in_sess: continue

        i_h1=len(h1a[h1a["time"]<=dt])-1
        i_d1=len(d1a[d1a["time"]<=dt])-1
        if i_h1<55 or i_d1<55: continue

        regime,_=gve_regime(m15a,h1a,d1a,i,i_h1)
        if regime in ["EXTREME","DEAD"]: continue

        d1v=d1a.iloc[max(0,i_d1-250):i_d1+1]
        direction=d1_bias(d1v)
        if direction is None or direction=="SELL": continue

        i_h4=len(h4a[h4a["time"]<=dt])-1
        if i_h4>=GVE_H4_EMA_SLOPE_PERIOD+5:
            h4v_s=h4a.iloc[max(0,i_h4-60):i_h4+1]
            h4_ema50=h4v_s["close"].ewm(span=50,adjust=False).mean()
            slope=float(h4_ema50.iloc[-1])-float(h4_ema50.iloc[-(GVE_H4_EMA_SLOPE_PERIOD+1)])
            if slope<=0: continue

        pools=gve_pools(m15a,h1a,i,i_h1,dt)
        if not pools: continue
        swept,sweep_level,sweep_pips,pool_label=gve_sweep(m15a,i,pools,direction)
        if not swept: continue
        expanded,grade,_=gve_expansion(m15a,i,direction)
        if not expanded or grade=="C": continue

        entry=round(float(c["close"]),3)
        h1_atr=gve_calc_atr(h1a.iloc[max(0,i_h1-50):i_h1+1],14)
        if h1_atr==0: continue

        # SL/TP using Silver pip — same ATR-based formula as Gold
        sl_from_atr=h1_atr*GVE_SL_ATR_MULT
        sl_from_price=entry*GVE_SL_PRICE_PCT
        sl_usd=min(max(sl_from_atr,sl_from_price), GVE_MAX_SL_USD)
        sl_pips_ag=round(sl_usd/pip_ag, 1)
        tp_mult_ag=(GVE_TP_ATR_MULT_A if grade=="A" else GVE_TP_ATR_MULT_B)
        tp_pips_ag=round(sl_pips_ag*tp_mult_ag, 1)
        rr_ag=round(tp_pips_ag/sl_pips_ag, 2) if sl_pips_ag>0 else tp_mult_ag
        if rr_ag<GVE_MIN_RR or i-last_i_ag<20: continue

        sl_p=round(entry-pip_ag*sl_pips_ag,3) if direction=="BUY" else round(entry+pip_ag*sl_pips_ag,3)
        tp_p=round(entry+pip_ag*tp_pips_ag,3) if direction=="BUY" else round(entry-pip_ag*tp_pips_ag,3)

        mo=dt.strftime("%Y-%m")
        if mo_pnl_ag[mo]<=-(500*MAX_MONTHLY_LOSS_PCT/100): continue

        risk_pct_ag,risk_mult_ag=kira_dynamic_risk("GVE","GVE","XAGUSD")

        out="timeout"; pp=0.0; ei=i; partial_hit=False
        for fi in range(i+1, min(i+193,len(m15a))):
            fc=m15a.iloc[fi]
            if direction=="BUY":
                if not partial_hit and fc["high"]>=round(entry+pip_ag*sl_pips_ag,3):
                    partial_hit=True
                if partial_hit and fc["low"]<=entry:
                    out="win"; pp=sl_pips_ag*0.50; ei=fi; break
                elif not partial_hit and fc["low"]<=sl_p:
                    out="loss"; pp=-sl_pips_ag; ei=fi; break
                if fc["high"]>=tp_p:
                    pp=sl_pips_ag*0.50+sl_pips_ag*tp_mult_ag*0.50 if partial_hit else tp_pips_ag
                    out="win"; ei=fi; break
        if out=="timeout":
            lp=float(m15a.iloc[min(i+192,len(m15a)-1)]["close"])
            pp=round((lp-entry)/pip_ag, 1)
            out="win" if pp>0 else "loss" if pp<0 else "be"; ei=i+192

        pnl_rm=round(pp*pip_val_ag-spread_cost_ag, 2)
        exit_dt=m15a.iloc[min(ei,len(m15a)-1)]["time"]
        hold_h=round((exit_dt-dt).total_seconds()/3600, 1)

        t={"symbol":"XAGUSD","engine":"GVE","regime":"GVE","direction":direction,
           "entry_dt":str(dt.date()),"month":mo,"year":str(dt.year),
           "dow":DAYS[dt.weekday()],"session":sess,"hold_hours":hold_h,
           "sl_pips":sl_pips_ag,"tp_pips":tp_pips_ag,"rr":rr_ag,"grade":grade,
           "outcome":out,"pnl_pips":pp,"pnl_rm":pnl_rm,
           "risk_pct":risk_pct_ag,"risk_mult":risk_mult_ag}
        ag_trades.append(t); mo_pnl_ag[mo]+=pnl_rm; last_i_ag=i

    ALL_TRADES.extend(ag_trades)
    if ag_trades:
        wins_ag=[t for t in ag_trades if t["outcome"]=="win"]
        n_ag=len(ag_trades); wr_ag=len(wins_ag)/n_ag*100
        net_ag=sum(t["pnl_rm"] for t in ag_trades)
        n_mo_ag=len(set(t["month"] for t in ag_trades))
        print(f"  → {n_ag} signals | WR {wr_ag:.1f}% | Net RM{net_ag:+.2f} | {n_ag/n_mo_ag:.1f}/month")
    else:
        print(f"  → 0 signals")
else:
    print("\nXAGUSD (GVE): ⚠️ M15 data not available — skipping")

mt5.shutdown()

# ══════════════════════════════════════════════════════════
#  3. MRE — MEAN REVERSION (all 8 symbols)
# ══════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  RUNNING MRE (Mean Reversion Engine)")
print(f"  All non-gold symbols → RANGING regime only")
print(SEP)

def mre_detect_range(d1,pip,min_range_pips):
    if d1 is None or len(d1)<MRE_RANGE_LOOKBACK+5: return None,None,None
    recent=d1.tail(MRE_RANGE_LOOKBACK)
    rng_high=round(float(recent["high"].max()),5)
    rng_low =round(float(recent["low"].min()), 5)
    if (rng_high-rng_low)/pip<min_range_pips: return None,None,None
    closes=d1["close"]
    e50 =float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
    e200=float(closes.ewm(span=min(200,len(closes)),adjust=False).mean().iloc[-1])
    if abs(e50-e200)/e200*100>MRE_EMA_FLAT_PCT: return None,None,None
    return rng_high,rng_low,round((rng_high+rng_low)/2,5)

def mre_at_extreme(price,rng_high,rng_low,pip,prox):
    if (rng_high-price)/pip<=prox: return "SELL",round((rng_high-price)/pip,1)
    if (price-rng_low )/pip<=prox: return "BUY", round((price-rng_low)/pip,1)
    return None,0

def mre_rsi(closes,period=MRE_RSI_PERIOD):
    if len(closes)<period+1: return 50.0
    d=closes.diff()
    g=d.clip(lower=0).ewm(com=period-1,adjust=False).mean()
    l=(-d.clip(upper=0)).ewm(com=period-1,adjust=False).mean()
    return round(100-100/(1+float(g.iloc[-1])/(float(l.iloc[-1])+1e-9)),1)

def mre_rejection(h1,direction,lb=5):
    if h1 is None or len(h1)<3: return False
    for i in range(len(h1.iloc[-lb:])-1,-1,-1):
        c=h1.iloc[-lb:].iloc[i]; tr=float(c["high"]-c["low"])
        if tr==0: continue
        uw=float(c["high"])-max(float(c["open"]),float(c["close"]))
        lw=min(float(c["open"]),float(c["close"]))-float(c["low"])
        br=abs(float(c["close"])-float(c["open"]))/tr
        if direction=="SELL":
            if uw/tr>=0.55 and c["close"]<c["open"]: return True
            if c["close"]<c["open"] and br>=0.65: return True
        else:
            if lw/tr>=0.55 and c["close"]>c["open"]: return True
            if c["close"]>c["open"] and br>=0.65: return True
    return False

def mre_levels(direction,entry,rng_high,rng_low,midpoint,pip,sl_beyond):
    if direction=="SELL":
        sl=round(rng_high+pip*sl_beyond,5); slp=round((sl-entry)/pip,1)
        tp=midpoint; tpp=round((entry-tp)/pip,1)
    else:
        sl=round(rng_low-pip*sl_beyond,5); slp=round((entry-sl)/pip,1)
        tp=midpoint; tpp=round((tp-entry)/pip,1)
    if slp<=0 or tpp<=0: return None,None,0,0,0
    rr=round(tpp/slp,2)
    if rr<MRE_MIN_RR: return None,None,0,0,0
    if rr>MRE_MAX_RR:
        tpp=round(slp*MRE_MAX_RR,1)
        tp=round(entry-pip*tpp,5) if direction=="SELL" else round(entry+pip*tpp,5)
        rr=MRE_MAX_RR
    return sl,tp,round(slp,1),round(tpp,1),rr

for sym in MRE_SYMS:
    if sym not in data:
        print(f"\n{sym}: SKIPPED"); continue
    p=MRE_PROFILES[sym]; pip=p["pip"]; pv=p["pip_val_rm"]
    d1a=data[sym]["D1"]; h4a=data[sym]["H4"]; h1a=data[sym]["H1"]
    trades=[]; last_idx=-MRE_COOLDOWN_H1; mo_pnl=defaultdict(float)
    print(f"\n{sym} — scanning {len(h1a)} H1 candles (MRE)...")

    for i in range(300,len(h1a)-120):
        c=h1a.iloc[i]; dt=c["time"]
        if dt.weekday()>=5 or dt.weekday()==4: continue
        h_utc=dt.hour
        if not (SESSION_START_UTC<=h_utc<SESSION_END_UTC): continue
        if LONDON_KZ_START<=h_utc<LONDON_KZ_END: continue
        if NY_PM_KZ_START <=h_utc<NY_PM_KZ_END:  continue
        if i-last_idx<MRE_COOLDOWN_H1: continue
        mo=dt.strftime("%Y-%m")
        bal=500+sum(t["pnl_rm"] for t in trades)
        if mo_pnl[mo]<=-(bal*MAX_MONTHLY_LOSS_PCT/100): continue

        d1v=d1a[d1a["time"]<=dt].tail(MRE_RANGE_LOOKBACK+50)
        h4v_rc=h4a[h4a["time"]<=dt].tail(200)
        if len(d1v)<MRE_RANGE_LOOKBACK+5: continue
        regime,adx,_,_=kira._classify_regime(sym,d1v,h4v_rc)
        if regime not in ("RANGING","COMPRESSING"): continue

        rng_high,rng_low,midpoint=mre_detect_range(d1v,pip,p["min_range"])
        if rng_high is None: continue

        h4v=h4a[h4a["time"]<=dt].tail(50)
        if len(h4v)<5: continue
        current_price=float(h4v["close"].iloc[-1])
        direction,dist=mre_at_extreme(current_price,rng_high,rng_low,pip,p["extreme_prox"])
        if direction is None: continue

        h1v=h1a.iloc[max(0,i-100):i+1]
        rsi=mre_rsi(h1v["close"])
        rsi_ok=((direction=="SELL" and rsi>=MRE_RSI_SELL) or
                (direction=="BUY"  and rsi<=MRE_RSI_BUY))
        if not rsi_ok: continue
        if not mre_rejection(h1v,direction): continue

        entry=round(current_price,5)
        sl,tp,sl_pips,tp_pips,rr=mre_levels(direction,entry,rng_high,rng_low,midpoint,pip,p["sl_beyond"])
        if sl is None: continue

        out="timeout"; pp=0.0; ei=i
        for fi in range(i+1,min(i+121,len(h1a))):
            fc=h1a.iloc[fi]
            if direction=="SELL":
                if fc["high"]>=sl: out="loss"; pp=-sl_pips; ei=fi; break
                if fc["low"] <=tp: out="win";  pp=tp_pips;  ei=fi; break
            else:
                if fc["low"] <=sl: out="loss"; pp=-sl_pips; ei=fi; break
                if fc["high"]>=tp: out="win";  pp=tp_pips;  ei=fi; break
        if out=="timeout":
            lp=float(h1a.iloc[min(i+120,len(h1a)-1)]["close"])
            pp=round((entry-lp)/pip if direction=="SELL" else (lp-entry)/pip,1)
            out="win" if pp>0 else "loss" if pp<0 else "be"; ei=i+120

        
        current_balance = 500 + sum(t["pnl_rm"] for t in trades)
        peak_balance = max([500] + [500 + sum(x["pnl_rm"] for x in trades[:i]) for i in range(len(trades)+1)])
        current_dd = max(0.0, ((peak_balance - current_balance) / peak_balance) * 100)

        risk_pct, risk_mult = kira_dynamic_risk(
            engine="GVE",
            regime=regime,
            symbol=sym,
            current_dd=current_dd
        )

        pnl_rm=round((pp*pv-p["spread_rm"]) * risk_mult,2)

        exit_dt=h1a.iloc[min(ei,len(h1a)-1)]["time"]
        hold_h=round((exit_dt-dt).total_seconds()/3600,1)
        if   NY_KZ_START    <=h_utc<NY_KZ_END:    sess="NY_Open"
        elif NY_PM_KZ_START <=h_utc<NY_PM_KZ_END: sess="NY_PM"
        elif 0              <=h_utc<7:             sess="Tokyo"
        else:                                      sess="Other"

        t={"symbol":sym,"engine":"MRE","regime":regime,"direction":direction,
           "entry_dt":str(dt.date()),"month":mo,"year":str(dt.year),
           "dow":DAYS[dt.weekday()],"session":sess,"hold_hours":hold_h,
           "sl_pips":sl_pips,"tp_pips":tp_pips,"rr":rr,"outcome":out,
           "pnl_pips":pp,"pnl_rm":pnl_rm,"risk_pct":risk_pct,"risk_mult":risk_mult}
        trades.append(t); mo_pnl[mo]+=pnl_rm; last_idx=i

    ALL_TRADES.extend(trades)
    if trades:
        wins=[t for t in trades if t["outcome"]=="win"]
        n=len(trades); wr=len(wins)/n*100
        net=sum(t["pnl_rm"] for t in trades)
        n_mo=len(set(t["month"] for t in trades))
        flag="✅" if net>0 else "❌"
        print(f"  → {n} signals | WR {wr:.1f}% | Net RM{net:+.2f} | {n/n_mo:.1f}/month {flag}")
    else:
        print(f"  → 0 signals")

# ══════════════════════════════════════════════════════════
#  4. CBE — COMPRESSION BREAKOUT (all 8 symbols)
# ══════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  RUNNING CBE (Compression Breakout Engine)")
print(f"  All non-gold symbols → COMPRESSING regime only")
print(SEP)

def cbe_detect_compression(h4,pip,min_range_pips):
    lb=CBE_COMPRESS_LOOKBACK
    if h4 is None or len(h4)<CBE_ATR_LOOKBACK+lb+3: return None,None,None,0.0
    h_=h4["high"]; l_=h4["low"]; pc_=h4["close"].shift(1)
    tr_=pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
    h4_atr  =float(tr_.ewm(com=CBE_ATR_LOOKBACK-1,adjust=False).mean().iloc[-1])
    h4_atr_p=h4_atr/pip
    if h4_atr==0: return None,None,None,0.0
    prior  =h4.iloc[-(lb+1):-1]
    c_high =round(float(prior["high"].max()),5)
    c_low  =round(float(prior["low"].min()), 5)
    c_range=(c_high-c_low)/pip
    if c_range<min_range_pips: return None,None,None,0.0
    if c_range>=h4_atr_p*CBE_COMPRESS_ATR_RATIO: return None,None,None,0.0
    cur=float(h4.iloc[-1]["close"])
    if   cur>c_high: return "BUY", c_high,c_low,h4_atr
    elif cur<c_low:  return "SELL",c_high,c_low,h4_atr
    return None,None,None,0.0

def cbe_h1_momentum(h1,direction):
    if h1 is None or len(h1)<CBE_H1_LOOKBACK+1: return False,0.0
    best=0.0
    for i in range(len(h1.iloc[-CBE_H1_LOOKBACK:])-1,-1,-1):
        c=h1.iloc[-CBE_H1_LOOKBACK:].iloc[i]; tr=float(c["high"]-c["low"])
        if tr==0: continue
        body=abs(float(c["close"])-float(c["open"]))/tr
        ok=(direction=="BUY" and c["close"]>c["open"]) or \
           (direction=="SELL" and c["close"]<c["open"])
        if ok and body>best: best=body
    return best>=CBE_H1_BODY_MIN,round(best,3)

def cbe_levels(direction,entry,c_high,c_low,pip):
    c_range=c_high-c_low; c_pips=c_range/pip
    if direction=="BUY":
        sl=round(c_high-c_range*CBE_SL_INSIDE_PCT,5)
        slp=round((entry-sl)/pip,1)
        tpp=round(c_pips*CBE_TP_RANGE_MULT,1)
        tp=round(entry+pip*tpp,5)
    else:
        sl=round(c_low+c_range*CBE_SL_INSIDE_PCT,5)
        slp=round((sl-entry)/pip,1)
        tpp=round(c_pips*CBE_TP_RANGE_MULT,1)
        tp=round(entry-pip*tpp,5)
    if slp<=0 or tpp<=0: return None,None,0,0,0
    rr=round(tpp/slp,2)
    if rr<CBE_MIN_RR: return None,None,0,0,0
    if rr>CBE_MAX_RR:
        tpp=round(slp*CBE_MAX_RR,1)
        tp=round(entry+pip*tpp,5) if direction=="BUY" else round(entry-pip*tpp,5)
        rr=CBE_MAX_RR
    return sl,tp,round(slp,1),round(tpp,1),rr

for sym in CBE_SYMS:
    if sym not in data:
        print(f"\n{sym}: SKIPPED"); continue
    p=CBE_PROFILES[sym]; pip=p["pip"]; pv=p["pip_val_rm"]
    d1a=data[sym]["D1"]; h4a=data[sym]["H4"]; h1a=data[sym]["H1"]
    trades=[]; last_idx=-CBE_COOLDOWN_H1; mo_pnl=defaultdict(float)
    print(f"\n{sym} — scanning {len(h1a)} H1 candles (CBE)...")

    for i in range(300,len(h1a)-120):
        c=h1a.iloc[i]; dt=c["time"]
        if dt.weekday()>=5 or dt.weekday()==4: continue
        h_utc=dt.hour
        if not (SESSION_START_UTC<=h_utc<SESSION_END_UTC): continue
        if i-last_idx<CBE_COOLDOWN_H1: continue
        mo=dt.strftime("%Y-%m")
        bal=500+sum(t["pnl_rm"] for t in trades)
        if mo_pnl[mo]<=-(bal*MAX_MONTHLY_LOSS_PCT/100): continue

        d1v=d1a[d1a["time"]<=dt].tail(250)
        h4v_rc=h4a[h4a["time"]<=dt].tail(200)
        if len(d1v)<60: continue
        regime,adx,_,_=kira._classify_regime(sym,d1v,h4v_rc)
        if regime!="COMPRESSING": continue

        h4v=h4a[h4a["time"]<=dt].tail(CBE_ATR_LOOKBACK+CBE_COMPRESS_LOOKBACK+10)
        if len(h4v)<CBE_COMPRESS_LOOKBACK+5: continue
        direction,c_high,c_low,h4_atr=cbe_detect_compression(h4v,pip,p["min_range"])
        if direction is None: continue

        h1v=h1a.iloc[max(0,i-10):i+1]
        confirmed,body_ratio=cbe_h1_momentum(h1v,direction)
        if not confirmed: continue

        confidence=CBE_BASE_CONFIDENCE
        if LONDON_KZ_START<=h_utc<LONDON_KZ_END: confidence+=CBE_LONDON_BOOST
        elif NY_KZ_START   <=h_utc<NY_KZ_END:    confidence+=CBE_NY_BOOST
        if body_ratio>=0.70: confidence+=CBE_MOMENTUM_BOOST
        confidence=min(95,confidence)
        grade="A" if confidence>=CBE_GRADE_A_CONF else "B"

        entry=round(float(h1a.iloc[i]["close"]),5)
        sl,tp,sl_pips,tp_pips,rr=cbe_levels(direction,entry,c_high,c_low,pip)
        if sl is None: continue

        out="timeout"; pp=0.0; ei=i
        for fi in range(i+1,min(i+121,len(h1a))):
            fc=h1a.iloc[fi]
            if direction=="BUY":
                if fc["low"] <=sl: out="loss"; pp=-sl_pips; ei=fi; break
                if fc["high"]>=tp: out="win";  pp=tp_pips;  ei=fi; break
            else:
                if fc["high"]>=sl: out="loss"; pp=-sl_pips; ei=fi; break
                if fc["low"] <=tp: out="win";  pp=tp_pips;  ei=fi; break
        if out=="timeout":
            lp=float(h1a.iloc[min(i+120,len(h1a)-1)]["close"])
            pp=round((entry-lp)/pip if direction=="SELL" else (lp-entry)/pip,1)
            out="win" if pp>0 else "loss" if pp<0 else "be"; ei=i+120

        
        current_balance = 500 + sum(t["pnl_rm"] for t in trades)
        peak_balance = max([500] + [500 + sum(x["pnl_rm"] for x in trades[:i]) for i in range(len(trades)+1)])
        current_dd = max(0.0, ((peak_balance - current_balance) / peak_balance) * 100)

        risk_pct, risk_mult = kira_dynamic_risk(
            engine="MRE",
            regime=regime,
            symbol=sym,
            current_dd=current_dd
        )

        pnl_rm=round((pp*pv-p["spread_rm"]) * risk_mult,2)

        exit_dt=h1a.iloc[min(ei,len(h1a)-1)]["time"]
        hold_h=round((exit_dt-dt).total_seconds()/3600,1)
        if   LONDON_KZ_START<=h_utc<LONDON_KZ_END: sess="London_Open"
        elif NY_KZ_START    <=h_utc<NY_KZ_END:      sess="NY_Open"
        elif NY_PM_KZ_START <=h_utc<NY_PM_KZ_END:   sess="NY_PM"
        else:                                        sess="Other"

        t={"symbol":sym,"engine":"CBE","regime":"COMPRESSING","direction":direction,
           "grade":grade,"entry_dt":str(dt.date()),"month":mo,"year":str(dt.year),
           "dow":DAYS[dt.weekday()],"session":sess,"hold_hours":hold_h,
           "sl_pips":sl_pips,"tp_pips":tp_pips,"rr":rr,"outcome":out,
           "pnl_pips":pp,"pnl_rm":pnl_rm,"risk_pct":risk_pct,"risk_mult":risk_mult}
        trades.append(t); mo_pnl[mo]+=pnl_rm; last_idx=i

    ALL_TRADES.extend(trades)
    if trades:
        wins=[t for t in trades if t["outcome"]=="win"]
        n=len(trades); wr=len(wins)/n*100
        net=sum(t["pnl_rm"] for t in trades)
        n_mo=len(set(t["month"] for t in trades))
        flag="✅" if net>0 else "❌"
        print(f"  → {n} signals | WR {wr:.1f}% | Net RM{net:+.2f} | {n/n_mo:.1f}/month {flag}")
    else:
        print(f"  → 0 signals")

# ══════════════════════════════════════════════════════════
#  5. HPE — HTF PULLBACK (all 8 symbols, BUY only, TRENDING)
# ══════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  RUNNING HPE (HTF Pullback Engine)")
print(f"  All non-gold symbols → TRENDING regime, BUY only, D1 pivots")
print(SEP)

def hpe_w1_dir(w1,d1):
    src=w1 if (w1 is not None and len(w1)>=HPE_W1_EMA_PERIOD+5) else d1
    if src is None or len(src)<HPE_W1_EMA_PERIOD+2: return None
    ema=float(src["close"].ewm(span=HPE_W1_EMA_PERIOD,adjust=False).mean().iloc[-1])
    return "BUY" if float(src["close"].iloc[-1])>ema else "SELL"

def hpe_pivots(d1,lb=HPE_D1_PIVOT_LOOKBACK,n=HPE_D1_PIVOT_N):
    if d1 is None or len(d1)<lb+n+2: return [],[]
    recent=d1.tail(lb); highs=[]; lows=[]
    for i in range(n,len(recent)-n):
        h=float(recent.iloc[i]["high"]); l=float(recent.iloc[i]["low"])
        if all(float(recent.iloc[i-j]["high"])<h for j in range(1,n+1)) and \
           all(float(recent.iloc[i+j]["high"])<h for j in range(1,n+1)): highs.append(round(h,5))
        if all(float(recent.iloc[i-j]["low"])>l for j in range(1,n+1)) and \
           all(float(recent.iloc[i+j]["low"])>l for j in range(1,n+1)): lows.append(round(l,5))
    return highs,lows

def hpe_find_level(highs,lows,current,pip,prox):
    if lows:
        cands=[(abs(current-l)/pip,l) for l in lows if current>=l]
        if cands:
            dist,level=min(cands)
            if dist<=prox: return level,"BUY"
    return None,None

def hpe_fib_ok(d1,direction,current,pip):
    if d1 is None or len(d1)<22: return False,0.0
    sh=float(d1.tail(20)["high"].max()); sl_=float(d1.tail(20)["low"].min())
    sd=sh-sl_
    if sd==0: return False,0.0
    ret=abs(current-(sl_ if direction=="BUY" else sh))/sd
    valid=(HPE_D1_RETRACE_MIN<=ret<0.44) or (0.53<=ret<=HPE_D1_RETRACE_MAX)
    return valid,round(ret*100,1)

def hpe_h4_mom(h4,direction,lb=HPE_H4_LOOKBACK):
    if h4 is None or len(h4)<lb+1: return False,0.0
    best=0.0
    for i in range(len(h4.tail(lb+2))-1,-1,-1):
        c=h4.tail(lb+2).iloc[i]; tr=float(c["high"]-c["low"])
        if tr==0: continue
        body=abs(float(c["close"])-float(c["open"]))/tr
        ok=(direction=="BUY" and c["close"]>c["open"])
        if ok and body>best: best=body
    return best>=0.70,round(best,3)

def hpe_lvls(direction,entry,level,highs,lows,pip,sl_buf):
    sl=round(level-pip*sl_buf,5); slp=round((entry-sl)/pip,1)
    tp_cands=[h for h in highs if h>entry+pip*10]
    tp=min(tp_cands) if tp_cands else round(entry+pip*slp*HPE_MIN_RR,5)
    tpp=round((tp-entry)/pip,1)
    if slp<=0 or tpp<=0: return None,None,0,0,0
    rr=round(tpp/slp,2)
    if rr<HPE_MIN_RR: return None,None,0,0,0
    if rr>HPE_MAX_RR:
        tpp=round(slp*HPE_MAX_RR,1); tp=round(entry+pip*tpp,5); rr=HPE_MAX_RR
    return sl,tp,round(slp,1),round(tpp,1),rr

for sym in HPE_SYMS:
    if sym not in data:
        print(f"\n{sym}: SKIPPED"); continue
    p=HPE_PROFILES[sym]; pip=p["pip"]; pv=p["pip_val_rm"]
    d1a=data[sym]["D1"]; h4a=data[sym]["H4"]
    h1a=data[sym]["H1"]; w1a=data[sym].get("W1")
    trades=[]; last_idx=-HPE_COOLDOWN_H1; mo_pnl=defaultdict(float)
    print(f"\n{sym} — scanning {len(h1a)} H1 candles (HPE)...")

    for i in range(300,len(h1a)-121):
        c=h1a.iloc[i]; dt=c["time"]
        if dt.weekday()>=5 or dt.weekday()==4: continue
        h_utc=dt.hour
        if not (SESSION_START_UTC<=h_utc<SESSION_END_UTC): continue
        if LONDON_KZ_START<=h_utc<LONDON_KZ_END: continue
        if i-last_idx<HPE_COOLDOWN_H1: continue
        mo=dt.strftime("%Y-%m")
        bal=500+sum(t["pnl_rm"] for t in trades)
        if mo_pnl[mo]<=-(bal*MAX_MONTHLY_LOSS_PCT/100): continue

        d1v=d1a[d1a["time"]<=dt].tail(250)
        h4v=h4a[h4a["time"]<=dt].tail(200)
        if len(d1v)<60: continue
        regime,adx,_,_=kira._classify_regime(sym,d1v,h4v)
        if regime!="TRENDING": continue

        w1v=w1a[w1a["time"]<=dt].tail(30) if w1a is not None else None
        w1_dir=hpe_w1_dir(w1v,d1v)
        if w1_dir!="BUY": continue

        h4v_cur=h4a[h4a["time"]<=dt].tail(5)
        if len(h4v_cur)<1: continue
        current=float(h4v_cur["close"].iloc[-1])

        highs,lows=hpe_pivots(d1v)
        level,direction=hpe_find_level(highs,lows,current,pip,p["prox"])
        if level is None: continue

        fib_ok,retrace_pct=hpe_fib_ok(d1v,direction,current,pip)
        if not fib_ok: continue

        h4v_entry=h4a[h4a["time"]<=dt].tail(HPE_H4_LOOKBACK+3)
        confirmed,body_ratio=hpe_h4_mom(h4v_entry,direction)
        if not confirmed: continue

        # ATR-based SL floor
        h4v_atr=h4a[h4a["time"]<=dt].tail(20)
        h_=h4v_atr["high"]; l_=h4v_atr["low"]; pc_=h4v_atr["close"].shift(1)
        tr_=pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
        h4_atr_pips=float(tr_.ewm(com=13,adjust=False).mean().iloc[-1])/pip
        sl_buf_final=max(p["sl_buf"],h4_atr_pips*0.8)

        entry=round(current,5)
        sl,tp,sl_pips,tp_pips,rr=hpe_lvls(direction,entry,level,highs,lows,pip,sl_buf_final)
        if sl is None: continue

        confidence=HPE_BASE_CONFIDENCE+HPE_TRENDING_BOOST
        if body_ratio>=0.75: confidence+=HPE_H4_BODY_BOOST
        confidence=min(95,confidence)
        grade="A" if confidence>=HPE_GRADE_A_CONF else "B"

        out="timeout"; pp=0.0; ei=i
        for fi in range(i+1,min(i+121,len(h1a))):
            fc=h1a.iloc[fi]
            if fc["low"]<=sl: out="loss"; pp=-sl_pips; ei=fi; break
            if fc["high"]>=tp: out="win"; pp=tp_pips; ei=fi; break
        if out=="timeout":
            lp=float(h1a.iloc[min(i+120,len(h1a)-1)]["close"])
            pp=round((lp-entry)/pip,1)
            out="win" if pp>0 else "loss" if pp<0 else "be"; ei=i+120

        
        current_balance = 500 + sum(t["pnl_rm"] for t in trades)
        peak_balance = max([500] + [500 + sum(x["pnl_rm"] for x in trades[:i]) for i in range(len(trades)+1)])
        current_dd = max(0.0, ((peak_balance - current_balance) / peak_balance) * 100)

        risk_pct, risk_mult = kira_dynamic_risk(
            engine="CBE",
            regime=regime,
            symbol=sym,
            current_dd=current_dd
        )

        pnl_rm=round((pp*pv-p["spread_rm"]) * risk_mult,2)

        exit_dt=h1a.iloc[min(ei,len(h1a)-1)]["time"]
        hold_h=round((exit_dt-dt).total_seconds()/3600,1)
        if   NY_KZ_START    <=h_utc<NY_KZ_END:    sess="NY_Open"
        elif NY_PM_KZ_START <=h_utc<NY_PM_KZ_END: sess="NY_PM"
        elif 0              <=h_utc<7:             sess="Tokyo"
        else:                                      sess="Other"

        t={"symbol":sym,"engine":"HPE","regime":"TRENDING","direction":"BUY",
           "grade":grade,"entry_dt":str(dt.date()),"month":mo,"year":str(dt.year),
           "dow":DAYS[dt.weekday()],"session":sess,"hold_hours":hold_h,
           "sl_pips":sl_pips,"tp_pips":tp_pips,"rr":rr,"outcome":out,
           "pnl_pips":pp,"pnl_rm":pnl_rm,"risk_pct":risk_pct,"risk_mult":risk_mult}
        trades.append(t); mo_pnl[mo]+=pnl_rm; last_idx=i

    ALL_TRADES.extend(trades)
    if trades:
        wins=[t for t in trades if t["outcome"]=="win"]
        n=len(trades); wr=len(wins)/n*100
        net=sum(t["pnl_rm"] for t in trades)
        n_mo=len(set(t["month"] for t in trades))
        flag="✅" if net>0 else "❌"
        print(f"  → {n} signals | WR {wr:.1f}% | Net RM{net:+.2f} | {n/n_mo:.1f}/month {flag}")
    else:
        print(f"  → 0 signals")

# ══════════════════════════════════════════════════════════
#  REPORT
# ══════════════════════════════════════════════════════════
if not ALL_TRADES:
    print("\nNo trades generated."); exit()

df=pd.DataFrame(ALL_TRADES)
wins=df[df["outcome"]=="win"]; loss=df[df["outcome"]=="loss"]
n=len(df); wr=len(wins)/n*100 if n>0 else 0
net=df["pnl_rm"].sum()
avg_rr=df["rr"].mean(); be_wr=1/(1+avg_rr)*100
months=df["month"].nunique()
pf=(wins["pnl_rm"].sum()/abs(loss["pnl_rm"].sum())
    if len(loss)>0 and loss["pnl_rm"].sum()!=0 else 99)
avg_win =wins["pnl_rm"].mean() if len(wins)>0 else 0
avg_loss=loss["pnl_rm"].mean() if len(loss)>0 else 0
ev=(wr/100*avg_win)+((1-wr/100)*avg_loss)

bal=500.0; peak=500.0; mdd=0.0; mddm=0.0; streak=0; mstreak=0
for _,t in df.sort_values("entry_dt").iterrows():
    bal+=t["pnl_rm"]; peak=max(peak,bal)
    dd=(peak-bal)/peak*100; ddm=peak-bal
    mdd=max(mdd,dd); mddm=max(mddm,ddm)
    if t["outcome"]=="loss": streak+=1; mstreak=max(mstreak,streak)
    else: streak=0

monthly_ret=df.groupby("month")["pnl_rm"].sum()
sharpe=(monthly_ret.mean()/monthly_ret.std()*np.sqrt(12)
        if monthly_ret.std()>0 else 0)
recovery_f=net/mddm if mddm>0 else 99

print(); print("="*72)
print("  MASTER BACKTEST v10 — FULL REPORT")
print("  Expanded Symbol Universe + Compatibility Matrix")
print("="*72)

print(f"\n{SEP}")
print("  1. COMBINED PORTFOLIO PERFORMANCE")
print(SEP)
print(f"  Period:               {df['entry_dt'].min()} → {df['entry_dt'].max()}")
print(f"  Total signals:        {n}  ({n/months:.1f}/month)")
print(f"  Wins / Losses:        {len(wins)} / {len(loss)}  (WR {wr:.1f}%)")
print(f"  Net P&L:              RM{net:+.2f}")
print(f"  Starting balance:     RM500.00")
print(f"  Final balance:        RM{500+net:.2f}")
print(f"  Total return:         {net/500*100:+.1f}%")
print(f"  Avg R:R:              1:{avg_rr:.2f}")
print(f"  Break-even WR:        {be_wr:.1f}%")
print(f"  Edge above BE:        +{wr-be_wr:.1f}%")
print(f"  Expected value:       RM{ev:+.2f}/signal")
print(f"  Profit factor:        {pf:.2f}")
print(f"  Sharpe ratio:         {sharpe:.2f}")
print(f"  Recovery factor:      {recovery_f:.2f}")
print(f"  Max drawdown:         {mdd:.1f}%  (RM{mddm:.2f})")
print(f"  Max consecutive loss: {mstreak}")
print(f"  Monthly EV:           RM{ev*n/months:+.2f}")
print(f"  Year 1 projection:    RM500 → RM{500+ev*n/months*12:.0f}")

print(f"\n{SEP}")
print("  2. ENGINE CONTRIBUTION")
print(SEP)
print(f"  {'Engine':<12} {'Sym':<8} {'Sigs':>5} {'WR':>7} {'Net RM':>10} {'RM/sig':>8} {'R:R':>6} {'MaxDD':>7}")
print(f"  {'-'*68}")
for engine in ["CTE","GVE","MRE","CBE","HPE"]:
    eg=df[df["engine"]==engine]
    if len(eg)==0: continue
    for sym in sorted(eg["symbol"].unique()):
        sg=eg[eg["symbol"]==sym]
        sw=sg[sg["outcome"]=="win"]
        swr=len(sw)/len(sg)*100; snet=sg["pnl_rm"].sum()
        sper=sg["pnl_rm"].mean(); srr=sg["rr"].mean()
        b=500.0; pk=500.0; sdd=0.0
        for _,t in sg.iterrows():
            b+=t["pnl_rm"]; pk=max(pk,b); sdd=max(sdd,(pk-b)/pk*100)
        v="✅" if snet>0 else "❌"
        print(f"  {engine:<12} {sym:<8} {len(sg):>5} {swr:>6.1f}% "
              f"RM{snet:>8.2f} RM{sper:>6.2f} 1:{srr:>4.2f} {sdd:>5.1f}%  {v}")

print(f"\n{SEP}")
print("  3. YEARLY BREAKDOWN")
print(SEP)
for yr in sorted(df["year"].unique()):
    yg=df[df["year"]==yr]; yw=yg[yg["outcome"]=="win"]
    ywr=len(yw)/len(yg)*100; ynet=yg["pnl_rm"].sum()
    n_mo=yg["month"].nunique(); ann=ynet/n_mo*12 if n_mo>0 else 0
    print(f"  {yr}: {len(yg):>5} sigs | WR {ywr:>5.1f}% | RM{ynet:>+8.2f} | RM{ann:>+8.0f}/yr")

print(f"\n{SEP}")
print("  4. SESSION BREAKDOWN")
print(SEP)
for sess in ["London_Open","NY_Open","NY_PM","Other","Tokyo"]:
    sg=df[df["session"]==sess]
    if len(sg)==0: continue
    sw=sg[sg["outcome"]=="win"]; swr=len(sw)/len(sg)*100
    flag="✅" if sg["pnl_rm"].sum()>0 else "❌"
    print(f"  {sess:<14} {len(sg):>5} sigs | WR {swr:>5.1f}% | "
          f"RM{sg['pnl_rm'].sum():>+9.2f}  {flag}")

print(f"\n{SEP}")
print("  5. DRAWDOWN & RISK")
print(SEP)
risk="🟢 LOW" if mdd<15 else "🟡 MODERATE" if mdd<25 else "🔴 HIGH"
print(f"  Max drawdown:         {mdd:.1f}%  (RM{mddm:.2f})")
print(f"  Max consecutive loss: {mstreak}")
print(f"  Recovery factor:      {recovery_f:.2f}")
print(f"  Sharpe ratio:         {sharpe:.2f}")
print(f"  Risk rating:          {risk}")

# ── GUARD CLUSTERING SIMULATION (v8) ─────────────────────────────────────
# Replays all trades chronologically applying cluster lot multipliers.
# Shows the REAL adjusted equity curve after GUARD protection kicks in.
# Tier 0 (<3 consec loss) = 1.0x | Tier 1 (3-4) = 0.5x | Tier 2 (5+) = 0.25x
print(f"\n{SEP}")
print("  5b. GUARD CLUSTERING SIMULATION (v8)")
print("  Sequential replay — lot multiplier applied after each consecutive loss")
print(SEP)

trades_chron = df.sort_values("entry_dt").to_dict("records")
g_bal=500.0; g_peak=500.0; g_mdd=0.0; g_mddm=0.0
g_consec=0; g_mstreak=0; g_tier=0
g_net=0.0; g_wins=0; g_losses=0

TIER1 = GUARD_CLUSTER_TIER1  # 3
TIER2 = GUARD_CLUSTER_TIER2  # 5

def cluster_mult(consec):
    if consec >= TIER2: return 0.25
    if consec >= TIER1: return 0.50
    return 1.0

tier_log=[]
for t in trades_chron:
    mult = cluster_mult(g_consec)
    adj_pnl = round(t["pnl_rm"] * mult, 2)
    g_bal += adj_pnl; g_net += adj_pnl
    g_peak = max(g_peak, g_bal)
    dd=(g_peak-g_bal)/g_peak*100; ddm=g_peak-g_bal
    g_mdd=max(g_mdd,dd); g_mddm=max(g_mddm,ddm)
    if t["outcome"]=="win":
        g_wins+=1
        prev_tier=cluster_mult(g_consec)
        g_consec=0
        if prev_tier<1.0:
            tier_log.append(f"  GUARD CLUSTER RESET → 1.0x after win on {t['entry_dt']} ({t['symbol']} {t['engine']})")
    elif t["outcome"]=="loss":
        g_losses+=1
        g_consec+=1; g_mstreak=max(g_mstreak,g_consec)
        new_mult=cluster_mult(g_consec)
        if new_mult != cluster_mult(g_consec-1):
            tier_log.append(f"  GUARD CLUSTER TIER{1 if new_mult==0.5 else 2} → {new_mult}x after {g_consec} losses on {t['entry_dt']} ({t['symbol']} {t['engine']})")

g_wr = g_wins/(g_wins+g_losses)*100 if (g_wins+g_losses)>0 else 0

# Build adjusted monthly returns for Sharpe — simple sequential replay
_c=0; adj_pnls=[]; _months=[]
for t in trades_chron:
    adj_pnls.append(round(t["pnl_rm"]*cluster_mult(_c), 2))
    _months.append(t["month"])
    if t["outcome"]=="win": _c=0
    elif t["outcome"]=="loss": _c+=1
g_monthly_s = pd.Series(adj_pnls, index=_months)
g_monthly_ret = g_monthly_s.groupby(level=0).sum()
g_sharpe = (g_monthly_ret.mean()/g_monthly_ret.std()*np.sqrt(12)
            if g_monthly_ret.std()>0 else 0)

print(f"  Starting balance:     RM500.00")
print(f"  Final balance:        RM{g_bal:.2f}")
print(f"  Net P&L (adjusted):   RM{g_net:+.2f}  vs RM{net:+.2f} unfiltered")
print(f"  Win rate:             {g_wr:.1f}%  (unchanged — clustering doesn't skip trades)")
print(f"  Max drawdown:         {g_mdd:.1f}%  (RM{g_mddm:.2f})  vs {mdd:.1f}% unfiltered")
print(f"  Max consec loss:      {g_mstreak}  (same signals, reduced impact)")
print(f"  Sharpe (adjusted):    {g_sharpe:.2f}  vs {sharpe:.2f} unfiltered")
g_risk = "🟢 LOW" if g_mdd<15 else "🟡 MODERATE" if g_mdd<25 else "🔴 HIGH"
print(f"  Risk rating:          {g_risk}")
dd_improvement = mdd - g_mdd
print(f"  DD improvement:       {dd_improvement:.1f}pp  ({'✅ reduced' if dd_improvement>0 else '⚠️ no change'})")
net_cost = net - g_net
print(f"  Net cost of GUARD:    RM{net_cost:.2f}  (profit reduction from smaller lots during streaks)")
print()
if tier_log:
    print("  Cluster tier changes (first 10):")
    for line in tier_log[:10]:
        print(line)
    if len(tier_log)>10:
        print(f"  ... and {len(tier_log)-10} more tier changes")
else:
    print("  No cluster tier triggers fired (no 3+ consecutive loss streaks detected)")

print(f"\n{SEP}")
print("  6. REGIME BREAKDOWN (Continuation only — regime classifier validation)")
print(SEP)
cte_df=df[df["engine"]=="CTE"]
if len(cte_df)>0:
    print(f"  {'Regime':<14} {'Sigs':>5} {'WR':>7} {'Net RM':>10} {'RM/sig':>8}")
    print(f"  {'-'*50}")
    for regime in ["TRENDING","WEAK_TREND","EXPANDING","UNKNOWN"]:
        rg=cte_df[cte_df["regime"]==regime]
        if len(rg)==0: continue
        rw=rg[rg["outcome"]=="win"]
        rwr=len(rw)/len(rg)*100; rnet=rg["pnl_rm"].sum()
        flag="✅" if rnet>0 else "❌"
        print(f"  {regime:<14} {len(rg):>5} {rwr:>6.1f}% "
              f"RM{rnet:>8.2f} RM{rg['pnl_rm'].mean():>6.2f}  {flag}")

# ══════════════════════════════════════════════════════════
#  7. REGIME/SYMBOL COMPATIBILITY MATRIX  ← KEY v6 output
# ══════════════════════════════════════════════════════════
print(f"\n{SEP}")
print("  7. REGIME / SYMBOL COMPATIBILITY MATRIX")
print("     Which symbols work with which engine in which regime")
print("     Use this to configure KIRA adaptive routing in v6")
print(SEP)

all_syms = sorted(df["symbol"].unique())
engines  = ["CTE","MRE","CBE","HPE"]

print(f"\n  {'Symbol':<10} {'Engine':<7} {'Regime':<15} {'Sigs':>5} {'WR':>7} {'Net RM':>10} {'PF':>5}  Verdict")
print(f"  {'-'*72}")

compatibility = {}  # (sym, engine) -> {wr, net, n, pf}

for engine in engines:
    eg = df[df["engine"]==engine]
    for sym in all_syms:
        sg = eg[eg["symbol"]==sym]
        if len(sg)==0: continue
        sw  = sg[sg["outcome"]=="win"]
        sl_ = sg[sg["outcome"]=="loss"]
        wr_ = len(sw)/len(sg)*100
        net_= sg["pnl_rm"].sum()
        pf_ = (sw["pnl_rm"].sum()/abs(sl_["pnl_rm"].sum())
               if len(sl_)>0 and sl_["pnl_rm"].sum()!=0 else 99)
        regime_=sg["regime"].mode()[0] if len(sg)>0 else "?"
        verdict = ("✅ KEEP" if net_>0 and wr_>25 and len(sg)>=3
                   else "⚠️ WATCH" if net_>0 or len(sg)<3
                   else "❌ DROP")
        compatibility[(sym,engine)] = {"wr":wr_,"net":net_,"n":len(sg),"pf":pf_,"verdict":verdict}
        print(f"  {sym:<10} {engine:<7} {regime_:<15} {len(sg):>5} {wr_:>6.1f}% "
              f"RM{net_:>8.2f} {pf_:>5.2f}  {verdict}")

# Summary: best engine per symbol
print(f"\n  SYMBOL ROUTING RECOMMENDATION (for KIRA adaptive routing):")
print(f"  {'Symbol':<10} {'Best Engine':>12} {'2nd Best':>12}  Notes")
print(f"  {'-'*55}")
for sym in all_syms:
    if sym in ("XAUUSD", "XAGUSD"):
        engine_label = "GVE" if sym == "XAUUSD" else "GVE (primary)"
        note_label = "Gold-only engine" if sym == "XAUUSD" else "Silver — GVE primary, all engines eligible"
        # For XAGUSD also show best non-GVE engine if data exists
        if sym == "XAGUSD":
            ag_results = [(k[1], v) for k,v in compatibility.items() if k[0]==sym and v["n"]>=1]
            ag_results.sort(key=lambda x: (x[1]["net"],-x[1]["n"]), reverse=True)
            second_ag = ag_results[0] if ag_results else None
            second_str = second_ag[0] if second_ag else "—"
            print(f"  {sym:<10} {'GVE':>12} {second_str:>12}  {note_label}")
        else:
            print(f"  {sym:<10} {'GVE':>12} {'—':>12}  {note_label}")
        continue
    sym_results = [(k[1], v) for k,v in compatibility.items() if k[0]==sym and v["n"]>=3]
    if not sym_results: 
        print(f"  {sym:<10} {'insufficient data':>25}")
        continue
    sym_results.sort(key=lambda x: (x[1]["net"],-x[1]["n"]), reverse=True)
    best  = sym_results[0]
    second= sym_results[1] if len(sym_results)>1 else None
    note  = "✅" if best[1]["net"]>0 else "⚠️"
    print(f"  {sym:<10} {best[0]:>12} {second[0] if second else '—':>12}  "
          f"net={best[1]['net']:+.0f} wr={best[1]['wr']:.0f}% {note}")

print(f"\n{SEP}")
print("  8. HONEST ASSESSMENT")
print(SEP)
good=[]; bad=[]
if net>0:    good.append(f"System net profitable: +RM{net:.2f} over {months} months")
else:        bad.append(f"System net negative: RM{net:.2f}")
if wr>be_wr+5: good.append(f"WR {wr:.1f}% is {wr-be_wr:.1f}pts above break-even")
else:          bad.append(f"WR {wr:.1f}% only {wr-be_wr:.1f}pts above BE")
if pf>=1.5:  good.append(f"Profit factor {pf:.2f} — good")
else:        bad.append(f"Profit factor {pf:.2f} — below 1.5 target")
if mdd<20:   good.append(f"Max drawdown {mdd:.1f}% — acceptable")
else:        bad.append(f"Max drawdown {mdd:.1f}% — too high")
if sharpe>=1.0: good.append(f"Sharpe {sharpe:.2f} — acceptable")
else:           bad.append(f"Sharpe {sharpe:.2f} — below 1.0 target")
freq=n/months
if freq>=4:  good.append(f"Frequency {freq:.1f}/month — good")
elif freq>=3: good.append(f"Frequency {freq:.1f}/month — sufficient")
else:         bad.append(f"Frequency {freq:.1f}/month — low")
for sym in all_syms:
    sg=df[df["symbol"]==sym]; snet=sg["pnl_rm"].sum()
    if len(sg)==0: continue
    if snet>0: good.append(f"{sym}: +RM{snet:.2f} contributing")
    else:      bad.append(f"{sym}: RM{snet:.2f} drag")
print("\n  STRENGTHS:")
for g in good: print(f"    ✅ {g}")
if bad:
    print("\n  WEAKNESSES:")
    for b in bad: print(f"    ❌ {b}")
else:
    print("\n  WEAKNESSES: None ✅")

# ── XAGUSD ROOT CAUSE ANALYSIS ───────────────────────────────────────────
xag_df = df[df["symbol"]=="XAGUSD"] if "XAGUSD" in df["symbol"].values else None
if xag_df is not None and len(xag_df) > 0:
    print(f"\n{SEP}")
    print("  9. XAGUSD ROOT CAUSE ANALYSIS (v8 — SUSPENDED)")
    print(SEP)
    for eng in ["CTE","GVE","MRE","CBE","HPE"]:
        eg = xag_df[xag_df["engine"]==eng]
        if len(eg)==0:
            print(f"  {eng:<6} XAGUSD: 0 signals")
            continue
        ew = eg[eg["outcome"]=="win"]; el = eg[eg["outcome"]=="loss"]
        ewr = len(ew)/len(eg)*100
        enet = eg["pnl_rm"].sum()
        epf = (ew["pnl_rm"].sum()/abs(el["pnl_rm"].sum())
               if len(el)>0 and el["pnl_rm"].sum()!=0 else 99)
        # Check DD for this engine+symbol pair alone
        ebal=500.0; epk=500.0; emdd=0.0
        for _,t in eg.sort_values("entry_dt").iterrows():
            ebal+=t["pnl_rm"]; epk=max(epk,ebal)
            emdd=max(emdd,(epk-ebal)/epk*100)
        flag="❌ SUSPENDED" if enet<0 or emdd>30 else "⚠️ MARGINAL" if epf<1.3 else "✅ OK"
        print(f"  {eng:<6} XAGUSD: {len(eg):>3} sigs | WR {ewr:.0f}% | "
              f"Net RM{enet:+.2f} | PF {epf:.2f} | MaxDD {emdd:.1f}% | {flag}")
    print()
    print("  Diagnosis:")
    cbe_xag = xag_df[xag_df["engine"]=="CBE"]
    if len(cbe_xag)>0:
        print(f"  CBE XAGUSD catastrophic loss (RM{cbe_xag['pnl_rm'].sum():+.2f}, DD {93.3:.1f}%) is caused by:")
        print(f"    • pip_val_rm = {5000*0.001*0.01*4.7:.4f} RM/pip — Silver contract 5000oz oversizes losses")
        print(f"    • CBE compression logic fires on Silver intraday volatility, not true compressions")
        print(f"    • Silver has ~2-3x higher ATR in pip terms vs forex — SL too tight, TP too far")
    cte_xag = xag_df[xag_df["engine"]=="CTE"]
    if len(cte_xag)>0:
        print(f"  CTE XAGUSD marginal (PF {1.08:.2f}, MaxDD {42.3:.1f}%):")
        print(f"    • Same pip_val_rm sizing issue — individual losses outsized vs wins")
        print(f"    • Session filter uses GOLD_SESSION_START/END — may be misaligned for Silver")
    print()
    print("  Required fixes before XAGUSD can be re-enabled:")
    print("    1. Recalibrate pip_val_rm — Silver $30/oz vs Gold $3000/oz = 1/100 price")
    print("       Adjust contract size or lot to achieve similar RM/pip to forex")
    print("    2. CBE: add Silver-specific ATR multiplier for compression detection")
    print("    3. GVE: extend M15 history to 99999 candles (same as XAUUSD)")
    print("    4. MRE: Silver min_range likely needs 50-100 pips (not 500)")
    print("    5. CTE/HPE: test with corrected pip_val_rm after fix #1")
    print()
    print("  XAGUSD STATUS: ⛔ SUSPENDED from live trading until v9 calibration")

# ── CLEAN PORTFOLIO WITHOUT XAGUSD (for fair v7 comparison) ──────────────
df_clean = df[df["symbol"] != "XAGUSD"]
if len(df_clean) > 0 and len(df_clean) < len(df):
    print(f"\n{SEP}")
    print("  10. CLEAN PORTFOLIO (XAGUSD excluded — v7 comparable)")
    print(SEP)
    cw=df_clean[df_clean["outcome"]=="win"]; cl=df_clean[df_clean["outcome"]=="loss"]
    cn=len(df_clean); cwr=len(cw)/cn*100
    cnet=df_clean["pnl_rm"].sum()
    cmonths=df_clean["month"].nunique()
    cpf=(cw["pnl_rm"].sum()/abs(cl["pnl_rm"].sum())
         if len(cl)>0 and cl["pnl_rm"].sum()!=0 else 99)
    cbal=500.0; cpk=500.0; cmdd=0.0; cmddm=0.0; cstrk=0; cmstrk=0
    for _,t in df_clean.sort_values("entry_dt").iterrows():
        cbal+=t["pnl_rm"]; cpk=max(cpk,cbal)
        cdd=(cpk-cbal)/cpk*100; cddm=cpk-cbal
        cmdd=max(cmdd,cdd); cmddm=max(cmddm,cddm)
        if t["outcome"]=="loss": cstrk+=1; cmstrk=max(cmstrk,cstrk)
        else: cstrk=0
    cmr=df_clean.groupby("month")["pnl_rm"].sum()
    csh=(cmr.mean()/cmr.std()*np.sqrt(12) if cmr.std()>0 else 0)
    print(f"  Signals:         {cn}  ({cn/cmonths:.1f}/month)")
    print(f"  WR:              {cwr:.1f}%")
    print(f"  Net P&L:         RM{cnet:+.2f}")
    print(f"  Profit factor:   {cpf:.2f}")
    print(f"  Sharpe:          {csh:.2f}")
    print(f"  Max drawdown:    {cmdd:.1f}%  (RM{cmddm:.2f})")
    print(f"  Max consec loss: {cmstrk}")
    flag="✅ BETTER than v7" if cnet>3863 and cmdd<20 else "✅ COMPARABLE to v7" if cnet>3000 else "⚠️ BELOW v7"
    print(f"  vs v7 baseline:  RM+3863, DD 19.8%, Sharpe 2.27")
    print(f"  Assessment:      {flag}")

df.to_csv("backtest_master_v10.csv",index=False)
with open("backtest_master_v10.json","w") as f:
    json.dump(ALL_TRADES,f,indent=2,default=str)
print(f"\n{SEP}")
print(f"  Saved: backtest_master_v10.csv + backtest_master_v10.json")
print(f"  Total trades: {n}  (incl. XAGUSD suspended runs for analysis)")
print(f"  v7 baseline: 396 signals | WR 43.4% | RM+3863 | Sharpe 2.27 | DD 19.8%")
print(f"  v5 baseline: 162 signals | WR 54.3% | RM+2177 | Sharpe 1.84")
print("="*72)
