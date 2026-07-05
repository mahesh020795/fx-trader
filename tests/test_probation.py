"""v13 probation sizing: newly-promoted combos trade at reduced size
until they accumulate PROBATION_GRADUATION closed signals, then graduate."""
from agent_atlas import AgentATLAS
from config import PROBATION_COMBOS, PROBATION_MULT, PROBATION_GRADUATION


def _atlas_with(history):
    a = AgentATLAS()
    a.trade_history = history
    return a


def _closed(symbol, engine, n, status="win"):
    return [{"symbol": symbol, "engine": engine, "status": status,
             "pnl_rm": 10.0} for _ in range(n)]


def test_non_probation_combo_full_size():
    # CBE AUDUSD is a baseline live combo, NOT under probation
    assert ("CBE", "AUDUSD") not in PROBATION_COMBOS
    a = _atlas_with(_closed("AUDUSD", "CBE", 3))
    mult, n = a.get_probation_mult("AUDUSD", "CBE")
    assert mult == 1.0


def test_probation_combo_reduced_before_graduation():
    eng, sym = next(iter(PROBATION_COMBOS))
    a = _atlas_with(_closed(sym, eng, 5))
    mult, n = a.get_probation_mult(sym, eng)
    assert mult == PROBATION_MULT
    assert n == 5


def test_probation_combo_graduates_at_threshold():
    eng, sym = next(iter(PROBATION_COMBOS))
    a = _atlas_with(_closed(sym, eng, PROBATION_GRADUATION))
    mult, n = a.get_probation_mult(sym, eng)
    assert mult == 1.0
    assert n >= PROBATION_GRADUATION


def test_probation_one_below_threshold_still_reduced():
    eng, sym = next(iter(PROBATION_COMBOS))
    a = _atlas_with(_closed(sym, eng, PROBATION_GRADUATION - 1))
    mult, _ = a.get_probation_mult(sym, eng)
    assert mult == PROBATION_MULT


def test_open_trades_do_not_count_toward_graduation():
    eng, sym = next(iter(PROBATION_COMBOS))
    hist = _closed(sym, eng, 5) + _closed(sym, eng, 30, status="open")
    a = _atlas_with(hist)
    mult, n = a.get_probation_mult(sym, eng)
    assert n == 5           # only the 5 closed count
    assert mult == PROBATION_MULT
