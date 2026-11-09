#!/usr/bin/env python3
"""Indian ticker news and corporate-announcement monitor."""

import argparse
import datetime
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import india_common


NEWS_PATH = os.path.join("trader", "news.json")
STATE_PATH = os.path.join("trader", "news_state.json")
USER_AGENT = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0)"
YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
NSE_URL = "https://www.nseindia.com/api/corporate-announcements"
BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"


class NewsError(Exception):
    pass


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(data, path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def _get(url, params=None, opener=None, retries=1, pause=0.5):
    query = urllib.parse.urlencode(params or {})
    full_url = url + (("&" if "?" in url else "?") + query if query else "")
    opener = opener or urllib.request.urlopen
    last = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(full_url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.nseindia.com/" if "nseindia" in url
                else "https://www.bseindia.com/",
            })
            with opener(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, OSError,
                ValueError) as error:
            last = error
            if attempt < retries:
                time.sleep(pause * (attempt + 1))
    raise NewsError("fetch failed for %s: %s" % (url, last))


def _fixture(path, symbol):
    if not path:
        return None
    if os.path.isdir(path):
        key = str(symbol).upper().replace(".NS", "")
        candidates = [os.path.join(path, key + ".json"),
                      os.path.join(path, "news-" + key + ".json")]
        path = next((item for item in candidates if os.path.exists(item)), None)
    if not path or not os.path.exists(path):
        raise NewsError("no offline fixture for %s" % symbol)
    return _read_json(path)


def _iso_time(value):
    if not value:
        return india_common.to_ist().isoformat()
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(
            int(value), datetime.timezone.utc).astimezone(india_common.IST).isoformat()
    text = str(value).replace("Z", "+00:00")
    try:
        return india_common.to_ist(datetime.datetime.fromisoformat(text)).isoformat()
    except ValueError:
        return str(value)


def tag_headline(text):
    text = str(text).lower()
    groups = {
        "results": ("results", "earnings", "profit", "revenue", "quarter"),
        "dividend": ("dividend", "payout", "record date"),
        "board meeting": ("board meeting", "board to meet", "meeting of board"),
        "deal": ("acquire", "acquisition", "merger", "deal", "order win", "contract"),
        "rating change": ("upgrade", "downgrade", "rating", "target price"),
        "regulatory": (" sebi ", " sebi", "rbi", "regulatory", "penalty", "show cause"),
    }
    return [name for name, words in groups.items() if any(word in text for word in words)]


def _normalise(item, symbol, source):
    title = item.get("title") or item.get("headline") or item.get("subject") or ""
    url = item.get("url") or item.get("link") or item.get("attachment") or ""
    published = item.get("published") or item.get("published_at") or item.get(
        "timestamp") or item.get("date")
    identity = item.get("id") or ("%s|%s|%s" % (source, title, url))
    identity = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:20]
    return {
        "id": identity,
        "symbol": str(symbol).upper().replace(".NS", ""),
        "source": source,
        "title": str(title).strip(),
        "url": url,
        "published": _iso_time(published),
        "tags": item.get("tags") or tag_headline(title),
        "summary": item.get("summary") or item.get("description") or "",
    }


def yahoo_news(symbol, offline=None, opener=None):
    data = _fixture(offline, symbol) if offline else _get(
        YAHOO_SEARCH_URL, {"q": india_common.yahoo_symbol(symbol),
                           "newsCount": 20, "quotesCount": 0}, opener=opener)
    rows = data.get("news", data if isinstance(data, list) else [])
    return [_normalise(item, symbol, "yahoo") for item in rows
            if isinstance(item, dict) and (item.get("title") or item.get("headline"))]


def nse_announcements(symbol, offline=None, opener=None):
    data = _fixture(offline, symbol) if offline else _get(
        NSE_URL, {"index": "equities", "symbol": str(symbol).upper()},
        opener=opener)
    rows = data.get("data", data if isinstance(data, list) else [])
    return [_normalise(item, symbol, "nse") for item in rows if isinstance(item, dict)]


def bse_announcements(symbol, offline=None, opener=None):
    data = _fixture(offline, symbol) if offline else _get(
        BSE_URL, {"pageno": 1, "strCat": "-1", "strPrevDate": "",
                  "strScrip": str(symbol).upper(), "strSearch": "P",
                  "strToDate": "", "strType": "C"}, opener=opener)
    rows = data.get("Table", data.get("data", data if isinstance(data, list) else []))
    return [_normalise(item, symbol, "bse") for item in rows if isinstance(item, dict)]


def load_seen(path=STATE_PATH):
    if not os.path.exists(path):
        return set()
    data = _read_json(path)
    return set(data.get("seen", data if isinstance(data, list) else []))


def save_seen(seen, path=STATE_PATH):
    _write_json({"updated_at": india_common.to_ist().isoformat(),
                 "seen": sorted(seen)}, path)


def collect(symbols, sources=("yahoo", "nse", "bse"), offline=None, opener=None):
    handlers = {"yahoo": yahoo_news, "nse": nse_announcements,
                "bse": bse_announcements}
    items, errors = [], []
    for symbol in symbols:
        for source in sources:
            try:
                items.extend(handlers[source](symbol, offline=offline, opener=opener))
            except (NewsError, OSError, ValueError) as error:
                errors.append("%s/%s: %s" % (symbol, source, error))
            time.sleep(0.5)
    unique = {item["id"]: item for item in items}
    return sorted(unique.values(), key=lambda item: item.get("published", ""),
                  reverse=True), errors


def new_items(items, seen):
    return [item for item in items if item["id"] not in seen]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbols", nargs="+")
    parser.add_argument("--source", default="yahoo,nse,bse")
    parser.add_argument("--offline")
    parser.add_argument("--state", default=STATE_PATH)
    parser.add_argument("--output", default=NEWS_PATH)
    args = parser.parse_args(argv)
    try:
        sources = tuple(item.strip().lower() for item in args.source.split(",") if item.strip())
        invalid = set(sources) - {"yahoo", "nse", "bse"}
        if invalid:
            raise NewsError("unknown source(s): %s" % ", ".join(sorted(invalid)))
        items, errors = collect(args.symbols, sources, args.offline)
        seen = load_seen(args.state)
        fresh = new_items(items, seen)
        _write_json({"checked_at": india_common.to_ist().isoformat(),
                     "items": fresh, "errors": errors}, args.output)
        save_seen(seen | {item["id"] for item in items}, args.state)
        for item in fresh:
            print("[%s] %s: %s" % (item["source"], item["symbol"], item["title"]))
        for error in errors:
            print("WARNING: %s" % error, file=sys.stderr)
        return 0
    except (NewsError, OSError, ValueError) as error:
        print("news: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
