#!/usr/bin/env python3
"""Indian pre-trade PASS/BLOCK checks for proposed bracket orders."""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

import india_common

RISK_PATH = os.path.join("trader", "state", "risk.json")
ORDER_FIELDS = ("symbol", "side", "qty", "notional", "type", "time_in_force",
                "limit_price", "stop_price", "order_class",
                "take_profit_limit_price", "stop_loss_stop_price",
                "stop_loss_limit_price")
DEFAULTS = {
    "require_stop": True, "min_reward_risk": 1.0, "max_trades_per_day": 0,
    "entry_window": ["09:15", "15:00"], "blocked": [], "circuit_limit_stocks": [],
    "asm_gsm_stocks": [], "allow_short": False, "allow_fno": False,
    "allow_options": False,
}


class RiskError(Exception):
    pass


def fingerprint(order):
    fields = {key: order[key] for key in ORDER_FIELDS
              if key in order and order[key] is not None}
    blob = json.dumps(fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _time(value):
    try:
        hour, minute = str(value).split(":")[:2]
        return datetime.time(int(hour), int(minute))
    except (ValueError, TypeError):
        raise RiskError("invalid configured time %r" % value)


def _float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _plan(order):
    plan = order.get("plan") or {}
    entry = _float(plan.get("entry"))
    stop = _float(plan.get("stop", order.get("stop_loss_stop_price")))
    target = _float(plan.get("target", order.get("take_profit_limit_price")))
    qty = _float(order.get("qty"))
    return entry, stop, target, qty


def check(orders, config=None, now=None, holidays=None, state=None):
    config = dict(DEFAULTS, **(config or india_common.load_config()))
    current = india_common.to_ist(now)
    today = current.date().isoformat()
    state = state or {}
    placed_today = state.get("trades_today", state.get(today, 0))
    results = []
    for order in orders:
        reasons, warnings = [], []
        symbol = str(order.get("symbol", "")).upper()
        side = str(order.get("side", "")).lower()
        entry, stop, target, qty = _plan(order)
        is_exit = bool(order.get("kind") == "exit" or order.get("reduce_only"))
        if not symbol:
            reasons.append("format: missing symbol")
        if side not in ("buy", "sell"):
            reasons.append("format: side must be buy or sell")
        if side == "sell" and not is_exit and not config.get("allow_short"):
            reasons.append("short: short selling is disabled")
        if not is_exit:
            if symbol in {str(x).upper() for x in config.get("blocked", [])}:
                reasons.append("blocked: ticker is on the blocked list")
            if symbol in {str(x).upper() for x in config.get("circuit_limit_stocks", [])}:
                reasons.append("circuit: ticker is on the circuit-limit list")
            if symbol in {str(x).upper() for x in config.get("asm_gsm_stocks", [])}:
                reasons.append("ASM/GSM: ticker is on the user-maintained surveillance list")
            if symbol.endswith((".NS-F", "-F")) or order.get("asset_class") in ("fno", "future"):
                if not config.get("allow_fno"):
                    reasons.append("asset: F&O is disabled")
            if re.search(r"\d{6}[CP]\d{8}$", symbol) or order.get("asset_class") == "option":
                if not config.get("allow_options"):
                    reasons.append("asset: options are disabled")
            if config.get("require_stop") and stop is None:
                reasons.append("stop: stop is required")
            if entry is not None and stop is not None and stop >= entry:
                reasons.append("stop: stop must be below entry")
            if entry is not None and target is not None and target <= entry:
                reasons.append("target: target must be above entry")
            if entry and stop is not None and target:
                risk = entry - stop
                reward_risk = (target - entry) / risk if risk > 0 else 0
                max_loss = risk * (qty or 0)
                if max_loss > float(config.get("max_loss_per_trade", 0) or 0) > 0:
                    reasons.append("loss: max loss %.2f exceeds configured limit" % max_loss)
                daily_loss = float(state.get("daily_loss", 0) or 0) + max_loss
                daily_limit = float(config.get("daily_loss_limit", 0) or 0)
                if daily_limit > 0 and daily_loss > daily_limit:
                    reasons.append("daily loss: %.2f exceeds configured limit %.2f" %
                                   (daily_loss, daily_limit))
                if reward_risk < float(config.get("min_reward_risk", 0) or 0):
                    reasons.append("reward:risk: %.2f is below minimum %s" %
                                   (reward_risk, config["min_reward_risk"]))
            if config.get("max_trades_per_day", 0) and placed_today >= config["max_trades_per_day"]:
                reasons.append("trades: daily trade limit reached")
            window = config.get("entry_window", DEFAULTS["entry_window"])
            if current.time() < _time(window[0]) or current.time() > _time(window[1]):
                reasons.append("window: entry is outside %s-%s IST" % (window[0], window[1]))
            if not india_common.is_market_open(current, holidays=holidays, config=config):
                reasons.append("market: NSE is closed or this is a holiday")
        results.append({"symbol": symbol, "verdict": "PASS" if not reasons else "BLOCK",
                        "reasons": reasons, "warnings": warnings,
                        "fingerprint": fingerprint(order), "kind": "exit" if is_exit else "entry",
                        "entry": entry, "stop": stop, "target": target, "qty": qty})
        if not is_exit and not reasons:
            placed_today += 1
    return {"date": today, "checked_at": current.isoformat(), "results": results,
            "passed": sum(result["verdict"] == "PASS" for result in results),
            "blocked": sum(result["verdict"] == "BLOCK" for result in results)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orders", default=os.path.join("trader", "orders.json"))
    parser.add_argument("--config", default=india_common.DEFAULT_CONFIG_PATH)
    parser.add_argument("--now")
    parser.add_argument("--out", default=RISK_PATH)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)
    try:
        with open(args.orders, encoding="utf-8") as handle:
            document = json.load(handle)
        orders = document.get("orders", document if isinstance(document, list) else [])
        result = check(orders, india_common.load_config(args.config),
                       _parse_now(args.now))
        if not args.no_write:
            os.makedirs(os.path.dirname(args.out), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2)
        for index, item in enumerate(result["results"], 1):
            print("%s #%d %s" % (item["verdict"], index, item["symbol"]))
        return 0 if result["blocked"] == 0 else 1
    except (OSError, ValueError, RiskError) as error:
        print("risk: %s" % error, file=sys.stderr)
        return 1


def _parse_now(value):
    if not value:
        return india_common.to_ist()
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RiskError("invalid --now") from error
    return india_common.to_ist(parsed)


if __name__ == "__main__":
    sys.exit(main())
