# ════════════════════════════════════════════════════════════
#  TRADE MANAGER — Final Build
#  Tracks open/closed trades with MAE/MFE data for ATLAS.
# ════════════════════════════════════════════════════════════

import json
import os
import logging
from datetime import datetime, timezone
from config import *

logger = logging.getLogger("TRADE_MGR")


class TradeManager:

    def __init__(self, mt5_connector, guard, oracle, kira):
        self.mt5         = mt5_connector
        self.guard       = guard
        self.oracle      = oracle
        self.kira        = kira
        self.open_trades = {}   # ticket → trade dict
        self._load()

    def _load(self):
        if os.path.exists(TRADE_LOG):
            try:
                with open(TRADE_LOG) as f:
                    data = json.load(f)
                # Restore open trades (status == 'open')
                for t in data:
                    if t.get("status") == "open":
                        self.open_trades[t["ticket"]] = t
                logger.info(f"TradeManager: {len(self.open_trades)} open trades loaded")
            except Exception as e:
                logger.error(f"TradeManager load: {e}")

    def _save_all(self):
        all_trades = []
        if os.path.exists(TRADE_LOG):
            try:
                with open(TRADE_LOG) as f:
                    all_trades = json.load(f)
            except Exception:
                all_trades = []

        # Update or add open trades
        open_tickets = set(self.open_trades.keys())
        updated = []
        for t in all_trades:
            if t["ticket"] in open_tickets:
                updated.append(self.open_trades[t["ticket"]])
                open_tickets.discard(t["ticket"])
            else:
                updated.append(t)
        # Add any new open trades
        for ticket in open_tickets:
            updated.append(self.open_trades[ticket])

        try:
            with open(TRADE_LOG, "w") as f:
                json.dump(updated, f, indent=2)
        except Exception as e:
            logger.error(f"TradeManager save: {e}")

    def open_trade(self, kira_brief, order):
        ticket = order["ticket"]
        trade  = {
            "ticket":     ticket,
            "symbol":     kira_brief["symbol"],
            "direction":  kira_brief["direction"],
            "grade":      kira_brief["grade"],
            "engine":     kira_brief.get("engine","SIG"),
            "regime":     kira_brief.get("regime","?"),
            "signal_id":  kira_brief.get("signal_id",""),
            "confidence": kira_brief["confidence"],
            "entry":      order["price"],
            "sl":         kira_brief["sl"],
            "tp":         kira_brief["tp"],
            "lot_size":   kira_brief.get("lot_size", LOT_SIZE),
            "sl_pips":    kira_brief["sl_pips"],
            "tp_pips":    kira_brief["tp_pips"],
            "risk_rm":    kira_brief["risk_rm"],
            "kz_name":    kira_brief.get("kz_name",""),
            "sweep_level":kira_brief.get("sweep_level",0),
            "fvg_size":   kira_brief.get("fvg_size_pips",0),
            "open_time":  datetime.now(tz=timezone.utc).isoformat(),
            "status":     "open",
            # MAE/MFE tracking
            "mae_pips":   0.0,   # Max adverse excursion
            "mfe_pips":   0.0,   # Max favorable excursion
        }
        self.open_trades[ticket] = trade
        self._save_all()
        logger.info(f"TradeManager: opened #{ticket} {trade['direction']} {trade['symbol']}")
        return trade

    def update_mae_mfe(self, ticket, current_price):
        """Update MAE/MFE for an open trade — call on every tick."""
        if ticket not in self.open_trades:
            return
        trade = self.open_trades[ticket]
        pip   = 0.01 if "JPY" in trade["symbol"] else 0.0001
        entry = trade["entry"]

        if trade["direction"] == "BUY":
            favorable = (current_price - entry) / pip
            adverse   = (entry - current_price) / pip
        else:
            favorable = (entry - current_price) / pip
            adverse   = (current_price - entry) / pip

        trade["mfe_pips"] = max(trade["mfe_pips"], favorable)
        trade["mae_pips"] = max(trade["mae_pips"], adverse)

    def close_trade(self, ticket, pnl_usd, close_type):
        if ticket not in self.open_trades:
            return None

        trade = self.open_trades.pop(ticket)
        trade["status"]     = "win" if pnl_usd > 0 else ("loss" if pnl_usd < 0 else "be")
        trade["pnl_usd"]    = pnl_usd
        trade["pnl_rm"]     = round(pnl_usd * USD_MYR_RATE, 2)
        trade["close_type"] = close_type
        trade["close_time"] = datetime.now(tz=timezone.utc).isoformat()

        # Load all, update
        all_trades = []
        if os.path.exists(TRADE_LOG):
            try:
                with open(TRADE_LOG) as f:
                    all_trades = json.load(f)
            except Exception:
                all_trades = []

        # Replace or append
        found = False
        for i, t in enumerate(all_trades):
            if t["ticket"] == ticket:
                all_trades[i] = trade
                found = True
                break
        if not found:
            all_trades.append(trade)

        try:
            with open(TRADE_LOG, "w") as f:
                json.dump(all_trades, f, indent=2)
        except Exception as e:
            logger.error(f"TradeManager close save: {e}")

        logger.info(
            f"TradeManager: closed #{ticket} {trade['status'].upper()} "
            f"RM{trade['pnl_rm']} MAE:{trade['mae_pips']:.1f}pip "
            f"MFE:{trade['mfe_pips']:.1f}pip"
        )
        return trade

    def get_stats(self):
        all_trades = []
        if os.path.exists(TRADE_LOG):
            try:
                with open(TRADE_LOG) as f:
                    all_trades = json.load(f)
            except Exception:
                return {"trades": 0, "win_rate": 0}

        completed = [t for t in all_trades if t.get("status") in ["win","loss","be"]]
        n = len(completed)
        if n == 0:
            return {"trades": 0, "win_rate": 0}

        wins = [t for t in completed if t.get("status") == "win"]
        return {
            "trades":   n,
            "wins":     len(wins),
            "losses":   n - len(wins),
            "win_rate": round(len(wins)/n*100, 1),
            "pnl_rm":   round(sum(t.get("pnl_rm",0) for t in completed), 2),
        }

    def _get_closed_pnl(self, ticket):
        """Get P&L for a trade closed by MT5."""
        try:
            return self.mt5.get_closed_pnl(ticket)
        except Exception:
            return 0.0
