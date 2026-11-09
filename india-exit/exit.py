#!/usr/bin/env python3
"""NSE long-only exit planner with configurable tick-size stops and targets."""

import argparse
import datetime
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_FLOOR

import india_common

PLAN_PATH = os.path.join("trader", "plan.json")
ATR_BARS = 14
MIN_RISK_PCT = Decimal("0.05")


class PlanError(Exception):
    pass


def decimal(value, what="number"):
    try:
        return Decimal(repr(value)) if isinstance(value, float) else Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise PlanError("%s is not a number: %r" % (what, value))


def parse_stop(value):
    text = str(value).lower().strip()
    if text in ("or-mid", "or_mid", "midpoint"):
        return "or_mid", None
    if text in ("or-low", "or_low", "range-low"):
        return "or_low", None
    for prefix in ("price:", "pct:", "atr:"):
        if text.startswith(prefix):
            amount = decimal(text[len(prefix):], "stop")
            if amount <= 0 or (prefix == "pct:" and amount >= 100) or (prefix == "atr:" and amount <= 0):
                raise PlanError("invalid stop %r" % value)
            return prefix[:-1], amount
    raise PlanError("stop must be or-mid, or-low, price:X, pct:X, or atr:K")


def parse_target(value):
    text = str(value).strip().lower()
    if text.startswith("price:"):
        amount = decimal(text[6:], "target")
        if amount <= 0:
            raise PlanError("invalid target %r" % value)
        return "price", amount
    match = re.match(r"^(\d+(?:\.\d+)?)r$", text)
    if not match or decimal(match.group(1)) <= 0:
        raise PlanError("target must be NR or price:X")
    return "r", decimal(match.group(1))


def atr_of(bars):
    if not bars:
        raise PlanError("ATR needs session bars")
    values, previous = [], None
    for bar in bars[-ATR_BARS:]:
        high, low, close = decimal(bar["high"]), decimal(bar["low"]), decimal(bar["close"])
        true_range = high - low
        if previous is not None:
            true_range = max(true_range, abs(high - previous), abs(low - previous))
        values.append(true_range)
        previous = close
    return sum(values, Decimal("0")) / len(values), len(values)


def compute(entry, stop_rule, stop_value, target_rule, target_value,
            or_high, or_low, atr=None, atr_n=None, symbol=None, config=None,
            planned_exit_time=None):
    config = config or india_common.load_config()
    entry = india_common.round_to_tick(decimal(entry, "entry"), symbol, config)
    if stop_rule == "or_mid":
        if or_high is None or or_low is None:
            raise PlanError("opening range is required for or-mid")
        raw_stop = (decimal(or_high) + decimal(or_low)) / 2
        stop_label = "opening-range midpoint"
    elif stop_rule == "or_low":
        if or_low is None:
            raise PlanError("opening range low is required for or-low")
        raw_stop, stop_label = decimal(or_low), "opening-range low"
    elif stop_rule == "price":
        raw_stop, stop_label = stop_value, "your price"
    elif stop_rule == "pct":
        raw_stop = entry * (Decimal("1") - stop_value / 100)
        stop_label = "%s%% under the entry" % stop_value
    else:
        if atr is None:
            raise PlanError("ATR stop needs session bars")
        raw_stop = entry - decimal(atr) * stop_value
        stop_label = "%s x ATR(%s) under the entry" % (stop_value, atr_n or ATR_BARS)
    tick = config.get("tick_sizes", {}).get(str(symbol).upper(), india_common.DEFAULT_TICK_SIZE)
    stop = (decimal(raw_stop) / tick).quantize(Decimal("1"), rounding=ROUND_FLOOR) * tick
    if stop >= entry:
        raise PlanError("stop is at or above the entry")
    risk = entry - stop
    if risk < entry * MIN_RISK_PCT / 100:
        raise PlanError("risk is too tight to survive the spread")
    if target_rule == "price":
        target = decimal(target_value)
        target_label = "your price"
        target_r = (target - entry) / risk
    else:
        target_r = target_value
        target = entry + risk * target_r
        target_label = "%sR (%s times the risk)" % (target_r, target_r)
    target = india_common.round_to_tick(target, symbol, config)
    if target <= entry:
        raise PlanError("target is at or below the entry")
    target_r = (target - entry) / risk
    flat_by = config.get("flat_by", "15:15")
    warning = None
    if planned_exit_time and parse_hhmm(planned_exit_time) > parse_hhmm(flat_by):
        warning = "planned exit is after the flat-by time %s IST" % flat_by
    return {
        "entry": entry, "stop": stop, "target": target, "risk": risk,
        "reward_risk": target_r, "stop_rule": stop_rule, "stop_label": stop_label,
        "target_label": target_label, "target_r": target_r, "flat_by": flat_by,
        "planned_exit_time": planned_exit_time or flat_by, "warning": warning,
    }


def parse_hhmm(value):
    match = re.match(r"^(\d{1,2}):(\d{2})$", str(value))
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise PlanError("invalid time %r" % value)
    return datetime.time(int(match.group(1)), int(match.group(2)))


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def plan_from_entry(entry_doc, stop_text, target_text, symbol=None, config=None,
                    planned_exit_time=None, atr=None, atr_n=None):
    if entry_doc.get("status") != "triggered":
        raise PlanError("entry.json has not triggered")
    stop_rule, stop_value = parse_stop(stop_text)
    target_rule, target_value = parse_target(target_text)
    return compute(entry_doc["trigger"]["price"], stop_rule, stop_value, target_rule,
                   target_value, entry_doc.get("opening_range", {}).get("high"),
                   entry_doc.get("opening_range", {}).get("low"), symbol=symbol or entry_doc.get("symbol"),
                   config=config, planned_exit_time=planned_exit_time, atr=atr, atr_n=atr_n)


def write_plan(plan, entry_doc, path=PLAN_PATH):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    document = {"created_by": "india-exit", "symbol": entry_doc.get("symbol"),
                "side": "buy", "date": entry_doc.get("date"), **_jsonable(plan)}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan",))
    parser.add_argument("--entry", default=os.path.join("trader", "entry.json"))
    parser.add_argument("--stop", default="or-mid")
    parser.add_argument("--target", default="1R")
    parser.add_argument("--symbol")
    parser.add_argument("--flat-by", default=None)
    parser.add_argument("--exit-time")
    parser.add_argument("--atr-value", type=float,
                        help="completed-session ATR value when using --stop atr:K")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", default=PLAN_PATH)
    args = parser.parse_args(argv)
    try:
        with open(args.entry, encoding="utf-8") as handle:
            entry_doc = json.load(handle)
        config = india_common.load_config()
        if args.flat_by:
            config["flat_by"] = args.flat_by
        plan = plan_from_entry(entry_doc, args.stop, args.target, args.symbol, config,
                               args.exit_time, args.atr_value)
        if args.write:
            write_plan(plan, entry_doc, args.output)
        print("stop %s target %s" % (plan["stop"], plan["target"]))
        if plan["warning"]:
            print("WARNING: %s" % plan["warning"])
        return 0
    except (PlanError, OSError, ValueError) as error:
        print("exit: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
