#!/usr/bin/env python3
"""Indian order tickets with risk and two-step approval gates."""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from decimal import Decimal

import india_common


ORDERS_PATH = os.path.join("trader", "orders.json")
RISK_PATH = os.path.join("trader", "state", "risk.json")
STATE_PATH = os.path.join("trader", "state", "india-broker.json")
YES = "yes"


class TicketError(Exception):
    pass


def _read(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write(path, value):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def fingerprint(order):
    fields = ("symbol", "side", "qty", "notional", "type", "time_in_force",
              "limit_price", "stop_price", "order_class",
              "take_profit_limit_price", "stop_loss_stop_price",
              "stop_loss_limit_price")
    core = {key: order[key] for key in fields
            if key in order and order[key] is not None}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _orders(data):
    if isinstance(data, dict):
        return data.get("orders", [])
    return data if isinstance(data, list) else []


def _risk_result(risk, order, today):
    if not risk or risk.get("date") != today:
        return None
    wanted = fingerprint(order)
    for result in risk.get("results", []):
        if result.get("fingerprint") == wanted:
            return result
    return None


def _charges(order, config):
    qty = _number(order.get("qty")) or 0
    entry = _number((order.get("plan") or {}).get("entry"))
    stop = _number((order.get("plan") or {}).get("stop"))
    target = _number((order.get("plan") or {}).get("target"))
    if entry is None:
        entry = _number(order.get("limit_price")) or 0
    exit_price = stop if stop is not None else target if target is not None else entry
    return india_common.calculate_trading_costs(
        Decimal(str(qty * entry)), Decimal(str(qty * exit_price)), config)["total"]


def max_loss(order):
    plan = order.get("plan") or {}
    entry = _number(plan.get("entry")) or _number(order.get("limit_price"))
    stop = _number(plan.get("stop")) or _number(order.get("stop_loss_stop_price"))
    qty = _number(order.get("qty"))
    if entry is None or stop is None or qty is None:
        return None
    return round(abs(entry - stop) * qty, 2)


def plain_ticket(order, config=None):
    config = config or india_common.load_config()
    plan = order.get("plan") or {}
    symbol = str(order.get("symbol", "")).upper().replace(".NS", "")
    qty = order.get("qty")
    entry = plan.get("entry", order.get("limit_price", "market"))
    stop = plan.get("stop", order.get("stop_loss_stop_price"))
    target = plan.get("target", order.get("take_profit_limit_price"))
    charges = _charges(order, config)
    lines = [
        "%s %s shares of %s" % (str(order.get("side", "buy")).upper(), qty, symbol),
        "Entry: %s" % entry,
    ]
    if stop is not None:
        lines.append("Stop: %s" % stop)
    if target is not None:
        lines.append("Target: %s" % target)
    loss = max_loss(order)
    if loss is not None:
        lines.append("Maximum loss at stop: Rs %.2f" % loss)
    lines.append("Estimated round-trip charges: Rs %.2f" % charges)
    if order.get("flat_by"):
        lines.append("Flatten before: %s IST" % order["flat_by"])
    return "\n".join(lines)


def ready_orders(orders, risk, now=None):
    current = india_common.to_ist(now)
    today = current.date().isoformat()
    ready = []
    for index, order in enumerate(orders, 1):
        result = _risk_result(risk, order, today)
        if result and result.get("verdict") == "PASS":
            ready.append((index, order, result))
    return ready


def _load_state(path):
    return _read(path, {"approvals": [], "results": []})


def _approved(state, fp, today):
    return any(item.get("fingerprint") == fp and item.get("date") == today
               and item.get("reply") == YES for item in state.get("approvals", []))


def flatten_order(symbol, qty, price=None, flat_by=None):
    order = {
        "symbol": str(symbol).upper().replace(".NS", ""),
        "side": "sell",
        "qty": int(qty),
        "type": "market" if price is None else "limit",
        "time_in_force": "day",
        "kind": "exit",
        "reduce_only": True,
        "flat_by": flat_by or india_common.load_config().get("flat_by", "15:15"),
        "plan": {"entry": price, "stop": None, "target": None},
        "why": "flatten before the NSE square-off time",
    }
    if price is not None:
        order["limit_price"] = price
    return order


def _parse_now(value):
    if not value:
        return india_common.to_ist()
    try:
        return india_common.to_ist(datetime.datetime.fromisoformat(
            str(value).replace("Z", "+00:00")))
    except ValueError as error:
        raise TicketError("invalid --now timestamp") from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("--orders", default=ORDERS_PATH)
    show.add_argument("--risk", default=RISK_PATH)
    show.add_argument("--now")
    show.add_argument("--json", action="store_true")
    approve = sub.add_parser("approve")
    approve.add_argument("--index", type=int, required=True)
    approve.add_argument("--reply", required=True)
    approve.add_argument("--orders", default=ORDERS_PATH)
    approve.add_argument("--risk", default=RISK_PATH)
    approve.add_argument("--state", default=STATE_PATH)
    approve.add_argument("--now")
    result = sub.add_parser("result")
    result.add_argument("--index", type=int, required=True)
    result.add_argument("--status", choices=("allowed", "denied", "simulated"), required=True)
    result.add_argument("--orders", default=ORDERS_PATH)
    result.add_argument("--risk", default=RISK_PATH)
    result.add_argument("--state", default=STATE_PATH)
    result.add_argument("--now")
    flatten = sub.add_parser("flatten")
    flatten.add_argument("--symbol", required=True)
    flatten.add_argument("--qty", type=int, required=True)
    flatten.add_argument("--price", type=float)
    flatten.add_argument("--flat-by")
    flatten.add_argument("--orders", default=ORDERS_PATH)
    args = parser.parse_args(argv)
    try:
        now = _parse_now(getattr(args, "now", None))
        if args.command == "flatten":
            if args.qty <= 0:
                raise TicketError("qty must be positive")
            existing = _orders(_read(args.orders, []))
            existing.append(flatten_order(args.symbol, args.qty, args.price, args.flat_by))
            _write(args.orders, {"orders": existing})
            print(plain_ticket(existing[-1]))
            print("Run india-risk before requesting approval.")
            return 0
        orders = _orders(_read(args.orders, None))
        if not orders:
            raise TicketError("no orders found at %s" % args.orders)
        risk = _read(args.risk, None)
        if args.command == "show":
            output = []
            for index, order in enumerate(orders, 1):
                verdict = _risk_result(risk, order, now.date().isoformat())
                item = {"index": index, "ticket": plain_ticket(order),
                        "fingerprint": fingerprint(order),
                        "risk": verdict.get("verdict") if verdict else "NOT CHECKED",
                        "ready": bool(verdict and verdict.get("verdict") == "PASS")}
                output.append(item)
            if args.json:
                print(json.dumps(output, indent=2))
            else:
                for item in output:
                    print("ORDER %d - %s" % (item["index"], item["risk"]))
                    print(item["ticket"])
                    print("Exact ticket fingerprint: %s" % item["fingerprint"])
                    if item["ready"]:
                        print('Reply exactly "yes" for this one order.')
                        print("Claude Allow/Deny approval is still required.")
                    print()
            return 0
        if args.index < 1 or args.index > len(orders):
            raise TicketError("invalid order index")
        order = orders[args.index - 1]
        verdict = _risk_result(risk, order, now.date().isoformat())
        if not verdict or verdict.get("verdict") != "PASS":
            raise TicketError("this exact order has not passed india-risk today")
        state = _load_state(args.state)
        fp = fingerprint(order)
        if args.command == "approve":
            if args.reply != YES:
                raise TicketError('approval must be the exact lowercase reply "yes"')
            state.setdefault("approvals", []).append({
                "date": now.date().isoformat(), "at": now.isoformat(),
                "index": args.index, "fingerprint": fp, "reply": args.reply})
            _write(args.state, state)
            print("Recorded exact yes for order %d." % args.index)
            print("The external Claude Allow/Deny approval is still required.")
            return 0
        if not _approved(state, fp, now.date().isoformat()):
            raise TicketError("exact yes is required before recording a result")
        state.setdefault("results", []).append({
            "date": now.date().isoformat(), "at": now.isoformat(),
            "index": args.index, "fingerprint": fp, "status": args.status})
        _write(args.state, state)
        print("Recorded %s after the external Allow/Deny step." % args.status)
        return 0
    except (TicketError, OSError, ValueError) as error:
        print("india-broker: %s" % error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
