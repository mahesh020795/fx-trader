# ════════════════════════════════════════════════════════════
#  mt5_connector.py — MT5 Connection (FINAL BUILD + GOLD/JPY)
# ════════════════════════════════════════════════════════════

import MetaTrader5 as mt5
import pandas as pd
import logging
import time
from config import *

logger = logging.getLogger("mt5_connector")


class MT5Connector:

    def __init__(self):
        self.connected = False
        # SIM virtual-position engine (SIM_MODE only). Real orders get a broker
        # ticket and the broker holds them to SL/TP; SIM must simulate that
        # itself — previously it didn't (every SIM trade closed BE next cycle).
        self._sim_positions = {}   # ticket -> position dict
        self._sim_closed    = {}   # ticket -> realized pnl_usd (consumed once)
        self._sim_ticket    = 500000

    def _sim_pnl_usd(self, pos, exit_price):
        """Realized/unrealized USD P&L for a SIM position at exit_price."""
        pip = get_pip(pos["symbol"])
        pnl_pips = (exit_price - pos["entry"]) / pip * (1 if pos["direction"] == "BUY" else -1)
        usd_per_pip = get_pip_value_rm(pos["symbol"]) / USD_MYR_RATE * (pos["lots"] / 0.01)
        return round(pnl_pips * usd_per_pip, 2)

    def _sim_open_positions(self):
        """Check each SIM position against SL/TP with the live tick. Realize
        (move to _sim_closed, remove from open) when a level is hit so
        _detect_closed picks it up with the correct pnl; otherwise return it as
        an open position with updated price for MAE/MFE tracking."""
        result = []
        for ticket, pos in list(self._sim_positions.items()):
            tick = self.get_tick(pos["symbol"])
            if not tick:
                continue
            cur = tick["bid"] if pos["direction"] == "BUY" else tick["ask"]
            hit = None
            if pos["direction"] == "BUY":
                if   cur <= pos["sl"]: hit = pos["sl"]
                elif cur >= pos["tp"]: hit = pos["tp"]
            else:
                if   cur >= pos["sl"]: hit = pos["sl"]
                elif cur <= pos["tp"]: hit = pos["tp"]
            if hit is not None:
                self._sim_closed[ticket] = self._sim_pnl_usd(pos, hit)
                del self._sim_positions[ticket]
                continue
            pip = get_pip(pos["symbol"])
            result.append({
                "ticket": ticket, "symbol": pos["symbol"], "direction": pos["direction"],
                "lots": pos["lots"], "entry": pos["entry"], "current": cur,
                "sl": pos["sl"], "tp": pos["tp"], "profit": self._sim_pnl_usd(pos, cur),
                "pnl_pips": round((cur - pos["entry"]) / pip * (1 if pos["direction"] == "BUY" else -1), 1),
                "magic": 20260525,
            })
        return result

    def connect(self):
        if not mt5.initialize():
            logger.error(f"MT5 init failed: {mt5.last_error()}")
            return False
        if not mt5.login(MT5_LOGIN, MT5_PASSWORD, MT5_SERVER):
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            return False
        info = mt5.account_info()
        logger.info(f"MT5 connected: {info.login} | Balance: ${info.balance:.2f}")
        self.connected = True
        self.warm_up_symbols()
        return True

    def warm_up_symbols(self):
        logger.info("Warming up symbols...")
        for symbol in ALL_PAIRS:
            if self._ensure_symbol(symbol):
                for tf in [TF_D1, TF_H4, TF_H1, TF_M15, TF_W1]:
                    for attempt in range(5):
                        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 50)
                        if rates is not None and len(rates) > 0:
                            break
                        time.sleep(1)
                logger.info(f"  {symbol} ready OK")
            else:
                logger.warning(f"  {symbol} could not be selected")
        time.sleep(3)
        logger.info("Warm-up complete — agents scanning")

    def ensure_connected(self):
        if not self.connected:
            return self.connect()
        try:
            info = mt5.account_info()
            if info is None:
                logger.warning("MT5 disconnected — reconnecting")
                return self.connect()
            return True
        except Exception:
            return self.connect()

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    def _ensure_symbol(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            mt5.symbol_select(symbol, True)
            time.sleep(0.5)
            info = mt5.symbol_info(symbol)
        if info is None:
            return False
        if not info.visible:
            mt5.symbol_select(symbol, True)
        return True

    def get_candles(self, symbol, timeframe, count):
        self._ensure_symbol(symbol)
        rates = None
        for attempt in range(3):
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is not None and len(rates) > 0:
                break
            if attempt < 2: time.sleep(1)
        if rates is None or len(rates) == 0:
            logger.error(f"Cannot get candles for {symbol} TF:{timeframe}")
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"tick_volume": "volume"})
        return df[["time","open","high","low","close","volume"]]

    def get_all_timeframes(self, symbol):
        # Metals (XAUUSD, XAGUSD) need more M15 candles for GVE sweep detection
        # 300 M15 = 3 trading days — too few; GVE lookback needs 30+ days
        # Fix v8: fetch CANDLES_M15_METAL for metals, standard CANDLES_M15 for forex
        from config import is_metal, CANDLES_M15, CANDLES_M15_METAL
        m15_count = CANDLES_M15_METAL if is_metal(symbol) else CANDLES_M15
        return {
            "D1":  self.get_candles(symbol, TF_D1,  CANDLES_D1),
            "H4":  self.get_candles(symbol, TF_H4,  CANDLES_H4),
            "H1":  self.get_candles(symbol, TF_H1,  CANDLES_H1),
            "M15": self.get_candles(symbol, TF_M15, m15_count),
            "W1":  self.get_candles(symbol, TF_W1,  20),
        }

    def get_tick(self, symbol):
        self._ensure_symbol(symbol)
        tick = mt5.symbol_info_tick(symbol)
        if tick is None: return None
        info = mt5.symbol_info(symbol)
        pip  = get_pip(symbol)
        point = info.point if info else pip / 10
        spread_pips = round((tick.ask - tick.bid) / pip, 1)
        return {"bid": tick.bid, "ask": tick.ask, "spread": spread_pips}

    def get_balance(self):
        if SIM_MODE: return SIM_BALANCE_USD
        info = mt5.account_info()
        return info.balance if info else 0.0

    def get_equity(self):
        info = mt5.account_info()
        return info.equity if info else 0.0

    def get_daily_pnl(self):
        try:
            from datetime import datetime, timezone
            import pytz
            now   = datetime.now(tz=timezone.utc)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            deals = mt5.history_deals_get(start, now)
            if deals is None: return 0.0
            return sum(d.profit for d in deals if d.entry == 1)
        except Exception:
            return 0.0

    def place_order(self, symbol, direction, lot_size, sl, tp, comment=""):
        if SIM_MODE:
            tick  = self.get_tick(symbol)
            price = tick["ask"] if direction == "BUY" else tick["bid"]
            self._sim_ticket += 1
            ticket = self._sim_ticket
            self._sim_positions[ticket] = {
                "ticket": ticket, "symbol": symbol, "direction": direction,
                "entry": price, "sl": sl, "tp": tp, "lots": lot_size,
            }
            logger.info(f"SIM ORDER: {direction} {symbol} @ {price} "
                        f"SL:{sl} TP:{tp} lots:{lot_size} #{ticket}")
            return {"ticket": ticket, "price": price}

        self._ensure_symbol(symbol)
        tick  = self.get_tick(symbol)
        if not tick: return None
        price = tick["ask"] if direction == "BUY" else tick["bid"]
        order_type = (mt5.ORDER_TYPE_BUY if direction == "BUY"
                      else mt5.ORDER_TYPE_SELL)

        # Auto-detect filling mode from symbol info
        sym_info = mt5.symbol_info(symbol)
        if sym_info is not None:
            fm = sym_info.filling_mode
            if fm == 1:   detected = mt5.ORDER_FILLING_FOK
            elif fm == 2: detected = mt5.ORDER_FILLING_IOC
            else:         detected = mt5.ORDER_FILLING_RETURN
        else:
            detected = mt5.ORDER_FILLING_RETURN

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       float(lot_size),
            "type":         order_type,
            "price":        price,
            "sl":           sl,
            "tp":           tp,
            "deviation":    50,
            "magic":        20260525,
            "comment":      comment[:31],
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": detected,
        }

        result = None
        for filling in [detected, mt5.ORDER_FILLING_RETURN,
                        mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]:
            request["type_filling"] = filling
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"Order success filling:{filling}")
                break
            logger.warning(f"Filling {filling} failed: "
                          f"{result.retcode if result else 'None'} "
                          f"{result.comment if result else ''}")

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: retcode="
                        f"{result.retcode if result else 'None'} "
                        f"{result.comment if result else ''}")
            return None

        return {"ticket": result.order, "price": result.price}

    def get_open_positions(self):
        if SIM_MODE:
            return self._sim_open_positions()
        positions = mt5.positions_get()
        if positions is None: return []
        result = []
        for p in positions:
            if p.magic != 20260525: continue
            direction = "BUY" if p.type == 0 else "SELL"
            pip       = get_pip(p.symbol)
            result.append({
                "ticket":    p.ticket,
                "symbol":    p.symbol,
                "direction": direction,
                "lots":      p.volume,
                "entry":     p.price_open,
                "current":   p.price_current,
                "sl":        p.sl,
                "tp":        p.tp,
                "profit":    p.profit,
                "pnl_pips":  round((p.price_current - p.price_open) /
                                   pip * (1 if direction=="BUY" else -1), 1),
            })
        return result

    def modify_sl(self, ticket, new_sl):
        positions = mt5.positions_get(ticket=ticket)
        if not positions: return False
        pos = positions[0]
        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "ticket":   ticket,
            "sl":       new_sl,
            "tp":       pos.tp,
        }
        result = mt5.order_send(request)
        return result and result.retcode == mt5.TRADE_RETCODE_DONE

    def close_position(self, ticket):
        if SIM_MODE:
            pos = self._sim_positions.pop(ticket, None)
            if pos is None: return False
            tick = self.get_tick(pos["symbol"])
            cur  = (tick["bid"] if pos["direction"] == "BUY" else tick["ask"]) if tick else pos["entry"]
            self._sim_closed[ticket] = self._sim_pnl_usd(pos, cur)
            return True
        positions = mt5.positions_get(ticket=ticket)
        if not positions: return False
        pos        = positions[0]
        direction  = "SELL" if pos.type == 0 else "BUY"
        order_type = (mt5.ORDER_TYPE_SELL if pos.type == 0
                      else mt5.ORDER_TYPE_BUY)
        tick = self.get_tick(pos.symbol)
        if not tick: return False
        price = tick["bid"] if direction == "SELL" else tick["ask"]
        sym_info = mt5.symbol_info(pos.symbol)
        filling  = (mt5.ORDER_FILLING_FOK if sym_info and sym_info.filling_mode == 1
                    else mt5.ORDER_FILLING_IOC if sym_info and sym_info.filling_mode == 2
                    else mt5.ORDER_FILLING_RETURN)
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "ticket":       ticket,
            "symbol":       pos.symbol,
            "volume":       pos.volume,
            "type":         order_type,
            "price":        price,
            "deviation":    50,
            "magic":        20260525,
            "type_filling": filling,
        }
        result = mt5.order_send(request)
        return result and result.retcode == mt5.TRADE_RETCODE_DONE

    def get_closed_pnl(self, ticket):
        if SIM_MODE:
            return self._sim_closed.pop(ticket, 0.0)
        try:
            from datetime import datetime, timezone, timedelta
            now   = datetime.now(tz=timezone.utc)
            start = now - timedelta(days=30)
            deals = mt5.history_deals_get(start, now)
            if deals is None: return 0.0
            pnl = sum(d.profit for d in deals
                      if d.position_id == ticket and d.entry == 1)
            return pnl
        except Exception:
            return 0.0
