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
