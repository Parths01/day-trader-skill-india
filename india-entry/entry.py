#!/usr/bin/env python3
"""NSE long-only entry timer for the 09:15-09:30 IST opening range."""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

import india_common

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s"
INTERVAL_SECONDS = {"5m": 300, "1m": 60}
ENTRY_PATH = os.path.join("trader", "entry.json")
DEFAULTS = {"entry_window": ["09:15", "15:00"], "paper": True}


class EntryError(Exception):
    pass


def parse_now(value=None):
    if not value:
        return india_common.to_ist()
    text = str(value).strip().replace("Z", "+00:00")
    if re.match(r"^\d{1,2}:\d{2}$", text):
        today = india_common.to_ist().date().isoformat()
        text = today + " " + text
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError as error:
        raise EntryError('--now wants an IST time like "2026-11-09 10:15"') from error
    return india_common.to_ist(parsed)


def parse_hhmm(value, what="time"):
    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", str(value))
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise EntryError("%s wants HH:MM, not %r" % (what, value))
    return datetime.time(int(match.group(1)), int(match.group(2)))


def _chart_result(document):
    if "chart" in document:
        result = document["chart"].get("result") or []
        if not result:
            raise EntryError("Yahoo response contains no chart")
        return result[0]
    return document


def parse_chart(document, symbol=""):
    if isinstance(document, str):
        document = json.loads(document)
    result = _chart_result(document)
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for index, timestamp in enumerate(timestamps):
        close = (quote.get("close") or [None] * len(timestamps))[index]
        if close is None:
            continue
        bars.append({
            "timestamp": int(timestamp),
            "local": datetime.datetime.fromtimestamp(
                int(timestamp), datetime.timezone.utc).astimezone(india_common.IST),
            "open": _value(quote, "open", index),
            "high": _value(quote, "high", index),
            "low": _value(quote, "low", index),
            "close": float(close),
            "volume": _value(quote, "volume", index),
        })
    return {"symbol": symbol.upper(), "bars": bars, "meta": result.get("meta", {})}


def _value(quote, key, index):
    values = quote.get(key) or []
    return values[index] if index < len(values) and values[index] is not None else None


def _load_offline(path, symbol):
    candidate = path
    if os.path.isdir(path):
        candidate = os.path.join(path, symbol.upper() + ".json")
    with open(candidate, encoding="utf-8") as handle:
        return json.load(handle)


def load_chart(symbol, offline=None, pause=0.5):
    if offline:
        return parse_chart(_load_offline(offline, symbol), symbol)
    query = urllib.parse.urlencode({"range": "1d", "interval": "5m",
                                    "events": "history", "includePrePost": "false"})
    url = YAHOO_URL % urllib.parse.quote(india_common.yahoo_symbol(symbol), safe="") + "?" + query
    request = urllib.request.Request(url, headers={"User-Agent": "day-trader-skill-india/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return parse_chart(json.loads(response.read().decode("utf-8")), symbol)
    except (HTTPError, URLError, OSError, ValueError) as error:
        raise EntryError("could not fetch %s: %s" % (symbol, error))


def _completed_bars(chart, now, interval="5m"):
    seconds = INTERVAL_SECONDS[interval]
    bars = []
    for bar in chart["bars"]:
        local = bar["local"]
        if local.tzinfo is None or local.date() != now.date():
            continue
        if local.second or local.minute % (seconds // 60):
            continue
        if local + datetime.timedelta(seconds=seconds) <= now:
            bars.append(bar)
    return bars


def evaluate(chart, now=None, min_volume_x=None, level=None, config=None):
    config = config or india_common.load_config()
    now = india_common.to_ist(now)
    date = now.date()
    session_open = datetime.datetime.combine(date, datetime.time(9, 15),
                                             tzinfo=india_common.IST)
    range_end = session_open + datetime.timedelta(minutes=15)
    bars = _completed_bars(chart, now)
    range_bars = [bar for bar in bars if session_open <= bar["local"] < range_end]
    opening = {"bars": len(range_bars), "complete": len(range_bars) == 3}
    if range_bars:
        opening.update({
            "high": max(float(bar["high"] or bar["close"]) for bar in range_bars),
            "low": min(float(bar["low"] or bar["close"]) for bar in range_bars),
        })
        volumes = [bar["volume"] for bar in range_bars if bar["volume"] is not None]
        if volumes:
            opening["avg_volume"] = sum(volumes) / len(volumes)
    result = {
        "symbol": chart.get("symbol", ""),
        "date": date.isoformat(),
        "now": now.isoformat(),
        "status": "waiting",
        "phase": "pre-open",
        "opening_range": opening,
        "trigger": None,
        "level": float(level) if level is not None else None,
    }
    if now.weekday() >= 5 or not india_common.is_market_open(
            now, config=config, include_pre_open=True):
        result["status"] = "not_open_yet" if now.time() < datetime.time(9, 15) else "expired"
        result["phase"] = "closed"
        result["reason"] = "NSE is closed"
        return result
    if now.time() < datetime.time(9, 15):
        return result
    if now < range_end:
        result["phase"] = "forming"
        return result
    opening["complete"] = len(range_bars) == 3
    if not opening["complete"]:
        result["reason"] = "opening range is incomplete"
        return result
    result["phase"] = "open"
    threshold = float(level) if level is not None else opening["high"]
    eligible_start = max(range_end, datetime.datetime.combine(
        date, parse_hhmm(config.get("entry_window", DEFAULTS["entry_window"])[0]), tzinfo=india_common.IST))
    cutoff = parse_hhmm(config.get("entry_window", DEFAULTS["entry_window"])[1])
    for bar in bars:
        if bar["local"] < eligible_start or bar["close"] <= threshold:
            continue
        if min_volume_x is not None and opening.get("avg_volume"):
            volume_x = float(bar["volume"] or 0) / opening["avg_volume"]
            if volume_x < min_volume_x:
                continue
        else:
            volume_x = None
        result["status"] = "triggered"
        result["trigger"] = {
            "time": bar["local"].isoformat(),
            "bar_start": bar["local"].strftime("%H:%M"),
            "price": bar["close"],
            "close": bar["close"],
            "bar_index": bars.index(bar),
        }
        if volume_x is not None:
            result["trigger"]["volume_x"] = round(volume_x, 2)
        return result
    if now.time() >= cutoff:
        result["status"] = "expired"
        result["reason"] = "no completed close above %s by %s" % (threshold, cutoff.strftime("%H:%M"))
    return result


def write_entry(result, path=ENTRY_PATH):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"created_by": "india-entry", "side": "buy", **result}, handle, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check")
    check.add_argument("symbol")
    check.add_argument("--offline")
    check.add_argument("--now")
    check.add_argument("--level", type=float)
    check.add_argument("--min-volume-x", type=float)
    check.add_argument("--write", action="store_true")
    check.add_argument("--output", default=ENTRY_PATH)
    args = parser.parse_args(argv)
    if args.command != "check":
        return 1
    try:
        chart = load_chart(args.symbol, args.offline)
        result = evaluate(chart, parse_now(args.now), args.min_volume_x, args.level)
        if args.write and result["status"] == "triggered":
            write_entry(result, args.output)
        print("%s: %s" % (args.symbol.upper(), result["status"]))
        return 0 if result["status"] == "triggered" else 1
    except (EntryError, OSError, ValueError) as error:
        print("entry: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
