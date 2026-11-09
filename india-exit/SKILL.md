---
name: india-exit
description: >-
  Indian NSE long-only exit planner. Reads trader/entry.json, selects an
  opening-range midpoint or low, fixed-price, percent, or ATR stop, rounds to
  the configured NSE tick size, calculates 1R or 2R targets, rejects unsafe
  plans, and warns when a planned exit is after the IST flat-by time. Use for
  "plan my NSE stop", "set the Indian target", "make an exit plan", "use ATR
  stop", or "where should I square off".
argument-hint: "plan [--stop or-mid] [--target 1R] [--write]"
---

# india-exit

This skill prepares a long-only risk plan before entry. It never places an
order. It uses [`india_common.py`](../india_common.py) for tick-size
configuration and [`india-entry`](../india-entry/SKILL.md) output.

```bash
python3 exit.py plan
python3 exit.py plan --stop or-mid --target 1R --write
python3 exit.py plan --stop pct:1 --target 2R
python3 exit.py plan --stop price:2450 --target price:2500
python3 exit.py plan --stop atr:1.5 --atr-value 12.4 --target 1R
```

Stops are `or-mid` (default), `or-low`, `price:X`, `pct:X`, or `atr:K`.
Targets are `1R`, `2R`, another positive `NR`, or `price:X`. A long stop is
rounded down to the configured per-symbol NSE tick, away from the entry; a
target is rounded using half-up rounding. The default tick is Rs 0.05 and
overrides belong in `trader/config.json`.

The planner refuses a stop at or above entry, a target at or below entry, a
missing opening range for an opening-range stop, or risk below 0.05 percent of
entry because that is too tight to survive the spread. ATR is computed from
the available session bars when supplied by a caller; a short side is not
supported.

`flat_by` defaults to 15:15 IST from the shared Indian configuration. Use
`--exit-time` to record the intended exit time. If it is after flat-by, the
plan is still produced but includes and prints an explicit warning. Squaring
off before the broker's actual cutoff remains the trader's responsibility.

The plan reads only `entry.json`, writes `trader/plan.json` with `--write`, and
does not silently invent an entry when the entry status is not triggered.
Missing or malformed files are errors. Verify charges, liquidity, slippage,
and broker square-off rules independently. This is not financial advice.

## Operating assumptions

All plan times are wall-clock IST values.
The plan is for long positions only; short stops are not inferred.
The midpoint stop is calculated from the entry module's recorded range.
The low stop uses the recorded opening-range low without inventing a range.
Percent stops are percentages below the rounded entry.
ATR stops use true range and the available completed session bars. The CLI
accepts a verified completed-session ATR through `--atr-value`.
The default ATR lookback is 14 bars, or fewer when less history exists.
Tick size is read per symbol from trader/config.json when configured.
The Rs 0.05 default is a market convention, not broker confirmation.
Stops round downward to avoid moving risk closer to the entry.
Targets round to the nearest configured tick using half-up rounding.
The spread guard is a conservative 0.05 percent of entry.
A flat-by warning does not place a square-off order or change broker behavior.
Review slippage, gaps, taxes, and charges separately before using a plan.
