# FX Command Agents — Claude Code Briefing Document
*Prepared 3 July 2026. Use this as the opening context when starting a Claude Code session on this project, including future upgrade work with Claude Fable 5.*
---
## 1. What This Is
FX Command Agents is an autonomous MT5 (MetaTrader 5) forex and gold trading system built and iterated solo by Mahesh over roughly six weeks (late May – 11 June 2026). It runs five independent signal-generation engines under a shared routing layer, six AI/rule-based agents for execution, risk, news, learning, and self-review, and currently operates in SIM_MODE (paper trading on a MetaQuotes demo account, zero real capital at risk).
The system is validated, not just backtested: a walk-forward test (5/5 out-of-sample folds profitable) and a 10,000-run Monte Carlo stress test back the current baseline. It is one build away from a live-money decision, gated on accumulating 30 SIM signals.
**Owner's stated goal for this session:** bring the codebase into Claude Code, understand it well enough to extend it, and later use Claude Fable 5 specifically for the upgrade work.
---
## 2. Version Lineage (confirmed from three uploaded zips + Notion)
| Version | What changed | Signals | WR | Net P&L | Sharpe | Max DD | PF |
|---|---|---|---|---|---|---|---|
| v3 (baseline) | Original 2-engine system | 79 | 55.7% | +RM1,214 | 1.15 | 13.9% | 1.77 |
| v7 | Full 8-symbol universe, no filtering | 396 | 43.4% | +RM3,863 | 2.27 | 19.8% | 1.85 |
| v8 | KIRA adaptive routing, GUARD clustering, XAGUSD M15 fix attempt | 396 | 43.4% | +RM3,927 | 2.30 | 18.1% | 1.86 |
| v9 | Engine×symbol whitelist precision layer (had a bug — `ALL_SYMBOLS` built from CTE whitelist only, silently dropped RM+563 of good trades) | — | — | — | — | — | — |
| **v10 (CONFIRMED BASELINE)** | Fixed v9 bug, dropped unstable GBPJPY-MRE, removed CTE double-filter, full agent upgrades | **287** | **49.5%** | **+RM4,192** | **2.53** | **12.6%** | **2.19** |
| v11 | Added walk-forward validator (`walkforward_v11.py`), Monte Carlo fixed-mode only | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 |
| **v11.1 ("THE MILESTONE")** | Monte Carlo upgraded to compounding mode, GUARD capital-adequacy rule (0.7× risk until balance ≥1.5× start) | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 |
| **v12 (CURRENT — `fx_agents_v12_final`)** | Added SAGE (self-review agent), Prop Firm Mode in GUARD | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 |
**Key point:** v10 → v12 is entirely risk-management, validation, and oversight tooling. No version past v10 has changed the trading logic or improved the WR/profit numbers — they're all running the same validated core (`backtest_master_v10.py`). Any real performance upgrade (the kind Fable 5 work would target) means new signal logic, not new agents.
There is a separate, unrelated "v12" naming collision to be aware of: **GVE v12** refers to the Gold Volatility Engine's own internal version history (39 signals, WR 69.2%, PF 1.90, Max DD 15.9%), reached earlier and independently of the system-level v12. Don't conflate the two in conversation with Claude Code — always say "system v12" or "GVE v12" explicitly.
---
## 3. Validation Findings (why v10 is trusted)
1. **Edge is structural, not curve-fit** — walk-forward test: every out-of-sample fold profitable across 2023–2026, 5/5, median PF 1.86.
2. **Don't re-filter combos in short windows** — trading all 20 v10 engine×symbol combos beat per-fold re-whitelisting in 5/5 folds (RM+2,506 vs RM+1,301 OOS). Edges are lumpy; a quiet patch isn't a dead edge. This is why the alpha-decay monitor (ATLAS) uses a catastrophe-brake model (window 25, degrade at PF<0.7, suspend at PF<0.4) instead of aggressive re-filtering.
3. **The 12.6% backtest max DD was a lucky path** — Monte Carlo (10,000 sims) shows median DD 21.9%, P95 53.8%, and a 4.09% risk of ruin in fixed-size mode. This is why GUARD's capital-adequacy rule and compounding-mode Monte Carlo exist.
4. **XAGUSD (Silver) is suspended**, not dropped for lack of trying — tested across all 5 engines. CBE was catastrophic on Silver (PF 0.28, -RM466, MaxDD 93.3%) due to pip-value oversizing on the 5000oz contract and compression logic misfiring on Silver's volatility profile. Root causes are documented in Notion; re-enabling needs Silver-specific calibration (GVE needs ~99,999 M15 candles not 3,000; MRE min_range should be 50–100 pips not 500).
---
## 4. Architecture
### 4.1 Five Signal Engines (all inside `agent_kira.py`)
| Engine | Full name | Symbols (whitelisted) | Regime | Notes |
|---|---|---|---|---|
| **CTE** | Continuation Engine (renamed from CTN) | AUDUSD, EURJPY, EURUSD, GBPJPY, NZDUSD | TRENDING / WEAK_TREND | D1 EMA bias → H4 VP zone → H1 sweep+FVG+rejection. Friday blocked. |
| **GVE** | Gold Volatility Engine (v12 internal — see §2) | XAUUSD only | — | London Open 07:00–09:00 UTC only, BUY only, Grade A+B, M15 sweep + H4 EMA slope filter, SL cap $35 |
| **MRE** | Mean Reversion Engine | AUDUSD, EURUSD, GBPUSD, NZDUSD, USDJPY | RANGING only | D1 range detection → H4 extreme proximity → H1 RSI overextension. TP = range midpoint, SL = 8 pips beyond boundary |
| **CBE** | Compression Breakout Engine | AUDUSD, EURJPY, GBPJPY, GBPUSD, NZDUSD, USDCAD | COMPRESSING only | D1 ADX<15 + H4 range/ATR<4.0 → breakout + momentum candle. TP = compression range × 1.8 |
| **HPE** | HTF Pullback Engine | EURUSD, USDCAD, USDJPY | TRENDING only | D1 pivot-based, BUY only, probationary (0.5× sizing until 20 live signals) |
**XAUUSD → GVE only. XAGUSD → suspended (no engine currently whitelisted).**
### 4.2 Six Agents
| Agent | Role | Model/cost |
|---|---|---|
| **KIRA** | Regime classifier + adaptive routing (`KIRA_ROUTING_TABLE` → `_route_engine()` → `_dispatch_engine()`) + technical analysis on real MT5 data | Python only, free |
| **NOVA** | News/sentiment filtering, ForexFactory calendar JSON blackouts, 9-symbol coverage | Claude Sonnet, ~RM0.013/signal |
| **ATLAS** | Pattern learning from trade history, alpha-decay catastrophe-brake, extended COT data (7 markets), MAE/MFE advisory | Claude Haiku, ~RM0.005/signal |
| **GUARD** | Risk management: daily/weekly/monthly loss limits, DD tiers (10%→0.5% risk, 20%→STOP), clustering protection (Tier1 0.5× after 3 consec losses, Tier2 0.25× after 5), capital-adequacy rule, currency exposure shield, Prop Firm Mode (v12) | Claude Haiku, ~RM0.003/signal |
| **ORACLE** | Master orchestrator, final decision, decision journal, attribution report, Telegram delivery | Claude Sonnet, ~RM0.022/signal |
| **SAGE (v12, new)** | Weekly self-review — perception (reads ORACLE journal + ATLAS history + combo health) → Claude reasoning → proposed action → **human approval required, never auto-changes parameters** | Claude (model TBD in code), run via cron/Task Scheduler |
Total cost per signal: ~RM0.043. Monthly cost at 2 signals/day: ~RM1.87 API + ~RM15 electricity ≈ RM16.87.
### 4.3 Prop Firm Mode (v12, in `agent_guard.py` / `config.py`)
Off by default (`PROP_MODE = False`). When enabled: risk per trade drops from 1.0% to 0.5%, daily stop at -3% (vs typical prop rule of 5%), total DD halt at 7% (vs typical rule of 10%), max 2 concurrent positions. Designed so a prop-firm rule breach is structurally impossible — internal limits are always tighter than the external rule. The system's low trade frequency (~6/month, H1+ holds) is noted as compliant with standard prop-firm EA rules (no HFT/arbitrage bans triggered).
---
## 5. File Structure (`fx_agents_v12_final/`)
```
fx_agents_v12_final/
├── main_agents.py           ← autonomous execution loop
├── agent_kira.py             ← all 5 engines + classifier + routing (87KB, largest file)
├── agent_guard.py            ← risk management, clustering, prop mode
├── agent_atlas.py            ← pattern learning, COT, alpha-decay brake
├── agent_nova.py              ← news/calendar filtering
├── agent_oracle.py            ← orchestration, decision journal
├── agent_sage.py              ← v12 weekly self-review (NEW)
├── config.py                  ← all parameters, credentials, routing tables (28KB)
├── mt5_connector.py            ← MT5 API wrapper
├── trade_manager.py            ← position/order handling
├── telegram_commands.py        ← bot command interface
├── walkforward_v11.py          ← Pardo-standard walk-forward validator
├── montecarlo_v11.py           ← bootstrap Monte Carlo (compounding mode as of v11.1)
├── backtest_master_v10.py      ← the confirmed-baseline backtest (84KB)
├── backtest_master_v7.py       ← archived earlier backtest
├── test_full_system.py         ← pre-flight diagnostic (run this first)
├── test_candles.py
├── setup_windows.bat / start_agents.bat
├── OPERATING_GUIDE.txt         ← 3-phase guide: pre-flight → SIM → live (v12 only)
├── README_AGENTS.md            ← setup instructions
└── fx_agents.log
```
Local working copy lives at `C:\fx_agents\` on the Windows laptop (per OPERATING_GUIDE.txt: unzip there specifically, not to a Downloads path with spaces — causes MT5 issues).
---
## 6. Environment & Credentials Reference
- **MT5 Demo account:** 107377015, server MetaQuotes-Demo, SIM balance ≈ $125 USD (RM500 equiv). Password stored in your MT5 client / Notion — not reproduced here.
- **VPS (used for the separate Spark project, not FX agents):** `205.209.121.79`, credentials in Notion page `36cf0d18-b53f-81ee-8f7a-effc6f67c727` — not reproduced here.
- **Telegram bot + Anthropic API key:** already filled into `config.py` in the v12 zip (not reproduced here — treat as live secrets, don't paste config.py contents into any public repo or chat).
- **Python:** 3.11+, packages: `MetaTrader5 pandas numpy requests anthropic feedparser`
- **MT5 desktop settings required:** Tools → Options → Expert Advisors → Allow automated trading + Allow DLL imports. All 9 symbols visible in Market Watch (AUDUSD, EURUSD, EURJPY, GBPUSD, GBPJPY, NZDUSD, USDCAD, USDJPY, XAUUSD).
- **SIM_MODE = True, AUTONOMOUS_MODE = True** currently — auto-executes signals in the demo account, no manual tap needed. This is intentional and safe (no real money).
---
## 7. Current State / Where It's Stuck
- **SIM signal gate not yet cleared.** The live-deployment rule is: accumulate 30 SIM signals with WR > 50%, then go live at RM500. As of the last Notion update this counter had not reached 30 — check `fx_agents.log` or ORACLE's decision journal for the current count when you start.
- **v12's SAGE and Prop Firm Mode are unvalidated additions** — they exist in code but don't have their own backtest/live-performance confirmation the way v10's core does. Don't assume they've been proven; they're operational/oversight features layered on a proven core.
- **XAGUSD is off** and needs the specific calibration fixes noted in §3 before any engine can be re-enabled on it.
- **This zip (`fx_agents_v12.zip`) contains two near-duplicate folders**: `fx_agents_v12/` (05:58) and `fx_agents_v12_final/` (07:23, +`OPERATING_GUIDE.txt`). Use `fx_agents_v12_final/` as the working copy — it's the completed one.
- **Notion page `36cf0d18-b53f-81ee-8f7a-effc6f67c727`** ("FX Command Agents — Live 27 May 2026") is the canonical system-state log but currently only has entries up to v11.1 — the v12 SAGE/Prop Firm Mode work hasn't been written back there yet.
---
## 8. What "Upgrading This" Likely Means
Given that v10→v12 was all oversight tooling with flat performance, the highest-leverage next moves for a Fable 5 session are probably:
1. **New/improved signal logic** — the only lever that moves WR/profit. Candidates already flagged in the codebase's own notes: re-attempt XAGUSD with the specific parameter fixes noted (§3); explore whether HPE graduates out of probationary status; investigate whether NZDUSD's special CTE regime permission (TRENDING + WEAK_TREND, unlike every other symbol) generalizes.
2. **Closing the SIM gate** — get to 30 signals, verify WR > 50% holds live vs backtest, then execute the go-live decision at RM500.
3. **Wiring SAGE's proposals into an actual review habit** — it's built to propose changes for human approval; there's no evidence yet it's been run on a real weekly cadence.
4. **Writing the v12 changelog back to Notion** so the project state and the code stop drifting apart (currently offered, not yet done as of this doc).
---
## 9. Suggested Opening Prompt for Claude Code
```
I'm working on FX Command Agents, an autonomous MT5 forex/gold trading system.
Full background is in FX_Command_Agents_Claude_Code_Briefing.md in this repo —
read it first. Current version: v12 (fx_agents_v12_final/), built on the
validated v10 baseline (287 signals, WR 49.5%, RM+4,192, Sharpe 2.53, DD 12.6%,
PF 2.19, walk-forward validated 5/5 OOS folds). SIM_MODE=True, not live yet.
Today's task: [describe task]
```
---
*This document was compiled from the Notion system-state page, three uploaded zip files (fx_agents_v11.zip, fx_agents_v11_1.zip, fx_agents_v12.zip), and prior chat history. It does not include live credentials — pull those from config.py locally or Notion when needed.*
