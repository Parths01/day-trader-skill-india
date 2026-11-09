#!/usr/bin/env python3
"""Track official Indian stock-market disclosure rows."""

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


OUTPUT_PATH = os.path.join("trader", "disclosures.json")
STATE_PATH = os.path.join("trader", "disclosures_state.json")
WATCHLIST_PATH = os.path.join("trader", "watchlist.json")
USER_AGENT = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0)"
NSE_BULK_URL = "https://www.nseindia.com/api/snapshot-capital-market-largedeal"
NSE_INSIDER_URL = "https://www.nseindia.com/api/corporate-announcements"
NSE_FLOW_URL = "https://www.nseindia.com/api/fiidiiTradeReact?type=equity"
BSE_BULK_URL = "https://www.bseindia.com/markets/equity/EQReports/bulk_deals.aspx"


class DisclosureError(Exception):
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


def _fetch_json(url, params=None, opener=None):
    query = urllib.parse.urlencode(params or {})
    full_url = url + (("&" if "?" in url else "?") + query if query else "")
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(full_url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.nseindia.com/" if "nseindia" in url
        else "https://www.bseindia.com/",
    })
    try:
        with opener(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            ValueError) as error:
        raise DisclosureError("official data fetch failed: %s" % error)


def _fixture(path, name):
    if not path:
        return None
    if os.path.isdir(path):
        path = os.path.join(path, name + ".json")
    if not os.path.exists(path):
        raise DisclosureError("no offline fixture for %s" % name)
    return _read_json(path)


def _first(row, *names):
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _date(value):
    if value in (None, ""):
        return None
    text = str(value).strip().replace("T", " ").split(" ")[0]
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d",
                "%d-%b-%y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None


def _side(value):
    text = str(value or "").strip().upper()
    if text in ("B", "BUY", "PURCHASE", "ACQUISITION"):
        return "buy"
    if text in ("S", "SELL", "SALE", "DISPOSAL"):
        return "sell"
    return text.lower() or None


def _rows(data, *keys):
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
    for value in data.values():
        if isinstance(value, list) and (not value or isinstance(value[0], dict)):
            return value
    return []


def normalise(row, source, kind, disclosed_date=None):
    symbol = _first(row, "symbol", "Symbol", "scripCode", "securityCode")
    symbol = str(symbol or "").upper().replace(".NS", "")
    trade_date = _date(_first(row, "date", "tradeDate", "transactionDate",
                              "dateOfTransaction", "transaction_date"))
    disclosed = _date(_first(row, "disclosedDate", "filingDate",
                             "dateOfDisclosure", "broadcastDate")) or disclosed_date
    side = _side(_first(row, "buySell", "buy_sell", "transactionType",
                        "tdpTransactionType", "type", "acqMode"))
    quantity = _number(_first(row, "qty", "quantity", "numberOfSecurities",
                              "securitiesTransacted"))
    price = _number(_first(row, "watp", "price", "tradePrice", "valuePerSecurity"))
    who = _first(row, "clientName", "client", "personName", "acquirerName",
                 "sellerName", "entityName", "name")
    identity = _first(row, "id", "seq", "srNo", "filingId")
    if identity is None:
        identity = "%s|%s|%s|%s|%s|%s" % (
            source, kind, symbol, who, trade_date, quantity)
    identifier = hashlib.sha256(str(identity).encode("utf-8")).hexdigest()[:20]
    days = None
    if trade_date and disclosed:
        try:
            days = (datetime.date.fromisoformat(disclosed) -
                    datetime.date.fromisoformat(trade_date)).days
        except ValueError:
            pass
    return {
        "id": identifier,
        "source": source,
        "kind": kind,
        "who": str(who or "").strip(),
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "price": price,
        "date": trade_date,
        "disclosed_date": disclosed,
        "days_to_disclose": days,
        "watchlist": False,
        "url": _first(row, "url", "link", "attachment", "pdf") or "",
    }


def parse_bulk(data, source="nse", disclosed_date=None):
    rows = _rows(data, "BULK_DEALS_DATA", "bulkDeals", "data", "Table")
    if isinstance(data, dict):
        disclosed_date = disclosed_date or _date(
            _first(data, "as_on_date", "asOnDate", "date"))
    return [normalise(row, source, "bulk", disclosed_date) for row in rows
            if isinstance(row, dict)]


def parse_block(data, source="nse", disclosed_date=None):
    rows = _rows(data, "BLOCK_DEALS_DATA", "blockDeals", "data", "Table")
    return [normalise(row, source, "block", disclosed_date) for row in rows
            if isinstance(row, dict)]


def parse_insider(data, source="nse"):
    rows = _rows(data, "data", "insider", "insiderTrading", "Table")
    return [normalise(row, source, "insider") for row in rows
            if isinstance(row, dict)]


def parse_flows(data, source="nse"):
    rows = _rows(data, "data", "fiiDii", "FII_DII", "Table")
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result.append({
            "id": hashlib.sha256(json.dumps(row, sort_keys=True).encode(
                "utf-8")).hexdigest()[:20],
            "source": source,
            "kind": "fii_dii_flow",
            "who": _first(row, "category", "clientType", "type") or "",
            "symbol": "",
            "side": _side(_first(row, "buySell", "side")),
            "quantity": _number(_first(row, "buyValue", "buy_value")),
            "price": _number(_first(row, "sellValue", "sell_value")),
            "date": _date(_first(row, "date", "tradeDate", "dt")),
            "disclosed_date": _date(_first(row, "date", "tradeDate", "dt")),
            "days_to_disclose": 0,
            "watchlist": False,
            "url": "",
            "buy_value": _number(_first(row, "buyValue", "buy_value")),
            "sell_value": _number(_first(row, "sellValue", "sell_value")),
            "net_value": _number(_first(row, "netValue", "net_value")),
        })
    return result


def load_watchlist(path=WATCHLIST_PATH):
    if not os.path.exists(path):
        return set()
    data = _read_json(path)
    values = data.get("symbols", data.get("watchlist", data)) if isinstance(data, dict) else data
    result = set()
    for value in values if isinstance(values, list) else []:
        result.add(str(value.get("symbol", value) if isinstance(value, dict) else value)
                   .upper().replace(".NS", ""))
    return result


def mark_watchlist(rows, symbols):
    for row in rows:
        row["watchlist"] = bool(row.get("symbol") and row["symbol"] in symbols)
    return rows


def load_seen(path=STATE_PATH):
    if not os.path.exists(path):
        return set()
    data = _read_json(path)
    return set(data.get("seen", data if isinstance(data, list) else []))


def save_seen(seen, path=STATE_PATH):
    _write_json({"updated_at": india_common.to_ist().isoformat(),
                 "seen": sorted(seen)}, path)


def collect(offline=None, sources=("bulk", "block", "insider", "flows"),
            opener=None):
    rows, errors = [], []
    for source in sources:
        try:
            if source == "bulk":
                data = _fixture(offline, "bulk") if offline else _fetch_json(
                    NSE_BULK_URL, opener=opener)
                rows.extend(parse_bulk(data))
            elif source == "block":
                data = _fixture(offline, "block") if offline else _fetch_json(
                    "https://www.nseindia.com/api/block-deal", opener=opener)
                rows.extend(parse_block(data))
            elif source == "insider":
                data = _fixture(offline, "insider") if offline else _fetch_json(
                    NSE_INSIDER_URL, {"index": "equities"}, opener=opener)
                rows.extend(parse_insider(data))
            elif source == "flows":
                data = _fixture(offline, "flows") if offline else _fetch_json(
                    NSE_FLOW_URL, opener=opener)
                rows.extend(parse_flows(data))
            else:
                raise DisclosureError("unknown source %s" % source)
        except (DisclosureError, OSError, ValueError) as error:
            errors.append("%s: %s" % (source, error))
        time.sleep(0.5)
    unique = {row["id"]: row for row in rows}
    return list(unique.values()), errors


def new_rows(rows, seen):
    return [row for row in rows if row["id"] not in seen]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="bulk,block,insider,flows")
    parser.add_argument("--offline")
    parser.add_argument("--watchlist", default=WATCHLIST_PATH)
    parser.add_argument("--state", default=STATE_PATH)
    parser.add_argument("--output", default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    try:
        sources = tuple(item.strip().lower() for item in args.source.split(",")
                        if item.strip())
        rows, errors = collect(args.offline, sources)
        mark_watchlist(rows, load_watchlist(args.watchlist))
        seen = load_seen(args.state)
        fresh = new_rows(rows, seen)
        _write_json({"checked_at": india_common.to_ist().isoformat(),
                     "rows": fresh, "errors": errors}, args.output)
        save_seen(seen | {row["id"] for row in rows}, args.state)
        for row in fresh:
            flag = " WATCHLIST" if row["watchlist"] else ""
            print("NEW %s %s %s %s%s" % (
                row["kind"], row["symbol"] or row["who"], row["side"] or "",
                row["date"] or "", flag))
        for error in errors:
            print("WARNING: %s" % error, file=sys.stderr)
        return 0 if fresh else 1
    except (DisclosureError, OSError, ValueError) as error:
        print("disclosures: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
