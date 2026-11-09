---
name: india-risk
description: >-
  Indian NSE pre-trade risk gate. Returns PASS or BLOCK for stop, loss,
  reward:risk, daily limits, entry window, market calendar, blocked tickers,
  circuit limits, ASM/GSM surveillance, short selling, F&O, and options.
  Records exact-order verdicts for the Indian broker skill. Use for "check this
  Indian order", "risk check my NSE trade", or "is this bracket allowed".
argument-hint: "[--orders trader/orders.json] [--now HH:MM]"
---

# india-risk

```bash
python3 check.py
python3 check.py --orders trader/orders.json --now "2026-11-09 10:15"
```

Every proposed entry receives a PASS or BLOCK verdict and a fingerprint in
`trader/state/risk.json`. The broker should show only orders whose exact
fingerprint passed. Exits are never blocked by daily loss, trade-count,
entry-window, or market-entry rules; they remain available for risk reduction.

The checker uses IST and [`india_common.py`](../india_common.py). Lists for
blocked, circuit-limit, ASM, and GSM stocks are user-maintained in
`trader/config.json`. Short selling, F&O, and options are disabled by default.
All limits are safety gates, not guarantees of execution. This is not financial
advice.

## Operating assumptions

Checks apply to entry orders unless the order is explicitly marked as an exit.
Exits remain available even after daily loss or trade-count limits are reached.
The entry window is interpreted in IST and uses completed configuration values.
The shared holiday file is authoritative for dates maintained by the user.
The market check requires a regular NSE session, not merely a weekday.
A missing stop blocks when `require_stop` is true.
A plan stop is accepted as evidence when the order has no attached stop leg.
A lower stop and higher target are required for long entries.
The daily loss limit is a configured rupee safety ceiling.
Trades already used today must be supplied through the state input or persisted record.
Blocked, circuit, ASM, and GSM symbols are exact ticker matches after uppercasing.
The surveillance lists are intentionally user-maintained and may be stale.
Short selling is disabled unless explicitly enabled in config.
F&O and options are disabled unless explicitly enabled in config.
Risk verdicts include an exact order fingerprint for broker handoff.
Changing quantity, prices, or order legs invalidates the prior fingerprint.
A PASS is a rules result, not a guarantee of liquidity or execution.
This skill does not verify broker-specific square-off or margin rules.

Daily loss and trade-count state must come from a trusted account record.
The checker does not infer realized P&L from market prices.
Exit orders are reduce-only safety actions and bypass entry limits.
A PASS verdict applies only to the exact fingerprinted order.
Changing price, quantity, stop, target, or symbol requires a new verdict.
Keep blocked, ASM/GSM, and circuit-limit lists current and reviewable.
A listed surveillance status is treated conservatively as a block.
The default policy is long-only cash equity intraday trading.
F&O and options require an explicit policy change and separate validation.
A PASS is a gate for paper workflow, not a broker execution instruction.
Keep the generated risk state file private to the local trading workspace.
Review every BLOCK reason before changing policy or surveillance data.
