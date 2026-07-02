# ════════════════════════════════════════════════════════════
#  AGENT SAGE — Weekly Self-Review (v12)
#  The first TRUE AI agent in the system: perception → reasoning →
#  proposed action → human approval. SAGE reads the ORACLE decision
#  journal + ATLAS trade history + combo health, sends it to Claude
#  for genuine multi-step reasoning, and delivers a weekly review to
#  Telegram with concrete proposals. It NEVER changes parameters
#  itself — human-in-the-loop is the institutional standard.
#
#  Run weekly (Task Scheduler / cron):  python agent_sage.py
# ════════════════════════════════════════════════════════════
import json, os, logging
from datetime import datetime, timezone, timedelta

import anthropic
import requests

from config import *

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SAGE] %(message)s")
logger = logging.getLogger("SAGE")


class AgentSAGE:

    def __init__(self):
        self.client = (anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                       if ANTHROPIC_API_KEY != "YOUR_ANTHROPIC_KEY_HERE" else None)

    # ── PERCEPTION ────────────────────────────────────────────
    def gather_context(self, days=7):
        ctx = {"period_days": days,
               "generated": datetime.now(timezone.utc).isoformat()}
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Closed trades this week
        trades = []
        if os.path.exists(TRADE_LOG):
            with open(TRADE_LOG) as f:
                all_t = json.load(f)
            for t in all_t:
                ct = t.get("close_time", "")
                if t.get("status") in ("win", "loss", "be") and ct:
                    try:
                        if datetime.fromisoformat(ct) >= cutoff:
                            trades.append({k: t.get(k) for k in
                                ("symbol","engine","regime","direction","grade",
                                 "status","pnl_rm","sl_pips","tp_pips",
                                 "mae_pips","mfe_pips")})
                    except Exception:
                        pass
        ctx["closed_trades_this_week"] = trades

        # Decision journal — decisions incl. blocked/cancelled
        decisions = []
        if os.path.exists("oracle_journal.json"):
            with open("oracle_journal.json") as f:
                journal = json.load(f)
            for e in journal:
                try:
                    if datetime.fromisoformat(e["ts"]) >= cutoff:
                        decisions.append(e)
                except Exception:
                    pass
        ctx["decisions_this_week"] = decisions

        # Combo health + lifetime stats from ATLAS
        try:
            from agent_atlas import AgentATLAS
            atlas = AgentATLAS()
            ctx["combo_health"] = atlas.combo_health_report()
            stats = atlas.get_stats()
            ctx["lifetime"] = {k: stats.get(k) for k in
                               ("trades","win_rate","by_engine","by_pair")}
            ctx["sl_tp_advisory"] = atlas.get_sl_tp_advisory()
        except Exception as e:
            ctx["combo_health"] = f"unavailable: {e}"

        return ctx

    # ── REASONING ─────────────────────────────────────────────
    def reason(self, ctx):
        if not self.client:
            return None
        prompt = f"""You are SAGE, the self-review agent of an autonomous FX trading
system (engines: CTE/GVE/MRE/CBE/HPE; agents: KIRA/NOVA/ATLAS/GUARD/ORACLE).
Backtest baseline you are protecting: WR 49.5%, PF 2.19, ~6 signals/month,
expectancy ~RM14.6/signal. Walk-forward validated 5/5 folds. Important prior
evidence: short-window performance filtering of combos DESTROYS value (edges
are lumpy) — so do NOT propose cutting combos on small samples.

Here is this week's system data (JSON):
{json.dumps(ctx, indent=1, default=str)[:9000]}

Think step by step, then produce a WEEKLY REVIEW with exactly these sections:
1. PERFORMANCE vs EXPECTANCY — is the week within normal variance of the
   baseline (use binomial intuition, ~6 trades is a tiny sample)?
2. PROCESS CHECK — any decisions that violated system rules (blocked combos
   trading, exposure stacking, missing journal outcomes)?
3. AGENT VALUE — from the journal scores, did NOVA/ATLAS/GUARD scores
   differentiate winners from losers this week? (small sample caveats)
4. RISKS NEXT WEEK — concrete, from combo health + open context.
5. PROPOSALS — 0 to 3 specific, conservative proposals for the human
   (e.g. "investigate X", "keep as is"). NEVER propose adding risk after
   a winning week or removing combos after small-sample losses.

Be concise (max 350 words), brutally honest, and numerically grounded."""
        try:
            resp = self.client.messages.create(
                model=MODEL_SONNET, max_tokens=900,
                messages=[{"role": "user", "content": prompt}])
            return resp.content[0].text.strip()
        except Exception as e:
            logger.error(f"Claude reasoning failed: {e}")
            return None

    # ── ACTION (report to human) ──────────────────────────────
    def send_telegram(self, text):
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID,
                      "text": f"🧠 SAGE WEEKLY REVIEW\n{'━'*30}\n{text}"[:4000]},
                timeout=10)
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def run(self):
        logger.info("SAGE gathering context...")
        ctx = self.gather_context()
        n_tr = len(ctx.get("closed_trades_this_week", []))
        n_dec = len(ctx.get("decisions_this_week", []))
        logger.info(f"Context: {n_tr} closed trades, {n_dec} decisions")

        review = self.reason(ctx)
        if review is None:
            review = (f"(Claude unavailable — raw summary)\n"
                      f"Closed trades: {n_tr} | Decisions: {n_dec}\n"
                      f"Combo health: {json.dumps(ctx.get('combo_health'), default=str)[:800]}")
        # Persist review history
        try:
            hist = []
            if os.path.exists("sage_reviews.json"):
                with open("sage_reviews.json") as f:
                    hist = json.load(f)
            hist.append({"ts": ctx["generated"], "review": review})
            with open("sage_reviews.json", "w") as f:
                json.dump(hist, f, indent=2)
        except Exception:
            pass
        self.send_telegram(review)
        print("\n" + review)
        logger.info("SAGE review delivered")


if __name__ == "__main__":
    AgentSAGE().run()
