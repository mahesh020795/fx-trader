# ════════════════════════════════════════════════════════════
#  AGENT GUARD — Risk Management (FINAL BUILD)
#  Capital protection above all else.
#  Daily + Weekly + Monthly loss limits.
#  Trailing SL management (no partial close — mathematically worse).
#  Drawdown tiers: 10%→0.5% risk, 20%→STOP.
# ════════════════════════════════════════════════════════════

import logging
from datetime import datetime, timezone, date, timedelta
from config import *  # includes is_silver, is_metal (v8)

logger = logging.getLogger("GUARD")


class AgentGUARD:

    def __init__(self, mt5_connector):
        self.mt5              = mt5_connector
        self.start_balance    = None
        self.peak_balance     = None
        self.recovery_mode    = False
        self.stopped          = False
        self.daily_trades     = 0
        self.daily_pnl_usd    = 0.0
        self.weekly_pnl_usd   = 0.0
        self.monthly_pnl_usd  = 0.0
        self._last_day        = None
        self._last_week       = None
        self._last_month      = None
        self.trail_state      = {}   # ticket → {active, trail_sl}
        self.name             = "GUARD"

        # ── Clustering Protection (v8) ──────────────────────
        # Track consecutive losses across all engines to detect loss clusters
        # Max consec loss hit 11 in v7 backtest — need progressive lot reduction
        self.consec_loss      = 0     # global consecutive loss counter
        self.consec_win       = 0     # consecutive win counter (for reset)
        self.cluster_tier     = 0     # 0=normal, 1=tier1 (0.5×), 2=tier2 (0.25×)

        # ── Currency Exposure Shield (v10) ───────────────────
        # Prevents stacking correlated positions: long AUDUSD + long NZDUSD
        # + long GBPUSD = 3× concentrated short-USD risk that the per-trade
        # 1% risk model doesn't see. The single biggest hidden risk pre-v10.
        # CORRELATED_GROUPS: symbols whose P&L moves together
        self.CORRELATED_GROUPS = [
            {"AUDUSD", "NZDUSD"},               # commodity dollars ~0.85 corr
            {"EURJPY", "GBPJPY", "USDJPY"},     # yen crosses — BOJ/risk-off moves all
            {"EURUSD", "GBPUSD"},               # European majors ~0.80 corr
            {"XAUUSD", "XAGUSD"},               # metals
        ]
        self.MAX_PER_CURRENCY    = 2    # max open positions sharing one currency
        self.CORRELATED_LOT_MULT = 0.5  # 2nd position in correlated group → half size

    # ── RESET TRACKING ────────────────────────────────────────

    def _reset_if_new_period(self):
        today   = date.today()
        week    = today.isocalendar()[1]
        month   = today.month

        if self._last_day != today:
            self.daily_trades  = 0
            self.daily_pnl_usd = self.mt5.get_daily_pnl()
            self._last_day     = today

        if self._last_week != week:
            self.weekly_pnl_usd = 0.0
            self._last_week     = week

        if self._last_month != month:
            self.monthly_pnl_usd = 0.0
            self._last_month     = month

    # ── DRAWDOWN MANAGEMENT ───────────────────────────────────

    def update_peak(self):
        current = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        if self.peak_balance is None or current > self.peak_balance:
            self.peak_balance = current

    def get_drawdown_pct(self):
        if self.peak_balance is None or self.peak_balance == 0:
            return 0.0
        current = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        return (self.peak_balance - current) / self.peak_balance * 100

    def get_risk_pct(self):
        dd = self.get_drawdown_pct()
        if dd >= DD_TIER2_PCT:
            return 0.0  # STOP
        elif dd >= DD_TIER1_PCT:
            return RECOVERY_RISK
        return RISK_PERCENT

    # ── CLUSTERING PROTECTION (v8) ───────────────────────────

    def get_cluster_multiplier(self):
        """
        Returns lot size multiplier based on consecutive loss tier.
        TIER 0 (normal):      1.0× — fewer than 3 consecutive losses
        TIER 1 (caution):     0.5× — 3-4 consecutive losses
        TIER 2 (protect):    0.25× — 5+ consecutive losses
        Resets to 1.0× after first win.
        v7 backtest: max consec loss = 11 — without clustering this
        compounds drawdown rapidly. Tier system caps the damage.
        """
        if self.consec_loss >= GUARD_CLUSTER_TIER2:
            return 0.25
        elif self.consec_loss >= GUARD_CLUSTER_TIER1:
            return 0.5
        return 1.0

    def update_cluster(self, result):
        """
        Update consecutive loss counter. Call after each trade close.
        result: 'win', 'loss', or 'be' (breakeven)
        """
        prev_tier = self.cluster_tier
        if result == "loss":
            self.consec_loss += 1
            self.consec_win   = 0
        elif result == "win":
            self.consec_win  += 1
            self.consec_loss  = 0  # single win resets the streak
        # be (breakeven) — no change to counters

        # Update tier
        if self.consec_loss >= GUARD_CLUSTER_TIER2:
            self.cluster_tier = 2
        elif self.consec_loss >= GUARD_CLUSTER_TIER1:
            self.cluster_tier = 1
        else:
            self.cluster_tier = 0

        if GUARD_CLUSTER_LOG and self.cluster_tier != prev_tier:
            new_mult = self.get_cluster_multiplier()
            logger.warning(
                f"GUARD CLUSTER: tier changed {prev_tier}→{self.cluster_tier} "                f"(consec_loss={self.consec_loss}) → lot multiplier {new_mult}×"
            )

    # ── ADAPTIVE RISK ENGINE (v11 — institutional sizing) ────
    # Three principled layers, none data-mined from the backtest:
    #  1. VOLATILITY TARGETING: when current ATR is elevated vs its own
    #     1-year history, SL distances widen — same lot = more RM risk.
    #     Scale lots inversely so RM-at-risk stays constant. (QuantPedia/
    #     industry standard "vol targeting".)
    #  2. FRACTIONAL KELLY CAP: quarter-Kelly from rolling live results
    #     caps risk mathematically. Kelly f = (b·p − q)/b. Institutions
    #     run 25–50% Kelly; we use 25%.
    #  3. EQUITY-CURVE THROTTLE: when system equity is below its own
    #     20-trade moving average, the system is out of sync with current
    #     conditions → 0.75× until it re-syncs. Adaptive, self-healing.

    def get_volatility_multiplier(self, symbol, current_atr, atr_history):
        """Vol targeting: returns 0.5–1.25× lot multiplier.
        current_atr vs percentile of its own 1yr history."""
        if not atr_history or len(atr_history) < 50 or current_atr <= 0:
            return 1.0
        below = sum(1 for a in atr_history if a < current_atr)
        pctile = below / len(atr_history)
        if pctile > 0.90:  return 0.50   # extreme vol — half size
        if pctile > 0.75:  return 0.75   # elevated vol
        if pctile < 0.25:  return 1.25   # calm market — slightly larger
        return 1.0

    def get_kelly_cap(self, recent_trades, fraction=0.25):
        """Quarter-Kelly risk cap from the last N live trades.
        Returns max risk %% of balance (capped 0.25–2.0)."""
        closed = [t for t in recent_trades
                  if t.get("status") in ("win", "loss")][-50:]
        if len(closed) < 20:
            return RISK_PERCENT          # not enough data — use default
        wins   = [t for t in closed if t["status"] == "win"]
        losses = [t for t in closed if t["status"] == "loss"]
        if not wins or not losses:
            return RISK_PERCENT
        p = len(wins) / len(closed)
        avg_w = sum(t.get("pnl_rm", 0) for t in wins) / len(wins)
        avg_l = abs(sum(t.get("pnl_rm", 0) for t in losses)) / len(losses)
        if avg_l == 0:
            return RISK_PERCENT
        b = avg_w / avg_l
        kelly = (b * p - (1 - p)) / b
        if kelly <= 0:
            return 0.25                  # negative edge detected — minimum risk
        return round(max(0.25, min(2.0, kelly * fraction * 100)), 2)

    # ── PROP FIRM MODE (v12) ─────────────────────────────────
    def check_prop_limits(self):
        """Hard gate for funded accounts. Returns (can_trade, reason).
        Internal limits sit WELL inside firm rules: -3% daily (rule 5%),
        -7% total (rule 10%) — breach becomes structurally impossible."""
        if not PROP_MODE:
            return True, ""
        bal = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        # Daily stop
        if self.start_balance > 0:
            daily_pct = self.daily_pnl_usd / self.start_balance * 100
            if daily_pct <= -PROP_DAILY_STOP_PCT:
                return False, (f"PROP DAILY STOP: {daily_pct:.1f}% "
                               f"(internal limit -{PROP_DAILY_STOP_PCT}%)")
        # Total trailing DD from peak
        dd = self.get_drawdown_pct()
        if dd >= PROP_TOTAL_DD_STOP:
            self.stopped = True
            return False, (f"PROP TOTAL DD HALT: {dd:.1f}% "
                           f"(internal limit {PROP_TOTAL_DD_STOP}%)")
        # Concurrent position cap
        try:
            if len(self.mt5.get_positions()) >= PROP_MAX_CONCURRENT:
                return False, f"PROP: max {PROP_MAX_CONCURRENT} concurrent positions"
        except Exception:
            pass
        return True, ""

    def get_capital_adequacy_mult(self):
        """v11.1: Monte Carlo showed the danger zone is EARLY account life,
        before the profit cushion builds (median expected DD 21.9% vs the
        backtest's lucky 12.6% path). Until balance reaches 1.5x starting
        capital, risk 0.7x. Cuts early ruin probability sharply; cost is
        slightly slower first months. Removes itself automatically."""
        bal = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        if self.start_balance > 0 and bal < self.start_balance * 1.5:
            return 0.7
        return 1.0

    def get_equity_throttle(self):
        """0.75× when equity below its own 20-trade MA (system out of sync)."""
        if not hasattr(self, "_equity_track"):
            self._equity_track = []
        bal = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        self._equity_track.append(bal)
        self._equity_track = self._equity_track[-40:]
        if len(self._equity_track) < 20:
            return 1.0
        ma20 = sum(self._equity_track[-20:]) / 20
        return 0.75 if bal < ma20 else 1.0

    # ── CURRENCY EXPOSURE SHIELD (v10) ───────────────────────

    def _split_currencies(self, symbol):
        """XAUUSD → ('XAU','USD'); EURJPY → ('EUR','JPY')."""
        return symbol[:3], symbol[3:6]

    def check_exposure(self, symbol, direction):
        """Portfolio-level correlation check BEFORE opening a position.
        Returns (allowed: bool, lot_multiplier: float, reason: str).

        Rules:
          1. Same symbol already open → block (handled upstream, double-check)
          2. >= MAX_PER_CURRENCY positions sharing a currency SAME direction
             of exposure → block
          3. Open position in the same CORRELATED_GROUP, same direction
             → allow at CORRELATED_LOT_MULT (half size)
        """
        try:
            positions = self.mt5.get_positions()
        except Exception:
            positions = []
        if not positions:
            return True, 1.0, ""

        base, quote = self._split_currencies(symbol)
        # Exposure sign per currency for the NEW trade:
        # BUY EURUSD = long EUR, short USD
        new_exposure = {}
        if direction == "BUY":
            new_exposure[base]  = 1
            new_exposure[quote] = -1
        else:
            new_exposure[base]  = -1
            new_exposure[quote] = 1

        currency_stack = {c: 0 for c in new_exposure}
        correlated_hit = None

        for pos in positions:
            p_sym = pos.get("symbol", "")
            p_dir = "BUY" if pos.get("type", 0) == 0 else "SELL"
            if p_sym == symbol:
                return False, 0.0, f"{symbol} already open"

            pb, pq = self._split_currencies(p_sym)
            p_exp = ({pb: 1, pq: -1} if p_dir == "BUY" else {pb: -1, pq: 1})
            # Count same-direction currency exposure stacking
            for cur, sign in new_exposure.items():
                if p_exp.get(cur, 0) == sign:
                    currency_stack[cur] += 1

            # Correlated group, same direction?
            for group in self.CORRELATED_GROUPS:
                if symbol in group and p_sym in group and p_dir == direction:
                    correlated_hit = p_sym

        for cur, count in currency_stack.items():
            if count >= self.MAX_PER_CURRENCY:
                return False, 0.0, (f"Currency exposure: {count} open positions "
                                    f"already stacked on {cur} same direction")

        if correlated_hit:
            return True, self.CORRELATED_LOT_MULT, (
                f"Correlated with open {correlated_hit} — half size")

        return True, 1.0, ""

    def get_lot_size(self, sl_pips=12, symbol="EURUSD"):
        risk_pct = self.get_risk_pct()
        if PROP_MODE:
            risk_pct = min(risk_pct, PROP_RISK_PERCENT)   # v12: prop cap
        if risk_pct == 0:
            return 0.0
        balance  = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        risk_usd = balance * (risk_pct / 100)

        # Gold / Silver: dynamic sizing based on actual SL distance
        if is_gold(symbol) or is_silver(symbol):
            pip_val_per_001  = 0.01    # USD per pip at 0.01 lots for metals
            lots_raw = (risk_usd / (sl_pips * pip_val_per_001)) * 0.01
            lots     = max(LOT_GOLD, min(0.50, round(lots_raw / 0.01) * 0.01))
        else:
            pip_val  = 0.10   # USD per pip at 0.01 lot for forex
            lots_raw = (risk_usd / (sl_pips * pip_val)) * 0.01
            lots     = max(LOT_FOREX, min(0.20, round(lots_raw / 0.01) * 0.01))

        # v11.1: capital-adequacy protection (early account life)
        ca_mult = self.get_capital_adequacy_mult()
        if ca_mult < 1.0:
            lots = max(0.01, round(lots * ca_mult / 0.01) * 0.01)

        # v11: equity-curve throttle (adaptive — system out of sync detection)
        eq_mult = self.get_equity_throttle()
        if eq_mult < 1.0:
            lots = max(0.01, round(lots * eq_mult / 0.01) * 0.01)
            logger.debug(f"GUARD equity throttle: 0.75x (below 20-trade equity MA)")

        # Apply cluster multiplier AFTER base lot calculation
        cluster_mult = self.get_cluster_multiplier()
        if cluster_mult < 1.0:
            min_lot = LOT_GOLD if (is_gold(symbol) or is_silver(symbol)) else LOT_FOREX
            lots = max(min_lot, round(lots * cluster_mult / 0.01) * 0.01)
            logger.debug(f"GUARD CLUSTER: {symbol} lot {lots} (mult={cluster_mult}×, streak={self.consec_loss})")

        return lots

    # ── SESSION ───────────────────────────────────────────────

    def is_good_session(self):
        h = datetime.now(tz=timezone.utc).hour
        return SESSION_START_UTC <= h < SESSION_END_UTC

    def is_weekend(self):
        now = datetime.now(tz=timezone.utc)
        return now.weekday() in [5, 6]

    def is_friday_close(self):
        now = datetime.now(tz=timezone.utc)
        return now.weekday() == 4 and now.hour >= 20

    # ── TRADE APPROVAL ────────────────────────────────────────

    def can_trade(self):
        """Returns (allowed, reason)."""
        self._reset_if_new_period()
        self.update_peak()

        now = datetime.now(tz=timezone.utc)

        if self.stopped:
            return False, f"System stopped — 20% drawdown reached"

        if self.is_weekend():
            return False, "Weekend — market closed"

        if self.is_friday_close():
            return False, "Friday close approaching — no new positions"

        if not self.is_good_session():
            return False, "Outside London/NY session"

        if self.daily_trades >= MAX_DAILY_TRADES:
            return False, f"Daily limit {MAX_DAILY_TRADES} trades reached"

        balance = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()

        if balance > 0:
            daily_pct = (self.daily_pnl_usd / balance) * 100
            if daily_pct <= -MAX_DAILY_LOSS_PCT:
                return False, f"Daily loss limit hit ({daily_pct:.1f}%)"

            weekly_pct = (self.weekly_pnl_usd / balance) * 100
            if weekly_pct <= -MAX_WEEKLY_LOSS_PCT:
                return False, f"Weekly loss limit hit ({weekly_pct:.1f}%)"

            monthly_pct = (self.monthly_pnl_usd / balance) * 100
            if monthly_pct <= -MAX_MONTHLY_LOSS_PCT:
                return False, f"Monthly loss limit hit ({monthly_pct:.1f}%)"

        dd = self.get_drawdown_pct()
        if dd >= DD_TIER2_PCT:
            self.stopped = True
            return False, f"Drawdown {dd:.1f}% — system stopped"

        risk_pct = self.get_risk_pct()
        if risk_pct == 0:
            return False, "Risk reduced to zero — review system"

        return True, "OK"

    # ── MAIN ANALYSIS ─────────────────────────────────────────

    def analyse(self, kira_brief, active_signals):
        self._reset_if_new_period()
        self.update_peak()

        symbol    = kira_brief["symbol"]
        direction = kira_brief["direction"]

        can, reason = self.can_trade()

        # Correlation check
        usd_pairs    = ["AUDUSD","EURUSD","GBPUSD"]
        active_usd   = [s for s in active_signals if s.get("symbol") in usd_pairs]
        conflict     = False
        conflict_rsn = ""
        if active_usd and symbol in usd_pairs:
            for ex in active_usd:
                if ex.get("direction") != direction:
                    conflict     = True
                    conflict_rsn = f"{ex['symbol']} {ex['direction']} open — opposite USD"
                    break
            if len(active_usd) >= 2:
                conflict     = True
                conflict_rsn = "Max 2 USD pairs already open"

        balance   = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        lots      = self.get_lot_size(kira_brief.get("sl_pips", 12), symbol)
        risk_pct  = self.get_risk_pct()
        dd        = self.get_drawdown_pct()
        open_n    = len(self.mt5.get_open_positions())

        pip_val   = 0.10 * USD_MYR_RATE
        risk_rm   = round(lots/LOT_SIZE * kira_brief.get("sl_pips",12) * pip_val, 2)
        profit_rm = round(lots/LOT_SIZE * kira_brief.get("tp_pips",35) * pip_val, 2)

        # Guard score
        score = 100
        warnings = []
        if not can:
            score = 0
            warnings.append(reason)
        else:
            if conflict:       score -= 30; warnings.append(conflict_rsn)
            if dd >= DD_TIER1_PCT: score -= 20; warnings.append(f"Recovery mode — {risk_pct}% risk")
            if open_n >= 2:    score -= 10; warnings.append(f"{open_n} positions open")

        brief = {
            "agent":         "GUARD",
            "guard_score":   max(0, score),
            "can_trade":     can,
            "cluster_tier":  self.cluster_tier,
            "consec_loss":   self.consec_loss,
            "lot_multiplier":self.get_cluster_multiplier(),
            "blocked_reason": reason if not can else "",
            "conflict":      conflict,
            "conflict_reason": conflict_rsn,
            "recovery_mode": dd >= DD_TIER1_PCT,
            "drawdown_pct":  round(dd, 2),
            "effective_risk": risk_pct,
            "lot_size":      lots,
            "risk_rm":       risk_rm,
            "profit_rm":     profit_rm,
            "daily_trades":  self.daily_trades,
            "daily_pnl_rm":  round(self.daily_pnl_usd * USD_MYR_RATE, 2),
            "weekly_pnl_rm": round(self.weekly_pnl_usd * USD_MYR_RATE, 2),
            "open_positions": open_n,
            "balance_usd":   balance,
            "warnings":      warnings,
        }

        logger.info(
            f"GUARD: {symbol} score:{score} can:{can} "
            f"conflict:{conflict} DD:{dd:.1f}% risk:{risk_pct}%"
        )
        return brief

    # ── TRAILING SL ───────────────────────────────────────────

    def monitor_positions(self):
        """
        Monitor open positions.
        Activate trailing SL after 40% of TP distance.
        Trail SL in TRAIL_STEP_PIPS increments.
        Returns list of (ticket, action, pos) tuples.
        """
        actions   = []
        positions = self.mt5.get_open_positions()

        for pos in positions:
            ticket    = pos["ticket"]
            direction = pos["direction"]
            entry     = pos["entry"]
            current   = pos["current"]
            symbol    = pos["symbol"]
            tp        = pos.get("tp", 0)
            sl        = pos.get("sl", 0)

            pip = 0.01 if "JPY" in symbol else 0.0001

            if ticket not in self.trail_state:
                self.trail_state[ticket] = {"active": False, "trail_sl": sl}

            tp_dist  = abs(tp - entry) / pip if tp else 35
            activation_dist = tp_dist * TRAIL_ACTIVATION_PCT

            if direction == "SELL":
                move_in_favor = (entry - current) / pip
                at_activation = move_in_favor >= activation_dist
                new_trail_sl  = round(current + TRAIL_STEP_PIPS * pip, 5)
                better_sl     = new_trail_sl < (self.trail_state[ticket]["trail_sl"] or sl)
            else:
                move_in_favor = (current - entry) / pip
                at_activation = move_in_favor >= activation_dist
                new_trail_sl  = round(current - TRAIL_STEP_PIPS * pip, 5)
                better_sl     = new_trail_sl > (self.trail_state[ticket]["trail_sl"] or sl)

            if at_activation and better_sl:
                success = self.mt5.modify_sl(ticket, new_trail_sl)
                if success:
                    self.trail_state[ticket] = {
                        "active":   True,
                        "trail_sl": new_trail_sl
                    }
                    action_type = "TRAIL_SL"
                    actions.append((ticket, action_type, pos, new_trail_sl))
                    logger.info(f"GUARD: Trail SL #{ticket} → {new_trail_sl}")

        # Weekend close
        if self.is_friday_close():
            for pos in positions:
                if pos["ticket"] not in [a[0] for a in actions if a[1] == "WEEKEND_CLOSE"]:
                    actions.append((pos["ticket"], "WEEKEND_CLOSE", pos, 0))

        return actions

    # ── RECORD ───────────────────────────────────────────────

    def record_open(self, ticket, sl):
        self.daily_trades += 1
        self.trail_state[ticket] = {"active": False, "trail_sl": sl}

    def record_close(self, ticket, pnl_usd):
        self.daily_pnl_usd   += pnl_usd
        self.weekly_pnl_usd  += pnl_usd
        self.monthly_pnl_usd += pnl_usd
        self.update_peak()
        if ticket in self.trail_state:
            del self.trail_state[ticket]
        # Update clustering protection
        result = "win" if pnl_usd > 0 else "loss" if pnl_usd < 0 else "be"
        self.update_cluster(result)

    def get_summary(self):
        balance = SIM_BALANCE_USD if SIM_MODE else self.mt5.get_balance()
        return {
            "balance_usd":      balance,
            "drawdown_pct":     round(self.get_drawdown_pct(), 2),
            "effective_risk":   self.get_risk_pct(),
            "daily_trades":     self.daily_trades,
            "daily_pnl_rm":     round(self.daily_pnl_usd * USD_MYR_RATE, 2),
            "weekly_pnl_rm":    round(self.weekly_pnl_usd * USD_MYR_RATE, 2),
            "monthly_pnl_rm":   round(self.monthly_pnl_usd * USD_MYR_RATE, 2),
            "recovery_mode":    self.get_drawdown_pct() >= DD_TIER1_PCT,
            "stopped":          self.stopped,
            # ── Clustering state (v8) ──
            "cluster_tier":     self.cluster_tier,
            "consec_loss":      self.consec_loss,
            "lot_multiplier":   self.get_cluster_multiplier(),
        }
