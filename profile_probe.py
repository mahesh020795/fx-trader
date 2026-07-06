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
