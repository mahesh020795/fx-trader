# ════════════════════════════════════════════════════════════
#  AGENT ORACLE — Orchestrator (FINAL BUILD)
#  Weighs all 4 agent briefs → final decision → Telegram.
#  KIRA 35% + NOVA 25% + ATLAS 25% + GUARD 15%
# ════════════════════════════════════════════════════════════

import json
import logging
import requests
import time
from datetime import datetime, timezone
from config import *

logger = logging.getLogger("ORACLE")


class AgentORACLE:

    BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    def __init__(self):
        self._last_update_id = 0
        self.pending         = {}
        self.name            = "ORACLE"
        self.journal_path    = "oracle_journal.json"
        self._journal        = self._load_journal()

    # ── DECISION JOURNAL (v10) ────────────────────────────────
    # The missing feedback loop: every decision is recorded with ALL agent
    # scores + context. When the trade closes, the outcome is attached.
    # After 50+ entries, attribution_report() shows which agents actually
    # predict outcomes — turning fixed weights into evidence.

    def _load_journal(self):
        import os
        if os.path.exists(self.journal_path):
            try:
                with open(self.journal_path) as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_journal(self):
        try:
            with open(self.journal_path, "w") as f:
                json.dump(self._journal, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"ORACLE journal save: {e}")

    def record_decision(self, signal_id, kira, nova, atlas, guard, oracle):
        """Log every decision with full agent context. Call on every signal."""
        entry = {
            "signal_id":   signal_id,
            "ts":          datetime.now(timezone.utc).isoformat(),
            "symbol":      kira.get("symbol"),
            "direction":   kira.get("direction"),
            "engine":      kira.get("engine", "SIG"),
            "regime":      kira.get("regime", "?"),
            "grade":       kira.get("grade"),
            "session":     kira.get("kz_name", "?"),
            "kira_score":  kira.get("kira_score", 50),
            "nova_score":  nova.get("nova_score", 55),
            "nova_verdict":nova.get("verdict", "?"),
            "atlas_score": atlas.get("atlas_score", 50),
            "cot_aligned": atlas.get("cot_aligned", False),
            "guard_score": guard.get("guard_score", 50),
            "cluster_tier":guard.get("cluster_tier", 0),
            "composite":   oracle.get("composite_score", 0),
            "decision":    oracle.get("decision", "?"),
            "outcome":     None,        # filled by record_outcome()
            "pnl_rm":      None,
        }
        self._journal.append(entry)
        self._save_journal()

    def record_outcome(self, signal_id, outcome, pnl_rm):
        """Attach trade outcome to its journal entry. Call on trade close."""
        for entry in reversed(self._journal):
            if entry.get("signal_id") == signal_id:
                entry["outcome"] = outcome
                entry["pnl_rm"]  = round(pnl_rm, 2)
                self._save_journal()
                return True
        return False

    def attribution_report(self, min_samples=30):
        """Which agent scores actually predict wins? Splits closed decisions
        by above/below-median score per agent and compares win rates.
        A useful agent shows a meaningful WR gap. A decorative one doesn't."""
        closed = [e for e in self._journal
                  if e.get("outcome") in ("win", "loss")]
        if len(closed) < min_samples:
            return {"ready": False, "samples": len(closed), "needed": min_samples}

        report = {"ready": True, "samples": len(closed), "agents": {}}
        for agent_key in ["kira_score", "nova_score", "atlas_score", "guard_score", "composite"]:
            scores = sorted(e[agent_key] for e in closed)
            median = scores[len(scores)//2]
            hi = [e for e in closed if e[agent_key] >  median]
            lo = [e for e in closed if e[agent_key] <= median]
            if not hi or not lo:
                continue
            hi_wr = sum(1 for e in hi if e["outcome"]=="win")/len(hi)*100
            lo_wr = sum(1 for e in lo if e["outcome"]=="win")/len(lo)*100
            report["agents"][agent_key] = {
                "median": median,
                "above_median_wr": round(hi_wr, 1),
                "below_median_wr": round(lo_wr, 1),
                "predictive_gap":  round(hi_wr - lo_wr, 1),
                "verdict": ("✅ PREDICTIVE" if hi_wr - lo_wr > 8 else
                            "⚠️ WEAK" if hi_wr - lo_wr > 3 else
                            "❌ NOT PREDICTIVE — consider reweighting"),
            }
        return report

    # ── SCORING ───────────────────────────────────────────────

    def orchestrate(self, kira, nova, atlas, guard):
        """Weighted composite score → final decision."""

        # Immediate blocks
        if nova.get("verdict") == "BLACKOUT":
            return self._blocked("News blackout active", kira, nova, atlas, guard)

        if not guard.get("can_trade", True):
            return self._blocked(guard.get("blocked_reason","Risk block"), kira, nova, atlas, guard)

        kira_score  = kira.get("kira_score", 50)
        nova_score  = nova.get("nova_score", 55)
        atlas_score = atlas.get("atlas_score", 50)
        guard_score = guard.get("guard_score", 50)

        composite = (
            kira_score  * WEIGHT_KIRA  / 100 +
            nova_score  * WEIGHT_NOVA  / 100 +
            atlas_score * WEIGHT_ATLAS / 100 +
            guard_score * WEIGHT_GUARD / 100
        )

        # Adjustments
        if nova.get("verdict") == "CANCEL":   composite *= 0.40
        elif nova.get("verdict") == "DELAY":  composite *= 0.75
        if guard.get("conflict"):             composite *= 0.85

        composite = round(composite, 1)

        if composite >= ORACLE_PROCEED_THRESHOLD:
            decision = "PROCEED"
            reason   = "Multi-agent consensus — signal approved"
        elif composite >= 45:
            decision = "DELAY"
            reason   = f"Score {composite} below threshold — wait for better setup"
        else:
            decision = "CANCEL"
            reason   = f"Score {composite} too low — skip"

        return {
            "composite_score": composite,
            "decision":        decision,
            "reason":          reason,
            "lot_size":        guard.get("lot_size", LOT_SIZE),
            "risk_rm":         guard.get("risk_rm", 5.97),
            "profit_rm":       guard.get("profit_rm", 15.12),
            "kira_score":      kira_score,
            "nova_score":      nova_score,
            "atlas_score":     atlas_score,
            "guard_score":     guard_score,
            "nova_verdict":    nova.get("verdict","PROCEED"),
            "nova_sentiment":  nova.get("sentiment","NEUTRAL"),
            "nova_reason":     nova.get("reason",""),
            "cot_reason":      atlas.get("cot_reason",""),
            "guard_warnings":  guard.get("warnings",[]),
        }

    def _blocked(self, reason, kira, nova, atlas, guard):
        return {
            "composite_score": 0, "decision": "BLOCKED",
            "reason": reason, "lot_size": LOT_SIZE,
            "risk_rm": 0, "profit_rm": 0,
            "kira_score": kira.get("kira_score",50),
            "nova_score": nova.get("nova_score",50),
            "atlas_score": atlas.get("atlas_score",50),
            "guard_score": guard.get("guard_score",50),
            "nova_verdict": nova.get("verdict",""),
            "nova_sentiment": nova.get("sentiment",""),
            "nova_reason": nova.get("reason",""),
            "cot_reason": atlas.get("cot_reason",""),
            "guard_warnings": guard.get("warnings",[]),
        }

    # ── TELEGRAM SIGNAL ───────────────────────────────────────

    def send_signal(self, kira, nova, atlas, guard, oracle, signal_id):
        direction  = kira["direction"]
        symbol     = kira["symbol"]
        grade      = kira["grade"]
        composite  = oracle["composite_score"]

        dir_emoji   = "🟢 ▲ BUY" if direction == "BUY" else "🔴 ▼ SELL"
        grade_emoji = {"A":"🏆","B":"🥈","C":"🥉"}.get(grade,"")

        # Regime note
        atr_note = ""
        if kira.get("atr_regime_adj", 0) < 0:
            atr_note = f"\n  ⚠️ {kira.get('atr_regime_rsn','')}"

        # D1/W1 level note
        level_note = ""
        if kira.get("level_boost", 0) > 0:
            level_note = f"\n  Key level: ✅ {kira.get('level_reason','')}"

        # COT note
        cot_note = ""
        if atlas.get("cot_reason"):
            cot_note = f"\n  COT: {atlas['cot_reason']}"

        # Warnings
        warn_text = ""
        for w in oracle.get("guard_warnings", []):
            warn_text += f"\n  ⚠️ {w}"

        # MAE/MFE note
        mae_note = ""
        if atlas.get("mae_note"):
            mae_note = f"\n  📊 {atlas['mae_note']}"

        msg = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{grade_emoji} <b>ORACLE — GRADE {grade}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{dir_emoji} <b>{symbol}</b>\n"
            f"<b>Composite: {composite}/100</b>\n\n"
            f"<b>📊 KIRA</b> — {kira['kira_score']}/100\n"
            f"  D1:{kira.get('d1_direction','?')} | H4 VP ✅ | H1 SMC ✅\n"
            f"  KZ: {kira.get('kz_name','?').replace('_',' ')} | RSI H1:{kira.get('rsi_h1',50):.0f}{atr_note}\n\n"
            f"<b>🎯 SMC CONFIRMATION</b>\n"
            f"  Sweep: ✅ {kira.get('sweep_level','?')}\n"
            f"  FVG: ✅ {kira.get('fvg_low','?')}–{kira.get('fvg_high','?')} ({kira.get('fvg_size_pips',0):.1f}pip)\n"
            f"  Rejection: ✅ {kira.get('rejection_type','?').replace('_',' ')}\n"
            f"  VP POC: {kira.get('vp_poc','?')}{level_note}\n\n"
            f"<b>📰 NOVA</b> — {oracle['nova_score']}/100\n"
            f"  {oracle['nova_verdict']} · {oracle['nova_sentiment']}\n"
            f"  {oracle['nova_reason']}\n\n"
            f"<b>📈 ATLAS</b> — {oracle['atlas_score']}/100\n"
            f"  Your WR: {atlas.get('pair_win_rate',50):.0f}% ({atlas.get('total_trades',0)} trades){cot_note}{mae_note}\n\n"
            f"<b>🛡 GUARD</b> — {oracle['guard_score']}/100\n"
            f"  Risk: {guard.get('effective_risk',1)}% | "
            f"DD: {guard.get('drawdown_pct',0):.1f}%{warn_text}\n\n"
            f"<b>📍 COPY TO MT5</b>\n"
            f"  Entry:   <code>{kira['entry']}</code>\n"
            f"  SL:      <code>{kira['sl']}</code>  ({kira['sl_pips']}pip)\n"
            f"  TP:      <code>{kira['tp']}</code>  ({kira['tp_pips']}pip)\n"
            f"  Exit:    Trailing SL (auto-managed)\n\n"
            f"<b>📦 Position</b>\n"
            f"  Lots: <code>{oracle['lot_size']}</code> | R:R: 1:{kira['rr']}\n"
            f"  Risk: <b>-RM{oracle['risk_rm']}</b> | "
            f"Target: <b>+RM{oracle['profit_rm']}</b>\n\n"
            f"<b>💡 ORACLE:</b> {oracle['reason']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        keyboard = {"inline_keyboard": [[
            {"text": BTN_APPROVE, "callback_data": f"approve_{signal_id}"},
            {"text": BTN_REJECT,  "callback_data": f"reject_{signal_id}"},
            {"text": BTN_DELAY,   "callback_data": f"delay_{signal_id}"},
        ]]}

        msg_id = self._send(msg, keyboard)
        if msg_id:
            self.pending[signal_id] = msg_id
        return msg_id

    # ── NOTIFICATIONS ─────────────────────────────────────────

    def send_trade_opened(self, kira, oracle, order):
        e = "🟢" if kira["direction"]=="BUY" else "🔴"
        self._send(
            f"✅ <b>TRADE PLACED</b>\n\n"
            f"{e} <b>{kira['direction']} {kira['symbol']}</b> #{order['ticket']}\n"
            f"Entry:  <code>{order['price']}</code>\n"
            f"SL:     <code>{kira['sl']}</code>\n"
            f"TP:     <code>{kira['tp']}</code>\n"
            f"Lots:   {oracle['lot_size']}\n"
            f"Risk:   -RM{oracle['risk_rm']}\n"
            f"Target: +RM{oracle['profit_rm']}\n\n"
            f"Trailing SL active — system manages the exit."
        )

    def send_trail_update(self, ticket, symbol, new_sl):
        self._send(
            f"📉 <b>TRAIL SL MOVED</b>\n\n"
            f"<b>{symbol}</b> #{ticket}\n"
            f"New SL: <code>{new_sl}</code>\n"
            f"Locking in profit as price extends."
        )

    def send_trade_closed(self, ticket, symbol, direction, pnl_usd, close_type):
        pnl_rm = pnl_usd * USD_MYR_RATE
        if pnl_usd > 0:
            emoji = "✅ WIN";      pnl_s = f"+RM{pnl_rm:.2f}"
        elif pnl_usd == 0:
            emoji = "🟡 BREAKEVEN"; pnl_s = "±RM0"
        else:
            emoji = "❌ LOSS";     pnl_s = f"-RM{abs(pnl_rm):.2f}"
        self._send(
            f"{emoji} <b>TRADE CLOSED</b>\n\n"
            f"<b>{direction} {symbol}</b> #{ticket}\n"
            f"Type: {close_type}\n"
            f"P&L:  <b>{pnl_s}</b>"
        )

    def send_signal_blocked(self, kira, oracle):
        self._send(
            f"⚠️ <b>SIGNAL {oracle['decision']}</b>\n\n"
            f"{kira['direction']} {kira['symbol']} Grade-{kira['grade']}\n"
            f"Score: {oracle['composite_score']}/100\n"
            f"Reason: {oracle['reason']}"
        )

    def send_startup(self):
        mode = f"SIM ${SIM_BALANCE_USD}" if SIM_MODE else "LIVE"
        auto = "AUTO" if AUTONOMOUS_MODE else "MANUAL"
        self._send(
            f"🤖 <b>FX COMMAND AGENTS — STARTED</b>\n\n"
            f"Agents: KIRA · NOVA · ATLAS · GUARD · ORACLE\n"
            f"Forex:  {', '.join(PAIRS)}\n"
            f"Gold:   {', '.join(GOLD_PAIRS)}\n"
            f"JPY:    {', '.join(JPY_PAIRS)}\n"
            f"Risk:   {RISK_PERCENT}% | Mode: {mode} | {auto}\n"
            f"Limits: Daily {MAX_DAILY_LOSS_PCT}% | "
            f"Weekly {MAX_WEEKLY_LOSS_PCT}% | Monthly {MAX_MONTHLY_LOSS_PCT}%\n\n"
            f"{'⚡ AUTONOMOUS — trades execute automatically' if AUTONOMOUS_MODE else 'System scanning. Tap ✅ APPROVE when signal arrives.'}"
        )

    def send_heartbeat(self, summary, n_open, stats):
        now = datetime.now(tz=timezone.utc).strftime("%H:%M UTC")
        wr  = stats.get("win_rate", 0)
        n   = stats.get("trades", 0)
        self._send(
            f"💓 <b>ALIVE</b> — {now}\n\n"
            f"Balance: ${summary['balance_usd']:.2f}\n"
            f"Open: {n_open} | DD: {summary['drawdown_pct']:.1f}%\n"
            f"Today: RM{summary['daily_pnl_rm']:.2f} | "
            f"Week: RM{summary['weekly_pnl_rm']:.2f}\n"
            f"History: {n} trades · {wr:.0f}% WR\n"
            f"Recovery: {'⚠️ ON' if summary['recovery_mode'] else '✅ OFF'} | "
            f"Stopped: {'🔴 YES' if summary['stopped'] else '✅ NO'}"
        )

    def send_daily_summary(self, summary, stats):
        pnl = summary["daily_pnl_rm"]
        sign = "+" if pnl >= 0 else ""
        e   = "✅" if pnl >= 0 else "📉"
        self._send(
            f"{e} <b>DAILY SUMMARY</b>\n\n"
            f"Trades: {summary['daily_trades']}\n"
            f"P&L:    <b>{sign}RM{pnl:.2f}</b>\n"
            f"WR:     {stats.get('win_rate',0):.0f}% ({stats.get('trades',0)} total)\n"
            f"DD:     {summary['drawdown_pct']:.1f}%"
        )

    def send_limit_hit(self, limit_type, pct):
        self._send(
            f"🛑 <b>{limit_type.upper()} LIMIT HIT</b>\n\n"
            f"Loss: {pct:.1f}%\n"
            f"Trading suspended until next {limit_type} period.\n"
            f"Capital protected."
        )

    def send_error(self, msg):
        self._send(f"⚠️ <b>AGENT ERROR</b>\n\n{msg[:200]}")

    # ── APPROVAL POLLING ──────────────────────────────────────

    def poll_approval(self, signal_id, timeout=APPROVAL_TIMEOUT):
        start = time.time()
        while time.time() - start < timeout:
            updates = self._get_updates()
            for upd in updates:
                if "callback_query" not in upd:
                    continue
                cb   = upd["callback_query"]
                data = cb.get("data","")
                self._answer_callback(cb["id"])
                mid  = cb["message"]["message_id"]
                if f"approve_{signal_id}" in data:
                    self._edit_msg(mid, "✅ APPROVED — placing order...")
                    return "approve"
                if f"reject_{signal_id}" in data:
                    self._edit_msg(mid, "❌ REJECTED — signal skipped")
                    return "reject"
                if f"delay_{signal_id}" in data:
                    self._edit_msg(mid, "⏳ DELAYED — retrying in 1 hour")
                    return "delay"
            time.sleep(3)
        return "timeout"

    # ── TELEGRAM HELPERS ──────────────────────────────────────

    def _send(self, text, reply_markup=None):
        try:
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
                       "parse_mode": "HTML"}
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            r = requests.post(f"{self.BASE}/sendMessage",
                              json=payload, timeout=10)
            d = r.json()
            if d.get("ok"):
                return d["result"]["message_id"]
        except Exception as e:
            logger.error(f"Telegram send: {e}")
        return None

    def _get_updates(self):
        try:
            r = requests.get(
                f"{self.BASE}/getUpdates",
                params={"offset": self._last_update_id+1, "timeout": 2},
                timeout=5
            )
            d = r.json()
            if d.get("ok") and d["result"]:
                self._last_update_id = d["result"][-1]["update_id"]
                return d["result"]
        except Exception:
            pass
        return []

    def _answer_callback(self, cid):
        try:
            requests.post(f"{self.BASE}/answerCallbackQuery",
                         json={"callback_query_id": cid}, timeout=5)
        except Exception:
            pass

    def _edit_msg(self, mid, text):
        try:
            requests.post(f"{self.BASE}/editMessageText",
                         json={"chat_id": TELEGRAM_CHAT_ID,
                               "message_id": mid, "text": text}, timeout=5)
        except Exception:
            pass
