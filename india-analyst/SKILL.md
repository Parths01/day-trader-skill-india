---
name: india-analyst
description: >-
  Indian quarterly facts analyst. Reads a swappable fundamentals source and
  reports revenue, operating margin, net profit, diluted EPS, year-on-year
  comparisons, and trailing-twelve-month totals. Yahoo is the initial
  best-effort adapter; use for "analyze Indian results", "compare quarterly
  earnings", "show TTM facts", or "check RELIANCE results".
argument-hint: "facts.py SYMBOL [--source yahoo] [--offline FILE]"
---

# india-analyst

```bash
python3 facts.py RELIANCE
python3 facts.py RELIANCE --offline tests/fixtures/india-analyst/RELIANCE.json
```

The output is factual data, not an investment recommendation. It contains
quarterly revenue, operating income, calculated operating margin, net income,
diluted EPS when available, year-on-year percentages, and TTM sums from the
latest four quarters.

The source boundary is deliberately isolated in `facts()`. Yahoo's public
fundamentals-timeseries endpoint is unofficial and can be incomplete,
rate-limited, changed, or blocked. This module does not bypass authentication,
CAPTCHAs, robots controls, or rate limits. A future approved NSE, BSE, company
investor-relations, or licensed-data adapter can replace it without changing
the normalized output.

## Offline fixtures

Fixtures may use the normalized shape `{"quarters": [...]}` or Yahoo
timeseries JSON. A normalized quarter has `period_end`, `revenue`,
`operating_income`, `net_income`, and `eps`. Missing metrics remain missing;
they are never invented or inferred from unrelated fields.

## Assumptions

Revenue and profit values retain the source currency and units.
The module does not convert lakh, crore, million, or billion units.
Operating margin is operating income divided by revenue times 100.
TTM is the arithmetic sum of the latest four reported quarters.
TTM operating margin is TTM operating income divided by TTM revenue.
TTM EPS is the sum of the latest four quarterly EPS values.
Year-on-year comparison matches the same month in the prior year.
Negative prior values use absolute prior values as the denominator.
Restated or revised filings are accepted as supplied by the source.
Standalone and consolidated statements are not mixed deliberately by this tool.
If the source does not identify statement scope, the source's default is used.
Yahoo may report duplicate or differently scoped periods.
The adapter preserves source periods rather than silently deduplicating them.
Missing quarters make TTM incomplete rather than zero-filled.
EPS may be diluted EPS only; basic EPS is not substituted silently.
The result date is the source's period-end date, not the filing date.
Data can be delayed and should be checked against the company's filing.
The tool does not parse PDF filings or OCR scanned statements.
Official exchange pages may require a browser session or licensed access.
Company investor-relations pages vary in format and publication policy.
Use only sources you are permitted to access and store.
No endpoint is called to evade a block or restriction.
This tool does not place trades or provide financial advice.
Review units, scope, accounting standards, and restatements before use.
