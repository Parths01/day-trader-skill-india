---
name: india-news
description: >-
  Indian per-ticker news and corporate-announcement monitor. Collects Yahoo
  Finance headlines plus best-effort NSE and BSE announcements, tags results,
  dividend, board meeting, deal, rating change, and regulatory items, shows
  only unseen items, and writes trader/news.json in IST. Use for "news on
  RELIANCE", "new NSE announcements", "check BSE filings", or "what changed
  since the last check".
argument-hint: "news.py SYMBOL [SYMBOL ...] [--source yahoo,nse,bse]"
---

# india-news

```bash
python3 news.py RELIANCE
python3 news.py RELIANCE TCS --source yahoo,nse,bse
python3 news.py RELIANCE --offline tests/fixtures/india-news
```

The command normalizes headlines and corporate announcements into
`trader/news.json`, stores seen identifiers in `trader/news_state.json`, and
prints only items not observed during an earlier check. All normalized
timestamps are represented in IST when a source supplies a timestamp. Sources
are adapters, so a licensed news or exchange feed can replace a public
best-effort endpoint later.

The Yahoo adapter uses Yahoo's public search endpoint for headlines. The NSE
adapter uses the public corporate-announcements interface, and the BSE adapter
uses the public announcement interface. These endpoints are not guaranteed
public APIs: they may change, rate-limit, require a session, or block automated
requests. This tool does not bypass those controls. Errors are reported per
symbol and source, and a failed fetch cannot create a fake item.

Tags are keyword-based hints, not editorial classifications. Items can have
more than one tag. The supported labels are `results`, `dividend`, `board
meeting`, `deal`, `rating change`, and `regulatory`.

## Offline fixtures

`--offline` accepts one JSON fixture or a directory containing `SYMBOL.json`.
The fixture may contain a Yahoo `news` list or an exchange `data`/`Table` list.
This keeps tests deterministic and permits use when an exchange blocks the
network or a licensed feed is not configured.

## Operating assumptions

Symbols are normalized to uppercase NSE symbols.
Yahoo symbols receive the `.NS` suffix.
Each requested symbol is fetched separately.
Each selected source is attempted independently.
The output is sorted newest first by the source timestamp.
Items are deduplicated by a source, title, and URL identity.
An explicit source ID is preferred when the source supplies one.
The seen state is local and should be backed up with the project.
Seen state is updated even when the output contains no new items.
Deleting or editing seen state can intentionally replay items.
The first successful check treats all returned items as new.
The command does not claim that a missing item was not published.
Exchange feeds can omit, revise, or reorder announcements.
Yahoo headlines can be delayed, syndicated, or incomplete.
Announcement attachment URLs may require a browser session.
Dates without offsets are retained as source text when conversion fails.
Source text is not translated or rewritten.
Keyword tagging does not verify the legal meaning of a filing.
The tool does not download arbitrary attachment content.
The tool does not scrape around robots, CAPTCHA, login, or rate limits.
Use only data access permitted by each source's terms.
Use a licensed feed for production-grade completeness and redistribution.
This monitor is informational and is not financial advice.
It never places orders or changes an order.
