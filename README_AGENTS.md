# FX COMMAND AGENTS — 5-Agent System Setup Guide

## The 5 Agents

| Agent | Role | Model | Cost |
|---|---|---|---|
| KIRA | Technical analysis on real MT5 data | Python only | Free |
| NOVA | News and sentiment analysis | Claude Sonnet | ~RM0.013/signal |
| ATLAS | Pattern learning from your trades | Claude Haiku | ~RM0.005/signal |
| GUARD | Risk management and capital protection | Claude Haiku | ~RM0.003/signal |
| ORACLE | Master orchestrator, final decision | Claude Sonnet | ~RM0.022/signal |

Total cost per signal: ~RM0.043 (4.3 sen)
Monthly cost (2 signals/day): ~RM1.87 Claude API + RM15 electricity = RM16.87

---

## STEP 1 — Install MT5 on Laptop

1. Go to xm.com → Platforms → MetaTrader 5 → Download
2. Install MT5
3. Login: File → Login → Account 107377015 | Password: 7kZ!FkGs | Server: MetaQuotes-Demo
4. Add pairs: Right-click Quotes → Show Symbols → AUDUSD, EURUSD, GBPUSD
5. Leave MT5 running — agents connect to it

---

## STEP 2 — Install Python

1. python.org/downloads → Python 3.11+
2. ⚠️ Check "Add Python to PATH" during install
3. Verify: open Command Prompt → type: python --version

---

## STEP 3 — Install Libraries

Open Command Prompt:
```
pip install MetaTrader5 pandas numpy requests anthropic feedparser
```

---

## STEP 4 — Get Your 4 API Keys

**Telegram Bot Token:**
1. Open Telegram → search @BotFather
2. /newbot → name it → get token like: 1234567890:ABCdef...
3. Start a chat with your new bot (send any message)

**Telegram Chat ID:**
1. Search @userinfobot on Telegram
2. Send any message → it replies with your ID

**NewsAPI Key (free):**
1. newsapi.org → Get API Key → sign up → copy key

**Anthropic API Key:**
1. console.anthropic.com → sign up → API Keys → Create Key
2. Copy sk-ant-... key (shown once only)
3. ~$5 free credits on signup = ~11 months free at 2 signals/day

---

## STEP 5 — Configure

Open config.py in Notepad. Fill in only these 4 lines:
```python
TELEGRAM_BOT_TOKEN = "paste your bot token"
TELEGRAM_CHAT_ID   = "paste your chat ID"
NEWS_API_KEY       = "paste your newsapi key"
ANTHROPIC_API_KEY  = "paste your sk-ant key"
```
Save. Done.

---

## STEP 6 — Run Setup Scripts

Right-click setup_windows.bat → Run as Administrator
(Disables sleep/hibernate — one time only)

---

## STEP 7 — Start the Agents

Make sure MT5 is open and showing live prices first.

Option A — Double-click start_agents.bat
Option B — Command Prompt:
```
cd C:\Users\YourName\fx_agents
python main_agents.py
```

You will see:
```
FX COMMAND AGENTS — 5-Agent System Starting
KIRA · NOVA · ATLAS · GUARD · ORACLE
MT5 connected: 107377015
All 5 agents running
```

Your Telegram receives the startup message.

---

## How Signals Work

When ORACLE approves a signal you receive this on Telegram:

```
🏆 ORACLE SIGNAL — GRADE A

🔴 ▼ SELL AUDUSD | ⭐ FULL ALIGN
Composite Score: 78/100

📊 KIRA (Technical) — 90/100
  D1:🔴 4H:🔴 1H:🔴 15M:🔴

📰 NOVA (News) — 72/100
  PROCEED · BEARISH
  Bad RBA data confirms selling thesis

📈 ATLAS (Patterns) — 68/100
  Your win rate: 65% (12 trades)
  COT: Institutions 71% net short AUD

🛡 GUARD (Risk) — 85/100
  Risk: 1% | Session: 🔥 Peak

📍 COPY TO MT5
  Entry:      0.71615
  Stop Loss:  0.71765
  Take Profit: 0.71235
  Breakeven:  0.71425

📦 Position
  Lots: 0.01 | R:R: 1:2.53
  Risk: -RM5.97 | Profit: +RM15.12

[✅ APPROVE] [❌ REJECT] [⏳ DELAY 1HR]
```

Tap ✅ APPROVE → agents place trade automatically.
You have 15 minutes to decide.

---

## What Agents Do After Trade Placed

```
GUARD monitors every 30 seconds:
→ When price hits breakeven trigger → moves SL to entry
→ You receive: "🛡 BREAKEVEN ACTIVATED"

When TP or SL hits:
→ MT5 closes trade automatically
→ ORACLE sends result to Telegram
→ ATLAS records outcome and learns
→ KIRA updates win/loss streaks
```

---

## Going Live (When Ready)

After 20+ demo trades with green readiness score:

1. Open XM real account at xm.com
2. Deposit RM500 minimum
3. Update config.py:
   - MT5_LOGIN = your real account number
   - MT5_PASSWORD = your real password
   - MT5_SERVER = your real server
   - SIM_MODE = False
4. Restart agents

---

## File Structure

```
fx_agents/
├── main_agents.py      ← Run this
├── agent_kira.py       ← Technical analysis
├── agent_nova.py       ← News sentiment
├── agent_atlas.py      ← Pattern learning
├── agent_guard.py      ← Risk management
├── agent_oracle.py     ← Orchestrator + Telegram
├── mt5_connector.py    ← MT5 connection
├── trade_manager.py    ← Trade tracking
├── config.py           ← Your settings
├── setup_windows.bat   ← Run once as Admin
├── start_agents.bat    ← Start agents
├── trade_history.json  ← Auto-created
├── pattern_database.json ← Auto-created
└── fx_agents.log       ← Auto-created
```

---

## Troubleshooting

**"Cannot connect to MT5"**
→ Open MT5 first, login, then run agents

**"Telegram messages not coming"**
→ Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
→ Make sure you sent a message to your bot first

**"No signals firing"**
→ Agents only signal during 8AM-10PM UTC (3PM-5AM MYT)
→ Check MT5 is showing live prices

**Agents crash with error**
→ Check fx_agents.log → send error to Claude

---

## Monthly Cost Reminder

```
Electricity:   RM15.00
Claude API:     RM1.87  (2 signals/day average)
Everything else: RM0.00
─────────────────────────────
TOTAL:         RM16.87/month

First 11 months: RM0 (covered by free Anthropic credits)
```

Built by Claude for Mahesh Rajagopal
FX Command Agents v1.0 — May 2026
