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
