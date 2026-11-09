---
name: india-broker
description: >-
  Safe Indian NSE broker ticket layer. Shows plain-English orders with entry,
  stop, target, maximum stop loss, estimated charges, and flatten-before-
  square-off tickets. It only shows orders that passed india-risk, requires
  the exact lowercase reply "yes" for one order, and still requires Claude's
  own Allow/Deny approval. Paper or simulated mode is the default. Use for
  "show my Indian order ticket", "approve this NSE order", "flatten before
  15:15", or "send the risk-passed order".
argument-hint: "ticket.py show | approve --index N --reply yes | flatten --symbol SYMBOL --qty N"
---

# india-broker

This skill creates and records safe order tickets. It does not silently place
orders. The checked-in implementation is paper/simulated by default and has no
live broker connector.

```bash
python3 ticket.py show
python3 ticket.py show --json
python3 ticket.py approve --index 1 --reply yes
python3 ticket.py result --index 1 --status simulated
python3 ticket.py flatten --symbol RELIANCE --qty 25
```

An order is displayed as a plain-English ticket with stock, side, quantity,
entry, stop, target, maximum loss at the stop, and estimated round-trip
charges. It is READY only when the exact order fingerprint appears as PASS in
the current-day `trader/state/risk.json` produced by `india-risk`.

Approval has two independent gates. First, the user must provide exactly the
lowercase reply `yes` for one indexed order. A batch approval, paraphrase,
conditional reply, or different word is rejected. Second, Claude's own
Allow/Deny approval must be presented before a real broker tool call. This
Python module records the first gate and the result after the second gate; it
does not manufacture or bypass Claude's approval card.

`flatten` creates a sell, reduce-only ticket with `kind: exit` and the
configured `flat_by` time, defaulting to 15:15 IST. It must still be checked
by `india-risk`, receive the exact `yes`, and pass the external Allow/Deny
step. It is a ticket to flatten, not an automatic square-off.

## Broker research and adapter policy

Indian brokers offer APIs, but terms differ and must be checked before live
use. Zerodha's official Kite Connect material documents ₹500/month for data
APIs and free order/account APIs; its access token is flushed daily. Upstox
documents OAuth login, standard access tokens that need daily regeneration,
analytics tokens, rate limits, and static-IP controls for supported account
access. Dhan documents access tokens, TOTP setup, and registered primary or
secondary static IPs with restricted modification windows. FYERS documents a
free Standard API plan with rate limits and says static IP is required for
order placement. Fees and limits can change.

Official broker MCP availability is not uniform. Public broker documentation
is authoritative for the API, not third-party lists claiming an MCP server.
The safe default here is no MCP and no live connector. If a broker later
provides an official MCP, verify its hosted endpoint, tool scope, order
placement capability, approval behavior, retention, and current terms directly
with that broker before enabling it.

API credentials must be environment variables owned by the local adapter. They
must never be pasted into chat, written to JSON, printed, or committed. This
module currently does not read credentials because it does not place live
orders.

## SEBI and exchange controls

SEBI's February 4, 2025 retail-algo circular requires broker-centered API
controls, unique algo identifiers for algo orders, and implementation through
broker/exchange standards. Applicability began August 1, 2025. Broker
requirements such as static IP registration, daily login, TOTP, rate limits,
order tagging, and kill switches are not optional implementation details.
Confirm the current broker and exchange implementation before enabling any
automation.

## Safety assumptions

Paper or simulated mode is the default.
No live order endpoint is called by this module.
Only current-day india-risk PASS results are eligible.
The fingerprint covers the exact order fields checked by india-risk.
Changing quantity, price, stop, target, side, or symbol requires a new risk check.
An exit ticket is still an explicit order and requires approval.
The exact user reply must be lowercase `yes`.
One yes applies to one fingerprinted order only.
Claude Allow/Deny remains a separate approval gate.
The module never interprets `sure`, `ok`, `go`, or `yes to all` as approval.
Estimated charges use configurable rates from `trader/config.json`.
Charges are estimates and may differ from the broker contract note.
Maximum loss assumes the stop fills at the planned stop price.
Gaps, slippage, rejected orders, and partial fills can change the result.
Market entries do not guarantee the displayed entry price.
The flat-by time is interpreted in IST.
The flatten ticket is reduce-only and long-position oriented.
The caller must verify the live position before flattening.
The caller must verify available quantity before flattening.
The caller must verify the broker's product and order variety.
No short selling, F&O, or options are enabled by this layer.
API keys are never accepted as command-line arguments.
API keys are never loaded from chat messages.
API keys are never written to state or ticket files.
Broker failures must be surfaced, not converted into success.
The tool does not retry an order submission because it submits none.
An order result is recorded only after the external approval step.
The result status is an audit record, not proof of broker execution.
Use broker order history and contract notes to confirm execution.
This tool is education and workflow support, not financial advice.
