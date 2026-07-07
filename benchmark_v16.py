# benchmark_v16.py
"""v16 acceptance benchmark: same-day walk-forward OOS profit,
v15 live universe (27 combos) vs the full v16-eligible set (27 + FX-cross
candidates). Mirrors benchmark_v15.py. Reads backtest_master_v13.json;
writes filtered JSONs; walk-forward is run by pointing walkforward_v13 at each.

The v16 'live' arm for the FINAL VERSION_HISTORY three-liner is
v15-live-27 PLUS whatever crosses actually promote (filled after the
matrix + walk-forward arbitration). This script's two standing arms are
the fixed reference (current-live vs full-eligible)."""
import json

# v15 live universe = the 27 combos in config after v15 (routing + whitelist).
V15_LIVE = {
    "CTE": {"AUDUSD", "EURJPY", "EURUSD", "GBPJPY", "NZDUSD", "USDCHF"},
    "GVE": {"XAUUSD"},
    "MRE": {"AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDJPY", "EURGBP"},
    "CBE": {"AUDUSD", "EURJPY", "GBPJPY", "GBPUSD", "NZDUSD", "USDCAD",
            "CADJPY", "EURGBP"},
    "HPE": {"EURUSD", "USDCAD", "USDJPY"},
    "IRE": {"EURGBP", "EURUSD", "AUDUSD"},
}   # 27 combos

def subset(trades, pred):
    return [t for t in trades if pred(t)]

def main():
    trades = json.load(open("backtest_master_v13.json"))
    live = subset(trades, lambda t: t["symbol"] in V15_LIVE.get(t["engine"], set()))
    with open("_bench_v15live.json", "w") as f: json.dump(live, f)
    with open("_bench_v16full.json", "w") as f: json.dump(trades, f)
    print(f"v15 live-27 trades: {len(live)} | full v16 universe trades: {len(trades)}")
    print("Run: copy each over backtest_master_v13.json, run walkforward_v13 + "
          "montecarlo_v13, record OOS whitelist net + fold ratios + MC. Then build "
          "the v15live-27 + promoted-crosses arm for the VERSION_HISTORY delta.")

if __name__ == "__main__":
    main()
