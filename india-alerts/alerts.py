#!/usr/bin/env python3
"""One-shot Indian NSE price and session alerts."""

import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import india_common


ALERTS_PATH = os.path.join("trader", "alerts.json")
PRICES_PATH = os.path.join("trader", "prices.json")
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s"
USER_AGENT = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0)"
PAUSE = 0.5


class AlertError(Exception):
    pass


def parse_hhmm(value):
    try:
        hour, minute = str(value).strip().split(":")[:2]
        result = datetime.time(int(hour), int(minute))
    except (ValueError, TypeError):
        raise AlertError("time must be HH:MM")
    if result.hour > 23 or result.minute > 59:
        raise AlertError("time must be HH:MM")
    return result


def parse_now(value=None):
    """Parse an ISO timestamp; a naive value is interpreted as IST."""
    if not value:
        return india_common.to_ist().replace(microsecond=0)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        result = datetime.datetime.fromisoformat(text)
    except ValueError as error:
        raise AlertError("--now must be an ISO timestamp")
    return india_common.to_ist(result)


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def load_alerts(path=ALERTS_PATH):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    rules = data.get("alerts", data) if isinstance(data, dict) else data
    if not isinstance(rules, list):
        raise AlertError("alerts.json must contain an alerts list")
    return rules


def write_alerts(rules, path=ALERTS_PATH):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"updated_at": india_common.to_ist().isoformat(),
                   "alerts": _jsonable(rules)}, handle, indent=2)


def write_prices(quotes, path=PRICES_PATH):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"updated_at": india_common.to_ist().isoformat(),
                   "quotes": _jsonable(quotes)}, handle, indent=2)


def _chart_result(data):
    if "chart" in data:
        result = (data["chart"].get("result") or [])
        if not result:
            error = data["chart"].get("error") or {}
            raise AlertError(error.get("description", "Yahoo returned no quote"))
        return result[0]
    if "timestamp" in data and "indicators" in data:
        return data
    raise AlertError("not a Yahoo chart response")


def parse_yahoo(data, symbol):
    """Extract the latest close/regular price and previous close from Yahoo."""
    chart = _chart_result(data)
    meta = chart.get("meta") or {}
    timestamps = chart.get("timestamp") or []
    quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
    closes = [item for item in (quote.get("close") or []) if item is not None]
    price = meta.get("regularMarketPrice")
    if price is None and closes:
        price = closes[-1]
    previous = meta.get("previousClose")
    if previous is None and len(closes) >= 2:
        previous = closes[-2]
    if price is None or previous is None:
        raise AlertError("Yahoo returned no current and previous close for %s" % symbol)
    timestamp = timestamps[-1] if timestamps else meta.get("regularMarketTime")
    quote_time = None
    if timestamp:
        quote_time = datetime.datetime.fromtimestamp(
            int(timestamp), datetime.timezone.utc).isoformat()
    return {
        "symbol": str(symbol).upper().replace(".NS", ""),
        "yahoo_symbol": india_common.yahoo_symbol(symbol),
        "price": float(price),
        "prev_close": float(previous),
        "percent_change": (float(price) - float(previous)) / float(previous) * 100,
        "time": quote_time,
    }


def _read_fixture(path, symbol):
    if not path:
        return None
    filename_symbol = str(symbol).upper().replace(".NS", "")
    candidate = path
    if os.path.isdir(path):
        names = [filename_symbol + ".json", filename_symbol + ".NS.json",
                 "yahoo-" + filename_symbol + ".json"]
        candidate = next((os.path.join(path, name) for name in names
                          if os.path.exists(os.path.join(path, name))), None)
    if not candidate or not os.path.exists(candidate):
        raise AlertError("no offline fixture for %s" % symbol)
    with open(candidate, encoding="utf-8") as handle:
        return json.load(handle)


def fetch_quote(symbol, offline=None, pause=PAUSE, retries=2, opener=None):
    fixture = _read_fixture(offline, symbol) if offline else None
    if fixture is not None:
        return parse_yahoo(fixture, symbol)
    url = YAHOO_URL % urllib.parse.quote(india_common.yahoo_symbol(symbol), safe="")
    query = urllib.parse.urlencode({"range": "2d", "interval": "1d",
                                    "events": "history", "includePrePost": "false"})
    opener = opener or urllib.request.urlopen
    last = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(
                url + "?" + query, headers={"User-Agent": USER_AGENT})
            with opener(request, timeout=20) as response:
                return parse_yahoo(json.loads(response.read().decode("utf-8")), symbol)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError,
                ValueError, AlertError) as error:
            last = error
            if attempt < retries:
                time.sleep(pause * (2 ** attempt))
    raise AlertError("quote failed for %s: %s" % (symbol, last))


def _trading_day(now, holidays=None, config=None):
    return now.weekday() < 5 and not (
        now.date() in (set(holidays) if holidays is not None
                       else india_common.load_holidays()))


def _matches_date(rule, now):
    return not rule.get("date") or rule["date"] == now.date().isoformat()


def _price_rules(rules):
    return sorted({rule["symbol"].upper().replace(".NS", "") for rule in rules
                   if rule.get("symbol") and rule.get("type") in
                   ("above", "below", "stop", "target", "pct_move")})


def evaluate_rule(rule, now, quote=None, holidays=None, config=None):
    """Return a human-readable firing reason, or None when not fired."""
    if rule.get("fired") or not _matches_date(rule, now):
        return None
    if rule.get("type") in ("time", "flat_by"):
        if not _trading_day(now, holidays, config):
            return None
        if now.time() >= parse_hhmm(rule["at"]):
            return "time reached: %s IST" % rule["at"]
        return None
    if rule.get("type") == "opening_bell":
        if _trading_day(now, holidays, config) and now.time() >= datetime.time(9, 15):
            return "NSE regular session is open"
        return None
    if quote is None:
        return None
    price = quote["price"]
    kind = rule.get("type")
    if kind in ("above", "target") and price >= float(rule["price"]):
        return "%s is at or above %.4f" % (rule["symbol"], float(rule["price"]))
    if kind in ("below", "stop") and price <= float(rule["price"]):
        return "%s is at or below %.4f" % (rule["symbol"], float(rule["price"]))
    if kind == "pct_move":
        move = quote["percent_change"]
        direction = rule.get("direction", "up")
        if direction == "up" and move >= float(rule["pct"]):
            return "%s moved %.2f%% up from previous close" % (rule["symbol"], move)
        if direction == "down" and move <= -abs(float(rule["pct"])):
            return "%s moved %.2f%% down from previous close" % (rule["symbol"], abs(move))
    return None


def rules_from_plan(plan):
    symbol = plan.get("symbol")
    if not symbol or plan.get("stop") is None or plan.get("target") is None:
        raise AlertError("plan.json needs symbol, stop, and target")
    date = plan.get("date")
    prefix = str(symbol).upper().replace(".NS", "")
    rules = [
        {"id": prefix.lower() + "-plan-stop", "symbol": prefix, "type": "stop",
         "price": plan["stop"], "date": date, "label": "plan stop"},
        {"id": prefix.lower() + "-plan-target", "symbol": prefix, "type": "target",
         "price": plan["target"], "date": date, "label": "plan target"},
        {"id": prefix.lower() + "-flat-by", "symbol": prefix, "type": "flat_by",
         "at": plan.get("flat_by", "15:15"), "date": date, "label": "flat by"},
    ]
    return [dict((key, value) for key, value in rule.items() if value is not None)
            for rule in rules]


def check(rules, now=None, offline=None, holidays=None, config=None, fetcher=None):
    now = parse_now(now) if not isinstance(now, datetime.datetime) else india_common.to_ist(now)
    fetcher = fetcher or fetch_quote
    quotes, errors, rang = {}, [], []
    for symbol in _price_rules(rules):
        try:
            quotes[symbol] = fetcher(symbol, offline=offline)
        except (AlertError, OSError, ValueError) as error:
            errors.append(str(error))
    for rule in rules:
        quote = quotes.get(str(rule.get("symbol", "")).upper().replace(".NS", ""))
        reason = evaluate_rule(rule, now, quote, holidays, config)
        if reason:
            rule["fired"] = True
            rule["fired_at"] = now.isoformat()
            rang.append({"id": rule.get("id"), "reason": reason})
    return {"rang": rang, "quotes": quotes, "errors": errors}


def _add_rule(args):
    if args.from_plan:
        with open(args.plan, encoding="utf-8") as handle:
            return rules_from_plan(json.load(handle))
    chosen = [(args.above is not None, "above", args.above),
              (args.below is not None, "below", args.below),
              (args.stop is not None, "stop", args.stop),
              (args.target is not None, "target", args.target),
              (args.pct is not None, "pct_move", args.pct),
              (args.at is not None, "time", args.at),
              (args.nse_open, "opening_bell", None)]
    selected = [item for item in chosen if item[0]]
    if len(selected) != 1:
        raise AlertError("choose exactly one alert rule")
    _, kind, value = selected[0]
    if kind in ("above", "below", "stop", "target", "pct_move") and not args.symbol:
        raise AlertError("--symbol is required for a price alert")
    rule = {"id": args.id or ("%s-%s" % (args.symbol or "nse", kind)),
            "type": kind, "label": args.label or kind}
    if args.symbol:
        rule["symbol"] = args.symbol.upper().replace(".NS", "")
    if kind in ("above", "below", "stop", "target"):
        rule["price"] = float(value)
    elif kind == "pct_move":
        rule["pct"] = abs(float(value))
        rule["direction"] = args.direction
    elif kind == "time":
        rule["at"] = parse_hhmm(value).strftime("%H:%M")
    return [rule]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--from-plan", action="store_true")
    add.add_argument("--plan", default=os.path.join("trader", "plan.json"))
    add.add_argument("--symbol")
    add.add_argument("--above", type=float)
    add.add_argument("--below", type=float)
    add.add_argument("--stop", type=float)
    add.add_argument("--target", type=float)
    add.add_argument("--pct", type=float)
    add.add_argument("--direction", choices=("up", "down"), default="up")
    add.add_argument("--at")
    add.add_argument("--nse-open", action="store_true")
    add.add_argument("--label")
    add.add_argument("--id")
    add.add_argument("--output", default=ALERTS_PATH)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--now")
    check_parser.add_argument("--offline")
    check_parser.add_argument("--alerts", default=ALERTS_PATH)
    check_parser.add_argument("--output", default=PRICES_PATH)
    quote = sub.add_parser("quote")
    quote.add_argument("symbol")
    quote.add_argument("--offline")
    quote.add_argument("--output", default=PRICES_PATH)
    listing = sub.add_parser("list")
    listing.add_argument("--alerts", default=ALERTS_PATH)
    reset = sub.add_parser("reset")
    reset.add_argument("id")
    reset.add_argument("--alerts", default=ALERTS_PATH)
    args = parser.parse_args(argv)
    try:
        if args.command == "add":
            rules = load_alerts(args.output)
            rules.extend(_add_rule(args))
            write_alerts(rules, args.output)
            print("added %d alert(s)" % len(rules))
            return 0
        if args.command == "list":
            for rule in load_alerts(args.alerts):
                print("%s %s%s" % (rule.get("id"), rule.get("type"),
                                    " [fired]" if rule.get("fired") else ""))
            return 0
        if args.command == "reset":
            rules = load_alerts(args.alerts)
            found = False
            for rule in rules:
                if rule.get("id") == args.id:
                    rule.pop("fired", None)
                    rule.pop("fired_at", None)
                    found = True
            if not found:
                raise AlertError("no alert with id %s" % args.id)
            write_alerts(rules, args.alerts)
            return 0
        if args.command == "quote":
            quote_data = fetch_quote(args.symbol, args.offline)
            write_prices({quote_data["symbol"]: quote_data}, args.output)
            print("%s %.4f" % (quote_data["symbol"], quote_data["price"]))
            return 0
        rules = load_alerts(args.alerts)
        result = check(rules, args.now, args.offline)
        write_alerts(rules, args.alerts)
        if result["quotes"]:
            write_prices(result["quotes"], args.output)
        for item in result["rang"]:
            print("ALERT %s: %s" % (item["id"], item["reason"]))
        for error in result["errors"]:
            print("WARNING: %s" % error, file=sys.stderr)
        return 0 if result["rang"] else 1
    except (AlertError, OSError, ValueError, KeyError) as error:
        print("alerts: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
