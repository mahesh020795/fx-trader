# benchmark_v15.py
"""v15 acceptance benchmark (spec §5): same-day walk-forward OOS profit,
v12 core (the original 20 combos) vs the full v15-eligible set.
Reads backtest_master_v13.json; writes filtered JSONs; reuses
walkforward_v13.run() by pointing it at each file."""
import json, shutil

V12_CORE = {
    "CTE": {"AUDUSD", "EURJPY", "EURUSD", "GBPJPY", "NZDUSD"},
    "GVE": {"XAUUSD"},
    "MRE": {"AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDJPY"},
    "CBE": {"AUDUSD", "EURJPY", "GBPJPY", "GBPUSD", "NZDUSD", "USDCAD"},
    "HPE": {"EURUSD", "USDCAD", "USDJPY"},
}   # 20 combos — the pre-v13 whitelist, from VERSION_HISTORY

def subset(trades, pred):
    return [t for t in trades if pred(t)]

def main():
    trades = json.load(open("backtest_master_v13.json"))
    core = subset(trades, lambda t: t["symbol"] in V12_CORE.get(t["engine"], set()))
    with open("_bench_core.json", "w") as f: json.dump(core, f)
    with open("_bench_full.json", "w") as f: json.dump(trades, f)
    print(f"v12-core trades: {len(core)} | full v15 universe trades: {len(trades)}")
    print("Run: point walkforward_v13 at each file (swap backtest_master_v13.json"
          " via copy) and record both OOS whitelist nets + fold ratios.")

if __name__ == "__main__":
    main()
