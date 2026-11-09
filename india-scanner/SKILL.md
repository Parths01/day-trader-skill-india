---
name: india-scanner
description: >-
  Indian NSE chart scanner. Builds an EQ-series universe, scans Yahoo Finance
  .NS daily bars for breakouts, bull flags, moving-average reclaims and
  oversold setups, and scans 5-minute bars for NSE opening-range breakouts.
  Use for "scan NSE", "scan Indian stocks", "find Indian breakouts", "find
  bull flags", "find oversold NSE stocks", "opening range breakout", "ORB",
  "pre-market India scan", or "build my Indian watchlist".
argument-hint: "[universe | daily | orb] [--limit N] [--nifty500]"
---

# india-scanner

This scanner produces charts to investigate, not buy recommendations. It never
places orders. It uses [`india_common.py`](../india_common.py) for IST, NSE
sessions, holidays, and symbol conversion.

```bash
python3 scan.py universe
python3 scan.py universe --nifty500
python3 scan.py daily --limit 25
python3 scan.py orb --limit 25 --min-price 20
```

`universe` downloads NSE's equity CSV and keeps only `EQ` series, caching
symbols in `trader/india_universe.json`. `--nifty500` uses the official Nifty
500 constituent CSV instead. `daily` uses three months of daily Yahoo bars:
20-day closing breakout, bull flag, reclaim of the 20-day average, RSI
oversold, and oversold bounce. `orb` uses 5-minute bars and the first 15
minutes (09:15-09:30 IST by default), then finds the first completed close
above the opening-range high.

Both scans apply minimum price and volume filters and write
`trader/watchlist.json`. Use `--offline PATH` with a directory of symbol-named
Yahoo JSON fixtures, or a symbol-keyed JSON bundle, for offline testing.
`--limit` limits the cached universe. `--pause` controls the polite delay
between requests. Failed symbols are recorded in the watchlist rather than
aborting the scan. Retries use exponential backoff; if the endpoint remains
unavailable, report the partial result and fix the network or use fixtures.

Bars can lag, contain incomplete candles, or omit illiquid symbols. A missing
or failed fetch is not evidence that a stock has no setup. Verify every hit
against live broker data, liquidity, spreads, and the current NSE holiday
configuration before acting. This is not financial advice.

## Operating assumptions

The universe cache is data, not a recommendation. Refresh it when NSE publishes a new list.
Only rows whose series is exactly EQ are retained from the NSE equity list.
Nifty 500 mode uses the constituent file and does not infer membership from ticker names.
Yahoo symbols are generated through the shared NSE helper and use the `.NS` suffix.
Daily signals use completed closes; an in-progress current-day bar is excluded before 15:30 IST.
RSI is Wilder-style RSI(14), with a 30 threshold for oversold conditions.
A bull flag is a greater-than-10-percent prior rise followed by a five-close range of five percent or less.
ORB uses completed five-minute candles and does not treat an equal close as a breakout.
The opening range starts at 09:15 IST and ends at 09:30 IST unless configured by `--or-minutes`.
Minimum price and volume are conservative defaults and can be overridden for testing.
Results are written even when some symbols fail, with each failure retained for review.
Do not treat an empty result as proof that the market is quiet: it may be a fetch failure.
Use `--offline` fixtures to reproduce a scan without network access or rate limits.
When data fetches fail, retry later, inspect the recorded `failed` entries, and do not trade from stale data.
Verify holidays and special sessions in `holidays.json` and `trader/config.json` before an ORB scan.
