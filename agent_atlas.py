# ════════════════════════════════════════════════════════════
#  AGENT ATLAS — Pattern Learning (FINAL BUILD)
#  Learns from YOUR real trade history.
#  Tracks MAE/MFE per trade for SL/TP intelligence.
#  Meaningful after 50+ trades (~6-12 months).
# ════════════════════════════════════════════════════════════

import json
import os
import requests
import logging
import numpy as np
from datetime import datetime, timezone
from config import *

logger = logging.getLogger("ATLAS")


class AgentATLAS:

    def __init__(self):
        self.trade_history = []
        self.pattern_db    = {}
        self.name          = "ATLAS"
        self._load_data()

    def _load_data(self):
        if os.path.exists(TRADE_LOG):
            try:
                with open(TRADE_LOG) as f:
                    self.trade_history = json.load(f)
                logger.info(f"ATLAS: {len(self.trade_history)} trades loaded")
            except Exception as e:
                logger.error(f"ATLAS load error: {e}")
                self.trade_history = []
        if os.path.exists(PATTERN_DB):
            try:
                with open(PATTERN_DB) as f:
                    self.pattern_db = json.load(f)
            except Exception:
                self.pattern_db = {}

    def reload(self):
        self._load_data()

    # ── STATISTICS ────────────────────────────────────────────

    def get_stats(self):
        completed = [t for t in self.trade_history
                     if t.get("status") in ["win","loss","be"]]
        n = len(completed)
        if n == 0:
            return {"trades": 0, "win_rate": 50.0}

        wins   = [t for t in completed if t.get("status") == "win"]
        losses = [t for t in completed if t.get("status") == "loss"]
        wr     = len(wins) / n * 100

        # By pair — v10 fix: ALL_PAIRS (was PAIRS only — Gold/JPY trades were
        # invisible to ATLAS learning, a silent bug since the symbol expansion)
        pair_stats = {}
        for sym in ALL_PAIRS:
            pt = [t for t in completed if t.get("symbol") in [sym, sym.replace("/","")]]
            if len(pt) >= 3:
                pw = sum(1 for t in pt if t.get("status") == "win")
                pair_stats[sym] = {
                    "total": len(pt), "wins": pw,
                    "win_rate": round(pw/len(pt)*100, 1),
                    "pnl_rm": round(sum(t.get("pnl_rm",0) for t in pt), 2)
                }

        # By engine — v10: engine is the most predictive dimension in this system
        engine_stats = {}
        for eng in ["CTE","GVE","MRE","CBE","HPE"]:
            et = [t for t in completed if t.get("engine") == eng]
            if len(et) >= 3:
                ew = sum(1 for t in et if t.get("status") == "win")
                engine_stats[eng] = {
                    "total": len(et), "wins": ew,
                    "win_rate": round(ew/len(et)*100, 1),
                    "pnl_rm": round(sum(t.get("pnl_rm",0) for t in et), 2)
                }

        # By grade
        grade_stats = {}
        for grade in ["A","B","C"]:
            gt = [t for t in completed if t.get("grade") == grade]
            if len(gt) >= 3:
                gw = sum(1 for t in gt if t.get("status") == "win")
                grade_stats[grade] = {
                    "total": len(gt),
                    "win_rate": round(gw/len(gt)*100, 1)
                }

        # MAE/MFE analysis (after 20+ trades)
        mae_mfe = {}
        trades_with_data = [t for t in completed if "mae_pips" in t and "mfe_pips" in t]
        if len(trades_with_data) >= 10:
            avg_mae  = np.mean([t["mae_pips"] for t in trades_with_data])
            avg_mfe  = np.mean([t["mfe_pips"] for t in trades_with_data])
            # Winners: how far did they go before closing
            winner_mfe = np.mean([t["mfe_pips"] for t in trades_with_data
                                   if t.get("status") == "win"]) if wins else 0
            mae_mfe = {
                "avg_mae_pips":    round(avg_mae, 1),
                "avg_mfe_pips":    round(avg_mfe, 1),
                "winner_mfe_pips": round(winner_mfe, 1),
                "samples":         len(trades_with_data),
            }

        avg_win  = sum(t.get("pnl_rm",0) for t in wins)  / len(wins)  if wins   else 0
        avg_loss = abs(sum(t.get("pnl_rm",0) for t in losses)) / len(losses) if losses else 0

        return {
            "trades":        n,
            "wins":          len(wins),
            "losses":        len(losses),
            "win_rate":      round(wr, 1),
            "avg_win_rm":    round(avg_win, 2),
            "avg_loss_rm":   round(avg_loss, 2),
            "by_pair":       pair_stats,
            "by_engine":     engine_stats,
            "by_grade":      grade_stats,
            "mae_mfe":       mae_mfe,
        }

    # ── COT DATA ─────────────────────────────────────────────

    # v10: proper CFTC market names — old code queried "AUD FUTURES" (exact
    # match, doesn't exist) so COT silently returned nothing since day one.
    # Also extended from 3 currencies → 7 markets including Gold.
    COT_MARKETS = {
        "AUDUSD": ("AUSTRALIAN DOLLAR", 1),    # (market prefix, sign vs symbol)
        "EURUSD": ("EURO FX", 1),
        "GBPUSD": ("BRITISH POUND", 1),
        "NZDUSD": ("NZ DOLLAR", 1),
        "USDCAD": ("CANADIAN DOLLAR", -1),     # CAD long = USDCAD bearish
        "USDJPY": ("JAPANESE YEN", -1),        # JPY long = USDJPY bearish
        "EURJPY": ("EURO FX", 1),              # proxy: EUR positioning
        "GBPJPY": ("BRITISH POUND", 1),        # proxy: GBP positioning
        "XAUUSD": ("GOLD", 1),
    }
    _cot_cache = {}
    COT_CACHE_SEC = 24 * 3600   # COT updates weekly — cache 24h

    def get_cot_sentiment(self, symbol):
        import time as _t
        entry = self.COT_MARKETS.get(symbol)
        if not entry:
            return 0, ""
        market_prefix, sign = entry
        cached = self._cot_cache.get(market_prefix)
        if cached and _t.time() - cached[0] < self.COT_CACHE_SEC:
            bias, reason = cached[1], cached[2]
            return bias * sign, reason
        try:
            url = (
                "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
                f"?$where=starts_with(market_and_exchange_names,'{market_prefix}')"
                "&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=1"
            )
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data:
                import time as _t
                row      = data[0]
                longs    = int(row.get("noncomm_positions_long_all", 0))
                shorts   = int(row.get("noncomm_positions_short_all", 0))
                total    = longs + shorts
                pct_long = longs / total * 100 if total > 0 else 50
                date_str = row.get("report_date_as_yyyy_mm_dd","unknown")[:10]
                if pct_long >= 60:
                    bias, reason = 1, f"Institutions {pct_long:.0f}% net LONG {market_prefix} (COT {date_str})"
                elif pct_long <= 40:
                    bias, reason = -1, f"Institutions {100-pct_long:.0f}% net SHORT {market_prefix} (COT {date_str})"
                else:
                    bias, reason = 0, f"COT neutral {market_prefix} — {pct_long:.0f}% long"
                self._cot_cache[market_prefix] = (_t.time(), bias, reason)
                return bias * sign, reason
        except Exception as e:
            logger.debug(f"COT fetch: {e}")
        return 0, "COT unavailable"

    # ── MAIN ANALYSIS ─────────────────────────────────────────

    def analyse(self, kira_brief):
        symbol    = kira_brief["symbol"]
        direction = kira_brief["direction"]
        grade     = kira_brief["grade"]

        self._load_data()
        stats = self.get_stats()
        n     = stats.get("trades", 0)

        # Historical win rate for this pair
        pair_wr   = 50.0
        pair_data = stats.get("by_pair", {}).get(symbol, {})
        if pair_data.get("total", 0) >= 5:
            pair_wr = pair_data["win_rate"]

        # Historical win rate for this grade
        grade_wr   = 50.0
        grade_data = stats.get("by_grade", {}).get(grade, {})
        if grade_data.get("total", 0) >= 3:
            grade_wr = grade_data["win_rate"]

        # COT
        cot_bias, cot_reason = self.get_cot_sentiment(symbol)
        cot_aligned = (
            (direction == "BUY"  and cot_bias == 1) or
            (direction == "SELL" and cot_bias == -1)
        )

        # ATLAS score
        if n >= 5:
            atlas_score = int(pair_wr * 0.6 + grade_wr * 0.4)
        else:
            atlas_score = 50  # Not enough data

        if cot_aligned:
            atlas_score = min(100, atlas_score + 15)
        elif cot_bias != 0:
            atlas_score = max(0, atlas_score - 10)

        # Blend toward neutral if low trade count
        if n < 20:
            atlas_score = int(atlas_score * (n/20) + 50 * (1 - n/20))

        # MAE/MFE insights
        mae_mfe    = stats.get("mae_mfe", {})
        mae_note   = ""
        if mae_mfe.get("avg_mae_pips", 0) > 0:
            mae_note = (f"Avg MAE {mae_mfe['avg_mae_pips']}pip | "
                        f"Avg MFE {mae_mfe['avg_mfe_pips']}pip")

        brief = {
            "agent":           "ATLAS",
            "atlas_score":     atlas_score,
            "pair_win_rate":   pair_wr,
            "grade_win_rate":  grade_wr,
            "total_trades":    n,
            "cot_bias":        cot_bias,
            "cot_aligned":     cot_aligned,
            "cot_reason":      cot_reason,
            "mae_mfe":         mae_mfe,
            "mae_note":        mae_note,
        }

        logger.info(
            f"ATLAS: {symbol} {direction} score:{atlas_score} "
            f"pairWR:{pair_wr:.0f}% gradeWR:{grade_wr:.0f}% "
            f"COT:{'✅' if cot_aligned else '—'}"
        )
        return brief

    # ── ALPHA-DECAY MONITOR (v11 — self-healing whitelist) ───
    # Research (QuantBench 2025, Maven Securities): alpha decays as edges
    # get crowded; institutions monitor rolling performance and demote
    # decaying models instead of waiting for the annual re-backtest.
    # Here: every engine×symbol combo gets a rolling health check from
    # LIVE results. Degraded combos auto-trade at half size; dead combos
    # are suspended — without touching the static whitelist.

    # v11.1 RECALIBRATION — walk-forward evidence (5/5 folds): short-window
    # re-filtering of proven combos LOST RM-1,205 OOS vs trading them all.
    # Edges here are real but LUMPY; a quiet patch is not a dead edge.
    # → Monitor is now a CATASTROPHE BRAKE, not a performance filter:
    #   wider window, lower thresholds, gentler demotion.
    COMBO_WINDOW       = 25    # rolling trades per combo (was 15)
    COMBO_MIN_SAMPLES  = 12    # min closed trades before judging (was 8)
    COMBO_DEGRADED_PF  = 0.70  # was 1.0 — only act on clear deterioration
    COMBO_DEAD_PF      = 0.40  # was 0.5 — suspend only on catastrophic decay

    def get_combo_health(self, symbol, engine):
        """Returns (multiplier, status, detail) for an engine×symbol combo
        based on its rolling live performance.
          1.0  HEALTHY   — edge intact
          0.5  DEGRADED  — rolling PF < 1.0, half size + alert
          0.0  SUSPENDED — rolling PF < 0.5, stop trading this combo
        Recovers automatically when rolling PF improves."""
        closed = [t for t in self.trade_history
                  if t.get("status") in ("win", "loss")
                  and t.get("symbol") == symbol
                  and t.get("engine") == engine][-self.COMBO_WINDOW:]
        if len(closed) < self.COMBO_MIN_SAMPLES:
            return 1.0, "HEALTHY", f"building history ({len(closed)}/{self.COMBO_MIN_SAMPLES})"
        gw = sum(t.get("pnl_rm", 0) for t in closed if t.get("pnl_rm", 0) > 0)
        gl = abs(sum(t.get("pnl_rm", 0) for t in closed if t.get("pnl_rm", 0) < 0))
        pf = gw / gl if gl > 0 else 99.0
        if pf < self.COMBO_DEAD_PF:
            return 0.0, "SUSPENDED", (f"rolling PF {pf:.2f} over last {len(closed)} "
                                      f"trades — edge appears dead, combo suspended")
        if pf < self.COMBO_DEGRADED_PF:
            return 0.75, "DEGRADED", (f"rolling PF {pf:.2f} over last {len(closed)} "
                                      f"trades — 0.75x until recovery")
        return 1.0, "HEALTHY", f"rolling PF {pf:.2f}"

    def combo_health_report(self):
        """Full health table across all combos with live history."""
        combos = {}
        for t in self.trade_history:
            if t.get("status") in ("win", "loss") and t.get("engine"):
                combos.setdefault((t["symbol"], t["engine"]), True)
        report = {}
        for (sym, eng) in sorted(combos):
            mult, status, detail = self.get_combo_health(sym, eng)
            report[f"{sym} {eng}"] = {"multiplier": mult,
                                      "status": status, "detail": detail}
        return report

    # ── SL/TP ADVISORY (v10) ─────────────────────────────────
    # Closes the MAE/MFE loop: data was collected but never used.

    def get_sl_tp_advisory(self, symbol=None, min_samples=15):
        """Returns SL/TP tuning advice from real MAE/MFE data.
        Logic:
          - If winners' max adverse excursion (MAE) is far below current SL,
            SL can tighten → smaller risk per trade → larger position for
            the same RM risk → higher expectancy.
          - If winners' MFE substantially exceeds TP, TP can extend.
        Only advisory — KIRA decides whether to apply."""
        completed = [t for t in self.trade_history
                     if t.get("status") in ["win","loss"]
                     and "mae_pips" in t and "mfe_pips" in t
                     and (symbol is None or t.get("symbol") == symbol)]
        if len(completed) < min_samples:
            return {"ready": False, "samples": len(completed),
                    "needed": min_samples}

        winners = [t for t in completed if t["status"] == "win"]
        if len(winners) < 5:
            return {"ready": False, "samples": len(completed),
                    "needed": min_samples, "note": "too few winners"}

        win_mae = sorted(t["mae_pips"] for t in winners)
        win_mfe = sorted(t["mfe_pips"] for t in winners)
        # 90th percentile of winner MAE = how much room winners actually need
        p90_mae = win_mae[int(len(win_mae)*0.9)]
        p50_mfe = win_mfe[len(win_mfe)//2]
        avg_sl  = np.mean([t.get("sl_pips", 0) for t in completed])
        avg_tp  = np.mean([t.get("tp_pips", 0) for t in completed])

        advice = {"ready": True, "samples": len(completed),
                  "winner_p90_mae": round(p90_mae,1),
                  "winner_median_mfe": round(p50_mfe,1),
                  "current_avg_sl": round(avg_sl,1),
                  "current_avg_tp": round(avg_tp,1),
                  "sl_advice": "OK", "tp_advice": "OK"}

        if avg_sl > 0 and p90_mae < avg_sl * 0.6:
            advice["sl_advice"] = (f"TIGHTEN: 90% of winners never went beyond "
                                   f"{p90_mae:.0f}pip but SL averages {avg_sl:.0f}pip — "
                                   f"could tighten to ~{p90_mae*1.2:.0f}pip (+20% buffer)")
        if avg_tp > 0 and p50_mfe > avg_tp * 1.3:
            advice["tp_advice"] = (f"EXTEND: median winner ran {p50_mfe:.0f}pip but TP "
                                   f"averages {avg_tp:.0f}pip — leaving profit on table")
        return advice

    # ── RECORD TRADE ─────────────────────────────────────────

    def save_trade(self, trade_data):
        """Save completed trade with MAE/MFE to trade history."""
        self.trade_history.append(trade_data)
        try:
            with open(TRADE_LOG, "w") as f:
                json.dump(self.trade_history, f, indent=2)
        except Exception as e:
            logger.error(f"ATLAS: save trade error: {e}")

    def save_pattern(self, signal, outcome):
        """Save signal outcome to pattern database.
        v10: key now includes ENGINE and REGIME — the two most predictive
        dimensions (the entire v9 whitelist was built on engine×symbol edges)."""
        key = (f"{signal.get('symbol')}_{signal.get('engine','SIG')}_"
               f"{signal.get('regime','?')}_{signal.get('direction')}_"
               f"{signal.get('grade','A')}")
        if key not in self.pattern_db:
            self.pattern_db[key] = {"wins":0,"losses":0,"total":0}
        self.pattern_db[key]["total"] += 1
        if outcome == "win":
            self.pattern_db[key]["wins"] += 1
        elif outcome == "loss":
            self.pattern_db[key]["losses"] += 1
        try:
            with open(PATTERN_DB, "w") as f:
                json.dump(self.pattern_db, f, indent=2)
        except Exception as e:
            logger.error(f"ATLAS: save pattern error: {e}")
