# ════════════════════════════════════════════════════════════
#  AGENT KIRA — Market Intelligence (FINAL BUILD + GOLD/JPY)
#
#  3-Layer Hierarchy — identical logic, calibrated parameters:
#
#  D1  : EMA bias (HARD) + BOS/CHoCH (SOFT) + ATR regime (SOFT)
#  H4  : Volume Profile zone (HARD)
#  H1  : Sweep (HARD) + FVG (HARD) + Rejection (HARD)
#         + D1/W1 level (SOFT)
#
#  Instrument-specific parameters from config.py helpers:
#    get_pip(symbol)        — pip size
#    get_pip_value_rm()     — RM value per pip at base lot
#    get_lot(symbol)        — correct lot for 1% risk
#    get_min_fvg(symbol)    — FVG minimum size
#    get_vp_proximity()     — VP zone proximity
#    get_sl_min(symbol)     — minimum SL in pips
#    get_spread_max()       — max spread to allow
#    get_session(symbol)    — trading session hours
# ════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone
from config import *
from ire_logic import (IRE_DEFAULTS, detect_displacement, find_fvg, ire_levels)  # v15

logger = logging.getLogger("KIRA")


class AgentKIRA:

    def __init__(self, mt5_connector):
        self.mt5             = mt5_connector
        self.loss_streak     = 0
        self.win_streak      = 0
        self.confidence_gate = MIN_CONFIDENCE
        self.name            = "KIRA"

    # ── BASE INDICATORS ──────────────────────────────────────

    def _ema(self, series, period):
        if len(series) < period:
            return float(series.iloc[-1]) if len(series) > 0 else 0.0
        return float(series.ewm(span=period, adjust=False).mean().iloc[-1])

    def _rsi(self, series, period=14):
        if len(series) < period + 1:
            return 50.0
        delta    = series.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=period-1, adjust=False).mean().iloc[-1]
        avg_loss = loss.ewm(com=period-1, adjust=False).mean().iloc[-1]
        if avg_loss == 0: return 100.0
        return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

    def _atr(self, df, period=14):
        if df is None or len(df) < period + 1: return 0.0
        h = df["high"]; l = df["low"]; c = df["close"].shift(1)
        tr = pd.concat([df["high"]-df["low"],
                        (df["high"]-c).abs(),
                        (df["low"] -c).abs()], axis=1).max(axis=1)
        return float(tr.ewm(com=period-1, adjust=False).mean().iloc[-1])

    # ── D1 LAYER ─────────────────────────────────────────────

    def _d1_bias(self, d1_df):
        if d1_df is None or len(d1_df) < 50:
            return None, 0, {}
        closes = d1_df["close"]
        price  = float(closes.iloc[-1])
        e50    = self._ema(closes, 50)
        e200   = self._ema(closes, min(200, len(closes)))
        if price > e50 > e200:   direction = "BUY"
        elif price < e50 < e200: direction = "SELL"
        else:                    return None, 0, {"reason":"EMA not aligned"}
        return direction, 0, {"price":round(price,5),
                               "ema50":round(e50,5),
                               "ema200":round(e200,5)}

    def _d1_bos_choch(self, d1_df, direction):
        if d1_df is None or len(d1_df) < 20:
            return 0, "insufficient data"
        highs = d1_df["high"].values; lows = d1_df["low"].values
        n     = len(highs)
        swing_highs, swing_lows = [], []
        for i in range(2, min(25, n-2)):
            idx = n - min(25, n-2) + i
            if idx <= 1 or idx >= n-1: continue
            if highs[idx] > highs[idx-1] and highs[idx] > highs[idx-2]:
                swing_highs.append(highs[idx])
            if lows[idx]  < lows[idx-1]  and lows[idx]  < lows[idx-2]:
                swing_lows.append(lows[idx])
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return 0, "insufficient swings"
        if direction == "SELL":
            if swing_highs[-1] < swing_highs[-2] or swing_lows[-1] < swing_lows[-2]:
                return 8, "BOS bearish confirmed"
        else:
            if swing_highs[-1] > swing_highs[-2] or swing_lows[-1] > swing_lows[-2]:
                return 8, "BOS bullish confirmed"
        return 0, "structure not confirmed"

    def _atr_regime(self, d1_df, symbol="EURUSD"):
        threshold = (ATR_REGIME_THRESH_GOLD if is_gold(symbol)
                     else ATR_REGIME_THRESH)
        if d1_df is None or len(d1_df) < ATR_REGIME_PERIOD + 5:
            return 0, "neutral"
        h = d1_df["high"]; l = d1_df["low"]; c = d1_df["close"].shift(1)
        tr         = pd.concat([d1_df["high"]-d1_df["low"],
                                 (d1_df["high"]-c).abs(),
                                 (d1_df["low"]-c).abs()], axis=1).max(axis=1)
        atr_series = tr.ewm(com=ATR_REGIME_PERIOD-1, adjust=False).mean()
        current    = float(atr_series.iloc[-1])
        avg        = float(atr_series.tail(ATR_REGIME_PERIOD).mean())
        if avg == 0: return 0, "neutral"
        ratio = current / avg
        if ratio < threshold: return -15, f"ATR compressed ({ratio:.2f}×)"
        elif ratio > 1.5:     return  5,  f"ATR expanding ({ratio:.2f}×)"
        return 0, f"ATR normal ({ratio:.2f}×)"

    def _adx(self, df, period=14):
        """Calculate ADX (Average Directional Index) — measures trend strength.
        ADX < 20: no trend / choppy. ADX 20-40: trend present. ADX > 40: strong trend.
        Returns ADX value (0-100). Returns 25 (neutral) if insufficient data."""
        if df is None or len(df) < period * 2 + 5:
            return 25.0  # neutral default
        h = df["high"]; l = df["low"]; pc = df["close"].shift(1)
        # True Range
        tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        # Directional Movement
        up   = h.diff();   down = -l.diff()
        pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0), index=df.index)
        ndm  = pd.Series(np.where((down > up) & (down > 0), down, 0), index=df.index)
        # Smoothed ATR and DM
        atr_s = tr.ewm(com=period-1,  adjust=False).mean()
        pdi   = 100 * pdm.ewm(com=period-1, adjust=False).mean() / atr_s.replace(0, 1)
        ndi   = 100 * ndm.ewm(com=period-1, adjust=False).mean() / atr_s.replace(0, 1)
        # ADX
        dx    = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, 1)
        adx   = dx.ewm(com=period-1, adjust=False).mean()
        return round(float(adx.iloc[-1]), 1)

    # ── H4 LAYER ─────────────────────────────────────────────

    def _h4_vp_zone(self, h4_df, direction, symbol="EURUSD",
                    periods=80, levels=50):
        # Gold and GBPJPY use shorter lookback and percentage-based proximity
        if is_gold(symbol):
            periods = VP_LOOKBACK_GOLD
        elif is_gbpjpy(symbol):
            periods = VP_LOOKBACK_GBPJPY
        proximity = get_vp_proximity(symbol)
        pip       = get_pip(symbol)

        if h4_df is None or len(h4_df) < 20:
            return False, 0.0, {}
        recent     = h4_df.tail(min(periods, len(h4_df)))
        price_min  = float(recent["low"].min())
        price_max  = float(recent["high"].max())
        total_range= price_max - price_min
        if total_range == 0: return False, 0.0, {}

        p_levels   = np.linspace(price_min, price_max, levels)
        vol_prof   = np.zeros(levels)
        for _, c in recent.iterrows():
            for j, p in enumerate(p_levels):
                if c["low"] <= p <= c["high"]:
                    vol_prof[j] += c.get("volume", 1)

        if vol_prof.sum() == 0: return False, 0.0, {}
        poc_idx    = int(np.argmax(vol_prof))
        poc        = round(float(p_levels[poc_idx]), 5)
        total_vol  = vol_prof.sum()
        si         = np.argsort(vol_prof)[::-1]
        va_vol     = 0.0; va_idx = []
        for idx in si:
            va_vol += vol_prof[idx]; va_idx.append(int(idx))
            if va_vol >= total_vol * 0.70: break
        vah        = round(float(p_levels[max(va_idx)]), 5)
        val        = round(float(p_levels[min(va_idx)]), 5)
        current    = float(h4_df["close"].iloc[-1])

        # Gold, GBPJPY and other JPY pairs use percentage-based proximity (scales with price)
        # EURJPY at 160: 0.5% = 80 pips (v3 used vp_prox_pct=0.5 for EURJPY)
        # Fixed 15-pip proximity is far too loose for a 160-price instrument
        if is_gold(symbol):
            proximity = int(current * VP_PROXIMITY_GOLD_PCT / 100 / pip)
        elif is_gbpjpy(symbol):
            proximity = int(current * VP_PROXIMITY_GBPJPY_PCT / 100 / pip)
        elif is_jpy(symbol):
            proximity = int(current * 0.5 / 100 / pip)  # 0.5% — matches v3 EURJPY profile
        
        near_poc   = abs(current - poc) < pip * proximity
        near_vah   = abs(current - vah) < pip * proximity
        near_val   = abs(current - val) < pip * proximity
        zone_active= near_poc or near_vah or near_val

        if direction == "SELL":
            cands = [x for x in [val, poc] if x < current - pip*5]
            vp_tp = min(cands) if cands else round(current - pip*(proximity*2), 5)
        else:
            cands = [x for x in [vah, poc] if x > current + pip*5]
            vp_tp = max(cands) if cands else round(current + pip*(proximity*2), 5)

        return zone_active, round(vp_tp, 5), {
            "poc":poc,"vah":vah,"val":val,
            "near_poc":near_poc,"near_vah":near_vah,"near_val":near_val}

    # ── H1 LAYER ─────────────────────────────────────────────

    def _h1_liquidity_sweep(self, h1_df, direction, lookback=20):
        if h1_df is None or len(h1_df) < lookback + 3: return False, 0.0, {}
        swing  = h1_df.iloc[-(lookback+5):-5]
        recent = h1_df.iloc[-5:]
        if len(swing) < 5: return False, 0.0, {}
        if direction == "SELL":
            sh = float(swing["high"].max())
            for i in range(len(recent)):
                c = recent.iloc[i]
                if c["high"] > sh and c["close"] < sh:
                    return True, round(sh, 5), {
                        "swing_level":round(sh,5),
                        "sweep_to":round(float(c["high"]),5)}
        else:
            sl = float(swing["low"].min())
            for i in range(len(recent)):
                c = recent.iloc[i]
                if c["low"] < sl and c["close"] > sl:
                    return True, round(sl, 5), {
                        "swing_level":round(sl,5),
                        "sweep_to":round(float(c["low"]),5)}
        return False, 0.0, {}

    def _h1_fvg(self, h1_df, direction, symbol="EURUSD", lookback=15):
        min_pips = get_min_fvg(symbol)
        pip      = get_pip(symbol)
        if h1_df is None or len(h1_df) < 10: return False, 0.0, 0.0, {}
        current  = float(h1_df["close"].iloc[-1])
        scan     = h1_df.iloc[-lookback-3:-1]
        fvgs     = []
        for i in range(len(scan)-2):
            c1 = scan.iloc[i]; c3 = scan.iloc[i+2]
            if direction == "SELL" and c1["low"] > c3["high"]:
                size = (c1["low"] - c3["high"]) / pip
                if size >= min_pips:
                    fvgs.append({"fvg_high":round(float(c1["low"]),5),
                                  "fvg_low":round(float(c3["high"]),5),
                                  "midpoint":round((c1["low"]+c3["high"])/2,5),
                                  "size_pips":round(size,1)})
            elif direction == "BUY" and c1["high"] < c3["low"]:
                size = (c3["low"] - c1["high"]) / pip
                if size >= min_pips:
                    fvgs.append({"fvg_high":round(float(c3["low"]),5),
                                  "fvg_low":round(float(c1["high"]),5),
                                  "midpoint":round((c3["low"]+c1["high"])/2,5),
                                  "size_pips":round(size,1)})
        if not fvgs: return False, 0.0, 0.0, {}
        for fvg in reversed(fvgs):
            if direction == "SELL":
                ok = fvg["fvg_low"] <= current <= fvg["fvg_high"]*1.002
                approx = abs(current - fvg["fvg_low"]) < pip*10
            else:
                ok = fvg["fvg_low"]*0.998 <= current <= fvg["fvg_high"]
                approx = abs(current - fvg["fvg_high"]) < pip*10
            if ok or approx:
                return True, fvg["fvg_high"], fvg["fvg_low"], fvg
        return False, 0.0, 0.0, {}

    def _h1_rejection_candle(self, h1_df, direction, lookback=5):
        if h1_df is None or len(h1_df) < 3: return False, "", {}
        recent = h1_df.iloc[-lookback:]
        for i in range(len(recent)-1, -1, -1):
            c  = recent.iloc[i]
            tr = float(c["high"] - c["low"])
            if tr == 0: continue
            body = abs(float(c["close"] - c["open"]))
            uw   = float(c["high"]) - max(float(c["open"]),float(c["close"]))
            lw   = min(float(c["open"]),float(c["close"])) - float(c["low"])
            uw_r = uw/tr; lw_r = lw/tr; br = body/tr
            if direction == "SELL":
                if uw_r >= 0.55 and c["close"] < c["open"]:
                    return True, "bearish_pin_bar", {"wick_ratio":round(uw_r,2)}
                if i > 0:
                    prev = recent.iloc[i-1]
                    if (c["close"] < c["open"] and br >= 0.65 and
                            c["open"] >= prev["close"] and c["close"] <= prev["open"]):
                        return True, "bearish_engulfing", {"body_ratio":round(br,2)}
                if c["close"] < c["open"] and br >= 0.70 and uw_r < 0.15:
                    return True, "strong_bearish", {"body_ratio":round(br,2)}
            else:
                if lw_r >= 0.55 and c["close"] > c["open"]:
                    return True, "bullish_pin_bar", {"wick_ratio":round(lw_r,2)}
                if i > 0:
                    prev = recent.iloc[i-1]
                    if (c["close"] > c["open"] and br >= 0.65 and
                            c["open"] <= prev["close"] and c["close"] >= prev["open"]):
                        return True, "bullish_engulfing", {"body_ratio":round(br,2)}
                if c["close"] > c["open"] and br >= 0.70 and lw_r < 0.15:
                    return True, "strong_bullish", {"body_ratio":round(br,2)}
        return False, "", {}

    def _d1_w1_level_boost(self, d1_df, w1_df, direction, sweep_level, symbol):
        pip   = get_pip(symbol)
        boost = 0; reason = ""
        if d1_df is not None and len(d1_df) >= 2:
            prev = d1_df.iloc[-2]
            if direction == "SELL":
                if abs(sweep_level - float(prev["high"])) < pip * 5:
                    boost += 8; reason = f"Sweep at prev D1 high {round(float(prev['high']),5)}"
            else:
                if abs(sweep_level - float(prev["low"])) < pip * 5:
                    boost += 8; reason = f"Sweep at prev D1 low {round(float(prev['low']),5)}"
        if w1_df is not None and len(w1_df) >= 2:
            prev = w1_df.iloc[-2]
            if direction == "SELL":
                if abs(sweep_level - float(prev["high"])) < pip * 8:
                    boost += 8; reason += f" + W1 high"
            else:
                if abs(sweep_level - float(prev["low"])) < pip * 8:
                    boost += 8; reason += f" + W1 low"
        return min(boost, 15), reason

    def _in_session(self, symbol, now_dt=None):
        """
        Session gate v2 — per-symbol refined rules from 3yr backtest.

        Backtest finding (97 signals, 2022-2026):
          London_Open  45 sigs | WR 67% | +RM1027  ✅
          NY_Open      12 sigs | WR 58% | +RM124   ✅
          NY_PM        18 sigs | WR 39% | +RM71    ⚠️  (AUDUSD 17% WR -RM89 → blocked)
          Other        22 sigs | WR 23% | -RM64    ❌  (EURUSD/EURJPY → blocked)

        Impact of per-symbol blocks: -27 trades, +RM210 net, DD 18.2%→14.1%
        """
        now     = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)
        h       = now.hour
        weekday = now.weekday()

        if weekday >= 5: return False   # Saturday / Sunday
        if weekday == 4: return False   # Friday — 0% WR in 3yr backtest

        s_start, s_end = get_session(symbol)
        if not (s_start <= h < s_end): return False

        # Session bucket
        if   LONDON_KZ_START <= h < LONDON_KZ_END:  sess = "London_Open"
        elif NY_KZ_START     <= h < NY_KZ_END:       sess = "NY_Open"
        elif NY_PM_KZ_START  <= h < NY_PM_KZ_END:    sess = "NY_PM"
        else:                                         sess = "Other"

        # Per-symbol session blocks (backtest-driven)
        if symbol == "EURUSD" and sess == "Other":
            logger.debug("EURUSD: blocked Other session (15% WR backtest)")
            return False
        if symbol == "EURJPY" and sess == "Other":
            logger.debug("EURJPY: blocked Other session (0% WR backtest)")
            return False
        if symbol == "AUDUSD" and sess == "NY_PM":
            logger.debug("AUDUSD: blocked NY_PM session (17% WR backtest)")
            return False

        return True

    def _calculate_levels(self, direction, entry, sweep_level,
                           fvg_h, fvg_l, vp_tp, symbol):
        pip      = get_pip(symbol)
        sl_min   = get_sl_min(symbol)
        lot      = get_lot(symbol)
        pip_val  = get_pip_value_rm(symbol) * (lot / (LOT_GOLD if is_gold(symbol)
                                                else LOT_JPY if is_jpy(symbol)
                                                else LOT_FOREX))

        if direction == "SELL":
            sl      = round(sweep_level + pip*3, 5)
            sl_pips = round((sl - entry) / pip, 1)
            if sl_pips < sl_min:
                sl = round(entry + pip*sl_min, 5); sl_pips = float(sl_min)
            tp = (vp_tp if vp_tp > 0 and vp_tp < entry
                  else round(entry - pip*sl_min*3, 5))
            tp_pips = round((entry - tp) / pip, 1)
            if tp_pips < sl_pips * MIN_RR:
                tp = round(entry - pip*sl_pips*MIN_RR, 5)
                tp_pips = round(sl_pips * MIN_RR, 1)
        else:
            sl      = round(sweep_level - pip*3, 5)
            sl_pips = round((entry - sl) / pip, 1)
            if sl_pips < sl_min:
                sl = round(entry - pip*sl_min, 5); sl_pips = float(sl_min)
            tp = (vp_tp if vp_tp > 0 and vp_tp > entry
                  else round(entry + pip*sl_min*3, 5))
            tp_pips = round((tp - entry) / pip, 1)
            if tp_pips < sl_pips * MIN_RR:
                tp = round(entry + pip*sl_pips*MIN_RR, 5)
                tp_pips = round(sl_pips * MIN_RR, 1)

        rr = round(tp_pips/sl_pips, 2) if sl_pips > 0 else MIN_RR

        # Cap R:R at MAX_RR — 3yr backtest: R:R >3.5 net -RM201, R:R 2.5-3.0 net +RM395
        # High R:R targets are unreachable — price reverses before TP hit
        if rr > MAX_RR:
            if direction == "SELL":
                tp      = round(entry - pip*sl_pips*MAX_RR, 5)
            else:
                tp      = round(entry + pip*sl_pips*MAX_RR, 5)
            tp_pips = round(sl_pips * MAX_RR, 1)
            rr      = MAX_RR

        risk_rm   = round(sl_pips  * pip_val, 2)
        profit_rm = round(tp_pips  * pip_val, 2)
        return {"entry":entry,"sl":sl,"tp":tp,
                "sl_pips":round(sl_pips,1),"tp_pips":round(tp_pips,1),
                "risk_rm":risk_rm,"profit_rm":profit_rm,"rr":rr}


    # ════════════════════════════════════════════════════════════
    #  GOLD VOLATILITY ENGINE (GVE)
    #  Session-Based Liquidity Expansion for XAUUSD
    #
    #  Architecture (6 layers per GPT + research validation):
    #    Layer 0 — Volatility Regime (ATR percentile + ADR + news)
    #    Layer 1 — D1 Macro Bias (EMA 50/200 only)
    #    Layer 2 — Session Gate (London Open + NY Open windows only)
    #    Layer 3 — Liquidity Pool Detection (Asian/session range)
    #    Layer 4 — Sweep Detection (M15 fake breakout confirmation)
    #    Layer 5 — Expansion Confirmation (displacement candle)
    #    Layer 6 — Dynamic ATR Exit (no fixed TP — trail on momentum)
    #
    #  Called by: analyse() when is_gold(symbol) == True
    #  Returns:   same brief format as _analyse_forex() — ORACLE unchanged
    # ════════════════════════════════════════════════════════════

    # ── GVE LAYER 0: VOLATILITY REGIME ───────────────────────

    def _gve_regime(self, m15_df, h1_df, d1_df, nova_brief=None):
        """
        Classify Gold volatility regime.
        Returns: (regime, reason)
          NORMAL    — engine runs fully
          EXPANSION — engine runs, reduced confidence
          EXTREME   — no trade (news event or ATR spike)
          DEAD      — no trade (compressed / no movement)
        """
        if m15_df is None or len(m15_df) < GVE_ATR_PERIOD + 5:
            return "NORMAL", "insufficient data — default NORMAL"

        # ── ATR percentile on M15 ──
        h = m15_df["high"]; l = m15_df["low"]; pc = m15_df["close"].shift(1)
        tr_m15 = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        atr_series = tr_m15.ewm(com=GVE_ATR_PERIOD-1, adjust=False).mean()
        current_atr = float(atr_series.iloc[-1])
        avg_atr     = float(atr_series.tail(GVE_ATR_PERIOD).mean())
        if avg_atr == 0:
            return "NORMAL", "ATR avg zero — default NORMAL"
        atr_ratio = current_atr / avg_atr

        # ── ADR consumption check (daily range already extended?) ──
        if d1_df is not None and len(d1_df) >= 20:
            today_range = float(d1_df["high"].iloc[-1] - d1_df["low"].iloc[-1])
            adr_20      = float((d1_df["high"] - d1_df["low"]).tail(20).mean())
            adr_used    = today_range / adr_20 if adr_20 > 0 else 0
        else:
            adr_used = 0

        # ── News check via NOVA brief (if passed) ──
        news_extreme = (nova_brief is not None and
                        nova_brief.get("verdict") in ["BLACKOUT", "EXTREME"])

        # ── Classify ──
        if news_extreme:
            return "EXTREME", "High-impact news event active"
        if atr_ratio > GVE_ATR_EXTREME:
            return "EXTREME", f"ATR spike {atr_ratio:.1f}x avg — Gold in panic/expansion"
        if adr_used > GVE_ADR_MAX_PCT:
            return "EXTREME", f"Daily range {adr_used*100:.0f}% consumed — already extended"
        if atr_ratio < GVE_ATR_COMPRESS:
            return "DEAD", f"ATR compressed {atr_ratio:.2f}x — no energy building"
        if 1.5 <= atr_ratio <= GVE_ATR_EXTREME:
            return "EXPANSION", f"ATR expanding {atr_ratio:.1f}x — active but elevated"
        return "NORMAL", f"ATR {atr_ratio:.2f}x — normal conditions"

    # ── GVE LAYER 2: SESSION GATE ─────────────────────────────

    def _gve_in_session(self, now_dt=None):
        """GVE London Open only.
        v11 data: London 73.3% WR +RM1128 vs NY 50% WR -RM147 on 56 signals.
        NY Open consistently net negative across all GVE versions — blocked.
        Re-enable NY by restoring the in_ny check after 30+ live signals confirm.
        now_dt: pass candle timestamp in backtest, leave None for live trading.
        """
        now = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)
        h   = now.hour
        in_london = GVE_LONDON_START <= h < GVE_LONDON_END   # 07:00–09:00 UTC
        if in_london: return True, "London_Open"
        return False, "outside GVE London window"

    # ── GVE LAYER 3: LIQUIDITY POOL DETECTION ────────────────

    def _gve_liquidity_pools(self, m15_df, h1_df, now_dt=None):
        """
        Identify key liquidity pools:
          - Asian session range high/low (00:00–07:00 UTC)
          - Previous day high/low
          - Recent swing highs/lows on M15
        Returns dict of levels with labels.
        """
        pools   = {}
        pip     = get_pip(symbol)
        now_utc = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)

        # ── Previous day high/low ──
        if h1_df is not None and len(h1_df) >= 30:
            today = now_utc.date()
            prev    = h1_df[h1_df["time"].dt.date < today].tail(24)
            if len(prev) >= 4:
                pools["prev_day_high"] = round(float(prev["high"].max()), 2)
                pools["prev_day_low"]  = round(float(prev["low"].min()),  2)

        # ── Asian session range (00:00–07:00 UTC today) ──
        if m15_df is not None and len(m15_df) >= 10:
            asian_m15 = m15_df[
                (m15_df["time"].dt.date == now_utc.date()) &
                (m15_df["time"].dt.hour <  7)
            ]
            if len(asian_m15) >= 4:
                pools["asian_high"] = round(float(asian_m15["high"].max()), 2)
                pools["asian_low"]  = round(float(asian_m15["low"].min()),  2)

        # ── Recent M15 swing highs/lows (last 20 candles) ──
        if m15_df is not None and len(m15_df) >= 10:
            recent = m15_df.tail(min(GVE_SWEEP_LOOKBACK, len(m15_df)))
            pools["swing_high"] = round(float(recent["high"].max()), 2)
            pools["swing_low"]  = round(float(recent["low"].min()),  2)

        return pools

    # ── GVE LAYER 4: SWEEP DETECTION ─────────────────────────

    def _gve_sweep(self, m15_df, pools, direction):
        """
        Detect liquidity sweep on M15:
          - Price spikes through a pool level
          - CLOSES back inside range (fake breakout = institutional trap)
          - Sweep size >= GVE_MIN_SWEEP_PIPS
        This is the core GVE trigger — removes enormous noise.
        Returns: (swept, level_swept, sweep_size_pips, pool_label)
        """
        if m15_df is None or len(m15_df) < 5 or not pools:
            return False, 0.0, 0, ""
        pip = get_pip(symbol)

        # Check last 5 M15 candles for a sweep
        recent = m15_df.tail(5)
        for _, c in recent.iloc[::-1].iterrows():
            for label, level in pools.items():
                if level == 0: continue
                sweep_size = 0
                swept      = False

                if direction == "SELL" and "high" in label or "high" in label:
                    # BUY setup: sweep LOW (trap sellers below support)
                    if direction == "BUY":
                        if c["low"] < level and c["close"] > level:
                            sweep_size = round((level - c["low"]) / pip, 1)
                            if sweep_size >= GVE_MIN_SWEEP_PIPS:
                                swept = True

                if direction == "SELL":
                    # SELL setup: sweep HIGH (trap buyers above resistance)
                    if "high" in label or "swing" in label:
                        if c["high"] > level and c["close"] < level:
                            sweep_size = round((c["high"] - level) / pip, 1)
                            if sweep_size >= GVE_MIN_SWEEP_PIPS:
                                swept = True

                if swept:
                    return True, round(level, 2), sweep_size, label

        return False, 0.0, 0, ""

    # ── GVE LAYER 5: EXPANSION CONFIRMATION ──────────────────

    def _gve_expansion(self, m15_df, direction):
        """
        Confirm expansion after sweep:
          - ATR expanding (current M15 ATR > recent avg)
          - Displacement candle: body > 55% of candle range
          - Momentum in correct direction
        Grades the setup quality for dynamic R:R assignment.
        Returns: (confirmed, grade, reason)
          Grade A+ — strong displacement, ATR expanding
          Grade B  — normal rejection
          Grade C  — marginal
        """
        if m15_df is None or len(m15_df) < 10:
            return False, "C", "insufficient M15 data"
        pip    = get_pip(symbol)
        recent = m15_df.tail(5)

        # ATR expansion check on M15
        h = m15_df["high"]; l = m15_df["low"]; pc = m15_df["close"].shift(1)
        tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        atr_now = float(tr.ewm(com=13, adjust=False).mean().iloc[-1])
        atr_avg = float(tr.ewm(com=13, adjust=False).mean().tail(20).mean())
        atr_expanding = atr_now > atr_avg * 1.1

        # Displacement candle check (last 3 M15 candles)
        best_grade = "C"; best_reason = ""
        for i in range(len(recent)-1, max(len(recent)-4, -1), -1):
            c  = recent.iloc[i]
            tr_c = float(c["high"] - c["low"])
            if tr_c == 0: continue
            body = abs(float(c["close"] - c["open"]))
            body_ratio = body / tr_c
            uw = float(c["high"]) - max(float(c["open"]), float(c["close"]))
            lw = min(float(c["open"]), float(c["close"])) - float(c["low"])

            correct_direction = (
                (direction == "BUY"  and c["close"] > c["open"]) or
                (direction == "SELL" and c["close"] < c["open"])
            )
            if not correct_direction: continue

            if body_ratio >= GVE_SWEEP_BODY_MIN:
                if atr_expanding and body_ratio >= 0.75:
                    # Grade A: strong displacement + confirmed ATR expansion
                    # Requires body >= 75% of range AND ATR clearly expanding
                    best_grade  = "A"
                    best_reason = (f"A+ displacement {body_ratio:.0%} body + "
                                   f"ATR {atr_now/atr_avg:.1f}x expanding")
                elif body_ratio >= 0.65 or (atr_expanding and body_ratio >= 0.60):
                    # Grade B: strong body OR moderate body with ATR support
                    if best_grade not in ["A"]:
                        best_grade  = "B"
                        best_reason = (f"B displacement {body_ratio:.0%} body"
                                       + (" ATR+" if atr_expanding else ""))
                else:
                    # Grade C: minimum threshold met — marginal setup
                    if best_grade not in ["A","B"]:
                        best_grade  = "C"
                        best_reason = f"C marginal {body_ratio:.0%} body"

        if best_grade == "C" and not best_reason:
            return False, "C", "no displacement candle detected"

        return True, best_grade, best_reason

    # ── GVE LAYER 6: DYNAMIC ATR LEVELS ──────────────────────

    def _gve_levels(self, direction, entry, sweep_level,
                    h1_atr, grade, symbol="XAUUSD"):
        """
        ATR-adaptive SL/TP — no fixed pip targets.
        SL  = 1.5× H1 ATR (adapts to current volatility)
        TP  = grade-based ATR multiplier (A=3.0, B=2.0, C=1.5)
        TP is a GUIDE — live system uses ATR trailing exit, not fixed TP.
        For backtest compatibility a TP is returned but marked as trail target.
        """
        pip     = get_pip(symbol)
        lot     = get_lot(symbol)
        pip_val = get_pip_value_rm(symbol) * (lot / LOT_GOLD)

        # SL = max(1.5×ATR, 0.8% of price)
        # 0.8% floor prevents noise-wipeout when ATR is compressed
        # At $1800 Gold: min=$14.4 | At $4400: min=$35.2
        # ATR-based dominates at normal/high volatility (active sessions)
        sl_from_atr   = h1_atr * GVE_SL_ATR_MULT          # price units
        sl_from_price = entry * GVE_SL_PRICE_PCT            # 0.8% of price floor
        sl_usd        = max(sl_from_atr, sl_from_price)    # take larger (noise protection)
        sl_usd        = min(sl_usd, GVE_MAX_SL_USD)        # hard cap at $25 — max RM99.5 risk
        sl_pips       = round(sl_usd / pip, 1)             # convert to pips

        # Grade-based TP multiplier
        tp_mult = (GVE_TP_ATR_MULT_A if grade == "A" else
                   GVE_TP_ATR_MULT_B if grade == "B" else
                   GVE_TP_ATR_MULT_C)
        tp_pips = round(sl_pips * tp_mult, 1)
        rr      = round(tp_pips / sl_pips, 2) if sl_pips > 0 else tp_mult

        if direction == "SELL":
            sl = round(entry + pip * sl_pips, 2)
            tp = round(entry - pip * tp_pips, 2)
        else:
            sl = round(entry - pip * sl_pips, 2)
            tp = round(entry + pip * tp_pips, 2)

        risk_rm   = round(sl_pips * pip_val, 2)
        profit_rm = round(tp_pips * pip_val, 2)

        return {
            "entry":      entry,
            "sl":         sl,
            "tp":         tp,
            "sl_pips":    round(sl_pips, 1),
            "tp_pips":    round(tp_pips, 1),
            "risk_rm":    risk_rm,
            "profit_rm":  profit_rm,
            "rr":         rr,
            "tp_mode":    "ATR_TRAIL",   # live system uses trailing, not fixed TP
            "sl_atr_used": round(h1_atr, 2),
            "tp_mult":    tp_mult,
        }

    # ── GVE MAIN PIPELINE ─────────────────────────────────────

    def _analyse_gold(self, symbol, candles, tick, nova_brief=None, now_dt=None):
        """
        Gold Volatility Engine — 6-layer pipeline.
        Called by analyse() when is_gold(symbol).
        Returns same brief format as _analyse_forex() for ORACLE compatibility.
        """
        d1_df  = candles.get("D1")
        h4_df  = candles.get("H4")
        h1_df  = candles.get("H1")
        m15_df = candles.get("M15")
        w1_df  = candles.get("W1")

        # ── LAYER 0: VOLATILITY REGIME ──
        regime, regime_reason = self._gve_regime(m15_df, h1_df, d1_df, nova_brief)
        if regime in ["EXTREME", "DEAD"]:
            logger.debug(f"{symbol} GVE: {regime} — {regime_reason}")
            return None

        # ── LAYER 2: SESSION GATE (hard) ──
        in_session, session_name = self._gve_in_session(now_dt=now_dt)
        if not in_session:
            logger.debug(f"{symbol} GVE: outside session windows")
            return None

        # ── LAYER 1: D1 MACRO BIAS ──
        direction, _, d1_inds = self._d1_bias(d1_df)
        if direction is None:
            logger.debug(f"{symbol} GVE: D1 EMA not aligned")
            return None

        # SELL disabled for XAUUSD GVE — Gold secular bull 2022-2026
        # XAGUSD: also BUY-only for GVE initial deployment (Silver follows Gold bias)
        if direction == "SELL":
            logger.debug(f"{symbol} GVE: SELL disabled — secular bull trend")
            return None

        # ── H4 EMA SLOPE FILTER ──
        # H4 EMA50 must be rising (slope > 0) for BUY signals
        # Blocks: 2026 Gold correction (declining H4 EMA50)
        #         2023 ranging Gold (flat H4 EMA50)
        # Research: EMA slope reacts faster than ADX on Gold (MQL5 forum validated)
        if h4_df is not None and len(h4_df) >= GVE_H4_EMA_SLOPE_PERIOD + 5:
            h4_ema50      = h4_df["close"].ewm(span=50, adjust=False).mean()
            slope_now     = float(h4_ema50.iloc[-1])
            slope_past    = float(h4_ema50.iloc[-(GVE_H4_EMA_SLOPE_PERIOD+1)])
            h4_slope      = slope_now - slope_past   # price units over 10 H4 candles
            if h4_slope <= 0:
                logger.debug(f"{symbol} GVE: H4 EMA50 slope {h4_slope:.2f} <= 0 — declining/flat trend")
                return None

        # ── LAYER 3: LIQUIDITY POOL DETECTION ──
        pools = self._gve_liquidity_pools(m15_df, h1_df, now_dt=now_dt)
        if not pools:
            logger.debug(f"{symbol} GVE: no liquidity pools identified")
            return None

        # ── LAYER 4: SWEEP DETECTION (core trigger) ──
        swept, sweep_level, sweep_pips, pool_label = self._gve_sweep(
            m15_df, pools, direction)
        if not swept:
            logger.debug(f"{symbol} GVE: no liquidity sweep detected")
            return None

        # ── LAYER 5: EXPANSION CONFIRMATION ──
        expanded, grade, expand_reason = self._gve_expansion(m15_df, direction)
        if not expanded:
            logger.debug(f"{symbol} GVE: no expansion confirmation — {expand_reason}")
            return None

        # ── H1 ATR for dynamic SL/TP ──
        h1_atr = self._atr(h1_df, period=14)
        if h1_atr == 0:
            logger.debug(f"{symbol} GVE: H1 ATR is zero")
            return None



        # ── ADX REGIME FILTER ──
        # ADX < 20 = no directional trend = choppy/ranging = skip
        # Directly addresses 2023 ranging Gold losses (Gold at $1800-2050, flat EMAs)
        h1_adx = self._adx(h1_df, period=GVE_ADX_PERIOD)
        if h1_adx < GVE_ADX_MIN:
            logger.debug(f"{symbol} GVE: ADX {h1_adx:.1f} < {GVE_ADX_MIN} — no trend direction")
            return None

        # ── RELATIVE VOLUME FILTER ──
        # Sweep must have above-average participation (real institutional activity)
        # Fake sweeps: quick spike, low volume, immediate reversal
        # Real sweeps: volume expands as price moves through liquidity
        if m15_df is not None and len(m15_df) >= 22:
            vol_series   = m15_df["volume"].tail(22)
            current_vol  = float(vol_series.iloc[-1])
            avg_vol      = float(vol_series.iloc[:-1].mean())
            rel_vol      = current_vol / avg_vol if avg_vol > 0 else 1.0
            # Only filter if threshold > 0 — disabled on MetaQuotes Demo (unreliable tick vol)
            # Re-enable after collecting 30+ live trades from real broker
            if GVE_REL_VOL_THRESH > 0 and rel_vol < GVE_REL_VOL_THRESH:
                logger.debug(f"{symbol} GVE: rel_vol {rel_vol:.2f} < {GVE_REL_VOL_THRESH}")
                return None
        else:
            rel_vol = 1.0

        # ── CONFIDENCE SCORING ──
        confidence = GVE_MIN_CONFIDENCE    # base 60

        # Regime adjustment
        if regime == "EXPANSION": confidence -= 10   # active but elevated — reduce
        if regime == "NORMAL":    confidence += 5    # clean conditions

        # Grade boost
        if grade == "A":   confidence += 20
        elif grade == "B": confidence += 10

        # Session quality boost
        if session_name == "NY_Open":     confidence += 8   # highest probability window
        elif session_name == "London_Open": confidence += 5

        # Pool quality boost — stronger level = more reliable sweep
        if "prev_day" in pool_label:  confidence += 8
        elif "asian"  in pool_label:  confidence += 5

        # Sweep size boost — larger sweep = cleaner liquidity grab
        if sweep_pips >= 200: confidence += 8
        elif sweep_pips >= 120: confidence += 4

        # Relative volume boost — high participation = stronger conviction
        if rel_vol >= 3.0:   confidence += 10  # very strong institutional activity
        elif rel_vol >= 2.5: confidence += 6
        elif rel_vol >= 1.8: confidence += 3   # minimum threshold already passed

        confidence = min(95, max(GVE_MIN_CONFIDENCE, confidence))

        # Grade label — Grade C blocked in GVE
        # Backtest: Grade C 10 sigs, 40% WR, -RM215 — marginal setups with large SL
        grade_label = ("A" if confidence >= GRADE_A_CONF else
                       "B" if confidence >= GRADE_B_CONF else "C")
        if grade_label == "C":
            logger.debug(f"{symbol} GVE: Grade C blocked — insufficient signal quality")
            return None

        # NY Open requires Grade A only
        # Data: London Grade B profitable, NY Grade B estimated negative (~44% WR)
        # London Open: keep both Grade A + B (both profitable, 66% WR overall)
        if session_name == "NY_Open" and grade_label == "B":
            logger.debug(f"{symbol} GVE: NY Open Grade B blocked — requires Grade A")
            return None

        # ── LAYER 6: DYNAMIC ATR LEVELS ──
        entry  = float(m15_df["close"].iloc[-1])
        levels = self._gve_levels(direction, entry, sweep_level,
                                   h1_atr, grade, symbol)

        if levels["rr"] < GVE_MIN_RR:   # GVE uses 1.5 minimum (live system trails ATR)
            logger.debug(f"{symbol} GVE: R:R {levels['rr']} < GVE min {GVE_MIN_RR}")
            return None

        kira_score = min(100, int(confidence + min(10, (levels["rr"] - 2.0) * 4)))
        lot        = get_lot(symbol)

        brief = {
            # ── Standard fields (ORACLE compatible) ──
            "agent":          "KIRA",
            "symbol":         symbol,
            "direction":      direction,
            "grade":          grade_label,
            "confidence":     confidence,
            "kira_score":     kira_score,
            "entry":          levels["entry"],
            "sl":             levels["sl"],
            "tp":             levels["tp"],
            "sl_pips":        levels["sl_pips"],
            "tp_pips":        levels["tp_pips"],
            "lot_size":       lot,
            "risk_rm":        levels["risk_rm"],
            "profit_rm":      levels["profit_rm"],
            "rr":             levels["rr"],
            "spread":         tick["spread"],
            "rsi_h1":         self._rsi(h1_df["close"]) if h1_df is not None else 50.0,
            "rsi_h4":         self._rsi(h4_df["close"]) if h4_df is not None else 50.0,
            "atr":            h1_atr,
            "d1_direction":   direction,
            "instrument_type": "gold_gve",
            "timestamp":      datetime.now(tz=timezone.utc).isoformat(),
            # ── GVE-specific fields ──
            "gve_regime":     regime,
            "gve_regime_rsn": regime_reason,
            "gve_session":    session_name,
            "gve_pool_label": pool_label,
            "gve_sweep_level":sweep_level,
            "gve_sweep_pips": sweep_pips,
            "gve_rel_vol":    round(rel_vol, 2),
            "gve_h1_adx":     round(h1_adx, 1),
            "gve_grade":      grade,
            "gve_expand_rsn": expand_reason,
            "gve_tp_mode":    "PARTIAL_THEN_TRAIL",
            "gve_sl_atr":     levels["sl_atr_used"],
            "gve_tp_mult":    levels["tp_mult"],
            # ── Dummy fields for ORACLE/ATLAS compatibility ──
            "d1_bos_boost":   0,
            "d1_bos_reason":  "GVE — no BOS filter",
            "atr_regime_adj": 0,
            "atr_regime_rsn": regime_reason,
            "vp_poc":         0,
            "vp_vah":         0,
            "vp_val":         0,
            "vp_tp":          levels["tp"],
            "smc_sweep":      True,
            "smc_fvg":        False,    # GVE uses sweep, not FVG
            "smc_rejection":  True,
            "sweep_level":    sweep_level,
            "fvg_high":       0,
            "fvg_low":        0,
            "fvg_size_pips":  0,
            "rejection_type": f"gve_{grade.lower()}_sweep",
            "kz_name":        session_name,
            "kz_boost":       0,
            "level_boost":    0,
            "level_reason":   pool_label,
        }

        logger.info(
            f"KIRA GVE: {direction} XAUUSD Grade-{grade_label} "
            f"{confidence}% Score:{kira_score} | "
            f"Regime:{regime} Session:{session_name} | "
            f"Pool:{pool_label} Sweep:{sweep_pips}pip | "
            f"SL:{levels['sl_pips']}pip TP:{levels['tp_pips']}pip "
            f"R:R 1:{levels['rr']} ATR:{h1_atr:.1f}"
        )
        return brief

    # ════════════════════════════════════════════════════════════
    #  REGIME CLASSIFIER
    #  Reads D1 + H4 market state and returns a regime label.
    #  KIRA's analyse() calls this first — decides which engine fires.
    #
    #  Regimes:
    #    TRENDING     — ADX>25, EMA stacked, ATR normal/expanding  → Continuation
    #    WEAK_TREND   — ADX 20-25, partial EMA alignment           → Continuation (penalised)
    #    EXPANDING    — ATR ratio >1.5× avg, any direction         → Continuation / GVE
    #    RANGING      — ADX<20, EMAs flat, ATR compressed          → MRE (future)
    #    COMPRESSING  — ADX<15, ATR <0.7× avg, coiling            → CBE (future)
    #    UNKNOWN      — insufficient data                          → no trade
    # ════════════════════════════════════════════════════════════

    def _classify_regime(self, symbol, d1_df, h4_df):
        """
        Returns (regime_label, adx, atr_ratio, details_dict).
        Uses D1 ADX + ATR ratio + EMA structure.
        Data already fetched — no extra MT5 calls needed.
        """
        if d1_df is None or len(d1_df) < 30:
            return "UNKNOWN", 0.0, 1.0, {"reason": "insufficient D1 data"}

        closes = d1_df["close"]
        highs  = d1_df["high"]
        lows   = d1_df["low"]

        # ── ADX (14-period) ──────────────────────────────────
        period = 14
        if len(d1_df) < period + 5:
            adx = 20.0
        else:
            high_s = highs.values; low_s = lows.values; close_s = closes.values
            plus_dm = []; minus_dm = []; tr_list = []
            for i in range(1, len(high_s)):
                h_diff = high_s[i]  - high_s[i-1]
                l_diff = low_s[i-1] - low_s[i]
                plus_dm.append(h_diff if h_diff > l_diff and h_diff > 0 else 0)
                minus_dm.append(l_diff if l_diff > h_diff and l_diff > 0 else 0)
                tr_list.append(max(
                    high_s[i] - low_s[i],
                    abs(high_s[i]  - close_s[i-1]),
                    abs(low_s[i]   - close_s[i-1])
                ))
            tr_s  = pd.Series(tr_list)
            pdm_s = pd.Series(plus_dm)
            mdm_s = pd.Series(minus_dm)
            atr14 = tr_s.ewm(com=period-1, adjust=False).mean()
            pdi   = 100 * pdm_s.ewm(com=period-1, adjust=False).mean() / (atr14 + 1e-9)
            mdi   = 100 * mdm_s.ewm(com=period-1, adjust=False).mean() / (atr14 + 1e-9)
            dx    = 100 * (pdi - mdi).abs() / (pdi + mdi + 1e-9)
            adx   = float(dx.ewm(com=period-1, adjust=False).mean().iloc[-1])

        # ── ATR ratio (current vs 20-period avg) ─────────────
        if len(d1_df) >= 25:
            h = highs; l = lows; c = closes.shift(1)
            tr_d      = pd.concat([h-l, (h-c).abs(), (l-c).abs()], axis=1).max(axis=1)
            atr_s     = tr_d.ewm(com=13, adjust=False).mean()
            atr_now   = float(atr_s.iloc[-1])
            atr_avg   = float(atr_s.tail(20).mean())
            atr_ratio = round(atr_now / atr_avg, 2) if atr_avg > 0 else 1.0
        else:
            atr_ratio = 1.0

        # ── EMA structure ─────────────────────────────────────
        price = float(closes.iloc[-1])
        e50   = float(closes.ewm(span=50,  adjust=False).mean().iloc[-1])
        e200  = float(closes.ewm(span=min(200, len(closes)), adjust=False).mean().iloc[-1])
        ema_stacked   = (price > e50 > e200) or (price < e50 < e200)
        ema_separation = abs(e50 - e200) / e200 * 100

        # ── CLASSIFY ──────────────────────────────────────────
        details = {
            "adx":            round(adx, 1),
            "atr_ratio":      atr_ratio,
            "ema_stacked":    ema_stacked,
            "ema_separation": round(ema_separation, 3),
            "price":          round(price, 5),
            "e50":            round(e50, 5),
            "e200":           round(e200, 5),
        }

        if adx > 25 and ema_stacked and atr_ratio >= 0.8:
            regime = "TRENDING"
        elif adx >= 20 and ema_stacked:
            regime = "WEAK_TREND"
        elif atr_ratio > 1.5:
            regime = "EXPANDING"
        elif adx < 15:
            regime = "COMPRESSING"  # ADX<15 = near-zero directional strength = coiling
        elif adx < 20 and not ema_stacked:
            regime = "RANGING"
        else:
            regime = "WEAK_TREND"

        logger.debug(
            f"{symbol} Regime: {regime} | ADX={adx:.1f} "
            f"ATR_ratio={atr_ratio:.2f} EMA_stacked={ema_stacked}"
        )
        return regime, round(adx, 1), atr_ratio, details

    # ════════════════════════════════════════════════════════════
    #  ENGINE: CONTINUATION
    #  Extracted from old analyse() — identical logic, now a named engine.
    #  Called by analyse() when regime is TRENDING or WEAK_TREND.
    # ════════════════════════════════════════════════════════════

    def _engine_continuation(self, symbol, candles, tick, regime, nova_brief=None, now_dt=None):
        """
        3-layer SMC continuation engine.
        D1 EMA bias → H4 VP zone → H1 sweep + FVG + rejection.
        """
        d1_df = candles.get("D1"); h4_df = candles.get("H4")
        h1_df = candles.get("H1"); w1_df = candles.get("W1")

        direction, _, d1_inds = self._d1_bias(d1_df)
        if direction is None:
            logger.debug(f"{symbol} Continuation: D1 EMA not aligned")
            return None

        bos_boost, bos_reason = self._d1_bos_choch(d1_df, direction)
        atr_adj,   atr_reason = self._atr_regime(d1_df, symbol)

        zone_active, vp_tp, vp_data = self._h4_vp_zone(h4_df, direction, symbol)
        if not zone_active:
            logger.debug(f"{symbol} Continuation: not near H4 VP zone")
            return None

        swept, sweep_level, _ = self._h1_liquidity_sweep(h1_df, direction)
        if not swept:
            logger.debug(f"{symbol} Continuation: no H1 sweep")
            return None

        fvg_ok, fvg_h, fvg_l, fvg_det = self._h1_fvg(h1_df, direction, symbol)
        if not fvg_ok:
            logger.debug(f"{symbol} Continuation: no FVG")
            return None

        rejected, candle_type, _ = self._h1_rejection_candle(h1_df, direction)
        if not rejected:
            logger.debug(f"{symbol} Continuation: no rejection candle")
            return None

        confidence = 70
        confidence += bos_boost
        confidence += atr_adj

        # WEAK_TREND penalty — needs stronger confirmation to pass grade threshold
        # Raised from -8 to -15 (4 Jun 2026): -8 was insufficient, allowing
        # low-conviction WEAK_TREND signals through that had 0% WR in backtest.
        # Signals with genuine strength (85%+ base confidence) still pass at 70%.
        if regime == "WEAK_TREND":
            confidence -= 15

        _now_kz = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)
        h_utc   = _now_kz.hour
        if   LONDON_KZ_START <= h_utc <= LONDON_KZ_END:  kz_name = "London_KZ"
        elif NY_KZ_START     <= h_utc <= NY_KZ_END:      kz_name = "NY_KZ"
        elif NY_PM_KZ_START  <= h_utc <= NY_PM_KZ_END:   kz_name = "NY_PM_KZ"
        else:                                             kz_name = "Session"

        level_boost, level_reason = self._d1_w1_level_boost(
            d1_df, w1_df, direction, sweep_level, symbol)
        confidence += level_boost

        if candle_type in ["bearish_engulfing","bullish_engulfing"]: confidence += 8
        elif candle_type in ["bearish_pin_bar","bullish_pin_bar"]:   confidence += 5
        if fvg_det.get("size_pips", 0) >= get_min_fvg(symbol) * 2:  confidence += 5

        confidence = min(95, max(50, confidence))

        if confidence < self.confidence_gate:
            logger.debug(f"{symbol} Continuation: confidence {confidence}% < gate {self.confidence_gate}%")
            return None

        grade = ("A" if confidence >= GRADE_A_CONF else
                 "B" if confidence >= GRADE_B_CONF else "C")

        entry  = round((fvg_h + fvg_l) / 2, 5)
        levels = self._calculate_levels(
            direction, entry, sweep_level, fvg_h, fvg_l, vp_tp, symbol)

        if levels["rr"] < MIN_RR:
            logger.debug(f"{symbol} Continuation: R:R {levels['rr']} < min {MIN_RR}")
            return None

        rr_bonus   = min(15, max(0, (levels["rr"] - 2.0) * 5))
        kira_score = min(100, int(confidence + rr_bonus))
        lot        = get_lot(symbol)

        brief = {
            "agent":          "KIRA",
            "engine":         "Continuation",
            "regime":         regime,
            "symbol":         symbol,
            "direction":      direction,
            "grade":          grade,
            "confidence":     confidence,
            "kira_score":     kira_score,
            "entry":          levels["entry"],
            "sl":             levels["sl"],
            "tp":             levels["tp"],
            "sl_pips":        levels["sl_pips"],
            "tp_pips":        levels["tp_pips"],
            "lot_size":       lot,
            "risk_rm":        levels["risk_rm"],
            "profit_rm":      levels["profit_rm"],
            "rr":             levels["rr"],
            "spread":         tick["spread"],
            "rsi_h1":         self._rsi(h1_df["close"]) if h1_df is not None else 50.0,
            "rsi_h4":         self._rsi(h4_df["close"]) if h4_df is not None else 50.0,
            "atr":            self._atr(h4_df) if h4_df is not None else 0,
            "d1_direction":   direction,
            "d1_bos_boost":   bos_boost,
            "d1_bos_reason":  bos_reason,
            "atr_regime_adj": atr_adj,
            "atr_regime_rsn": atr_reason,
            "vp_poc":         vp_data.get("poc", 0),
            "vp_vah":         vp_data.get("vah", 0),
            "vp_val":         vp_data.get("val", 0),
            "vp_tp":          vp_tp,
            "smc_sweep":      True,
            "smc_fvg":        True,
            "smc_rejection":  True,
            "sweep_level":    sweep_level,
            "fvg_high":       fvg_h,
            "fvg_low":        fvg_l,
            "fvg_size_pips":  fvg_det.get("size_pips", 0),
            "rejection_type": candle_type,
            "kz_name":        kz_name,
            "kz_boost":       0,
            "level_boost":    level_boost,
            "level_reason":   level_reason,
            "instrument_type":("gold" if is_gold(symbol) else
                               "jpy"  if is_jpy(symbol) else "forex"),
            "timestamp":      datetime.now(tz=timezone.utc).isoformat(),
        }

        logger.info(
            f"KIRA Continuation [{regime}]: {direction} {symbol} Grade-{grade} "
            f"{confidence}% Score:{kira_score} | "
            f"SL:{levels['sl_pips']}pip TP:{levels['tp_pips']}pip "
            f"R:R 1:{levels['rr']} Lots:{lot}"
        )
        return brief

    # ════════════════════════════════════════════════════════════
    #  ENGINE: MRE — MEAN REVERSION
    #  RANGING regime: entry at range extreme, target midpoint
    #  Symbols: EURUSD, AUDUSD | Block London Open + NY_PM
    # ════════════════════════════════════════════════════════════

    def _engine_mre(self, symbol, candles, tick, now_dt=None):
        d1  = candles.get("D1"); h4  = candles.get("H4")
        h1  = candles.get("H1")
        if d1 is None or h1 is None: return None

        pip = get_pip(symbol)
        min_range = MRE_MIN_RANGE_JPY if is_jpy(symbol) else MRE_MIN_RANGE_FOREX
        extreme_prox = MRE_EXTREME_PROX_JPY if is_jpy(symbol) else MRE_EXTREME_PROX_FOREX
        sl_beyond = MRE_SL_BEYOND_JPY if is_jpy(symbol) else MRE_SL_BEYOND_PIPS
        pv = get_pip_value_rm(symbol)

        # MRE session gate — block London Open + NY_PM
        now = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)
        h = now.hour
        if now.weekday() >= 5 or now.weekday() == 4: return None
        if not (SESSION_START_UTC <= h < SESSION_END_UTC): return None
        if LONDON_KZ_START <= h < LONDON_KZ_END:  return None
        if NY_PM_KZ_START  <= h < NY_PM_KZ_END:   return None

        # Layer 1: range detection
        d1v = d1.tail(MRE_RANGE_LOOKBACK + 50)
        recent = d1v.tail(MRE_RANGE_LOOKBACK)
        rng_high = round(float(recent["high"].max()), 5)
        rng_low  = round(float(recent["low"].min()),  5)
        if (rng_high - rng_low) / pip < min_range: return None
        closes = d1v["close"]
        e50  = float(closes.ewm(span=50,  adjust=False).mean().iloc[-1])
        e200 = float(closes.ewm(span=min(200, len(closes)), adjust=False).mean().iloc[-1])
        if abs(e50 - e200) / e200 * 100 > MRE_EMA_FLAT_PCT: return None
        midpoint = round((rng_high + rng_low) / 2, 5)

        # Layer 2: at range extreme
        h4v = h4.tail(50) if h4 is not None else None
        current = float(h4v["close"].iloc[-1]) if h4v is not None else float(h1["close"].iloc[-1])
        dist_top = (rng_high - current) / pip
        dist_bot = (current - rng_low)  / pip
        if dist_top <= extreme_prox:   direction = "SELL"
        elif dist_bot <= extreme_prox: direction = "BUY"
        else: return None

        # Layer 3: RSI overextension + rejection
        h1v = h1.tail(100)
        d = h1v["close"].diff()
        g = d.clip(lower=0).ewm(com=MRE_RSI_PERIOD-1, adjust=False).mean()
        l = (-d.clip(upper=0)).ewm(com=MRE_RSI_PERIOD-1, adjust=False).mean()
        rsi = round(100 - 100 / (1 + float(g.iloc[-1]) / (float(l.iloc[-1]) + 1e-9)), 1)
        rsi_ok = (direction == "SELL" and rsi >= MRE_RSI_SELL) or                  (direction == "BUY"  and rsi <= MRE_RSI_BUY)
        if not rsi_ok: return None

        rejected = self._h1_rejection_candle(h1v, direction)[0]
        if not rejected: return None

        # Levels
        sl_beyond_pips = sl_beyond
        if direction == "SELL":
            sl = round(rng_high + pip * sl_beyond_pips, 5)
            sl_pips = round((sl - current) / pip, 1)
            tp = midpoint; tp_pips = round((current - tp) / pip, 1)
        else:
            sl = round(rng_low - pip * sl_beyond_pips, 5)
            sl_pips = round((current - sl) / pip, 1)
            tp = midpoint; tp_pips = round((tp - current) / pip, 1)
        if sl_pips <= 0 or tp_pips <= 0: return None
        rr = round(tp_pips / sl_pips, 2)
        if rr < MRE_MIN_RR: return None
        if rr > MRE_MAX_RR:
            tp_pips = round(sl_pips * MRE_MAX_RR, 1)
            tp = round(current - pip*tp_pips, 5) if direction=="SELL" else round(current + pip*tp_pips, 5)
            rr = MRE_MAX_RR

        confidence = MRE_BASE_CONFIDENCE
        if (direction=="SELL" and rsi > 70) or (direction=="BUY" and rsi < 30):
            confidence += MRE_RSI_BOOST
        confidence += MRE_REJECTION_BOOST
        confidence = min(95, confidence)
        grade = "A" if confidence >= MRE_GRADE_A_CONF else "B"

        lot = get_lot(symbol)
        risk_rm  = round(sl_pips * pv * lot / 0.01, 2)
        profit_rm= round(tp_pips * pv * lot / 0.01, 2)

        brief = {
            "agent": "KIRA", "engine": "MRE", "regime": "RANGING",
            "symbol": symbol, "direction": direction, "grade": grade,
            "confidence": confidence, "kira_score": confidence,
            "entry": round(current, 5), "sl": sl, "tp": tp,
            "sl_pips": sl_pips, "tp_pips": tp_pips, "lot_size": lot,
            "risk_rm": risk_rm, "profit_rm": profit_rm, "rr": rr,
            "spread": tick["spread"], "rsi_h1": rsi,
            "rng_high": rng_high, "rng_low": rng_low, "midpoint": midpoint,
            "instrument_type": "jpy" if is_jpy(symbol) else "forex",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        logger.info(f"KIRA MRE [RANGING]: {direction} {symbol} Grade-{grade} "
                    f"{confidence}% RSI={rsi} SL:{sl_pips}pip TP:{tp_pips}pip R:R 1:{rr}")
        return brief

    # ════════════════════════════════════════════════════════════
    #  ENGINE: CBE — COMPRESSION BREAKOUT
    #  COMPRESSING regime: H4 coil detected, entry on breakout
    #  Symbols: AUDUSD, EURJPY | All sessions allowed
    # ════════════════════════════════════════════════════════════

    def _engine_cbe(self, symbol, candles, tick, now_dt=None):
        h4 = candles.get("H4"); h1 = candles.get("H1")
        if h4 is None or h1 is None: return None

        pip      = get_pip(symbol)
        min_range= CBE_MIN_RANGE_JPY if is_jpy(symbol) else CBE_MIN_RANGE_FOREX
        sl_inside= CBE_SL_INSIDE_PCT
        pv       = get_pip_value_rm(symbol)

        # CBE session — all sessions, block weekend + Friday
        now = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)
        if now.weekday() >= 5 or now.weekday() == 4: return None
        h = now.hour
        if not (SESSION_START_UTC <= h < SESSION_END_UTC): return None

        # Layer 1+2: H4 compression detection + breakout
        lb  = CBE_COMPRESS_LOOKBACK
        h4v = h4.tail(CBE_ATR_LOOKBACK + lb + 10)
        if len(h4v) < lb + 5: return None

        h_  = h4v["high"]; l_  = h4v["low"]; pc_ = h4v["close"].shift(1)
        tr_ = pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
        h4_atr   = float(tr_.ewm(com=CBE_ATR_LOOKBACK-1,adjust=False).mean().iloc[-1])
        h4_atr_p = h4_atr / pip
        if h4_atr == 0: return None

        prior   = h4v.iloc[-(lb+1):-1]
        c_high  = round(float(prior["high"].max()), 5)
        c_low   = round(float(prior["low"].min()),  5)
        c_range = (c_high - c_low) / pip
        if c_range < min_range: return None
        if c_range >= h4_atr_p * CBE_COMPRESS_ATR_RATIO: return None

        cur = float(h4v.iloc[-1]["close"])
        if   cur > c_high: direction = "BUY"
        elif cur < c_low:  direction = "SELL"
        else: return None

        # Layer 3: H1 momentum candle
        h1v  = h1.tail(CBE_H1_LOOKBACK + 3)
        best = 0.0
        for i in range(len(h1v)-1, -1, -1):
            c  = h1v.iloc[i]; tr = float(c["high"] - c["low"])
            if tr == 0: continue
            body = abs(float(c["close"]) - float(c["open"])) / tr
            ok   = (direction=="BUY" and c["close"]>c["open"]) or                    (direction=="SELL" and c["close"]<c["open"])
            if ok and body > best: best = body
        if best < CBE_H1_BODY_MIN: return None

        # Levels
        c_rng_pips = (c_high - c_low) / pip
        entry = round(float(h1.iloc[-1]["close"]), 5)
        if direction == "BUY":
            sl      = round(c_high - (c_high-c_low)*sl_inside, 5)
            sl_pips = round((entry - sl) / pip, 1)
            tp_pips = round(c_rng_pips * CBE_TP_RANGE_MULT, 1)
            tp      = round(entry + pip * tp_pips, 5)
        else:
            sl      = round(c_low + (c_high-c_low)*sl_inside, 5)
            sl_pips = round((sl - entry) / pip, 1)
            tp_pips = round(c_rng_pips * CBE_TP_RANGE_MULT, 1)
            tp      = round(entry - pip * tp_pips, 5)
        if sl_pips <= 0 or tp_pips <= 0: return None
        rr = round(tp_pips / sl_pips, 2)
        if rr < CBE_MIN_RR: return None
        if rr > CBE_MAX_RR:
            tp_pips = round(sl_pips * CBE_MAX_RR, 1)
            tp  = round(entry+pip*tp_pips,5) if direction=="BUY" else round(entry-pip*tp_pips,5)
            rr  = CBE_MAX_RR

        confidence = CBE_BASE_CONFIDENCE
        h_utc = now.hour
        if LONDON_KZ_START <= h_utc < LONDON_KZ_END: confidence += CBE_LONDON_BOOST
        elif NY_KZ_START   <= h_utc < NY_KZ_END:     confidence += CBE_NY_BOOST
        if best >= 0.70: confidence += CBE_MOMENTUM_BOOST
        confidence = min(95, confidence)
        grade = "A" if confidence >= CBE_GRADE_A_CONF else "B"

        lot      = get_lot(symbol)
        risk_rm  = round(sl_pips * pv * lot / 0.01, 2)
        profit_rm= round(tp_pips * pv * lot / 0.01, 2)

        brief = {
            "agent": "KIRA", "engine": "CBE", "regime": "COMPRESSING",
            "symbol": symbol, "direction": direction, "grade": grade,
            "confidence": confidence, "kira_score": confidence,
            "entry": entry, "sl": sl, "tp": tp,
            "sl_pips": sl_pips, "tp_pips": tp_pips, "lot_size": lot,
            "risk_rm": risk_rm, "profit_rm": profit_rm, "rr": rr,
            "spread": tick["spread"],
            "c_high": c_high, "c_low": c_low, "c_range_pips": round(c_range, 1),
            "body_ratio": round(best, 3),
            "instrument_type": "jpy" if is_jpy(symbol) else "forex",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        logger.info(f"KIRA CBE [COMPRESSING]: {direction} {symbol} Grade-{grade} "
                    f"{confidence}% body={best:.2f} SL:{sl_pips}pip TP:{tp_pips}pip R:R 1:{rr}")
        return brief

    # ════════════════════════════════════════════════════════════
    #  ENGINE: HPE — HTF PULLBACK
    #  TRENDING regime: W1 level + D1 pullback + H4 momentum
    #  Symbols: EURUSD, AUDUSD, EURJPY | All sessions
    # ════════════════════════════════════════════════════════════

    def _engine_hpe(self, symbol, candles, tick, regime, now_dt=None):
        d1 = candles.get("D1"); h4 = candles.get("H4")
        h1 = candles.get("H1"); w1 = candles.get("W1")
        if d1 is None or h4 is None or h1 is None: return None

        pip      = get_pip(symbol)
        prox     = HPE_W1_PROX_JPY if is_jpy(symbol) else HPE_W1_PROX_FOREX
        sl_buf   = HPE_SL_BEYOND_JPY if is_jpy(symbol) else HPE_SL_BEYOND_FOREX
        pv       = get_pip_value_rm(symbol)

        # HPE session — all sessions, block weekend + Friday
        now = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)
        if now.weekday() >= 5 or now.weekday() == 4: return None
        if not (SESSION_START_UTC <= now.hour < SESSION_END_UTC): return None

        # Layer 1: W1 trend + key level
        w1_src = w1 if w1 is not None else d1  # fallback to D1 if no W1
        if len(w1_src) < HPE_W1_SWING_LOOKBACK + HPE_W1_EMA_PERIOD + 2: return None

        w1_closes = w1_src["close"]
        w1_ema    = float(w1_closes.ewm(span=HPE_W1_EMA_PERIOD, adjust=False).mean().iloc[-1])
        w1_price  = float(w1_closes.iloc[-1])
        w1_bull   = w1_price > w1_ema
        w1_bear   = w1_price < w1_ema

        # W1 swing high/low as key level
        w1_swing  = w1_src.tail(HPE_W1_SWING_LOOKBACK)
        w1_s_high = round(float(w1_swing["high"].max()), 5)
        w1_s_low  = round(float(w1_swing["low"].min()),  5)

        current = float(h4["close"].iloc[-1])

        # Determine pullback direction
        dist_to_low  = (current - w1_s_low)  / pip
        dist_to_high = (w1_s_high - current) / pip

        if w1_bull and dist_to_low <= prox:
            direction = "BUY"; level = w1_s_low
        elif w1_bear and dist_to_high <= prox:
            direction = "SELL"; level = w1_s_high
        else:
            return None

        # Layer 2: D1 pullback confirmation
        if len(d1) < 30: return None
        d1_closes = d1["close"]
        h_ = d1["high"]; l_ = d1["low"]; pc_ = d1_closes.shift(1)
        tr_ = pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
        d1_adx_approx = float(tr_.ewm(com=13,adjust=False).mean().iloc[-1])  # ATR proxy
        # Check D1 pullback Fibonacci level
        d1_swing_h = float(d1.tail(20)["high"].max())
        d1_swing_l = float(d1.tail(20)["low"].min())
        d1_swing   = d1_swing_h - d1_swing_l
        if d1_swing == 0: return None
        retrace = abs(current - (d1_swing_l if direction=="BUY" else d1_swing_h)) / d1_swing
        if not (HPE_D1_RETRACE_MIN <= retrace <= HPE_D1_RETRACE_MAX): return None

        # Layer 3: H4 momentum candle in trade direction
        h4v  = h4.tail(HPE_H4_LOOKBACK + 2)
        best = 0.0
        for i in range(len(h4v)-1, -1, -1):
            c = h4v.iloc[i]; tr = float(c["high"] - c["low"])
            if tr == 0: continue
            body = abs(float(c["close"]) - float(c["open"])) / tr
            ok   = (direction=="BUY" and c["close"]>c["open"]) or                    (direction=="SELL" and c["close"]<c["open"])
            if ok and body > best: best = body
        if best < HPE_H4_BODY_MIN: return None

        # Levels — SL beyond W1 level, TP to opposite W1 swing
        entry = round(current, 5)
        if direction == "BUY":
            sl      = round(level - pip * sl_buf, 5)
            sl_pips = round((entry - sl) / pip, 1)
            tp      = w1_s_high
            tp_pips = round((tp - entry) / pip, 1)
        else:
            sl      = round(level + pip * sl_buf, 5)
            sl_pips = round((sl - entry) / pip, 1)
            tp      = w1_s_low
            tp_pips = round((entry - tp) / pip, 1)

        if sl_pips <= 0 or tp_pips <= 0: return None
        rr = round(tp_pips / sl_pips, 2)
        if rr < HPE_MIN_RR: return None
        if rr > HPE_MAX_RR:
            tp_pips = round(sl_pips * HPE_MAX_RR, 1)
            tp  = round(entry+pip*tp_pips,5) if direction=="BUY" else round(entry-pip*tp_pips,5)
            rr  = HPE_MAX_RR

        confidence = HPE_BASE_CONFIDENCE
        confidence += HPE_W1_ALIGN_BOOST   # W1 + D1 always aligned here
        if best >= 0.75: confidence += HPE_ADX_BOOST
        confidence = min(95, confidence)
        grade = "A" if confidence >= HPE_GRADE_A_CONF else "B"

        lot      = get_lot(symbol)
        risk_rm  = round(sl_pips * pv * lot / 0.01, 2)
        profit_rm= round(tp_pips * pv * lot / 0.01, 2)

        brief = {
            "agent": "KIRA", "engine": "HPE", "regime": regime,
            "symbol": symbol, "direction": direction, "grade": grade,
            "confidence": confidence, "kira_score": confidence,
            "entry": entry, "sl": sl, "tp": tp,
            "sl_pips": sl_pips, "tp_pips": tp_pips, "lot_size": lot,
            "risk_rm": risk_rm, "profit_rm": profit_rm, "rr": rr,
            "spread": tick["spread"],
            "w1_level": level, "w1_s_high": w1_s_high, "w1_s_low": w1_s_low,
            "retrace_pct": round(retrace*100, 1), "h4_body": round(best, 3),
            "instrument_type": "jpy" if is_jpy(symbol) else "forex",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        logger.info(f"KIRA HPE [{regime}]: {direction} {symbol} Grade-{grade} "
                    f"{confidence}% retrace={retrace*100:.0f}% SL:{sl_pips}pip TP:{tp_pips}pip R:R 1:{rr}")
        return brief

    # ════════════════════════════════════════════════════════════
    #  ENGINE: IRE — IMBALANCE REBALANCE (v15, 7 Jul 2026)
    #  Session-agnostic H1: displacement → FVG → enter the rebalance.
    #  Pure logic in ire_logic.py — the EXACT module the v15 backtest
    #  validated (106 trades; promoted: EURGBP PF 3.48, EURUSD 3.10,
    #  AUDUSD 1.39; all OOS majority-fold-positive; probation 0.5x).
    #  Stateless: every scan re-derives the setup from H1 history, so
    #  restarts lose nothing and live semantics mirror the backtest.
    # ════════════════════════════════════════════════════════════

    def _engine_ire(self, symbol, candles, tick, now_dt=None):
        h1 = candles.get("H1")
        if h1 is None: return None
        d = IRE_DEFAULTS
        if len(h1) < d["structure_bars"] + d["wait_bars"] + 20: return None

        pip     = get_pip(symbol)
        pv      = get_pip_value_rm(symbol)
        min_fvg = IRE_MIN_FVG_JPY if is_jpy(symbol) else MIN_FVG_PIPS_FOREX
        sl_cap  = IRE_SL_CAP_JPY  if is_jpy(symbol) else IRE_SL_CAP_FOREX

        # Tail window: structure lookback + wait window + ATR warmup.
        h1v = h1.tail(d["structure_bars"] + d["wait_bars"] + 40).reset_index(drop=True)
        h_  = h1v["high"]; l_ = h1v["low"]; pc_ = h1v["close"].shift(1)
        tr_ = pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
        atr_series = tr_.ewm(com=13, adjust=False).mean()
        bars = [{k: float(v) for k, v in b.items()}
                for b in h1v[["open","high","low","close"]].to_dict("records")]
        last = len(bars) - 1          # forming bar = "now" (live convention)

        # Newest displacement first; FVG needs bar i+1 CLOSED (i+1 <= last-1).
        lo = max(d["structure_bars"], last - (d["wait_bars"] + 2))
        for i in range(last - 2, lo - 1, -1):
            atr = float(atr_series.iloc[i])
            if atr <= 0: continue
            disp = detect_displacement(bars, i, atr)
            if disp is None: continue
            direction = disp["direction"]
            g = find_fvg(bars, i, direction, pip, min_fvg)
            if g is None: continue
            gap_lo, gap_hi = g
            mid   = (gap_lo + gap_hi) / 2.0
            start = i + 2
            if last - start >= d["wait_bars"]: continue      # window expired

            # Closed bars since FVG confirm: already consumed or invalidated?
            consumed = invalid = False
            for b in bars[start:last]:
                if direction == "BUY":
                    if b["low"]  <= disp["origin"]: invalid  = True; break
                    if b["low"]  <= mid:            consumed = True; break
                else:
                    if b["high"] >= disp["origin"]: invalid  = True; break
                    if b["high"] >= mid:            consumed = True; break
            if invalid or consumed: continue

            # Live trigger: the FORMING bar entering the gap right now
            # (backtest enters at gap midpoint when a bar's range touches it).
            fb = bars[last]
            if direction == "BUY":
                if fb["low"]  <= disp["origin"]: continue    # structure failed
                if fb["low"]  >  mid:            continue    # gap not reached yet
            else:
                if fb["high"] >= disp["origin"]: continue
                if fb["high"] <  mid:            continue

            entry = round(float(h1v.iloc[-1]["close"]), 5)   # house convention
            lvls = ire_levels(direction, entry, disp["origin"], disp["extreme"],
                              pip, atr, sl_cap)
            if lvls is None: continue
            sl, tp, sl_pips, tp_pips, rr = lvls
            sl = round(sl, 5); tp = round(tp, 5)
            sl_pips = round(sl_pips, 1); tp_pips = round(tp_pips, 1); rr = round(rr, 2)

            confidence = IRE_BASE_CONFIDENCE   # flat — no unvalidated boosts
            grade = "B"
            lot       = get_lot(symbol)
            risk_rm   = round(sl_pips * pv * lot / 0.01, 2)
            profit_rm = round(tp_pips * pv * lot / 0.01, 2)

            brief = {
                "agent": "KIRA", "engine": "IRE", "regime": "REBALANCE",
                "symbol": symbol, "direction": direction, "grade": grade,
                "confidence": confidence, "kira_score": confidence,
                "entry": entry, "sl": sl, "tp": tp,
                "sl_pips": sl_pips, "tp_pips": tp_pips, "lot_size": lot,
                "risk_rm": risk_rm, "profit_rm": profit_rm, "rr": rr,
                "spread": tick["spread"],
                "gap_lo": round(gap_lo, 5), "gap_hi": round(gap_hi, 5),
                "disp_origin": round(disp["origin"], 5),
                "disp_extreme": round(disp["extreme"], 5),
                "instrument_type": "jpy" if is_jpy(symbol) else "forex",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }
            logger.info(f"KIRA IRE [REBALANCE]: {direction} {symbol} Grade-{grade} "
                        f"{confidence}% gap={round((gap_hi-gap_lo)/pip,1)}pip "
                        f"SL:{sl_pips}pip TP:{tp_pips}pip R:R 1:{rr}")
            return brief
        return None

    # ════════════════════════════════════════════════════════════
    #  v18 LOWER-TF TRACK — IRE15 / CBE15 (isolated, own methods)
    #  Same validated logic on M15. The H4/H1 engines above are frozen.
    # ════════════════════════════════════════════════════════════
    def _engine_ire15(self, symbol, candles, tick, now_dt=None):
        """IRE on M15 (v18). Identical to _engine_ire but reads M15 candles."""
        m15 = candles.get("M15")
        if m15 is None: return None
        d = IRE_DEFAULTS
        if len(m15) < d["structure_bars"] + d["wait_bars"] + 20: return None
        pip     = get_pip(symbol)
        pv      = get_pip_value_rm(symbol)
        min_fvg = IRE_MIN_FVG_JPY if is_jpy(symbol) else MIN_FVG_PIPS_FOREX
        sl_cap  = IRE_SL_CAP_JPY  if is_jpy(symbol) else IRE_SL_CAP_FOREX
        mv = m15.tail(d["structure_bars"] + d["wait_bars"] + 40).reset_index(drop=True)
        h_ = mv["high"]; l_ = mv["low"]; pc_ = mv["close"].shift(1)
        tr_ = pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
        atr_series = tr_.ewm(com=13, adjust=False).mean()
        bars = [{k: float(v) for k, v in b.items()}
                for b in mv[["open","high","low","close"]].to_dict("records")]
        last = len(bars) - 1
        lo = max(d["structure_bars"], last - (d["wait_bars"] + 2))
        for i in range(last - 2, lo - 1, -1):
            atr = float(atr_series.iloc[i])
            if atr <= 0: continue
            disp = detect_displacement(bars, i, atr)
            if disp is None: continue
            direction = disp["direction"]
            g = find_fvg(bars, i, direction, pip, min_fvg)
            if g is None: continue
            gap_lo, gap_hi = g; mid = (gap_lo + gap_hi) / 2.0
            start = i + 2
            if last - start >= d["wait_bars"]: continue
            consumed = invalid = False
            for b in bars[start:last]:
                if direction == "BUY":
                    if b["low"]  <= disp["origin"]: invalid  = True; break
                    if b["low"]  <= mid:            consumed = True; break
                else:
                    if b["high"] >= disp["origin"]: invalid  = True; break
                    if b["high"] >= mid:            consumed = True; break
            if invalid or consumed: continue
            fb = bars[last]
            if direction == "BUY":
                if fb["low"]  <= disp["origin"]: continue
                if fb["low"]  >  mid:            continue
            else:
                if fb["high"] >= disp["origin"]: continue
                if fb["high"] <  mid:            continue
            entry = round(float(mv.iloc[-1]["close"]), 5)
            lvls = ire_levels(direction, entry, disp["origin"], disp["extreme"], pip, atr, sl_cap)
            if lvls is None: continue
            sl, tp, sl_pips, tp_pips, rr = lvls
            sl = round(sl, 5); tp = round(tp, 5)
            sl_pips = round(sl_pips, 1); tp_pips = round(tp_pips, 1); rr = round(rr, 2)
            grade = "B"; lot = get_lot(symbol)
            brief = {
                "agent": "KIRA", "engine": "IRE15", "regime": "REBALANCE",
                "symbol": symbol, "direction": direction, "grade": grade,
                "confidence": IRE_BASE_CONFIDENCE, "kira_score": IRE_BASE_CONFIDENCE,
                "entry": entry, "sl": sl, "tp": tp,
                "sl_pips": sl_pips, "tp_pips": tp_pips, "lot_size": lot,
                "risk_rm": round(sl_pips*pv*lot/0.01,2), "profit_rm": round(tp_pips*pv*lot/0.01,2),
                "rr": rr, "spread": tick["spread"],
                "instrument_type": "jpy" if is_jpy(symbol) else "forex",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            }
            logger.info(f"KIRA IRE15 [REBALANCE]: {direction} {symbol} Grade-{grade} "
                        f"SL:{sl_pips}pip TP:{tp_pips}pip R:R 1:{rr}")
            return brief
        return None

    def _engine_cbe15(self, symbol, candles, tick, now_dt=None):
        """CBE on lower TF (v18): H1 compression -> M15 momentum + entry.
        Mirrors _engine_cbe one timeframe down. H4/H1 CBE untouched."""
        h1 = candles.get("H1"); m15 = candles.get("M15")
        if h1 is None or m15 is None: return None
        pip       = get_pip(symbol)
        min_range = CBE_MIN_RANGE_JPY if is_jpy(symbol) else CBE_MIN_RANGE_FOREX
        pv        = get_pip_value_rm(symbol)
        now = now_dt if now_dt is not None else datetime.now(tz=timezone.utc)
        if now.weekday() >= 5 or now.weekday() == 4: return None
        if not (SESSION_START_UTC <= now.hour < SESSION_END_UTC): return None
        # compression on H1 (down from H4)
        lb  = CBE_COMPRESS_LOOKBACK
        h1v = h1.tail(CBE_ATR_LOOKBACK + lb + 10)
        if len(h1v) < lb + 5: return None
        h_ = h1v["high"]; l_ = h1v["low"]; pc_ = h1v["close"].shift(1)
        tr_ = pd.concat([h_-l_,(h_-pc_).abs(),(l_-pc_).abs()],axis=1).max(axis=1)
        h1_atr = float(tr_.ewm(com=CBE_ATR_LOOKBACK-1,adjust=False).mean().iloc[-1])
        if h1_atr == 0: return None
        h1_atr_p = h1_atr / pip
        prior = h1v.iloc[-(lb+1):-1]
        c_high = round(float(prior["high"].max()), 5); c_low = round(float(prior["low"].min()), 5)
        c_range = (c_high - c_low) / pip
        if c_range < min_range or c_range >= h1_atr_p * CBE_COMPRESS_ATR_RATIO: return None
        cur = float(h1v.iloc[-1]["close"])
        if   cur > c_high: direction = "BUY"
        elif cur < c_low:  direction = "SELL"
        else: return None
        # momentum on M15 (down from H1)
        m15v = m15.tail(CBE_H1_LOOKBACK + 3); best = 0.0
        for k in range(len(m15v)-1, -1, -1):
            c = m15v.iloc[k]; tr = float(c["high"] - c["low"])
            if tr == 0: continue
            body = abs(float(c["close"]) - float(c["open"])) / tr
            ok = (direction=="BUY" and c["close"]>c["open"]) or (direction=="SELL" and c["close"]<c["open"])
            if ok and body > best: best = body
        if best < CBE_H1_BODY_MIN: return None
        # entry on M15 close, levels via the CBE convention
        entry = round(float(m15.iloc[-1]["close"]), 5)
        c_rng_pips = (c_high - c_low) / pip
        if direction == "BUY":
            sl = round(c_high - (c_high-c_low)*CBE_SL_INSIDE_PCT, 5); sl_pips = round((entry-sl)/pip,1)
            tp_pips = round(c_rng_pips*CBE_TP_RANGE_MULT,1); tp = round(entry+pip*tp_pips,5)
        else:
            sl = round(c_low + (c_high-c_low)*CBE_SL_INSIDE_PCT, 5); sl_pips = round((sl-entry)/pip,1)
            tp_pips = round(c_rng_pips*CBE_TP_RANGE_MULT,1); tp = round(entry-pip*tp_pips,5)
        if sl_pips <= 0 or tp_pips <= 0: return None
        rr = round(tp_pips/sl_pips,2)
        if rr < CBE_MIN_RR: return None
        if rr > CBE_MAX_RR:
            tp_pips = round(sl_pips*CBE_MAX_RR,1)
            tp = round(entry+pip*tp_pips,5) if direction=="BUY" else round(entry-pip*tp_pips,5); rr = CBE_MAX_RR
        grade = "B"; lot = get_lot(symbol)
        brief = {
            "agent": "KIRA", "engine": "CBE15", "regime": "COMPRESSING",
            "symbol": symbol, "direction": direction, "grade": grade,
            "confidence": CBE_BASE_CONFIDENCE, "kira_score": CBE_BASE_CONFIDENCE,
            "entry": entry, "sl": sl, "tp": tp,
            "sl_pips": sl_pips, "tp_pips": tp_pips, "lot_size": lot,
            "risk_rm": round(sl_pips*pv*lot/0.01,2), "profit_rm": round(tp_pips*pv*lot/0.01,2),
            "rr": rr, "spread": tick["spread"],
            "c_high": c_high, "c_low": c_low, "body_ratio": round(best,3),
            "instrument_type": "jpy" if is_jpy(symbol) else "forex",
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
        logger.info(f"KIRA CBE15 [COMPRESSING]: {direction} {symbol} Grade-{grade} "
                    f"body={best:.2f} SL:{sl_pips}pip TP:{tp_pips}pip R:R 1:{rr}")
        return brief

        # ════════════════════════════════════════════════════════════
    #  MAIN PIPELINE — KIRA as dispatcher
    #
    #  Flow:
    #    1. Fetch candles + tick  (once, shared across all engines)
    #    2. Classify regime       (ADX + ATR + EMA)
    #    3. Route to engine       (symbol + regime → engine method)
    #    4. Return brief or None
    #
    #  Adding MRE / CBE / NIE later:
    #    1. Write _engine_mre(symbol, candles, tick, regime)
    #    2. Add one routing line below — nothing else changes
    #
    #  Engine routing table:
    #    XAUUSD              → GVE (always, regardless of regime)
    #    TRENDING/WEAK_TREND → HPE (if at W1 level) else Continuation
    #    EXPANDING           → blocked (bad edge, 0% WR in backtest)
    #    RANGING             → MRE  (EURUSD, AUDUSD)
    #    COMPRESSING         → CBE  (AUDUSD, EURJPY)
    #    UNKNOWN             → no trade
    # ════════════════════════════════════════════════════════════

    # ════════════════════════════════════════════════════════════
    #  _route_engine — KIRA adaptive engine dispatcher (v8)
    #  Uses KIRA_ROUTING_TABLE from config to try engines in
    #  priority order. First engine that returns a valid brief wins.
    #  regime must match entry in routing table (or entry has None = any).
    # ════════════════════════════════════════════════════════════

    def _route_engine(self, symbol, candles, tick, regime, nova_brief=None, now_dt=None):
        """
        Route to the best available engine for this symbol + regime.
        Tries engines in routing table priority order.
        Returns first non-None brief, or None if all engines pass.
        """
        routing = KIRA_ROUTING_TABLE.get(symbol, [])
        if not routing:
            # Symbol not in routing table — use legacy fallback
            logger.debug(f"{symbol}: not in routing table — using legacy fallback")
            return self._legacy_route(symbol, candles, tick, regime, nova_brief, now_dt)

        for (engine_name, required_regime) in routing:
            # Check regime compatibility
            if required_regime is not None and regime != required_regime:
                logger.debug(f"{symbol}: skip {engine_name} (needs {required_regime}, have {regime})")
                continue

            # Dispatch to engine
            result = self._dispatch_engine(engine_name, symbol, candles, tick,
                                           regime, nova_brief, now_dt)
            if result is not None:
                logger.info(f"{symbol} v8 routing: {engine_name} fired (regime={regime})")
                return result

        logger.debug(f"{symbol}: all engines in routing table passed (regime={regime})")
        return None

    def _dispatch_engine(self, engine_name, symbol, candles, tick,
                         regime, nova_brief=None, now_dt=None):
        """Dispatch to named engine method. Returns brief or None.
        v9 PRECISION: every dispatch passes the engine×symbol whitelist first —
        no proven-negative combo can fire regardless of routing table contents."""
        # ── v9 WHITELIST GATE ─────────────────────────────────
        if not engine_symbol_allowed(engine_name, symbol):
            logger.debug(f"{symbol}: {engine_name} blocked by v9 whitelist (proven negative)")
            return None

        if engine_name == "GVE":
            return self._analyse_gold(symbol, candles, tick, nova_brief, now_dt=now_dt)
        elif engine_name == "CTE":
            # CTE only fires in TRENDING or WEAK_TREND...
            if regime not in ("TRENDING", "WEAK_TREND"):
                return None
            # ...and v9: TRENDING is per-symbol permission (NZDUSD only).
            # CTE TRENDING globally: WR 26.5%, -RM51.77 — systematic loser.
            if not cte_regime_allowed(symbol, regime):
                logger.debug(f"{symbol}: CTE blocked in {regime} (v9 regime permission)")
                return None
            return self._engine_continuation(symbol, candles, tick, regime, nova_brief, now_dt)
        elif engine_name == "MRE":
            return self._engine_mre(symbol, candles, tick, now_dt=now_dt)
        elif engine_name == "CBE":
            return self._engine_cbe(symbol, candles, tick, now_dt=now_dt)
        elif engine_name == "HPE":
            return self._engine_hpe(symbol, candles, tick, regime, now_dt=now_dt)
        elif engine_name == "IRE":
            return self._engine_ire(symbol, candles, tick, now_dt=now_dt)
        elif engine_name == "IRE15":
            return self._engine_ire15(symbol, candles, tick, now_dt=now_dt)
        elif engine_name == "CBE15":
            return self._engine_cbe15(symbol, candles, tick, now_dt=now_dt)
        else:
            logger.warning(f"Unknown engine name: {engine_name}")
            return None

    def _legacy_route(self, symbol, candles, tick, regime, nova_brief=None, now_dt=None):
        """Legacy routing fallback for symbols not in KIRA_ROUTING_TABLE."""
        if regime == "RANGING":
            return self._engine_mre(symbol, candles, tick, now_dt=now_dt)
        if regime == "COMPRESSING":
            return self._engine_cbe(symbol, candles, tick, now_dt=now_dt)
        if regime in ("TRENDING", "WEAK_TREND"):
            hpe = self._engine_hpe(symbol, candles, tick, regime, now_dt=now_dt)
            return hpe if hpe else self._engine_continuation(
                symbol, candles, tick, regime, nova_brief, now_dt)
        return None

    def analyse(self, symbol, nova_brief=None, now_dt=None):
        # ── 1. DATA (fetched once, shared across all engines) ──
        candles = self.mt5.get_all_timeframes(symbol)
        if not candles:
            return None

        # Metals (XAUUSD, XAGUSD) need M15; all others need D1/H4/H1
        required = ["D1", "H4", "H1", "M15"] if is_metal(symbol) else ["D1", "H4", "H1"]
        if any(candles.get(tf) is None or len(candles.get(tf, [])) == 0 for tf in required):
            return None

        tick = self.mt5.get_tick(symbol)
        if not tick: return None

        spread_max = get_spread_max(symbol)
        if tick["spread"] > spread_max:
            logger.debug(f"{symbol}: spread {tick['spread']} > {spread_max}")
            return None

        # ── 2. REGIME CLASSIFICATION ──────────────────────────
        # Metals skip the classifier — GVE has its own internal regime guards
        if is_metal(symbol):
            regime = "GVE"
        else:
            regime, adx, atr_ratio, regime_details = self._classify_regime(
                symbol, candles.get("D1"), candles.get("H4")
            )
            # EXPANDING: 0% WR in backtest — block entirely
            if regime == "EXPANDING":
                logger.debug(f"{symbol}: EXPANDING — blocked (0% WR in backtest)")
                return None
            # UNKNOWN: insufficient data
            if regime == "UNKNOWN":
                logger.debug(f"{symbol}: UNKNOWN regime — insufficient data")
                return None

        # ── 3. SESSION GATE (non-metals only; metals gate is inside GVE) ──
        if not is_metal(symbol) and not self._in_session(symbol, now_dt=now_dt):
            logger.debug(f"{symbol}: outside session")
            return None

        # ── 4. KIRA ADAPTIVE ROUTING (v8) ─────────────────────
        # Uses KIRA_ROUTING_TABLE: tries best engine first, falls back down priority list
        return self._route_engine(symbol, candles, tick, regime, nova_brief, now_dt=now_dt)

    # ════════════════════════════════════════════════════════════
    #  LIVE EXECUTION HELPERS (v8)
    #  Called by main_agents._execute() or external callers.
    #  Each engine has a matching execute_*_signal() method so callers
    #  can reference engine-specific metadata, not just generic sl_pips/tp_pips.
    # ════════════════════════════════════════════════════════════

    def execute_mre_signal(self, symbol, candles=None, tick=None, now_dt=None):
        """
        MRE live execution wrapper.
        Returns execution-ready brief with entry, sl, tp at current market price.
        Mirrors execute_cbe_signal / execute_hpe_signal pattern.

        Usage:
            brief = kira.execute_mre_signal(symbol)
            if brief:
                order = mt5.place_order(symbol, brief['direction'],
                                        brief['lot_size'], brief['sl'], brief['tp'])
        """
        if candles is None:
            candles = self.mt5.get_all_timeframes(symbol)
        if tick is None:
            tick = self.mt5.get_tick(symbol)
        if not candles or not tick:
            return None

        brief = self._engine_mre(symbol, candles, tick, now_dt=now_dt)
        if brief is None:
            return None

        # Recalculate SL/TP from CURRENT price at execution time
        pip   = get_pip(symbol)
        entry = tick["ask"] if brief["direction"] == "BUY" else tick["bid"]
        sl_pips = brief["sl_pips"]
        tp_pips = brief["tp_pips"]

        if brief["direction"] == "BUY":
            sl = round(entry - pip * sl_pips, 5)
            tp = round(entry + pip * tp_pips, 5)
        else:
            sl = round(entry + pip * sl_pips, 5)
            tp = round(entry - pip * tp_pips, 5)

        brief.update({
            "entry":    entry,
            "sl":       sl,
            "tp":       tp,
            "exec_mode": "live_mre",
        })
        logger.info(
            f"MRE EXEC: {brief['direction']} {symbol} "            f"entry={entry} SL={sl} TP={tp} "            f"R:R 1:{brief['rr']} Grade-{brief['grade']}"
        )
        return brief

    def execute_cbe_signal(self, symbol, candles=None, tick=None, now_dt=None):
        """
        CBE live execution wrapper. Returns execution-ready brief.
        """
        if candles is None:
            candles = self.mt5.get_all_timeframes(symbol)
        if tick is None:
            tick = self.mt5.get_tick(symbol)
        if not candles or not tick:
            return None

        brief = self._engine_cbe(symbol, candles, tick, now_dt=now_dt)
        if brief is None:
            return None

        pip   = get_pip(symbol)
        entry = tick["ask"] if brief["direction"] == "BUY" else tick["bid"]

        if brief["direction"] == "BUY":
            sl = round(entry - pip * brief["sl_pips"], 5)
            tp = round(entry + pip * brief["tp_pips"], 5)
        else:
            sl = round(entry + pip * brief["sl_pips"], 5)
            tp = round(entry - pip * brief["tp_pips"], 5)

        brief.update({"entry": entry, "sl": sl, "tp": tp, "exec_mode": "live_cbe"})
        logger.info(
            f"CBE EXEC: {brief['direction']} {symbol} entry={entry} "            f"SL={sl} TP={tp} R:R 1:{brief['rr']} Grade-{brief['grade']}"
        )
        return brief

    def execute_hpe_signal(self, symbol, candles=None, tick=None, regime="TRENDING", now_dt=None):
        """
        HPE live execution wrapper. Returns execution-ready brief.
        """
        if candles is None:
            candles = self.mt5.get_all_timeframes(symbol)
        if tick is None:
            tick = self.mt5.get_tick(symbol)
        if not candles or not tick:
            return None

        brief = self._engine_hpe(symbol, candles, tick, regime, now_dt=now_dt)
        if brief is None:
            return None

        pip   = get_pip(symbol)
        entry = tick["ask"] if brief["direction"] == "BUY" else tick["bid"]

        if brief["direction"] == "BUY":
            sl = round(entry - pip * brief["sl_pips"], 5)
            tp = round(entry + pip * brief["tp_pips"], 5)
        else:
            sl = round(entry + pip * brief["sl_pips"], 5)
            tp = round(entry - pip * brief["tp_pips"], 5)

        brief.update({"entry": entry, "sl": sl, "tp": tp, "exec_mode": "live_hpe"})
        logger.info(
            f"HPE EXEC: {brief['direction']} {symbol} entry={entry} "            f"SL={sl} TP={tp} R:R 1:{brief['rr']} Grade-{brief['grade']}"
        )
        return brief

    # ── STREAKS ──────────────────────────────────────────────

    def update_streaks(self, result):
        if result == "win":
            self.win_streak  += 1; self.loss_streak  = 0
        elif result == "loss":
            self.loss_streak += 1; self.win_streak   = 0
        if self.loss_streak >= 3:    self.confidence_gate = LOSS_STREAK_GATE_3
        elif self.loss_streak >= 2:  self.confidence_gate = LOSS_STREAK_GATE_2
        elif self.win_streak >= 3:   self.confidence_gate = WIN_STREAK_EASE
        else:                        self.confidence_gate = MIN_CONFIDENCE

    def check_correlation(self, brief, active_signals):
        usd_pairs = ["AUDUSD","EURUSD","GBPUSD","USDJPY"]
        gbp_pairs = ["GBPUSD","GBPJPY"]
        jpy_pairs = ["USDJPY","GBPJPY"]
        sym = brief["symbol"]
        # Gold can trade alongside any forex pair
        if is_gold(sym): return True, ""
        # GBPJPY: conflicts with same-direction GBPUSD (GBP exposure) or USDJPY (JPY exposure)
        if sym == "GBPJPY":
            for ex in active_signals:
                es = ex.get("symbol","")
                if es in gbp_pairs and ex.get("direction") != brief["direction"]:
                    return False, f"GBPJPY conflicts with {es} {ex['direction']} (GBP exposure)"
                if es in jpy_pairs and ex.get("direction") != brief["direction"]:
                    return False, f"GBPJPY conflicts with {es} {ex['direction']} (JPY exposure)"
            return True, ""
        active_usd = [s for s in active_signals if s.get("symbol") in usd_pairs]
        if not active_usd: return True, ""
        if sym in usd_pairs:
            for ex in active_usd:
                if ex.get("direction") != brief["direction"]:
                    return False, f"Conflicts with {ex['symbol']} {ex['direction']}"
            if len(active_usd) >= 2:
                return False, "Max 2 USD pairs already open"
        return True, ""
