---
name: india-alerts
description: >-
  One-shot Indian NSE alerts for prices above or below a level, stops, targets,
  percentage moves from the previous close, IST times, the NSE open, and the
  15:15 IST flat-by deadline. Uses one free delayed Yahoo quote per ticker,
  persists fired state, and writes trader/prices.json. Use for "alert me on
  RELIANCE", "watch my Indian stop", "add plan alerts", "NSE open alert", or
  "flat by 15:15".
argument-hint: "add --symbol SYMBOL --above PRICE | --from-plan; check [--offline FILE]"
---

# india-alerts

This skill watches Indian cash-equity alerts. It never places an order and does
not replace a broker's live risk controls.

```bash
python3 alerts.py add --symbol RELIANCE --above 3000
python3 alerts.py add --symbol RELIANCE --below 2900 --label "support"
python3 alerts.py add --symbol RELIANCE --pct 2 --direction up
python3 alerts.py add --at 15:15 --label "flat by 15:15 IST"
python3 alerts.py add --nse-open --id nse-open
python3 alerts.py add --from-plan
python3 alerts.py check
python3 alerts.py check --now "2026-11-09 15:15" --offline tests/fixtures/india-alerts
python3 alerts.py quote RELIANCE
python3 alerts.py list
python3 alerts.py reset reliance-plan-stop
```

`--above` and `--target` ring at or above the price. `--below` and `--stop`
ring at or below it. A percentage alert compares the Yahoo price with the
previous close; use `--direction down` for a fall. The time alert and the
flat-by alert use IST and only ring on an NSE trading day.

`--from-plan` reads `trader/plan.json` and adds the plan stop, plan target, and
the plan's `flat_by` time as one group. The plan's symbol and date are copied
to each rule. It is intentionally additive: existing alerts are preserved.

Every rule has persistent `fired` state in `trader/alerts.json`. A fired rule
does not ring again until `reset ID` removes that state. This is deliberately
one-shot behavior, including the NSE-open and time rules.

Successful checks and quote commands write the latest snapshots to
`trader/prices.json`. Price checks fetch each distinct ticker separately, with
a polite delay and bounded retries. A failed symbol is reported as a warning;
it cannot produce a false alert. The process exits 1 when no alert rang and 0
when at least one alert rang.

Yahoo quotes are free, delayed, unofficial data. They are appropriate for
notifications, not for order timing, stop execution, or determining whether a
market has filled. Confirm the price, spread, liquidity, and order status with
your broker. This is not financial advice. Alerts never replace risk checks;
any resulting ticket still requires exact lowercase `yes` and Claude
Allow/Deny approval.

## Offline fixtures

For tests and disconnected use, `--offline` accepts one Yahoo chart JSON file
or a directory containing `SYMBOL.json`. The fixture must include a current
price and previous close, either in Yahoo `meta` or in two daily closes.

## Operating assumptions

The default symbol is an NSE equity symbol and receives the `.NS` Yahoo suffix.
Symbols are normalized to uppercase when stored.
Each distinct ticker is requested at most once per check invocation.
Requests use Yahoo's two-day daily chart endpoint.
The quote timestamp is retained when Yahoo provides one.
The previous close comes from Yahoo metadata or the prior daily close.
Percentage movement is signed before direction is applied.
Percentage thresholds are absolute values in the stored rule.
Price comparisons include equality at the threshold.
Time comparisons include the configured minute.
Naive `--now` timestamps are interpreted as IST.
Offset-bearing `--now` timestamps are converted to IST.
Weekends and configured holidays suppress time and open alerts.
The NSE regular open is treated as 09:15 IST.
Special sessions should be configured before relying on an open alert.
The shared holiday file is user-maintained and may be a placeholder.
`trader/alerts.json` is local state and should not be shared as an order feed.
`trader/prices.json` is a delayed observation, not an execution quote.
Missing or malformed quote data is an explicit failure.
No alert is silently treated as fired after a fetch failure.
Resetting an alert deliberately permits it to ring again.
Changing an alert threshold requires adding a new rule or editing local state.
The alert engine does not infer a position from a quote.
The flat-by alert is a reminder, not an automatic square-off.
The stop and target rules do not cancel each other.
Plan dates prevent old plan alerts from ringing on a later day.
An undated rule remains eligible on every matching trading day until fired.
The command never submits orders to NSE or to a broker.
