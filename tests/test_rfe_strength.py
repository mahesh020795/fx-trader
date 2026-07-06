"""RFE — relative currency strength (pure logic). Strength score per currency
= mean sign-adjusted ROC over `lookback` H4 closes across every supplied pair
containing it. Veto layer only — never generates signals."""
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
