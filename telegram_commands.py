# ════════════════════════════════════════════════════════════
#  telegram_commands.py — Telegram command handler
#  Runs inside main_agents.py loop
#  Commands work while agents are scanning live
# ════════════════════════════════════════════════════════════

import requests
import logging
from datetime import datetime, timezone
from config import *

logger = logging.getLogger("TELEGRAM_CMD")

BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


class TelegramCommands:

    def __init__(self, agents):
        self.agents          = agents   # reference to FXCommandAgents
        self._last_update_id = 0
        self.paused          = False

    # ── COMMAND POLLING ───────────────────────────────────────

    def poll_commands(self):
        """
        Call this every loop iteration in main_agents.py.
        Checks for new Telegram messages and handles commands.
        """
        try:
            r = requests.get(
                f"{BASE}/getUpdates",
                params={"offset": self._last_update_id + 1, "timeout": 1},
                timeout=5
            )
            data = r.json()
            if not data.get("ok") or not data.get("result"):
                return

            for update in data["result"]:
                self._last_update_id = update["update_id"]
                msg = update.get("message", {})
                text = msg.get("text", "").strip().lower()

                if text.startswith("/"):
                    self._handle(text)

        except Exception as e:
            logger.debug(f"Command poll error: {e}")

    # ── COMMAND HANDLER ───────────────────────────────────────

    def _handle(self, text):
        cmd = text.split()[0]
        logger.info(f"Command received: {cmd}")

        if cmd == "/kira":        self._cmd_kira()
        elif cmd == "/nova":      self._cmd_nova()
        elif cmd == "/status":    self._cmd_status()
        elif cmd == "/stop":      self._cmd_stop()
        elif cmd == "/resume":    self._cmd_resume()
        elif cmd == "/daily":     self._cmd_daily()
        elif cmd == "/debug":     self._cmd_debug()
        elif cmd == "/help":      self._cmd_help()
        else:
            self._send(f"Unknown command: {cmd}\nType /help for list")

    # ── /kira ─────────────────────────────────────────────────

    def _cmd_kira(self):
        """Run KIRA analysis on all pairs right now and report."""
        self._send("Running KIRA analysis on live data...")

        results = []
        for symbol in PAIRS:
            try:
                brief = self.agents.kira.analyse(symbol)
                if brief:
                    results.append(
                        f"SIGNAL: {brief['direction']} {symbol} "
                        f"Grade-{brief['grade']} {brief['confidence']}%\n"
                        f"  KIRA Score: {brief['kira_score']}/100\n"
                        f"  Entry: {brief['entry']} SL: {brief['sl']} "
                        f"TP: {brief['tp']}\n"
                        f"  R:R 1:{brief['rr']} | "
                        f"Risk: RM{brief['risk_rm']}\n"
                        f"  Sweep: {brief['sweep_level']} | "
                        f"FVG: {brief['fvg_low']}-{brief['fvg_high']}\n"
                        f"  Rejection: {brief['rejection_type']}"
                    )
                else:
                    # Get partial info from each layer
                    candles   = self.agents.mt5.get_all_timeframes(symbol)
                    tick      = self.agents.mt5.get_tick(symbol)
                    d1_df     = candles.get("D1") if candles else None
                    h4_df     = candles.get("H4") if candles else None
                    h1_df     = candles.get("H1") if candles else None

                    d1_dir, _, d1_inds = self.agents.kira._d1_bias(d1_df)
                    atr_adj, atr_rsn   = self.agents.kira._atr_regime(d1_df)

                    if d1_dir:
                        zone, vp_tp, vp_d = self.agents.kira._h4_vp_zone(
                            h4_df, d1_dir)
                        swept, sl, _      = self.agents.kira._h1_liquidity_sweep(
                            h1_df, d1_dir)
                        fvg, fh, fl, fd   = self.agents.kira._h1_fvg(
                            h1_df, d1_dir)
                        rej, rtype, _     = self.agents.kira._h1_rejection_candle(
                            h1_df, d1_dir)

                        blocking = []
                        if not zone:  blocking.append("H4 VP zone")
                        if not swept: blocking.append("H1 Sweep")
                        if not fvg:   blocking.append("H1 FVG")
                        if not rej:   blocking.append("H1 Rejection")

                        results.append(
                            f"NO SIGNAL: {symbol}\n"
                            f"  D1 bias: {d1_dir} | "
                            f"Price: {d1_inds.get('price',0):.5f} "
                            f"EMA50: {d1_inds.get('ema50',0):.5f}\n"
                            f"  ATR regime: {atr_rsn[:35]}\n"
                            f"  H4 VP zone: {'Active' if zone else 'NOT active'} | "
                            f"POC: {vp_d.get('poc',0):.5f}\n"
                            f"  H1 Sweep: {'Yes' if swept else 'No'} | "
                            f"FVG: {'Yes '+str(fd.get('size_pips',0))+'pip' if fvg else 'No'} | "
                            f"Rejection: {'Yes '+rtype if rej else 'No'}\n"
                            f"  Blocking: {', '.join(blocking) if blocking else 'none (signal should fire)'}"
                        )
                    else:
                        price = d1_inds.get('price', 0)
                        e50   = d1_inds.get('ema50', 0)
                        results.append(
                            f"BLOCKED: {symbol}\n"
                            f"  D1 bias: NONE\n"
                            f"  Price: {price:.5f} EMA50: {e50:.5f}\n"
                            f"  Reason: {atr_rsn}"
                        )
            except Exception as e:
                results.append(f"ERROR: {symbol}: {str(e)[:50]}")

        now = datetime.now(tz=timezone.utc).strftime("%H:%M UTC")
        msg = f"KIRA LIVE SCAN — {now}\n"
        msg += "=" * 35 + "\n"
        for r in results:
            msg += r + "\n" + "-" * 35 + "\n"

        self._send(msg)

    # ── /nova ─────────────────────────────────────────────────

    def _cmd_nova(self):
        """Run NOVA news check on all active pairs."""
        self._send("Running NOVA news check...")

        for symbol in PAIRS:
            try:
                # Check events
                blackout, b_reason = self.agents.nova.check_upcoming_events(symbol)
                headlines          = self.agents.nova.get_headlines(symbol)

                # Quick sentiment with test brief
                test_brief = {
                    "symbol": symbol, "direction": "BUY",
                    "grade": "A", "confidence": 80
                }
                result = self.agents.nova.analyse(test_brief)

                msg = (
                    f"NOVA: {symbol}\n"
                    f"  Blackout: {'YES - ' + b_reason[:40] if blackout else 'No'}\n"
                    f"  Headlines: {len(headlines)}\n"
                )
                for h in headlines[:2]:
                    msg += f"    - {h[:55]}\n"
                msg += (
                    f"  Sentiment: {result.get('verdict','?')} | "
                    f"Score: {result.get('nova_score','?')}\n"
                    f"  Reason: {result.get('reason','')[:60]}"
                )
                self._send(msg)

            except Exception as e:
                self._send(f"NOVA error {symbol}: {str(e)[:60]}")

    # ── /status ───────────────────────────────────────────────

    def _cmd_status(self):
        """Show current system status."""
        try:
            summary  = self.agents.guard.get_summary()
            stats    = self.agents.manager.get_stats()
            open_pos = self.agents.mt5.get_open_positions()
            now      = datetime.now(tz=timezone.utc).strftime("%H:%M UTC")

            msg = (
                f"SYSTEM STATUS — {now}\n\n"
                f"Balance:  ${summary['balance_usd']:.2f}\n"
                f"DD:       {summary['drawdown_pct']:.1f}%\n"
                f"Risk:     {summary['effective_risk']}%\n"
                f"Recovery: {'ON' if summary['recovery_mode'] else 'OFF'}\n"
                f"Stopped:  {'YES' if summary['stopped'] else 'NO'}\n"
                f"Paused:   {'YES' if self.paused else 'NO'}\n\n"
                f"Today:    RM{summary['daily_pnl_rm']:.2f} | "
                f"{summary['daily_trades']} trades\n"
                f"Week:     RM{summary['weekly_pnl_rm']:.2f}\n"
                f"Month:    RM{summary['monthly_pnl_rm']:.2f}\n\n"
                f"Open positions: {len(open_pos)}\n"
                f"Total trades:   {stats.get('trades',0)}\n"
                f"Win rate:       {stats.get('win_rate',0):.1f}%\n\n"
                f"Session active: {'YES' if self.agents.guard.is_good_session() else 'NO'}"
            )
            self._send(msg)
        except Exception as e:
            self._send(f"Status error: {str(e)[:100]}")

    # ── /stop ─────────────────────────────────────────────────

    def _cmd_stop(self):
        self.paused = True
        self._send(
            "AGENTS PAUSED\n\n"
            "No new signals will be processed.\n"
            "Open positions continue running.\n"
            "Type /resume to restart scanning."
        )
        logger.info("Agents paused via Telegram /stop")

    # ── /resume ───────────────────────────────────────────────

    def _cmd_resume(self):
        self.paused = False
        self._send(
            "AGENTS RESUMED\n\n"
            "Scanning all pairs again."
        )
        logger.info("Agents resumed via Telegram /resume")

    # ── /daily ────────────────────────────────────────────────

    def _cmd_daily(self):
        summary = self.agents.guard.get_summary()
        stats   = self.agents.manager.get_stats()
        self.agents.oracle.send_daily_summary(summary, stats)

    # ── /debug ────────────────────────────────────────────────

    def _cmd_debug(self):
        """Show raw D1 EMA values for all pairs."""
        import MetaTrader5 as mt5_lib

        now = datetime.now(tz=timezone.utc).strftime("%H:%M UTC")
        msg = f"D1 EMA DEBUG — {now}\n\n"

        for symbol in PAIRS:
            try:
                candles = self.agents.mt5.get_all_timeframes(symbol)
                d1_df   = candles.get("D1") if candles else None
                direction, _, inds = self.agents.kira._d1_bias(d1_df)
                atr_adj, atr_rsn   = self.agents.kira._atr_regime(d1_df)

                msg += (
                    f"{symbol}:\n"
                    f"  Bias: {direction or 'NONE'}\n"
                    f"  Price: {inds.get('price',0):.5f}\n"
                    f"  EMA50: {inds.get('ema50',0):.5f}\n"
                    f"  EMA200: {inds.get('ema200',0):.5f}\n"
                    f"  ATR: {atr_rsn[:40]}\n\n"
                )
            except Exception as e:
                msg += f"{symbol}: error {str(e)[:40]}\n\n"

        self._send(msg)

    # ── /help ─────────────────────────────────────────────────

    def _cmd_help(self):
        self._send(
            "FX COMMAND AGENTS — COMMANDS\n\n"
            "/kira    Run KIRA scan on all pairs\n"
            "         Shows each layer result live\n\n"
            "/nova    Run NOVA news check\n"
            "         Shows headlines + sentiment\n\n"
            "/debug   Show D1 EMA values\n"
            "         Explains why no signal\n\n"
            "/status  Show system status\n"
            "         Balance, DD, trades, WR\n\n"
            "/stop    Pause new signal processing\n"
            "/resume  Resume scanning\n\n"
            "/daily   Show today's summary\n"
            "/help    Show this message"
        )

    # ── SEND ──────────────────────────────────────────────────

    def _send(self, text):
        try:
            requests.post(
                f"{BASE}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID,
                      "text": text, "parse_mode": "HTML"},
                timeout=10
            )
        except Exception as e:
            logger.error(f"Send error: {e}")
