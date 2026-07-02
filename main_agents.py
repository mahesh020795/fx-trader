# ════════════════════════════════════════════════════════════
#  FX COMMAND AGENTS — main_agents.py  (FINAL BUILD)
#  Run: python main_agents.py
# ════════════════════════════════════════════════════════════

import time
import logging
import signal
import sys
import uuid
from datetime import datetime, timezone, date

from config       import *
from mt5_connector import MT5Connector
from trade_manager import TradeManager
from agent_kira    import AgentKIRA
from agent_nova    import AgentNOVA
from agent_atlas   import AgentATLAS
from agent_guard   import AgentGUARD
from agent_oracle  import AgentORACLE
from telegram_commands import TelegramCommands

# ── LOGGING ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)
# Fix Windows console Unicode encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
logger = logging.getLogger("MAIN")


def handle_shutdown(sig, frame):
    logger.info("Shutdown signal received")
    sys.exit(0)

signal.signal(signal.SIGINT,  handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


class FXCommandAgents:

    def __init__(self):
        logger.info("=" * 60)
        logger.info("  FX COMMAND AGENTS — FINAL BUILD")
        logger.info("  KIRA · NOVA · ATLAS · GUARD · ORACLE")
        logger.info("=" * 60)

        self.mt5     = MT5Connector()
        self.kira    = AgentKIRA(self.mt5)
        self.nova    = AgentNOVA()
        self.atlas   = AgentATLAS()
        self.guard   = AgentGUARD(self.mt5)
        self.oracle  = AgentORACLE()
        self.manager = TradeManager(self.mt5, self.guard, self.oracle, self.kira)

        self.active_signals  = []
        self.delayed_signals = {}
        self.last_scan       = {}
        self._last_heartbeat = 0
        self._summary_sent   = None
        self.telegram_cmd    = TelegramCommands(self)

    def start(self):
        if not self.mt5.connect():
            logger.critical("MT5 connection failed — open MT5 first")
            sys.exit(1)

        self.guard.start_balance = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        self.guard.peak_balance  = self.guard.start_balance

        self.oracle.send_startup()
        logger.info(f"Agents running | Mode:{'SIM $'+str(SIM_BALANCE_USD) if SIM_MODE else 'LIVE'}")
        logger.info(f"Forex: {', '.join(PAIRS)}")
        logger.info(f"Gold:  {', '.join(GOLD_PAIRS)}")
        logger.info(f"JPY:   {', '.join(JPY_PAIRS)}")

        self._main_loop()

    def _main_loop(self):
        while True:
            try:
                if not self.mt5.ensure_connected():
                    logger.error("MT5 disconnected — retrying in 30s")
                    time.sleep(30)
                    continue

                # Poll Telegram commands every loop
                self.telegram_cmd.poll_commands()

                # Check if paused via /stop command
                if self.telegram_cmd.paused:
                    time.sleep(TICK_INTERVAL_SEC)
                    continue

                # Monitor positions (trailing SL)
                actions = self.guard.monitor_positions()
                for ticket, action, pos, *extra in actions:
                    if action == "TRAIL_SL":
                        new_sl = extra[0] if extra else 0
                        self.oracle.send_trail_update(ticket, pos["symbol"], new_sl)
                    elif action == "WEEKEND_CLOSE":
                        self.mt5.close_position(ticket)
                        self.oracle._send(f"🌙 Weekend close: #{ticket}")
                    # Update MAE/MFE for all open positions
                    tick = self.mt5.get_tick(pos["symbol"])
                    if tick:
                        self.manager.update_mae_mfe(ticket, tick["bid"])

                # Detect MT5-closed trades (TP/SL/Trail hit)
                self._detect_closed()

                # Delayed signal retry
                self._check_delayed()

                # Scan pairs
                can, reason = self.guard.can_trade()
                if can:
                    for symbol in ALL_PAIRS:
                        self._scan(symbol)
                else:
                    logger.debug(f"Trading paused: {reason}")

                # Heartbeat
                self._heartbeat()

                # Daily summary
                self._daily_summary()

                time.sleep(TICK_INTERVAL_SEC)

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Main loop: {e}", exc_info=True)
                self.oracle.send_error(str(e))
                time.sleep(30)

        self._shutdown()

    def _scan(self, symbol):
        try:
            last = self.last_scan.get(symbol, 0)
            if time.time() - last < 300:  # Max 1 scan per 5 min per pair
                return
            self.last_scan[symbol] = time.time()

            # Skip if already open
            open_syms = [t["symbol"] for t in self.manager.open_trades.values()]
            if symbol in open_syms:
                return

            # KIRA — technical signal
            kira_brief = self.kira.analyse(symbol)
            if not kira_brief:
                return

            # Correlation check
            ok, reason = self.kira.check_correlation(kira_brief, self.active_signals)
            if not ok:
                logger.info(f"Correlation: {reason}")
                return

            self._process(kira_brief)

        except Exception as e:
            logger.error(f"Scan {symbol}: {e}", exc_info=True)

    def _process(self, kira_brief):
        symbol = kira_brief["symbol"]
        logger.info(
            f"Pipeline: {kira_brief['direction']} {symbol} "
            f"Grade-{kira_brief['grade']} KIRA:{kira_brief['kira_score']}"
        )

        # v12: Prop firm hard limits (no-op unless PROP_MODE)
        prop_ok, prop_reason = self.guard.check_prop_limits()
        if not prop_ok:
            logger.warning(f"GUARD {prop_reason}")
            return

        # v11: Alpha-decay monitor — self-healing whitelist
        combo_mult, combo_status, combo_detail = self.atlas.get_combo_health(
            symbol, kira_brief.get("engine", "SIG"))
        if combo_mult == 0.0:
            logger.warning(f"ATLAS combo SUSPENDED: {symbol} "
                           f"{kira_brief.get('engine')} — {combo_detail}")
            self.oracle._send(f"⚠️ ALPHA DECAY: {symbol} "
                              f"{kira_brief.get('engine')} suspended — {combo_detail}")
            return
        if combo_mult < 1.0:
            kira_brief["combo_mult"] = combo_mult
            logger.info(f"ATLAS combo {combo_status}: {combo_detail}")

        # v10: Currency Exposure Shield — portfolio-level correlation check
        # BEFORE spending API calls on NOVA/ATLAS analysis
        exp_ok, exp_mult, exp_reason = self.guard.check_exposure(
            symbol, kira_brief["direction"])
        if not exp_ok:
            logger.info(f"GUARD exposure block: {exp_reason}")
            return
        if exp_mult < 1.0:
            kira_brief["exposure_mult"] = exp_mult
            logger.info(f"GUARD exposure: {exp_reason}")

        nova_brief  = self.nova.analyse(kira_brief)
        atlas_brief = self.atlas.analyse(kira_brief)
        guard_brief = self.guard.analyse(kira_brief, self.active_signals)
        oracle_brief= self.oracle.orchestrate(kira_brief, nova_brief,
                                               atlas_brief, guard_brief)

        decision  = oracle_brief["decision"]
        signal_id = str(uuid.uuid4())[:8]
        kira_brief["signal_id"] = signal_id

        # v10: Decision journal — record EVERY decision with full agent context
        self.oracle.record_decision(signal_id, kira_brief, nova_brief,
                                    atlas_brief, guard_brief, oracle_brief)

        if decision == "BLOCKED":
            logger.info(f"Blocked: {oracle_brief['reason']}")
            return

        # Backtest finding: Grade A (6.2% WR) underperforms Grade B (39.3% WR)
        # Grade A enters too late in the move — block from execution
        if (not EXECUTE_GRADE_A and
                kira_brief.get("grade") == "A"):
            kira_brief["grade"] = "B"  # Treat as Grade B
            logger.info(f"Grade A downgraded to B (backtest finding)")

        if decision in ["DELAY","CANCEL"]:
            self.oracle.send_signal_blocked(kira_brief, oracle_brief)
            if decision == "DELAY":
                self.delayed_signals[signal_id] = (kira_brief, time.time()+3600)
            return

        # PROCEED — send Telegram notification
        self.oracle.send_signal(
            kira_brief, nova_brief, atlas_brief,
            guard_brief, oracle_brief, signal_id
        )

        if AUTONOMOUS_MODE:
            # Auto-execute immediately — no Telegram approval needed
            # SIM_MODE=True means no real money at risk
            logger.info(f"AUTO-EXECUTE: {signal_id} score:{oracle_brief['composite_score']}")
            self._execute(kira_brief, oracle_brief)
        else:
            # Manual mode — wait for Telegram tap to approve
            logger.info(f"Awaiting approval: {signal_id} score:{oracle_brief['composite_score']}")
            response = self.oracle.poll_approval(signal_id, APPROVAL_TIMEOUT)

            if response == "approve":
                self._execute(kira_brief, oracle_brief)
            elif response == "delay":
                self.delayed_signals[signal_id] = (kira_brief, time.time()+3600)
            elif response == "reject":
                logger.info(f"Rejected: {symbol}")
            else:  # timeout
                logger.info(f"Timeout: {symbol}")

    def _execute(self, kira_brief, oracle_brief):
        symbol    = kira_brief["symbol"]
        direction = kira_brief["direction"]

        # Re-ensure MT5 connection is fresh before placing order
        # Fixes retcode=10027 after AutoTrading toggle
        if not self.mt5.ensure_connected():
            self.oracle.send_error(f"MT5 not connected — cannot place order")
            return

        # Recalculate levels from CURRENT price at execution time
        tick = self.mt5.get_tick(symbol)
        if not tick:
            self.oracle.send_error(f"Cannot get tick for {symbol}")
            return

        # v8: use proper pip via config helper (handles metals, JPY, forex)
        from config import get_pip as _get_pip
        pip   = _get_pip(symbol)
        entry = tick["ask"] if direction == "BUY" else tick["bid"]

        if direction == "BUY":
            sl = round(entry - pip * kira_brief["sl_pips"], 5)
            tp = round(entry + pip * kira_brief["tp_pips"], 5)
        else:
            sl = round(entry + pip * kira_brief["sl_pips"], 5)
            tp = round(entry - pip * kira_brief["tp_pips"], 5)

        kira_brief.update({"entry": entry, "sl": sl, "tp": tp,
                           "lot_size": oracle_brief["lot_size"]})

        # v10/v11: apply exposure + combo-health multipliers
        exp_mult = (kira_brief.get("exposure_mult", 1.0) *
                    kira_brief.get("combo_mult", 1.0))
        if exp_mult < 1.0 and "lot_size" in oracle_brief:
            oracle_brief["lot_size"] = max(0.01,
                round(oracle_brief["lot_size"] * exp_mult / 0.01) * 0.01)

        order = self.mt5.place_order(
            symbol    = symbol,
            direction = direction,
            lot_size  = oracle_brief["lot_size"],
            sl        = sl,
            tp        = tp,
            comment   = f"KIRA_{kira_brief.get('engine','SIG')}_G{kira_brief['grade']}_{kira_brief['confidence']}"
        )

        if not order:
            self.oracle.send_error(f"MT5 order failed: {symbol}")
            return

        self.manager.open_trade(kira_brief, order)
        self.guard.record_open(order["ticket"], sl)
        self.active_signals.append(kira_brief)
        self.oracle.send_trade_opened(kira_brief, oracle_brief, order)

        logger.info(
            f"Executed: {direction} {symbol} #{order['ticket']} "
            f"@ {order['price']} SL:{sl} TP:{tp}"
        )

    def _detect_closed(self):
        open_positions = {p["ticket"]: p for p in self.mt5.get_open_positions()}
        for ticket, trade in list(self.manager.open_trades.items()):
            if ticket not in open_positions:
                pnl  = self.manager._get_closed_pnl(ticket)
                kind = ("TP/Trail" if pnl > 0 else
                        "SL"       if pnl < 0 else "BE")
                closed = self.manager.close_trade(ticket, pnl, kind)
                if closed:
                    self.guard.record_close(ticket, pnl)
                    result = "win" if pnl > 0 else "loss" if pnl < 0 else "be"
                    self.kira.update_streaks(result)
                    # v10: engine+regime in pattern key (most predictive dims)
                    self.atlas.save_pattern(
                        {"symbol": closed["symbol"],
                         "direction": closed["direction"],
                         "grade": closed.get("grade","A"),
                         "engine": closed.get("engine","SIG"),
                         "regime": closed.get("regime","?")},
                        result
                    )
                    # v10: close the ORACLE journal feedback loop
                    if closed.get("signal_id"):
                        self.oracle.record_outcome(
                            closed["signal_id"], result,
                            pnl * USD_MYR_RATE)
                    self.atlas.reload()
                    self.oracle.send_trade_closed(
                        ticket, closed["symbol"], closed["direction"], pnl, kind
                    )
                    self.active_signals = [
                        s for s in self.active_signals
                        if s.get("symbol") != closed["symbol"]
                    ]

    def _check_delayed(self):
        now     = time.time()
        expired = [sid for sid, (_, rt) in self.delayed_signals.items()
                   if now >= rt]
        for sid in expired:
            kira_brief, _ = self.delayed_signals.pop(sid)
            logger.info(f"Retrying delayed: {kira_brief['symbol']}")
            self._process(kira_brief)

    def _heartbeat(self):
        now = time.time()
        if now - self._last_heartbeat >= HEARTBEAT_INTERVAL:
            self._last_heartbeat = now
            summary = self.guard.get_summary()
            stats   = self.manager.get_stats()
            n_open  = len(self.mt5.get_open_positions())
            self.oracle.send_heartbeat(summary, n_open, stats)

    def _daily_summary(self):
        now   = datetime.now(tz=timezone.utc)
        today = now.date()
        if now.hour == 22 and self._summary_sent != today:
            self._summary_sent = today
            self.oracle.send_daily_summary(
                self.guard.get_summary(),
                self.manager.get_stats()
            )

    def _shutdown(self):
        logger.info("Shutting down agents...")
        self.mt5.disconnect()
        self.oracle._send("🔴 <b>FX COMMAND AGENTS STOPPED</b>")
        logger.info("Shutdown complete")


if __name__ == "__main__":
    FXCommandAgents().start()
