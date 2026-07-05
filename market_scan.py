# market_scan.py
"""Enumerate what MetaQuotes-Demo actually offers. Output feeds new-market
decision in spec 2026-07-03 §Phase 4. STRATEGY: enumerate all symbols with
specs (no history), identify interesting path classes, then deep-fetch M15
depth for indices/metals/crypto/energies/stocks + known FX pairs. Cap at ~100.
Run: python market_scan.py (MT5 open, PYTHONIOENCODING=utf-8)"""
import MetaTrader5 as mt5
from datetime import date
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# Symbols we already trade (always include in deep-fetch)
FX_PAIRS = {"AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "EURJPY", "GBPJPY", "USDJPY", "XAUUSD"}

def interesting_path_class(path):
    """Return path class name if symbol belongs to indices/metals/crypto/energies/stocks."""
    path_lower = path.lower()
    if any(x in path_lower for x in ['indic', 'index']):
        return 'indices'
    if any(x in path_lower for x in ['metal', 'gold', 'silver']):
        return 'metals'
    if 'crypto' in path_lower:
        return 'crypto'
    if any(x in path_lower for x in ['oil', 'energy', 'natural']):
        return 'energies'
    if 'stock' in path_lower or 'equit' in path_lower:
        return 'stocks'
    return None

def main():
    if not mt5.initialize():
        raise SystemExit("MT5 initialize failed — open the MT5 terminal first")

    # Login with config credentials
    if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
        mt5.shutdown()
        raise SystemExit(f"MT5 login failed for account {MT5_LOGIN}")

    syms = mt5.symbols_get()
    print(f"[PASS 1] Enumerating {len(syms)} symbols (specs only, no history)...")

    # Pass 1: collect all specs, identify interesting paths
    symbol_specs = {}
    path_classes = {}
    for s in syms:
        symbol_specs[s.name] = {
            'path': s.path,
            'contract': s.trade_contract_size,
            'tick_value': s.trade_tick_value,
            'spread': s.spread,
        }
        pclass = interesting_path_class(s.path)
        if pclass:
            if pclass not in path_classes:
                path_classes[pclass] = []
            path_classes[pclass].append(s.name)

    # Pass 2: decide which symbols to deep-fetch
    # Priority: FX pairs + one interesting symbol per path class + others if room
    deep_fetch_list = list(FX_PAIRS & set(syms))  # FX pairs that exist
    for pclass in sorted(path_classes.keys()):
        # Add up to 20 symbols per class (indices/metals/crypto/energies/stocks)
        candidates = [n for n in path_classes[pclass] if n not in deep_fetch_list]
        deep_fetch_list.extend(candidates[:20])

    deep_fetch_list = deep_fetch_list[:100]  # Hard cap at 100
    print(f"[PASS 2] Deep-fetching {len(deep_fetch_list)} symbols (FX + top per class)...")

    # Pass 3: deep-fetch M15 history for selected symbols
    deep_results = {}
    for sym in sorted(deep_fetch_list):
        mt5.symbol_select(sym, True)
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 99999)
        depth = len(rates) if rates is not None else 0
        deep_results[sym] = depth

    # Build report: deep-fetched symbols in table
    lines = ["# MetaQuotes-Demo Market Scan — " + str(date.today()), "",
             "## Deep-Fetched Symbols (M15 History)",
             "",
             "| symbol | path | contract | tick_value | spread_pts | M15 bars |",
             "|---|---|---|---|---|---|"]

    for sym in sorted(deep_results.keys()):
        spec = symbol_specs[sym]
        lines.append(f"| {sym} | {spec['path']} | {spec['contract']} "
                     f"| {spec['tick_value']} | {spec['spread']} | {deep_results[sym]} |")

    # Summary by path class
    lines.extend(["", "## Universe Summary (all symbols, specs only)", ""])
    for pclass in sorted(path_classes.keys()):
        count = len(path_classes[pclass])
        lines.append(f"- **{pclass.title()}**: {count} symbols")
    lines.append(f"- **Other**: {len(syms) - sum(len(c) for c in path_classes.values())} symbols")

    # Viable candidates: symbols with >=20k M15 bars
    viable = {sym: depth for sym, depth in deep_results.items()
              if depth >= 20000 and sym not in FX_PAIRS}

    if viable:
        lines.extend(["", "## Viable Future Candidates (≥20,000 M15 bars, requires new spec)", ""])
        for sym in sorted(viable.keys()):
            spec = symbol_specs[sym]
            pclass = interesting_path_class(spec['path'])
            bars = viable[sym]
            # One-line note suggesting engine class
            note = {
                'indices': 'Trend/compression candidate (large moves, wide range)',
                'metals': 'Mean-reversion or trend candidate (volatile, spikey)',
                'crypto': 'High-frequency/trend candidate (24/7, high volatility)',
                'energies': 'Trend or mean-reversion (geopolitical spikes)',
                'stocks': 'Trend/compression candidate (news-driven)',
            }.get(pclass, 'Unknown class')
            lines.append(f"- **{sym}** ({bars:,} bars, {spec['path']}) — {note}")

    mt5.shutdown()
    out = f"docs/reports/market_scan_{date.today()}.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    viable_count = len(viable)
    print(f"\nWrote {out}")
    print(f"  Total symbols: {len(syms)}")
    print(f"  Deep-fetched: {len(deep_results)}")
    print(f"  Viable candidates (≥20k bars): {viable_count}")

if __name__ == "__main__":
    main()
