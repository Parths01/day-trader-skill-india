#!/usr/bin/env python3
"""Quarterly Indian company facts from a swappable fundamentals source."""

import argparse
import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import india_common


FACTS_PATH = os.path.join("trader", "facts.json")
YAHOO_URL = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/%s"
USER_AGENT = "Mozilla/5.0 (compatible; day-trader-skill-india/1.0)"


class FactsError(Exception):
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


def _fixture(path, symbol):
    if not path:
        return None
    if os.path.isdir(path):
        key = str(symbol).upper().replace(".NS", "")
        candidates = [os.path.join(path, key + ".json"),
                      os.path.join(path, "facts-" + key + ".json")]
        path = next((item for item in candidates if os.path.exists(item)), None)
    if not path or not os.path.exists(path):
        raise FactsError("no offline fixture for %s" % symbol)
    return _read_json(path)


def _get_yahoo(symbol, opener=None):
    metrics = ",".join(("annualTotalRevenue", "quarterlyTotalRevenue",
                        "annualOperatingIncome", "quarterlyOperatingIncome",
                        "annualNetIncome", "quarterlyNetIncome",
                        "annualDilutedEPS", "quarterlyDilutedEPS"))
    end = int(time.time())
    start = end - 6 * 366 * 24 * 60 * 60
    url = YAHOO_URL % urllib.parse.quote(india_common.yahoo_symbol(symbol), safe="")
    params = urllib.parse.urlencode({"type": metrics, "period1": start, "period2": end})
    opener = opener or urllib.request.urlopen
    request = urllib.request.Request(url + "?" + params,
                                     headers={"User-Agent": USER_AGENT})
    try:
        with opener(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            ValueError) as error:
        raise FactsError("Yahoo fundamentals failed for %s: %s" % (symbol, error))


def _value(row):
    if isinstance(row, dict):
        for key in ("reportedValue", "raw", "value"):
            if row.get(key) is not None:
                return float(row[key])
    return float(row) if row is not None else None


def _rows(data, metric):
    if isinstance(data, dict) and "periods" in data:
        return data["periods"]
    result = data.get("timeseries", {}).get("result", []) if isinstance(data, dict) else []
    for row in result:
        if row.get("meta", {}).get("type", [None])[0] == metric or row.get("type") == metric:
            return row.get(metric) or row.get("data") or []
    return []


def _date(row):
    value = row.get("asOfDate") or row.get("periodEndDate") or row.get("date")
    return str(value)[:10]


def _normalise_periods(data):
    if isinstance(data, dict) and "quarters" in data:
        return data["quarters"]
    names = {
        "revenue": ("quarterlyTotalRevenue", "totalRevenue"),
        "operating_income": ("quarterlyOperatingIncome", "operatingIncome"),
        "net_income": ("quarterlyNetIncome", "netIncome"),
        "eps": ("quarterlyDilutedEPS", "dilutedEPS"),
    }
    found = {}
    for field, metrics in names.items():
        rows = []
        for metric in metrics:
            rows = _rows(data, metric)
            if rows:
                break
        for row in rows:
            found.setdefault(_date(row), {})[field] = _value(
                row.get("value", row) if isinstance(row, dict) else row)
    periods = []
    for date, values in found.items():
        values["period_end"] = date
        if values.get("revenue") and values.get("operating_income") is not None:
            values["operating_margin"] = values["operating_income"] / values["revenue"] * 100
        periods.append(values)
    return sorted(periods, key=lambda row: row["period_end"], reverse=True)


def _attach_comparisons(periods):
    by_month = {row["period_end"][5:7] + "-" + row["period_end"][:4]: row
                for row in periods}
    for row in periods:
        try:
            date = datetime.date.fromisoformat(row["period_end"])
        except ValueError:
            continue
        prior = by_month.get("%02d-%s" % (date.month, date.year - 1))
        if prior:
            for field in ("revenue", "operating_margin", "net_income", "eps"):
                if row.get(field) is not None and prior.get(field) not in (None, 0):
                    row[field + "_yoy_percent"] = (
                        (row[field] - prior[field]) / abs(prior[field]) * 100)
    return periods


def facts(symbol, source="yahoo", offline=None, opener=None):
    if source != "yahoo":
        raise FactsError("source %s is not implemented; use the adapter interface" % source)
    data = _fixture(offline, symbol) if offline else _get_yahoo(symbol, opener)
    periods = _attach_comparisons(_normalise_periods(data))
    if not periods:
        raise FactsError("no quarterly facts returned for %s" % symbol)
    ttm = {}
    recent = periods[:4]
    for field in ("revenue", "operating_income", "net_income", "eps"):
        values = [row[field] for row in recent if row.get(field) is not None]
        if len(values) == 4:
            ttm[field] = sum(values)
    if ttm.get("revenue") and ttm.get("operating_income") is not None:
        ttm["operating_margin"] = ttm["operating_income"] / ttm["revenue"] * 100
    return {"symbol": str(symbol).upper().replace(".NS", ""),
            "source": source, "updated_at": india_common.to_ist().isoformat(),
            "quarters": periods, "ttm": ttm}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol")
    parser.add_argument("--source", default="yahoo")
    parser.add_argument("--offline")
    parser.add_argument("--output", default=FACTS_PATH)
    args = parser.parse_args(argv)
    try:
        result = facts(args.symbol, args.source, args.offline)
        _write_json(result, args.output)
        print(json.dumps(result, indent=2))
        return 0
    except (FactsError, OSError, ValueError) as error:
        print("analyst: %s" % error)
        return 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
