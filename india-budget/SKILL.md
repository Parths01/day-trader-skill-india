---
name: india-budget
description: >-
  Indian NSE position sizer. Reads an Indian exit plan, computes whole shares
  under max loss, position cap, max order value, and cash-buffer limits, and
  writes one paper bracket order. Use for "size my NSE trade", "how many
  shares of Reliance", "budget this Indian setup", or "create the Indian
  bracket order".
argument-hint: "[--plan trader/plan.json] [--write]"
---

# india-budget

This skill sizes a proposed long-only NSE trade; it never sends an order.
`size.py` reads `trader/plan.json` and `trader/config.json`.

```bash
python3 size.py
python3 size.py --cash 100000 --write
```

The whole-share quantity is the floor of the smallest of max-loss shares,
position-cap shares, max-order-value shares, and cash-after-buffer shares.
The output says which limit binds. If even one share exceeds the risk or cash
limits, sizing refuses instead of shrinking the stop or silently producing a
zero-share order. Approximate intraday margin is applied only when
`allow_margin` is true and `intraday_margin_multiplier` is explicitly set.

Orders are written as proposed paper brackets to `trader/orders.json`. The
Indian risk checker must PASS the exact order before the broker skill can show
it. Prices are INR and stops/targets come from the plan. This is not financial
advice.

## Operating assumptions

The plan is interpreted as a long-only cash equity plan.
Quantity is always an integer; fractional shares are not produced.
The max-loss limit is per share risk multiplied by quantity.
The position cap is a percentage of configured capital.
The max-order limit is a rupee notional ceiling.
The cash limit preserves the configured cash buffer.
A supplied cash value represents current available cash, not total net worth.
Margin does not increase the max-loss or position-cap limits.
Margin is used only when `allow_margin` is true.
The margin multiplier is approximate and must match the broker's product rules.
Zero limits are treated as disabled for sizing, except zero capital leaves no funds.
A stop that permits no whole share is an explicit refusal.
The sizer does not move a stop to force a quantity.
The sizer does not round a quantity up to satisfy a minimum order.
The proposed order remains subject to the Indian risk gate.
The order is paper/proposed by default and never sent by this skill.
Review brokerage, taxes, and slippage separately from the gross size.
All prices and limits are rupees.

The `bound_by` field is suitable for explaining why quantity was capped.
The `limits` array preserves each limit for audit and review.
The generated bracket includes the plan values for the risk checker.
A proposed order is not an approval and is not an execution.
Use a current cash figure when the account has other open positions.
Do not enable margin based only on a generic broker marketing number.
Update configuration when the broker changes product-specific leverage.
A price gap can produce more loss than the planned stop risk.
A market order can fill away from the plan entry.
Confirm the final order and risk verdict before any broker action.
