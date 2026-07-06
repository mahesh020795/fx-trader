# v14 Profile Probe — 2026-07-06

| sym | cls | contract | tick_val | tick_size | point | pip | pip_val_rm(0.01) | M15 bars | ATR_M15 | spread %ATR | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| XAUEUR | gold_cross | 100.0 | 1.14312 | 0.01 | 0.01 | 0.1 | 0.45496 | 99999 | 6.635 | 62.5 | OUT(spread) |
| XAUGBP | gold_cross | 100000.0 | 1334.26 | 0.01 | 0.01 | 0.1 | 531.03548 | 98948 | 5.585 | 3.6 | OUT(risk) |
| XAUAUD | gold_cross | 100.0 | 0.69315 | 0.01 | 0.01 | 0.1 | 0.27587 | 99999 | 10.13 | 42.7 | OUT(spread) |
| US500 | index | 1.0 | 0.01 | 0.01 | 0.01 | 1.0 | 0.0398 | 99999 | 6.7 | 7.5 | IN |
| US30M | index | 0.1 | 0.1 | 1.0 | 1.0 | 1.0 | 0.00398 | 99999 | 42.0 | 14.3 | IN |
| USTECH100M | index | 1.0 | 0.1 | 0.1 | 0.1 | 1.0 | 0.0398 | 99999 | 39.1 | 9.5 | IN |
| UK100 | index | 10.0 | 0.1 | 0.1 | 0.1 | 1.0 | 0.0398 | 51640 | 11.1 | 9.9 | IN |
| JPN225 | index | 100.0 | 100.0 | 1.0 | 1.0 | 1.0 | 3.98 | 99999 | 134.0 | 14.2 | OUT(risk) |
| AUS200 | index | 10.0 | 0.1 | 0.1 | 0.1 | 1.0 | 0.0398 | 99999 | 11.4 | 26.3 | OUT(spread) |
| EUSTX50 | index | 1.0 | 0.1 | 0.1 | 0.1 | 1.0 | 0.0398 | 99999 | 8.8 | 27.3 | OUT(spread) |
| DE40 | index | 1.0 | 0.011431199999999999 | 0.01 | 0.01 | 1.0 | 0.0455 | 99999 | 32.5 | 6.2 | IN |
## London-hours spread re-probe addendum (07:19 UTC, market fully open)

| sym | quiet-hours %ATR | London spread | London %ATR | FINAL verdict |
|---|---|---|---|---|
| XAUEUR | 62.5 | 4.160 | 62.7 | **OUT — spread structural, not artifact** |
| XAUAUD | 42.7 | 4.330 | 42.7 | **OUT — spread structural** |
| AUS200 | 26.3 | 2.000 | 17.5 | OUT (improved, still >15%) |
| EUSTX50 | 27.3 | 1.900 | 21.6 | OUT |
| US500 | 7.5 | 0.500 | 7.5 | **IN** |
| US30M | 14.3 | 4.000 | 9.5 | **IN** |
| USTECH100M | 9.5 | 4.500 | 11.5 | **IN** |
| UK100 | 9.9 | 1.100 | 9.9 | **IN** |
| DE40 | 6.2 | 0.500 | 1.5 | **IN** (conditional cleared decisively) |

**Consequences:** Task 2 (GVE gold crosses) CANCELLED — all three crosses untradeable on this broker (XAUGBP contract trap; XAUEUR/XAUAUD spreads confirmed structural at peak liquidity). Phase A index universe FINAL: US500, US30M, USTECH100M, UK100, DE40.
