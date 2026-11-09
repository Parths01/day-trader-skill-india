---
name: india-entry
description: >-
  Indian NSE entry timer for long-only trades. Builds the 09:15-09:30 IST
  opening range from completed five-minute bars, checks an optional volume
  multiple or user level, reports waiting, triggered, expired, or not-open-yet,
  and writes trader/entry.json. Use for "time my NSE entry", "check the Indian
  ORB", "did the breakout trigger", "watch this NSE setup", or "check the
  opening range".
argument-hint: "check SYMBOL [--now HH:MM] [--offline FILE] [--write]"
---

# india-entry

This skill times a possible long entry; it does not place an order and does
not make a recommendation. It uses [`india_common.py`](../india_common.py) for
IST and the NSE session model.

```bash
python3 entry.py check RELIANCE
python3 entry.py check RELIANCE --now "2026-11-09 10:15" --write
python3 entry.py check RELIANCE --level 2500 --min-volume-x 1.2
python3 entry.py check RELIANCE --offline tests/fixtures/india-entry/RELIANCE.json
```

The opening range is the completed 09:15, 09:20, and 09:25 five-minute bars.
The first completed close strictly above its high triggers. A wick above the
range is not enough, and a close exactly at the level is not enough. The
optional `--level` replaces the range high. `--min-volume-x` requires the
trigger bar volume to be at least that multiple of the opening-range average.

Statuses are `not_open_yet`, `waiting`, `triggered`, and `expired`. Before the
range completes the status is waiting. The entry window comes from
`trader/config.json` and defaults to 09:15-15:00 IST. A result is written only
when `--write` is supplied and the status is triggered.

Yahoo Finance is unofficial and can lag or omit illiquid bars. The scanner
accepts a saved Yahoo chart JSON file or a directory containing
`SYMBOL.json` through `--offline`, so tests can run without a network. Network
errors are reported clearly and never converted into a successful trigger.
Recheck the live NSE quote, spread, volume, and current session status before
acting. This is not financial advice.

The output includes the symbol, date, opening-range high and low, trigger
close, trigger bar time, and optional volume multiple. All times are IST.
Only completed five-minute bars on the expected grid are considered.

## Operating assumptions

The opening range is based on highs and lows, not only closing prices.
The trigger compares a completed close strictly greater than the threshold.
The range itself never triggers an entry.
A user level replaces the range high but does not change the range calculation.
The volume check uses the arithmetic mean of available range-bar volumes.
Missing, null, off-grid, and incomplete bars are excluded from evaluation.
The configured entry window is interpreted in IST and is not a broker order window.
Weekends and configured NSE holidays are not trading opportunities.
Special sessions should be represented in trader/config.json before use.
A waiting result can mean Yahoo has not posted the newest completed bar.
A not-open-yet result is informational and does not imply a pending order.
An expired result does not mean the stock cannot move later in the session.
The output price is the observed Yahoo close, not a guaranteed execution price.
Use a fresh quote and confirm the spread before placing any separate order.
