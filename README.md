# Indian Day Trader skill

Indian NSE day-trading skills for scanning, planning, simulating, sizing,
risk-checking, alerting, researching, and paper-ticketing trades.

Free and standard-library-only. The tools use free public data where available,
including Yahoo Finance and official NSE/BSE public filing surfaces. Free data
can be delayed, incomplete, unofficial, rate-limited, or unavailable.

Nothing places an order automatically. Paper or simulated mode is the default.

## Install

Paste this into Claude:

```
https://github.com/parths01/day-trader-skill-india

install skill
```

Or install the plugin in Claude Code:

```text
/plugin marketplace add parths01/day-trader-skill-india
/plugin install india-day-trader-skill@india-day-trader-skill
```

The package requires Python 3.8 or newer and has no third-party dependencies.

The original US modules remain in this repository for compatibility:
`/trader-scanner`, `/trader-news`, `/trader-entry`, `/trader-exit`,
`/trader-timemachine`, `/trader-risk`, `/trader-budget`, `/trader-broker`,
`/trader-alerts`, `/trader-analyst`, and `/trader-pelosi`. The Indian commands
below use IST, NSE sessions, rupee risk, and Indian data conventions.

## The Indian skills

| command | job | what it does |
| --- | --- | --- |
| `/india-scanner` | NSE Chart Scanner | Scans EQ-series stocks for daily setups and opening-range breakouts. |
| `/india-entry` | NSE Entry Timer | Times long-only 09:15-09:30 IST opening-range entries. |
| `/india-exit` | NSE Exit Planner | Sets tick-rounded stops, targets, and square-off warnings. |
| `/india-timemachine` | NSE Simulator | Replays 10,000 simulated sessions plus historical setups with net costs. |
| `/india-budget` | NSE Position Sizer | Sizes whole shares under risk, position, order, and cash limits. |
| `/india-risk` | NSE Risk Gate | PASS/BLOCK checks exact proposed orders. |
| `/india-broker` | NSE Broker Ticket | Shows risk-passed paper tickets and requires exact yes plus Allow/Deny. |
| `/india-alerts` | NSE Price Alerts | Rings once for price, stop, target, open, percentage, and flat-by alerts. |
| `/india-news` | NSE News Monitor | Shows new Yahoo, NSE, and BSE headlines with event tags. |
| `/india-analyst` | Results Analyst | Reports quarterly revenue, margin, profit, EPS, YoY, and TTM facts. |
| `/india-disclosures` | Disclosure Tracker | Tracks official bulk, block, insider, promoter, and FII/DII disclosures. |

## Full workflow

```text
NSE universe / Nifty 500
          |
          v
    india-scanner
          |
          v
    india-entry  ----->  india-alerts
          |                    |
          v                    v
    india-exit          stop / target / flat-by
          |
          v
  india-timemachine
          |
          v
    india-budget
          |
          v
     india-risk
          |
    PASS only
          v
    india-broker
          |
     exact "yes"
          |
   Claude Allow/Deny
          |
   paper/simulated order

india-news -----------+
india-analyst --------+--> research context, never an automatic signal
india-disclosures ----+
```

The broker ticket is not a bypass around risk. It only displays an order when
the exact fingerprint passed `india-risk` on the current date. A flatten ticket
is a reduce-only sell ticket that must still be risk-checked and approved.

## Configuration

Copy [config.example.json](config.example.json) to `trader/config.json` and
replace the example values:

| setting | meaning |
| --- | --- |
| `capital` | Account cash in rupees used by the position sizer. |
| `max_loss_per_trade` | Maximum planned rupee loss at the stop. |
| `daily_loss_limit` | Maximum daily loss before new entries are blocked. |
| `flat_by` | Required square-off reminder, default `15:15` IST. |
| `entry_window` | Inclusive entry window in IST. |
| `paper` | Keep `true` until every live connector is independently verified. |
| `tick_sizes` | Per-symbol NSE tick-size overrides. |
| `special_sessions` | Date-keyed Muhurat or other special-session settings. |
| `max_position_pct` | Maximum fraction of capital in one position. |
| `max_order_value` | Maximum rupee notional for one order. |
| `cash_buffer_pct` | Cash retained after sizing. |
| `allow_margin` | Whether configured approximate intraday margin may affect cash sizing. |
| `intraday_margin_multiplier` | User-supplied margin multiplier; not broker advice. |
| `max_trades_per_day` | Entry count limit; zero means no configured count limit. |
| `require_stop` | Require a protective stop on entries. |
| `min_reward_risk` | Minimum target-to-risk ratio. |
| `blocked` | User-maintained symbols that cannot be entered. |
| `circuit_limit_stocks` | User-maintained circuit-limit symbols. |
| `asm_gsm_stocks` | User-maintained ASM/GSM surveillance symbols. |
| `allow_short` | Long-only default; keep `false` unless separately approved. |
| `allow_fno` | F&O disabled by default. |
| `allow_options` | Options disabled by default. |
| `trading_costs` | Broker charge-sheet rates used by sizing and simulation. |

The checked-in [trader/config.json](trader/config.json) intentionally uses
zero fee placeholders. Verify every fee against your broker before relying on
cost or net-P&L output.

## Indian worked example

Suppose `RELIANCE` triggers an opening-range breakout:

1. The 09:15-09:30 IST range is 2,480 to 2,500.
2. The first completed close above the range is 2,505.
3. `india-exit` chooses the range midpoint, 2,490, as the stop.
4. Risk per share is `2,505 - 2,490 = Rs 15`.
5. A 1R target is `Rs 2,520`.
6. With `max_loss_per_trade = Rs 1,000`, the risk limit allows at most
   `floor(1000 / 15) = 66` shares before other limits.
7. `india-budget` applies the position cap, order-value cap, and cash buffer,
   then writes one whole-share bracket order.
8. `india-risk` checks the stop, reward:risk, daily loss, trade count, entry
   window, NSE session, blocked lists, and exact order fingerprint.
9. `india-broker` displays the ticket only if that exact order passed.
10. You reply exactly `yes` for that one order, then Claude's own Allow/Deny
    approval is required. The default result is simulated or paper.
11. `india-alerts add --from-plan` creates stop, target, and 15:15 IST
    flat-by reminders. A reminder is not an automatic square-off.

The Time Machine's output is a simulation, not a prediction. A historical
sample cannot foresee gaps, halts, news, slippage, or changing liquidity.

## Common commands

```bash
python3 india-scanner/scan.py universe
python3 india-scanner/scan.py daily --limit 25
python3 india-entry/entry.py check RELIANCE --write
python3 india-exit/exit.py plan --stop or-mid --target 1R --write
python3 india-timemachine/timemachine.py run --seed 19 --write
python3 india-budget/size.py --write
python3 india-risk/check.py
python3 india-broker/ticket.py show
python3 india-alerts/alerts.py add --from-plan
python3 india-news/news.py RELIANCE
python3 india-analyst/facts.py RELIANCE
python3 india-disclosures/disclosures.py
```

## Disclaimer

**This is not investment advice.** This project is not a SEBI-registered
investment adviser, research analyst, broker, or tax adviser. It cannot assess
your financial situation, suitability, or risk tolerance.

Most retail intraday traders lose money. Paper-trade first, use small
non-critical amounts if you later choose to trade, and confirm every order
with your broker. No result, alert, simulation, disclosure, or historical
pattern is a promise of future performance.

The data is free and may be unofficial, delayed, incomplete, changed, or
blocked. Yahoo Finance is not an official NSE API. NSE and BSE public pages can
change, rate-limit, or require access conditions. Use only data access allowed
by the source terms.

The Time Machine is a simulation, not a prediction. Stops are plans, not
guaranteed fills. Slippage, gaps, spread, rejected orders, partial fills,
halts, taxes, and charges can make actual results materially different.

API keys belong in local environment variables only, never in chat, source
files, JSON state, or commits. Live broker integrations require current broker
terms, SEBI and exchange controls, and independent approval.

## Local testing

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The suite is offline and uses fixtures. It should finish with all tests
passing. On Windows, use `py -3` if `python3` is not available.

Additional checks:

```bash
python3 -m py_compile india_common.py india-scanner/scan.py india-broker/ticket.py
git diff --check
git status --short
```

## Publishing checklist for `github.com/parths01`

1. Review and personalize `config.example.json`; do not commit real API keys,
   broker tokens, account numbers, or private files.
2. Replace the placeholder fee rates in your local `trader/config.json`, not
   necessarily in the example file.
3. Update [holidays.json](holidays.json) from the official NSE calendar.
4. Run the full offline unittest command from a clean checkout.
5. Run syntax and whitespace checks.
6. Inspect `git diff` and confirm no generated `__pycache__`, `trader/*.json`,
   tokens, credentials, or account data are staged.
7. Confirm `.claude-plugin/plugin.json` and `marketplace.json` point to
   `https://github.com/parths01/day-trader-skill-india`.
8. Create the GitHub repository at
   `https://github.com/parths01/day-trader-skill-india`.
9. Initialize or connect the local repository, then create the first commit.
10. Push the default branch to GitHub.
11. Open the repository URL and verify the README, plugin metadata, skills,
    tests, and LICENSE render correctly.
12. Install from the GitHub URL in a test Claude/Claude Code environment.
13. Run an offline scanner, entry, risk, broker-ticket, alert, news, analyst,
    and disclosure example before considering publication complete.
14. Keep live broker execution disabled until the broker adapter, terms,
    credentials, static IP, login, algo tagging, and approval controls are
    independently verified.

## License

MIT. Original work by Jake Schincariol; Indian NSE extensions and packaging by
Parth. See [LICENSE](LICENSE).
