#!/usr/bin/env python3
"""NSE chart scanner. Standard library only; no order is ever placed."""

import argparse
import csv
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import india_common

NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s"
DEFAULT_UNIVERSE = os.path.join("trader", "india_universe.json")
WATCHLIST = os.path.join("trader", "watchlist.json")
USER_AGENT = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0)"
SETUPS = ("breakout_20d", "bull_flag", "reclaim_ma20", "oversold", "oversold_bounce")


class ScanError(Exception):
    pass


def _read_url(url, retries=2, pause=0.3, timeout=20):
    last = None
    for attempt in range(retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as error:
            last = error
            if attempt < retries:
                time.sleep(pause * (2 ** attempt))
    raise ScanError("fetch failed for %s: %s" % (url, last))


def _json_text(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def parse_equity_csv(text):
    """Return NSE EQ-series rows as ``{symbol, name}`` dictionaries."""
    rows = []
    reader = csv.DictReader(text.splitlines())
    fields = {str(field).strip().upper(): field for field in (reader.fieldnames or [])}
    symbol_field = fields.get("SYMBOL")
    series_field = fields.get("SERIES")
    name_field = fields.get("NAME OF COMPANY") or fields.get("NAME")
    if not symbol_field or not series_field:
        raise ScanError("NSE equity CSV has no SYMBOL/SERIES columns")
    for row in reader:
        if row.get(series_field, "").strip().upper() != "EQ":
            continue
        symbol = row.get(symbol_field, "").strip().upper()
        if symbol:
            rows.append({"symbol": symbol, "name": row.get(name_field, "").strip()
                         if name_field else ""})
    return rows


def parse_nifty500_csv(text):
    reader = csv.DictReader(text.splitlines())
    fields = {str(field).strip().upper(): field for field in (reader.fieldnames or [])}
    symbol_field = fields.get("SYMBOL")
    if not symbol_field:
        raise ScanError("Nifty 500 CSV has no SYMBOL column")
    return [{"symbol": row[symbol_field].strip().upper(),
             "name": row.get(fields.get("COMPANY NAME"), "").strip()
             if fields.get("COMPANY NAME") else ""}
            for row in reader if row.get(symbol_field, "").strip()]


def load_universe(path=DEFAULT_UNIVERSE):
    data = _json_text(path)
    if isinstance(data, dict):
        data = data.get("symbols", data.get("universe", []))
    if not isinstance(data, list):
        raise ScanError("universe cache must contain a list")
    return [{"symbol": str(row.get("symbol", row)).upper(),
             "name": row.get("name", "") if isinstance(row, dict) else ""}
            for row in data]


def write_universe(rows, path=DEFAULT_UNIVERSE, source="NSE"):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"source": source, "updated_at": datetime.datetime.now(
            india_common.IST).isoformat(), "symbols": rows}, handle, indent=2)


def _chart_doc(data):
    if "chart" in data:
        result = data["chart"].get("result") or []
        if not result:
            raise ScanError("Yahoo response contains no chart")
        return result[0]
    if "timestamp" in data and "indicators" in data:
        return data
    raise ScanError("not a Yahoo chart response")


def parse_chart(data):
    """Normalize Yahoo chart JSON to timestamped OHLCV rows."""
    chart = _chart_doc(data)
    timestamps = chart.get("timestamp") or []
    indicators = chart.get("indicators", {})
    quote = (indicators.get("quote") or [{}])[0]
    rows = []
    for index, timestamp in enumerate(timestamps):
        row = {"timestamp": int(timestamp)}
        for key in ("open", "high", "low", "close", "volume"):
            values = quote.get(key) or []
            row[key] = values[index] if index < len(values) else None
        if row["close"] is not None:
            rows.append(row)
    return rows, chart.get("meta", {})


def _fixture_map(path):
    if not path:
        return {}
    if os.path.isdir(path):
        result = {}
        for filename in os.listdir(path):
            if filename.endswith(".json"):
                result[filename[:-5].upper().replace(".NS", "")] = _json_text(
                    os.path.join(path, filename))
        return result
    data = _json_text(path)
    if isinstance(data, dict) and "chart" not in data and "timestamp" not in data:
        return {key.upper().replace(".NS", ""): value for key, value in data.items()}
    return {"*": data}


def fetch_chart(symbol, interval, range_name, pause=0.3, offline=None):
    fixtures = _fixture_map(offline)
    key = symbol.upper().replace(".NS", "")
    if fixtures:
        fixture = fixtures.get(key, fixtures.get("*"))
        if fixture is None:
            raise ScanError("no offline fixture for %s" % symbol)
        return _chart_doc(fixture)
    query = urllib.parse.urlencode({"range": range_name, "interval": interval,
                                    "events": "history", "includePrePost": "false"})
    return _chart_doc(json.loads(_read_url(YAHOO_URL % urllib.parse.quote(
        india_common.yahoo_symbol(symbol), safe="") + "?" + query,
        pause=pause).decode("utf-8")))


def _ist_timestamp(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).astimezone(
        india_common.IST)


def daily_closes(rows, now=None):
    """Drop today's incomplete daily bar when scanning before its close."""
    current = india_common.to_ist(now)
    result = []
    for row in rows:
        local = _ist_timestamp(row["timestamp"])
        if local.date() == current.date() and current.time() < datetime.time(15, 30):
            continue
        result.append((local.date(), float(row["close"])))
    return result


def _rsi(values, period=14):
    if len(values) <= period:
        return None
    gains = [max(values[i] - values[i - 1], 0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def daily_setups(closes):
    values = [value for _, value in closes]
    if len(values) < 21:
        return []
    hits = []
    last = values[-1]
    if last > max(values[-21:-1]):
        hits.append("breakout_20d")
    if len(values) >= 16:
        prior = values[-16:-6]
        flag = values[-5:]
        if prior[-1] > prior[0] * 1.10 and max(flag) - min(flag) <= max(flag) * 0.05:
            hits.append("bull_flag")
    ma = sum(values[-20:]) / 20
    previous_ma = sum(values[-21:-1]) / 20
    if values[-2] < previous_ma and last > ma:
        hits.append("reclaim_ma20")
    rsi = _rsi(values)
    if rsi is not None and rsi < 30:
        hits.append("oversold")
    if len(values) >= 16 and _rsi(values[:-1]) is not None and _rsi(values[:-1]) < 30 and last > values[-2]:
        hits.append("oversold_bounce")
    return hits


def _liquid(meta, min_price, min_volume):
    volume = meta.get("averageDailyVolume3Month") or meta.get("regularMarketVolume") or 0
    return float(meta.get("regularMarketPrice") or 0) >= min_price and int(volume) >= min_volume


def orb_breakout(rows, now=None, opening_minutes=15):
    current = india_common.to_ist(now)
    if not rows:
        return None
    day = _ist_timestamp(rows[0]["timestamp"]).date()
    session_open = datetime.datetime.combine(day, datetime.time(9, 15), tzinfo=india_common.IST)
    range_end = session_open + datetime.timedelta(minutes=opening_minutes)
    bars = []
    for row in rows:
        local = _ist_timestamp(row["timestamp"])
        start = local.replace(second=0, microsecond=0)
        if local.date() != day or local < session_open or start + datetime.timedelta(minutes=5) > current:
            continue
        bars.append((local, row))
    opening = [row for local, row in bars if session_open <= local < range_end]
    if not opening:
        return None
    high = max(float(row.get("high") or row["close"]) for row in opening)
    for local, row in bars:
        if local >= range_end and float(row["close"]) > high:
            return {"time": local.isoformat(), "close": float(row["close"]),
                    "range_high": high}
    return None


def _write_watchlist(mode, hits, scanned, failed, output=WATCHLIST):
    parent = os.path.dirname(output)
    if parent:
        os.makedirs(parent, exist_ok=True)
    document = {"mode": mode, "as_of": datetime.datetime.now(
        india_common.IST).isoformat(), "scanned": scanned, "failed": failed, "hits": hits}
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    return document


def _symbols(args):
    if args.symbols:
        return [{"symbol": value.strip().upper(), "name": ""} for value in args.symbols.split(",") if value.strip()]
    path = args.universe
    if getattr(args, "nifty500", False) and path == DEFAULT_UNIVERSE:
        path = os.path.join("trader", "nifty500.json")
    rows = load_universe(path)
    if args.limit:
        rows = rows[:args.limit]
    return rows


def run_daily(args):
    config = india_common.load_config(args.config)
    min_price = args.min_price
    min_volume = args.min_volume
    hits, failed = [], []
    symbols = _symbols(args)
    for row in symbols:
        symbol = row["symbol"]
        try:
            chart = fetch_chart(symbol, "1d", "3mo", args.pause, args.offline)
            rows, meta = parse_chart(chart)
            if not _liquid(meta, min_price, min_volume):
                continue
            setups = daily_setups(daily_closes(rows, args.now))
            if setups:
                hits.append({"symbol": symbol, "name": row.get("name", ""),
                             "setups": setups, "price": meta.get("regularMarketPrice"),
                             "volume": meta.get("regularMarketVolume")})
        except (ScanError, ValueError, KeyError, TypeError) as error:
            failed.append({"symbol": symbol, "error": str(error)})
        if not args.offline:
            time.sleep(args.pause)
    hits.sort(key=lambda hit: (hit.get("price") or 0) * (hit.get("volume") or 0), reverse=True)
    return _write_watchlist("daily", hits, len(symbols), failed, args.output)


def run_orb(args):
    hits, failed = [], []
    symbols = _symbols(args)
    for row in symbols:
        symbol = row["symbol"]
        try:
            chart = fetch_chart(symbol, "5m", "1d", args.pause, args.offline)
            bars, meta = parse_chart(chart)
            if not _liquid(meta, args.min_price, args.min_volume):
                continue
            breakout = orb_breakout(bars, args.now, args.or_minutes)
            if breakout:
                hits.append(dict({"symbol": symbol, "name": row.get("name", ""),
                                  "price": meta.get("regularMarketPrice"),
                                  "volume": meta.get("regularMarketVolume")}, **breakout))
        except (ScanError, ValueError, KeyError, TypeError) as error:
            failed.append({"symbol": symbol, "error": str(error)})
        if not args.offline:
            time.sleep(args.pause)
    return _write_watchlist("orb", hits, len(symbols), failed, args.output)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    universe = sub.add_parser("universe")
    universe.add_argument("--nifty500", action="store_true")
    universe.add_argument("--output", default=DEFAULT_UNIVERSE)
    universe.add_argument("--offline")
    for name in ("daily", "orb"):
        command = sub.add_parser(name)
        command.add_argument("--limit", type=int)
        command.add_argument("--symbols")
        command.add_argument("--universe", default=DEFAULT_UNIVERSE)
        command.add_argument("--nifty500", action="store_true")
        command.add_argument("--offline")
        command.add_argument("--output", default=WATCHLIST)
        command.add_argument("--pause", type=float, default=0.3)
        command.add_argument("--config", default=india_common.DEFAULT_CONFIG_PATH)
        command.add_argument("--now")
        command.add_argument("--min-price", type=float, default=20.0)
        command.add_argument("--min-volume", type=int, default=100000)
        if name == "orb":
            command.add_argument("--or-minutes", type=int, default=15)
    args = parser.parse_args(argv)
    if args.command == "universe":
        try:
            if args.offline:
                path = os.path.join(args.offline, "nifty500.csv" if args.nifty500 else "EQUITY_L.csv")
                text = open(path, encoding="utf-8").read()
            else:
                text = _read_url(NIFTY500_URL if args.nifty500 else NSE_EQUITY_URL).decode("utf-8-sig")
            rows = parse_nifty500_csv(text) if args.nifty500 else parse_equity_csv(text)
            write_universe(rows, args.output, "NIFTY500" if args.nifty500 else "NSE")
            print("Cached %d symbols in %s" % (len(rows), args.output))
            return 0
        except (OSError, ScanError) as error:
            print("universe: %s" % error, file=sys.stderr)
            return 1
    try:
        result = run_daily(args) if args.command == "daily" else run_orb(args)
        print("%s: %d hits, %d scanned, %d failed" %
              (args.command, len(result["hits"]), result["scanned"], len(result["failed"])))
        return 0 if result["hits"] else 1
    except (OSError, ScanError, ValueError) as error:
        print("%s: %s" % (args.command, error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
