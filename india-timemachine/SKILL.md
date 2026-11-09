---
name: india-timemachine
description: >-
  Indian NSE time machine. Replays the rest of a long-only intraday plan
  10,000 times from the stock's own historical five-minute candle moves,
  re-runs the opening-range rule on past sessions, subtracts configurable
  round-trip Indian trading costs, applies optional NSE circuit limits, and
  reports net expected value in rupees and R. Use for "simulate my NSE trade",
  "replay this Indian setup", "what are the odds", "run the India time
  machine", or "backtest this opening-range breakout".
argument-hint: "run [--plan trader/plan.json] [--seed 19] [--write]"
---

# india-timemachine

This skill is a simulation, not a prediction. It does not place orders or
claim that historical candle resampling predicts the next NSE session.

```bash
python3 timemachine.py run
python3 timemachine.py run --seed 7 --replays 20000 --write
python3 timemachine.py run --offline tests/fixtures/india-timemachine/chart.json
python3 timemachine.py run --circuit-limit 5 --json
```

The simulator reads the Indian plan written by
[`india-exit`](../india-exit/SKILL.md), downloads or reads a saved Yahoo chart,
keeps complete 75-bar NSE sessions from 09:15 through 15:30 IST, and builds a
same-time-of-day move pool from those sessions. Each path samples nearby
five-minute slots with a deterministic `random.Random(seed)`. The default is
10,000 paths and seed 19.

Each path walks from the recorded entry to the configured flat-by/close
window. A bar touching both stop and target counts as stop first, a
conservative convention. The simulator reports target-first, stop-first, and
neither-by-close probabilities, median simulated exit, average net rupees, and
average net R. Net results subtract the round-trip brokerage, STT, exchange,
SEBI, stamp-duty, and GST configuration from
[`india_common.py`](../india_common.py); replace the zero placeholders in
`trader/config.json` with the broker's current charge sheet.

Circuit limits are not discoverable reliably from Yahoo chart candles. Supply
`--circuit-limit PERCENT` or pass a configured band to the Python API; paths
are then capped to the corresponding price band. If no band is supplied, the
output explicitly warns that no circuit cap was applied.

The historical replay applies the same opening-range breakout rule to every
complete prior session and reports its triggered trades separately. Fewer than
20 complete sessions is an error rather than a success-shaped result. Missing
bars, halts, gaps, corporate actions, news, slippage, and future regime changes
can invalidate the simulation. Review the warnings and current NSE data before
making any decision. This is not financial advice.
Simulation output is not an order; continue through sizing and risk checks,
then require the broker's exact lowercase `yes` response and separate Claude
Allow/Deny approval before any ticket.

## Operating assumptions

The plan is interpreted as a long entry, a lower stop, and a higher target.
The first three five-minute candles define the default opening range.
Historical sessions must contain all 75 regular NSE candles to enter the pool.
Partial sessions are reported as skipped rather than filled synthetically.
The simulation checks the stop before the target when both occur in one candle.
The random seed controls every slot and candle selection.
Changing the seed intentionally changes the sample paths and probabilities.
The historical rule replay uses the same opening-range and target-R convention.
Net rupees are per one-share-equivalent position, before position sizing.
Net R divides net rupees by the plan's per-share risk.
Broker fees are only as accurate as the current trader/config.json values.
STT, GST, stamp duty, exchange charges, and SEBI fees may vary by broker.
Circuit-limit percentages must be supplied from current NSE security data.
An omitted circuit limit is explicitly reported and is not inferred.
The simulator does not model partial fills, market impact, or overnight gaps.
