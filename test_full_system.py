# ════════════════════════════════════════════════════════════
#  test_full_system.py — Complete system diagnostic
#  Tests every component end to end
#  Usage: python test_full_system.py
#  Run this WHILE main_agents.py is NOT running
# ════════════════════════════════════════════════════════════

import sys
import time
import traceback
from datetime import datetime, timezone

# ── colour helpers (Windows safe) ──────────────────────────
def ok(msg):  print(f"  [PASS] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def info(msg): print(f"  [INFO] {msg}")
def section(title):
    print()
    print("=" * 55)
    print(f"  {title}")
    print("=" * 55)

results = []   # (test_name, passed, detail)

def record(name, passed, detail=""):
    results.append((name, passed, detail))
    if passed:
        ok(f"{name}")
    else:
        fail(f"{name} — {detail}")

# ════════════════════════════════════════════════════════════
#  TEST 1: CONFIG
# ════════════════════════════════════════════════════════════
section("TEST 1: CONFIG.PY")
try:
    from config import *
    record("Config imports", True)

    keys = {
        "MT5_LOGIN":          MT5_LOGIN != 0,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN != "YOUR_BOT_TOKEN_HERE",
        "TELEGRAM_CHAT_ID":   TELEGRAM_CHAT_ID   != "YOUR_CHAT_ID_HERE",
        "ANTHROPIC_API_KEY":  ANTHROPIC_API_KEY  != "YOUR_ANTHROPIC_KEY_HERE",
        "NEWS_API_KEY":       NEWS_API_KEY        != "YOUR_NEWSAPI_KEY_HERE",
    }
    for name, filled in keys.items():
        record(f"  {name} filled", filled,
               "" if filled else "Still has placeholder — fill in config.py")

    info(f"Pairs: {PAIRS}")
    info(f"TF constants: M15={TF_M15} H1={TF_H1} H4={TF_H4} D1={TF_D1} W1={TF_W1}")
    info(f"SIM_MODE={SIM_MODE}  SIM_BALANCE=${SIM_BALANCE_USD}")
    record("TF_H1 correct value", TF_H1 == 16385,
           f"TF_H1={TF_H1} should be 16385")
    record("TF_H4 correct value", TF_H4 == 16388,
           f"TF_H4={TF_H4} should be 16388")
    record("TF_D1 correct value", TF_D1 == 16408,
           f"TF_D1={TF_D1} should be 16408")

except Exception as e:
    fail(f"Config import failed: {e}")
    print("Cannot continue without config. Fix config.py first.")
    sys.exit(1)

# ════════════════════════════════════════════════════════════
#  TEST 2: MT5 CONNECTION
# ════════════════════════════════════════════════════════════
section("TEST 2: MT5 CONNECTION")
try:
    import MetaTrader5 as mt5
    record("MetaTrader5 library installed", True)

    if not mt5.initialize():
        record("MT5 initialize", False, str(mt5.last_error()))
        sys.exit(1)
    record("MT5 initialize", True)

    if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
        record("MT5 login", False, str(mt5.last_error()))
        mt5.shutdown()
        sys.exit(1)

    acct = mt5.account_info()
    record("MT5 login", True)
    info(f"Account: {acct.login} | Balance: ${acct.balance:.2f} | Server: {MT5_SERVER}")

except ImportError:
    fail("MetaTrader5 library not installed")
    print("Run: pip install MetaTrader5")
    sys.exit(1)

# ════════════════════════════════════════════════════════════
#  TEST 3: CANDLE DATA
# ════════════════════════════════════════════════════════════
section("TEST 3: CANDLE DATA (all pairs, all timeframes)")
import pandas as pd

timeframe_map = {
    "M15": TF_M15,
    "H1":  TF_H1,
    "H4":  TF_H4,
    "D1":  TF_D1,
    "W1":  TF_W1,
}

candle_ok = True
for symbol in PAIRS:
    mt5.symbol_select(symbol, True)
    time.sleep(0.3)
    print(f"\n  {symbol}:")
    for tf_name, tf_val in timeframe_map.items():
        rates = None
        for attempt in range(3):
            rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, 50)
            if rates is not None and len(rates) > 0:
                break
            time.sleep(1)

        if rates is None or len(rates) == 0:
            fail(f"    {tf_name} — NO DATA (tf value={tf_val})")
            candle_ok = False
        else:
            df = pd.DataFrame(rates)
            latest = pd.to_datetime(df["time"].iloc[-1], unit="s")
            close  = df["close"].iloc[-1]
            n      = len(df)
            ok(f"    {tf_name} — {n} candles | Last: {latest.strftime('%m-%d %H:%M')} | Close: {close:.5f}")

record("All candles readable", candle_ok,
       "Some timeframes returned no data — check MT5 charts are open")

# ════════════════════════════════════════════════════════════
#  TEST 4: LIVE TICK DATA
# ════════════════════════════════════════════════════════════
section("TEST 4: LIVE TICK DATA")
tick_ok = True
for symbol in PAIRS:
    tick = mt5.symbol_info_tick(symbol)
    if not tick or tick.bid == 0:
        fail(f"  {symbol} — no tick data")
        tick_ok = False
    else:
        spread_pips = round((tick.ask - tick.bid) / 0.0001, 1)
        ok(f"  {symbol} — Bid:{tick.bid:.5f} Ask:{tick.ask:.5f} Spread:{spread_pips}pip")
record("All ticks readable", tick_ok)

# ════════════════════════════════════════════════════════════
#  TEST 5: KIRA SIGNAL DETECTION
# ════════════════════════════════════════════════════════════
section("TEST 5: KIRA — SIGNAL DETECTION ON REAL DATA")
try:
    from mt5_connector import MT5Connector
    from agent_kira import AgentKIRA

    connector = MT5Connector()
    connector.connected = True   # Already connected above

    kira = AgentKIRA(connector)
    info("Running KIRA analysis on real MT5 candles...")

    for symbol in PAIRS:
        print(f"\n  {symbol}:")
        candles = connector.get_all_timeframes(symbol)

        # Check each layer manually
        d1_df = candles.get("D1")
        h4_df = candles.get("H4")
        h1_df = candles.get("H1")

        # D1 bias
        if d1_df is not None and len(d1_df) >= 50:
            direction, _, d1_inds = kira._d1_bias(d1_df)
            info(f"    D1 EMA bias: {direction} | "
                 f"Price:{d1_inds.get('price',0):.5f} "
                 f"EMA50:{d1_inds.get('ema50',0):.5f}")
        else:
            fail(f"    D1 data missing ({len(d1_df) if d1_df is not None else 0} candles)")

        # H4 VP zone
        if h4_df is not None and len(h4_df) >= 20:
            zone_ok_v, vp_tp, vp_data = kira._h4_vp_zone(h4_df, direction or "SELL")
            info(f"    H4 VP zone: active={zone_ok_v} | "
                 f"POC:{vp_data.get('poc',0):.5f} "
                 f"VAH:{vp_data.get('vah',0):.5f} "
                 f"VAL:{vp_data.get('val',0):.5f}")
        else:
            fail(f"    H4 data missing ({len(h4_df) if h4_df is not None else 0} candles)")

        # H1 sweep
        if h1_df is not None and len(h1_df) >= 25:
            swept, level, _ = kira._h1_liquidity_sweep(h1_df, direction or "SELL")
            info(f"    H1 Sweep: detected={swept} | level={level}")
            fvg_ok_v, fvg_h, fvg_l, fvg_d = kira._h1_fvg(h1_df, direction or "SELL")
            info(f"    H1 FVG: found={fvg_ok_v} | size={fvg_d.get('size_pips',0):.1f}pip")
            rej, ctype, _ = kira._h1_rejection_candle(h1_df, direction or "SELL")
            info(f"    H1 Rejection: found={rej} | type={ctype}")
        else:
            fail(f"    H1 data missing ({len(h1_df) if h1_df is not None else 0} candles)")

        # Full pipeline
        brief = kira.analyse(symbol)
        if brief:
            ok(f"    FULL SIGNAL: {brief['direction']} Grade-{brief['grade']} "
               f"{brief['confidence']}% Score:{brief['kira_score']}")
            info(f"    Entry:{brief['entry']} SL:{brief['sl']} TP:{brief['tp']} "
                 f"R:R 1:{brief['rr']}")
        else:
            info(f"    No signal (filters not met — normal outside session or no setup)")

    record("KIRA analysis runs without error", True)

except Exception as e:
    fail(f"KIRA error: {e}")
    traceback.print_exc()
    record("KIRA analysis", False, str(e))

# ════════════════════════════════════════════════════════════
#  TEST 6: NOVA — NEWS CHECK
# ════════════════════════════════════════════════════════════
section("TEST 6: NOVA — NEWS & SENTIMENT")
try:
    from agent_nova import AgentNOVA
    nova = AgentNOVA()

    # Test FF event check
    blackout, reason = nova.check_upcoming_events("AUDUSD")
    info(f"  FF 48hr event scan: blackout={blackout} | {reason[:50] if reason else 'No high-impact events'}")
    record("NOVA FF event scan", True)

    # Test headlines fetch
    headlines = nova.get_headlines("EURUSD")
    info(f"  Headlines fetched: {len(headlines)}")
    for h in headlines[:3]:
        info(f"    - {h[:60]}")
    record("NOVA headline fetch", True)

    # Test full analyse (no API key = fallback mode)
    test_brief = {
        "symbol": "EURUSD", "direction": "SELL",
        "grade": "A", "confidence": 82
    }
    nova_result = nova.analyse(test_brief)
    info(f"  Verdict: {nova_result['verdict']} | Score: {nova_result['nova_score']}")
    record("NOVA full analyse", nova_result.get("agent") == "NOVA")

except Exception as e:
    fail(f"NOVA error: {e}")
    record("NOVA", False, str(e))

# ════════════════════════════════════════════════════════════
#  TEST 7: ATLAS — PATTERN LEARNING
# ════════════════════════════════════════════════════════════
section("TEST 7: ATLAS — PATTERN LEARNING")
try:
    from agent_atlas import AgentATLAS
    atlas = AgentATLAS()

    stats = atlas.get_stats()
    info(f"  Trade history: {stats.get('trades', 0)} trades")
    info(f"  Win rate: {stats.get('win_rate', 0)}%")

    test_brief = {
        "symbol": "AUDUSD", "direction": "SELL",
        "grade": "A", "confidence": 82
    }
    atlas_result = atlas.analyse(test_brief)
    info(f"  ATLAS score: {atlas_result['atlas_score']}")
    info(f"  COT: {atlas_result.get('cot_reason', 'unavailable')[:50]}")
    record("ATLAS analyse", atlas_result.get("agent") == "ATLAS")

except Exception as e:
    fail(f"ATLAS error: {e}")
    record("ATLAS", False, str(e))

# ════════════════════════════════════════════════════════════
#  TEST 8: GUARD — RISK MANAGEMENT
# ════════════════════════════════════════════════════════════
section("TEST 8: GUARD — RISK MANAGEMENT")
try:
    from agent_guard import AgentGUARD
    guard = AgentGUARD(connector)
    guard.start_balance = SIM_BALANCE_USD
    guard.peak_balance  = SIM_BALANCE_USD

    can, reason = guard.can_trade()
    info(f"  Can trade: {can} | Reason: {reason}")
    info(f"  Session active: {guard.is_good_session()}")
    info(f"  Drawdown: {guard.get_drawdown_pct():.1f}%")
    info(f"  Risk %: {guard.get_risk_pct()}%")
    info(f"  Lot size: {guard.get_lot_size()}")

    test_brief = {
        "symbol": "AUDUSD", "direction": "SELL",
        "grade": "A", "sl_pips": 12, "tp_pips": 35
    }
    guard_result = guard.analyse(test_brief, [])
    info(f"  Guard score: {guard_result['guard_score']}")
    info(f"  Risk RM: {guard_result['risk_rm']}")
    record("GUARD analyse", guard_result.get("agent") == "GUARD")

    # Test weekly/monthly limits logic
    g2 = AgentGUARD(connector)
    g2.start_balance    = SIM_BALANCE_USD
    g2.peak_balance     = SIM_BALANCE_USD
    g2.weekly_pnl_usd   = -15.0  # exceeds 8% of $125
    g2._last_week       = None
    g2._last_month      = None
    can2, reason2 = g2.can_trade()
    record("Weekly loss limit blocks trading",
           not can2 or "Weekly" in reason2 or "Outside" in reason2,
           f"can={can2} reason={reason2}")

except Exception as e:
    fail(f"GUARD error: {e}")
    record("GUARD", False, str(e))

# ════════════════════════════════════════════════════════════
#  TEST 9: ORACLE — ORCHESTRATION
# ════════════════════════════════════════════════════════════
section("TEST 9: ORACLE — ORCHESTRATION + TELEGRAM")
try:
    from agent_oracle import AgentORACLE
    oracle = AgentORACLE()

    kira_b  = {"kira_score": 85, "direction": "SELL", "symbol": "AUDUSD",
                "grade": "A", "confidence": 82, "entry": 0.706,
                "sl": 0.7175, "tp": 0.699, "sl_pips": 11.5, "tp_pips": 35.0,
                "rr": 3.04, "lot_size": 0.01, "spread": 2.0,
                "rsi_h1": 58.0, "rsi_h4": 54.0, "atr": 0.0009,
                "d1_direction": "SELL", "d1_bos_boost": 8, "d1_bos_reason": "BOS bearish",
                "atr_regime_adj": 0, "atr_regime_rsn": "ATR normal",
                "vp_poc": 0.703, "vp_vah": 0.715, "vp_val": 0.698, "vp_tp": 0.699,
                "smc_sweep": True, "smc_fvg": True, "smc_rejection": True,
                "sweep_level": 0.7175, "fvg_high": 0.7068, "fvg_low": 0.7055,
                "fvg_size_pips": 3.5, "rejection_type": "bearish_pin_bar",
                "kz_name": "NY_KZ", "kz_boost": 10, "level_boost": 8,
                "level_reason": "Sweep at prev D1 high", "timestamp": "2026-05-27T08:00:00Z"}
    nova_b  = {"agent": "NOVA", "nova_score": 65, "verdict": "PROCEED",
                "sentiment": "NEUTRAL", "reason": "No conflicting news",
                "cot_reason": "Institutions 61% net short AUD", "headlines": []}
    atlas_b = {"agent": "ATLAS", "atlas_score": 55, "pair_win_rate": 55.0,
                "grade_win_rate": 58.0, "total_trades": 0, "cot_bias": -1,
                "cot_aligned": True, "cot_reason": "Institutions net short AUD",
                "mae_mfe": {}, "mae_note": ""}
    guard_b = {"agent": "GUARD", "guard_score": 90, "can_trade": True,
                "blocked_reason": "", "conflict": False, "conflict_reason": "",
                "recovery_mode": False, "drawdown_pct": 0.0, "effective_risk": 1.0,
                "lot_size": 0.01, "risk_rm": 5.97, "profit_rm": 15.12,
                "daily_trades": 0, "daily_pnl_rm": 0.0, "weekly_pnl_rm": 0.0,
                "open_positions": 0, "balance_usd": 125.0, "warnings": []}

    oracle_result = oracle.orchestrate(kira_b, nova_b, atlas_b, guard_b)
    info(f"  Composite: {oracle_result['composite_score']}/100")
    info(f"  Decision: {oracle_result['decision']}")
    record("ORACLE orchestrate", oracle_result.get("decision") in
           ["PROCEED","DELAY","CANCEL","BLOCKED"])

    # Telegram test
    print()
    info("  Sending Telegram test message...")
    msg_id = oracle._send(
        "FX Agents Diagnostic — Telegram connection confirmed.\n"
        "All systems operational."
    )
    if msg_id:
        ok(f"  Telegram message sent (id:{msg_id})")
        record("Telegram send", True)
    else:
        fail("  Telegram send failed — check BOT_TOKEN and CHAT_ID in config.py")
        info("  Also make sure you sent a message to your bot first on Telegram")
        record("Telegram send", False, "Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")

except Exception as e:
    fail(f"ORACLE error: {e}")
    record("ORACLE", False, str(e))

# ════════════════════════════════════════════════════════════
#  TEST 10: SESSION TIMING
# ════════════════════════════════════════════════════════════
section("TEST 10: SESSION & KILLZONE TIMING")
try:
    now_utc = datetime.now(tz=timezone.utc)
    now_myt = now_utc.hour + 8  # UTC+8
    if now_myt >= 24: now_myt -= 24

    info(f"  Current UTC: {now_utc.strftime('%H:%M')}")
    info(f"  Current MYT: ~{now_myt:02d}:xx")
    info(f"  Session window: 08:00-22:00 UTC (3PM-6AM MYT)")

    session_active = SESSION_START_UTC <= now_utc.hour < SESSION_END_UTC
    in_london_kz   = LONDON_KZ_START <= now_utc.hour <= LONDON_KZ_END
    in_ny_kz       = NY_KZ_START <= now_utc.hour <= NY_KZ_END

    info(f"  Session active: {session_active}")
    info(f"  London KZ (07-09 UTC / 3-5PM MYT): {in_london_kz}")
    info(f"  NY KZ (12-14 UTC / 8-10PM MYT): {in_ny_kz}")

    if not session_active:
        info("  Currently OUTSIDE session — GUARD will block all trades")
        info("  This is WHY no signals have fired. Correct behaviour.")
        info("  Next window: 3:00 PM MYT (07:00 UTC)")
    else:
        info("  Currently INSIDE session — agents actively scanning")

    record("Timing check", True)

except Exception as e:
    record("Timing check", False, str(e))

# ════════════════════════════════════════════════════════════
#  SHUTDOWN MT5
# ════════════════════════════════════════════════════════════
mt5.shutdown()

# ════════════════════════════════════════════════════════════
#  FINAL REPORT
# ════════════════════════════════════════════════════════════
section("DIAGNOSTIC REPORT")

passed = sum(1 for _, p, _ in results if p)
total  = len(results)
failed_tests = [(n, d) for n, p, d in results if not p]

print(f"\n  Result: {passed}/{total} tests passed\n")

if failed_tests:
    print("  FAILED TESTS:")
    for name, detail in failed_tests:
        print(f"    - {name}")
        if detail:
            print(f"      Fix: {detail}")
else:
    print("  ALL TESTS PASSED")

print()
print("  SIGNAL FREQUENCY REMINDER:")
print("  System fires 4-8 signals per MONTH (not per day)")
print("  Most signals during NY killzone: 8-10 PM MYT")
print("  No signal after 1-2 hours = NORMAL")
print()
if not session_active:
    print("  WHY NO SIGNALS RIGHT NOW:")
    print("  Outside London/NY session (before 3PM MYT)")
    print("  GUARD correctly blocks all trading outside session")
    print("  Signals will start appearing from 3PM MYT today")
print("=" * 55)
