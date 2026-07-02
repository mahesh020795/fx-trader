# FX Command Agents — Version History

Every system version, what changed, and how to revert. From v13 onward each
version is a **git tag** — revert with `git checkout <tag>` (or
`git checkout -b rollback-<tag> <tag>` to branch from it). Versions v3–v12
predate git; their snapshots live in `Archive/` (not in git — old configs
contain secrets).

**Rule: `config.py` is never committed** (live Telegram + Anthropic keys).
Parameter changes are recorded in this file's notes instead.

## Version Table

| Version | Date | What changed | Signals | WR | Net P&L | Sharpe | Max DD | PF | Revert via |
|---|---|---|---|---|---|---|---|---|---|
| v3 | May 2026 | Original 2-engine system | 79 | 55.7% | +RM1,214 | 1.15 | 13.9% | 1.77 | `Archive/v3` |
| v7 | Jun 2026 | Full 8-symbol universe, no filtering | 396 | 43.4% | +RM3,863 | 2.27 | 19.8% | 1.85 | `Archive/` + fx_agents_v11.zip lineage |
| v8 | Jun 2026 | KIRA adaptive routing, GUARD clustering, XAGUSD fix attempt | 396 | 43.4% | +RM3,927 | 2.30 | 18.1% | 1.86 | — |
| v9 | Jun 2026 | Engine×symbol whitelist (had ALL_SYMBOLS bug, dropped RM+563) | — | — | — | — | — | — | — |
| **v10** | Jun 2026 | **CONFIRMED BASELINE** — fixed v9 bug, dropped GBPJPY-MRE, removed CTE double-filter | **287** | **49.5%** | **+RM4,192** | **2.53** | **12.6%** | **2.19** | `backtest_master_v10.py` is the reference |
| v11 | Jun 2026 | Walk-forward validator, Monte Carlo (fixed mode) | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 | — |
| v11.1 | Jun 2026 | Monte Carlo compounding mode, GUARD capital-adequacy rule | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 | — |
| v12 | 14 Jun 2026 | SAGE self-review agent, Prop Firm Mode in GUARD | 287 | 49.5% | +RM4,192 | 2.53 | 12.6% | 2.19 | git tag `v12` (initial commit) |
| v13 | Jul 2026 (in progress) | Validated Signal Expansion — new symbol universe test, XAGUSD recalibration, GVE SELL/NY variants, sell-side engine mirrors, new-market compatibility scan. Spec: `docs/specs/2026-07-03-v13-signal-expansion-design.md` | TBD | TBD | TBD | TBD | TBD | TBD | git tag `v13` when complete |

## Naming note

"GVE v12" is the Gold Volatility Engine's **internal** version number (39
signals, WR 69.2%, PF 1.90) and is unrelated to system v12. Always say
"system vN" or "GVE vN".

## Changelog discipline (from v13 onward)

1. Every meaningful change = a git commit with a message explaining *why*.
2. Every completed system version = a git tag `vN` + a row in the table above.
3. Performance numbers in the table come from `backtest_master_v13.py` (or
   its successor) runs — never estimates.
4. Live-config promotions (whitelist/routing changes) are listed explicitly
   in the version's notes, since `config.py` itself is untracked.
