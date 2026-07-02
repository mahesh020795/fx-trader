# ════════════════════════════════════════════════════════════
#  AGENT NOVA — News & Sentiment (FINAL BUILD + GOLD/JPY)
#  Per-signal only. FF 48hr + Claude sentiment.
#  Gold and JPY have different keyword sets.
# ════════════════════════════════════════════════════════════

import requests
import anthropic
import feedparser
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from config import *

logger = logging.getLogger("NOVA")


class AgentNOVA:

    # Keywords by instrument
    KEYWORDS = {
        "AUDUSD": ["AUD","Australian","RBA","Reserve Bank Australia","iron ore","China demand"],
        "EURUSD": ["EUR","Euro","ECB","European Central Bank","eurozone"],
        "GBPUSD": ["GBP","Sterling","BOE","Bank of England","Brexit"],
        "XAUUSD": ["gold","XAU","Fed","Federal Reserve","inflation","CPI","DXY",
                   "Treasury yields","real yields","geopolitical","safe haven",
                   "central bank","rate hike","rate cut","FOMC"],
        "USDJPY": ["JPY","yen","BOJ","Bank of Japan","intervention",
                   "carry trade","risk off","risk on","Treasury yields",
                   "Kishida","Ueda","yen weakness"],
        "USD":    ["Fed","Federal Reserve","FOMC","USD","NFP","nonfarm payroll"],
        "NZDUSD": ["NZD","New Zealand","RBNZ","kiwi","dairy"],
        "USDCAD": ["CAD","Canadian","BOC","Bank of Canada","oil price","crude"],
        "EURJPY": ["EUR","Euro","ECB","JPY","yen","BOJ","Bank of Japan"],
        "GBPJPY": ["GBP","Sterling","BOE","JPY","yen","BOJ","intervention"],
    }

    BLACKOUT_KEYWORDS = [
        "interest rate","rate decision","FOMC","NFP","nonfarm",
        "CPI","inflation","GDP","retail sales","RBA decision",
        "BOE decision","ECB decision","BOJ decision","emergency",
        "crisis","intervention","airstrike","military"
    ]

    # Gold-specific blackout — more sensitive to macro
    GOLD_BLACKOUT_KEYWORDS = [
        "Fed","FOMC","CPI","inflation","rate decision",
        "NFP","nonfarm","war","airstrike","nuclear",
        "emergency","crisis","sanctions","Treasury"
    ]

    def __init__(self):
        if ANTHROPIC_API_KEY != "YOUR_ANTHROPIC_KEY_HERE":
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        else:
            self.client = None
        self._cache = {}
        self.name   = "NOVA"

    # ── v10: Full 9-symbol currency map ───────────────────────
    CURRENCY_MAP = {
        "AUDUSD": ["AUD","USD"], "EURUSD": ["EUR","USD"],
        "GBPUSD": ["GBP","USD"], "NZDUSD": ["NZD","USD"],
        "USDCAD": ["CAD","USD"], "USDJPY": ["JPY","USD"],
        "EURJPY": ["EUR","JPY"], "GBPJPY": ["GBP","JPY"],
        "XAUUSD": ["USD"],       "XAGUSD": ["USD"],
    }

    # FF calendar cache — feed is rate-limited; refresh max every 4h
    _ff_cal_cache = {"ts": 0, "events": []}
    FF_CAL_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    FF_CAL_REFRESH_SEC = 4 * 3600
    BLACKOUT_BEFORE_MIN = 45   # block 45 min before high-impact event
    BLACKOUT_AFTER_MIN  = 30   # block 30 min after

    def _get_ff_calendar(self):
        """Fetch structured FF calendar JSON (cached 4h — feed is rate-limited)."""
        now = time.time()
        if now - self._ff_cal_cache["ts"] < self.FF_CAL_REFRESH_SEC:
            return self._ff_cal_cache["events"]
        try:
            resp = requests.get(self.FF_CAL_URL, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0"})
            events = resp.json()
            if isinstance(events, list):
                self._ff_cal_cache = {"ts": now, "events": events}
                logger.info(f"NOVA: FF calendar refreshed — {len(events)} events this week")
                return events
        except Exception as e:
            logger.warning(f"NOVA: FF calendar fetch failed: {e}")
        # Keep stale cache rather than nothing
        return self._ff_cal_cache["events"]

    def check_upcoming_events(self, symbol):
        """v10: Structured FF calendar — precise time-window blackout on
        High-impact events for the symbol's currencies. Far more accurate
        than the old RSS headline keyword matching."""
        relevant = self.CURRENCY_MAP.get(symbol, ["USD"])
        now = datetime.now(tz=timezone.utc)
        try:
            for ev in self._get_ff_calendar():
                if ev.get("impact") != "High":
                    continue
                if ev.get("country") not in relevant:
                    continue
                # FF dates are ISO with offset e.g. 2026-06-11T08:30:00-04:00
                try:
                    ev_dt = datetime.fromisoformat(ev["date"])
                except Exception:
                    continue
                delta_min = (ev_dt - now).total_seconds() / 60
                if -self.BLACKOUT_AFTER_MIN <= delta_min <= self.BLACKOUT_BEFORE_MIN:
                    return True, (f"High-impact {ev.get('country')} event: "
                                  f"{ev.get('title','?')} at {ev_dt.strftime('%H:%M UTC')}")
        except Exception as e:
            logger.debug(f"NOVA calendar check: {e}")

        # Fallback: legacy RSS keyword scan (kept as safety net)
        try:
            feed = feedparser.parse("https://www.forexfactory.com/feed")
            blackout_kw = (self.GOLD_BLACKOUT_KEYWORDS
                          if is_gold(symbol) else self.BLACKOUT_KEYWORDS)
            for entry in feed.entries[:30]:
                title = entry.get("title","").lower()
                if (any(c.lower() in title for c in relevant) and
                        any(kw.lower() in title for kw in blackout_kw)):
                    return True, f"Event: {entry.get('title','')}"
        except Exception as e:
            logger.debug(f"FF RSS: {e}")
        return False, ""

    def get_next_event_window(self, symbol):
        """Returns (minutes_until_next_high_impact, event_title) or (None, '').
        ORACLE can use this to avoid entries that would still be open into news."""
        relevant = self.CURRENCY_MAP.get(symbol, ["USD"])
        now = datetime.now(tz=timezone.utc)
        best = None; best_title = ""
        for ev in self._get_ff_calendar():
            if ev.get("impact") != "High" or ev.get("country") not in relevant:
                continue
            try:
                ev_dt = datetime.fromisoformat(ev["date"])
            except Exception:
                continue
            mins = (ev_dt - now).total_seconds() / 60
            if mins > 0 and (best is None or mins < best):
                best = mins; best_title = ev.get("title","?")
        return best, best_title

    def get_headlines(self, symbol):
        now = time.time()
        if symbol in self._cache:
            ct, ch = self._cache[symbol]
            if now - ct < NEWS_CACHE_SEC:
                return ch

        headlines = []
        keywords  = self.KEYWORDS.get(symbol, []) + self.KEYWORDS["USD"]

        if NEWS_API_KEY and NEWS_API_KEY != "YOUR_NEWSAPI_KEY_HERE":
            try:
                query = " OR ".join(keywords[:4])
                resp  = requests.get(
                    "https://newsapi.org/v2/everything",
                    params={"q": query,"language":"en",
                            "sortBy":"publishedAt","pageSize":6,
                            "apiKey": NEWS_API_KEY},
                    timeout=10
                )
                data = resp.json()
                if data.get("status") == "ok":
                    for a in data.get("articles",[])[:6]:
                        t = a.get("title","")
                        if t and "[Removed]" not in t:
                            headlines.append(t)
            except Exception as e:
                logger.warning(f"NewsAPI: {e}")

        try:
            feed = feedparser.parse("https://www.forexfactory.com/feed")
            for entry in feed.entries[:15]:
                title = entry.get("title","")
                if any(kw.lower() in title.lower() for kw in keywords[:4]):
                    headlines.append(title)
        except Exception:
            pass

        headlines = list(dict.fromkeys(headlines))[:8]
        self._cache[symbol] = (now, headlines)
        return headlines

    def analyse(self, kira_brief):
        symbol    = kira_brief["symbol"]
        direction = kira_brief["direction"]
        grade     = kira_brief["grade"]

        blackout, b_reason = self.check_upcoming_events(symbol)
        if blackout:
            logger.info(f"NOVA blackout {symbol}: {b_reason}")
            return {"agent":"NOVA","verdict":"BLACKOUT","nova_score":0,
                    "sentiment":"BLOCKED","reason":b_reason,"headlines":[]}

        headlines = self.get_headlines(symbol)
        if not self.client:
            return self._no_api(symbol, headlines)
        if not headlines:
            return {"agent":"NOVA","verdict":"PROCEED","nova_score":58,
                    "sentiment":"NEUTRAL","reason":"No recent headlines",
                    "headlines":[]}

        # Gold gets specialised macro context
        if is_gold(symbol):
            context = (
                "Gold is driven by: USD strength (inverse), "
                "real Treasury yields (inverse), inflation expectations (positive), "
                "geopolitical risk (positive), Fed policy (hawkish=bearish gold)."
            )
        elif is_jpy(symbol):
            context = (
                "USDJPY is driven by: US-Japan rate differential, "
                "BOJ intervention risk (extreme yen weakness triggers), "
                "risk-off flows (buy JPY = USDJPY falls), "
                "US Treasury yields (positive correlation)."
            )
        else:
            context = f"Forex pair {symbol} driven by central bank policy and risk flows."

        prompt = f"""You are NOVA, a professional forex news analyst AI agent.

KIRA signal:
  Pair:      {symbol}
  Direction: {direction}
  Grade:     {grade}

Market context: {context}

Headlines (last 2 hours):
{chr(10).join([f'- {h}' for h in headlines])}

Task: Does current news CONFIRM, CONTRADICT, or is NEUTRAL to the {direction} signal?

Respond ONLY in JSON (no other text):
{{
  "verdict": "PROCEED" | "DELAY" | "CANCEL",
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL" | "MIXED",
  "nova_score": 0-100,
  "reason": "One sentence explaining news impact",
  "key_headline": "Most important headline"
}}

Rules:
PROCEED: news neutral or confirms direction (nova_score 50+)
DELAY:   major event next 2hr OR mixed signals
CANCEL:  news directly and strongly contradicts direction"""

        try:
            response = self.client.messages.create(
                model=MODEL_SONNET, max_tokens=250,
                messages=[{"role":"user","content":prompt}]
            )
            raw    = response.content[0].text.strip()
            raw    = raw.replace("```json","").replace("```","").strip()
            result = json.loads(raw)
            result["agent"]     = "NOVA"
            result["headlines"] = headlines
            logger.info(f"NOVA {symbol}: {result['verdict']} {result.get('nova_score',50)}")
            return result
        except Exception as e:
            logger.error(f"NOVA API: {e}")
            return self._fallback(headlines)

    def _no_api(self, symbol, headlines):
        return {"agent":"NOVA","verdict":"PROCEED","nova_score":55,
                "sentiment":"NEUTRAL","reason":"No API key","headlines":headlines}

    def _fallback(self, headlines):
        return {"agent":"NOVA","verdict":"PROCEED","nova_score":55,
                "sentiment":"NEUTRAL","reason":"Sentiment check failed","headlines":headlines}
