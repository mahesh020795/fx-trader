# ════════════════════════════════════════════════════════════
#  test_candles.py — Run this to verify candle data is working
#  Usage: python test_candles.py
# ════════════════════════════════════════════════════════════

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from config import *

print("=" * 55)
print("  CANDLE DATA TEST")
print("=" * 55)
print()

# Connect
if not mt5.initialize():
    print(f"FAIL: MT5 initialize failed: {mt5.last_error()}")
    exit(1)

if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
    print(f"FAIL: MT5 login failed: {mt5.last_error()}")
    mt5.shutdown()
    exit(1)

info = mt5.account_info()
print(f"Connected: Account {info.login} | Balance ${info.balance:.2f}")
print()

# Test each pair and timeframe
timeframes = {
    "M15": TF_M15,
    "H1":  TF_H1,
    "H4":  TF_H4,
    "D1":  TF_D1,
    "W1":  TF_W1,
}

counts = {
    "M15": 50,
    "H1":  50,
    "H4":  50,
    "D1":  50,
    "W1":  10,
}

all_ok = True

for symbol in PAIRS:
    print(f"{symbol}:")
    mt5.symbol_select(symbol, True)

    for tf_name, tf_val in timeframes.items():
        rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, counts[tf_name])

        if rates is None or len(rates) == 0:
            print(f"  {tf_name:<5} FAIL — no data returned")
            all_ok = False
        else:
            df      = pd.DataFrame(rates)
            latest  = pd.to_datetime(df["time"].iloc[-1], unit="s")
            oldest  = pd.to_datetime(df["time"].iloc[0], unit="s")
            last_c  = df["close"].iloc[-1]
            n       = len(df)
            print(f"  {tf_name:<5} OK — {n} candles | "
                  f"Latest: {latest.strftime('%Y-%m-%d %H:%M')} | "
                  f"Close: {last_c:.5f}")
    print()

mt5.shutdown()

print("=" * 55)
if all_ok:
    print("  ALL CANDLES READING CORRECTLY")
    print("  KIRA has full data access on all timeframes")
else:
    print("  SOME TIMEFRAMES FAILED — see FAIL lines above")
print("=" * 55)
