---
name: india-disclosures
description: >-
  Tracker for official public Indian-stock disclosures: NSE bulk and block
  deals, insider and promoter trading filings, and FII/DII flows. Normalizes
  who, stock, buy or sell, quantity, price, date, days to disclose, and
  watchlist flags; alerts once on new rows and writes trader/disclosures.json.
  Use for "new bulk deals", "insider disclosures", "promoter activity", "FII
  DII flows", or "check disclosures on my watchlist".
argument-hint: "disclosures.py [--source bulk,block,insider,flows]"
---

# india-disclosures

```bash
python3 disclosures.py
python3 disclosures.py --source bulk,block,insider
python3 disclosures.py --offline tests/fixtures/india-disclosures
```

This tracker uses official public exchange data only. The default sources are
NSE's large-deal snapshot, NSE block-deal data, NSE corporate-filings data for
insider disclosures, and NSE FII/DII activity. BSE can be added as a
source adapter when its official public download or response is configured.
The source URLs are constants near the top of `disclosures.py` so an approved
official replacement can be supplied without changing the normalized row
shape.

Rows are written to `trader/disclosures.json`; identifiers already shown are
stored in `trader/disclosures_state.json`. Each filing alerts only once.
`trader/watchlist.json` is read when present. Rows whose normalized symbol is
on that list carry `"watchlist": true`.

The normalized fields are `who`, `symbol`, `side`, `quantity`, `price`, `date`,
`disclosed_date`, and `days_to_disclose`. Flow rows are market-level and have
no stock symbol; they retain buy, sell, and net values separately.

Official exchange web interfaces can require session headers, rate limits, or
change response shapes. This module reports failures and never bypasses
CAPTCHA, robots controls, authentication, rate limits, or access restrictions.
Use licensed exchange data if completeness, redistribution, or production
availability is required.

## What disclosure means

Disclosed trades are public information, not tips. They may be delayed,
revised, incomplete, aggregated, or reported after the market moved. A bulk
deal or insider sale does not predict the next price move. This tool is
informational, does not recommend copying a trade, and never places orders.

## Offline fixtures

`--offline DIRECTORY` reads `bulk.json`, `block.json`, `insider.json`, and
`flows.json`. Fixtures may use the official response shapes or simple lists of
rows. This is the preferred way to test parsers without contacting an exchange.

## Assumptions

NSE symbols are normalized to uppercase without the `.NS` suffix.
Bulk and block prices are treated as weighted or reported prices from the source.
Quantity is not converted between shares, units, and contracts.
Buy and sell labels are normalized to lowercase `buy` and `sell`.
Unknown transaction labels are retained in lowercase.
Who is copied from the exchange's client, person, acquirer, seller, or entity field.
Disclosure date is distinct from trade date.
Days to disclose is calendar days, not NSE sessions.
Missing dates produce a missing delay, never a guessed delay.
The first successful run alerts on every returned row.
Seen identifiers are local state and can be reset deliberately.
Rows are deduplicated by a stable source identity or normalized fallback.
FII/DII rows are flows, not individual stock trades.
FII/DII flow values retain the source's units.
The watchlist is informational and does not change alert eligibility.
The tracker does not infer a promoter from a generic client name.
The tracker does not classify intent beyond the source's transaction label.
Revised filings can appear as new source identifiers.
An exchange may omit historical rows from a current snapshot.
Official pages can be unavailable outside their normal publication window.
Public data can arrive after the actual trade date.
No third-party tracker is used as a source of record.
No endpoint is called to evade a block or restriction.
All timestamps and check metadata are recorded in IST.
Disclosed trades are public information, not tips.
This tool is not financial advice.
