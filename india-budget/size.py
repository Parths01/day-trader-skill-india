#!/usr/bin/env python3
"""Size one NSE long bracket order in whole shares."""

import argparse
import json
import math
import os
import sys
from decimal import Decimal, ROUND_FLOOR

import india_common

ORDER_PATH = os.path.join("trader", "orders.json")
DEFAULTS = {
    "max_position_pct": Decimal("75"),
    "max_order_value": Decimal("0"),
    "cash_buffer_pct": Decimal("10"),
    "allow_margin": False,
    "intraday_margin_multiplier": Decimal("1"),
}


class SizeError(Exception):
    pass


def _d(value, what="number"):
    try:
        return Decimal(str(value).replace(",", "").replace("Rs", "").strip())
    except Exception as error:
        raise SizeError("%s is not a number: %r" % (what, value)) from error


def load_config(path=india_common.DEFAULT_CONFIG_PATH):
    config = dict(DEFAULTS)
    config.update(india_common.load_config(path))
    for key in ("max_position_pct", "max_order_value", "cash_buffer_pct",
                "intraday_margin_multiplier"):
        config[key] = _d(config[key])
    return config


def _whole(value):
    return int(Decimal(value).to_integral_value(rounding=ROUND_FLOOR))


def size_plan(plan, config=None, cash=None, symbol=None):
    config = config or load_config()
    symbol = symbol or plan.get("symbol")
    entry = _d(plan.get("entry"), "entry")
    stop = _d(plan.get("stop"), "stop")
    target = _d(plan.get("target"), "target")
    if not symbol or entry <= 0 or stop >= entry or target <= entry:
        raise SizeError("plan must contain a long symbol, entry, lower stop, and higher target")
    capital = _d(config.get("capital", 0), "capital")
    risk = entry - stop
    max_loss = _d(config.get("max_loss_per_trade", 0), "max_loss_per_trade")
    position_limit = capital * config["max_position_pct"] / 100
    order_limit = config["max_order_value"] or capital
    cash_value = capital if cash is None else _d(cash, "cash")
    cash_limit = cash_value * (1 - config["cash_buffer_pct"] / 100)
    if config.get("allow_margin"):
        cash_limit *= config["intraday_margin_multiplier"]
    limits = [
        ("max loss", _whole(max_loss / risk) if max_loss > 0 else 10 ** 18),
        ("position cap", _whole(position_limit / entry) if position_limit > 0 else 10 ** 18),
        ("max order value", _whole(order_limit / entry) if order_limit > 0 else 10 ** 18),
        ("cash after buffer", _whole(cash_limit / entry) if cash_limit > 0 else 10 ** 18),
    ]
    qty = min(limit for _, limit in limits)
    if qty <= 0:
        raise SizeError("stop is too far away: one share exceeds max loss or available funds")
    bound = [name for name, limit in limits if limit == qty]
    cost = entry * qty
    return {
        "symbol": str(symbol).upper(), "qty": qty, "entry": entry, "stop": stop,
        "target": target, "risk_per_share": risk, "max_loss": risk * qty,
        "cost": cost, "bound_by": bound[0], "limits": [
            {"name": name, "shares": None if value >= 10 ** 18 else value,
             "binds": value == qty} for name, value in limits
        ], "cash_buffer": cash_value - cash_limit / (
            config["intraday_margin_multiplier"] if config.get("allow_margin") else 1
        ), "margin_enabled": bool(config.get("allow_margin")),
        "paper": bool(config.get("paper", True)),
    }


def bracket_order(sizing):
    return {
        "symbol": sizing["symbol"], "side": "buy", "qty": str(sizing["qty"]),
        "type": "market", "time_in_force": "day", "order_class": "bracket",
        "take_profit_limit_price": format(sizing["target"], "f"),
        "stop_loss_stop_price": format(sizing["stop"], "f"),
        "plan": {
            "entry": float(sizing["entry"]), "stop": float(sizing["stop"]),
            "target": float(sizing["target"]), "risk_per_share": float(sizing["risk_per_share"]),
            "max_loss": float(sizing["max_loss"]),
        },
    }


def write_order(order, sizing, path=ORDER_PATH):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"status": "proposed", "paper": sizing["paper"],
                   "orders": [order], "sizing": _jsonable(sizing)}, handle, indent=2)


def _jsonable(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", default=os.path.join("trader", "plan.json"))
    parser.add_argument("--config", default=india_common.DEFAULT_CONFIG_PATH)
    parser.add_argument("--cash", type=float)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", default=ORDER_PATH)
    args = parser.parse_args(argv)
    try:
        with open(args.plan, encoding="utf-8") as handle:
            plan = json.load(handle)
        sizing = size_plan(plan, load_config(args.config), args.cash)
        order = bracket_order(sizing)
        if args.write:
            write_order(order, sizing, args.output)
        print("Size: %d shares of %s at Rs %s, bound by %s" %
              (sizing["qty"], sizing["symbol"], sizing["entry"], sizing["bound_by"]))
        return 0
    except (OSError, ValueError, SizeError) as error:
        print("budget: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
