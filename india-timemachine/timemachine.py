#!/usr/bin/env python3
"""Monte Carlo replay of an Indian NSE intraday plan.

This is a simulation built from the stock's own historical candles, not a
prediction and not financial advice.
"""

import argparse
import datetime
import gzip
import json
import os
import random
import statistics
import sys
import urllib.parse
import urllib.request
from decimal import Decimal

import india_common

INTERVAL = 300
SESSION_OPEN = datetime.time(9, 15)
SESSION_CLOSE = datetime.time(15, 30)
SESSION_BARS = 75
MIN_SESSIONS = 20
DEFAULT_REPLAYS = 10000
DEFAULT_SEED = 19
DEFAULT_WINDOW = 2
PLAN_PATH = os.path.join("trader", "plan.json")
OUTPUT_PATH = os.path.join("trader", "timemachine.json")
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s"


class TMError(Exception):
    pass


def parse_now(value=None):
    if not value:
        return india_common.to_ist()
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.datetime.fromisoformat(text)
    except ValueError as error:
        raise TMError('--now wants an IST time like "2026-11-09 10:15"') from error
    return india_common.to_ist(dt)


def _chart_result(document):
    if "chart" in document:
        result = document["chart"].get("result") or []
        if not result:
            raise TMError("Yahoo response contains no chart")
        return result[0]
    return document


def parse_bars(document, now=None):
    """Return completed, on-grid, regular-session IST bars oldest first."""
    now = india_common.to_ist(now)
    result = _chart_result(document if isinstance(document, dict) else json.loads(document))
    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    bars = []
    for index, timestamp in enumerate(timestamps):
        if timestamp is None:
            continue
        local = datetime.datetime.fromtimestamp(
            int(timestamp), datetime.timezone.utc).astimezone(india_common.IST)
        values = {}
        for key in ("open", "high", "low", "close", "volume"):
            column = quote.get(key) or []
            values[key] = column[index] if index < len(column) else None
        if any(values[key] is None for key in ("open", "high", "low", "close")):
            continue
        if local.second or local.minute % 5:
            continue
        if local.time() < SESSION_OPEN or local.time() >= SESSION_CLOSE:
            continue
        if local + datetime.timedelta(seconds=INTERVAL) > now:
            continue
        bars.append({"date": local.date().isoformat(), "slot": (
            (local.hour * 60 + local.minute) - 9 * 60 - 15) // 5,
            "start": local.strftime("%H:%M"), "o": float(values["open"]),
            "h": float(values["high"]), "l": float(values["low"]),
            "c": float(values["close"]), "v": float(values["volume"] or 0),
            "timestamp": int(timestamp)})
    return result.get("meta") or {}, bars


def split_sessions(bars):
    sessions = {}
    for bar in bars:
        sessions.setdefault(bar["date"], {})[bar["slot"]] = bar
    return sessions


def full_sessions(sessions, before):
    complete, skipped = [], []
    for day in sorted(sessions):
        if day >= before:
            continue
        rows = sessions[day]
        if all(slot in rows for slot in range(SESSION_BARS)):
            complete.append((day, [rows[slot] for slot in range(SESSION_BARS)]))
        else:
            skipped.append({"date": day, "bars": len(rows)})
    return complete, skipped


def build_pool(sessions):
    """Pool same-time candle ratios, indexed by session slot."""
    pool = [[] for _ in range(SESSION_BARS)]
    for _, rows in sessions:
        for index in range(1, SESSION_BARS):
            previous = rows[index - 1]["c"]
            pool[index].append(tuple(rows[index][key] / previous
                                     for key in ("o", "h", "l", "c")))
    return pool


def _costs(buy, sell, config):
    values = india_common.calculate_trading_costs(buy, sell, config)
    return float(values["total"])


def _bands(entry, circuit_limit=None):
    if circuit_limit is None:
        return None
    if isinstance(circuit_limit, dict):
        lower = float(circuit_limit.get("lower_pct", circuit_limit.get("pct", 0)))
        upper = float(circuit_limit.get("upper_pct", circuit_limit.get("pct", 0)))
    else:
        lower = upper = float(circuit_limit)
    return entry * (1 - lower / 100), entry * (1 + upper / 100)


def simulate(pool, entry, stop, target, entry_slot, last_slot,
             replays=DEFAULT_REPLAYS, seed=DEFAULT_SEED, window=DEFAULT_WINDOW,
             config=None, circuit_limit=None):
    """Replay the remaining bars and return gross and net outcome statistics."""
    config = config or india_common.load_config()
    entry, stop, target = float(entry), float(stop), float(target)
    risk = entry - stop
    if risk <= 0:
        raise TMError("simulation requires a long entry above its stop")
    band = _bands(entry, circuit_limit)
    rng = random.Random(seed)
    outcomes, closes, net_rs, net_rupees = [], [], [], []
    sample_paths = []
    for replay in range(replays):
        price = entry
        outcome = "neither"
        exit_price = None
        path = [round(price, 2)]
        for slot in range(entry_slot + 1, last_slot + 1):
            if not pool[slot]:
                continue
            selected = min(SESSION_BARS - 1, max(1, slot + rng.randint(-window, window)))
            ratio = rng.choice(pool[selected])
            high, low, close = price * ratio[1], price * ratio[2], price * ratio[3]
            if band:
                low = max(low, band[0])
                high = min(high, band[1])
                close = min(max(close, band[0]), band[1])
            if low <= stop:
                outcome, exit_price = "stop", stop
                price = close
                path.append(round(price, 2))
                break
            if high >= target:
                outcome, exit_price = "target", target
                price = close
                path.append(round(price, 2))
                break
            price = close
            path.append(round(price, 2))
        if exit_price is None:
            exit_price = price
        gross = exit_price - entry
        net = gross - _costs(entry, exit_price, config)
        net_r = net / risk
        outcomes.append(outcome)
        closes.append(exit_price)
        net_rs.append(net_r)
        net_rupees.append(net)
        if replay < 160:
            sample_paths.append(path)
    counts = {name: outcomes.count(name) for name in ("target", "stop", "neither")}
    return {
        "replays": replays, "seed": seed, "window": window,
        "bars_left": max(0, last_slot - entry_slot),
        "target_first": counts["target"], "stop_first": counts["stop"],
        "neither": counts["neither"],
        "p_target": round(counts["target"] / replays, 4),
        "p_stop": round(counts["stop"] / replays, 4),
        "p_neither": round(counts["neither"] / replays, 4),
        "median_close": round(sorted(closes)[len(closes) // 2], 2),
        "avg_R": round(statistics.mean(net_rs), 4),
        "avg_net_rupees": round(statistics.mean(net_rupees), 2),
        "net_rs": net_rs,
        "sample_paths": sample_paths,
        "circuit_limit": circuit_limit,
        "cost_model": "round-trip intraday equity costs from india_common",
    }


def opening_range(rows, bars=3):
    selected = rows[:bars]
    if len(selected) < bars:
        raise TMError("opening range is incomplete")
    return max(row["h"] for row in selected), min(row["l"] for row in selected)


def _outcome(rows, entry_slot, entry, stop, target, config):
    for row in rows[entry_slot + 1:]:
        if row["l"] <= stop:
            exit_price, outcome = stop, "stop"
            break
        if row["h"] >= target:
            exit_price, outcome = target, "target"
            break
    else:
        exit_price, outcome = rows[-1]["c"], "neither"
    net = exit_price - entry - _costs(entry, exit_price, config)
    return outcome, round(net / (entry - stop), 4), round(net, 2)


def history_replay(sessions, rule, config=None):
    config = config or india_common.load_config()
    trades = []
    for day, rows in sessions:
        try:
            high, low = opening_range(rows, rule.get("or_minutes", 15) // 5)
        except TMError:
            continue
        entry_index = next((i for i in range(3, len(rows))
                            if rows[i]["c"] > high), None)
        if entry_index is None:
            continue
        entry = rows[entry_index]["c"]
        stop = (high + low) / 2 if rule.get("stop_rule", "or_mid") == "or_mid" else low
        target = entry + (entry - stop) * float(rule.get("target_r", 1))
        outcome, net_r, net_rupees = _outcome(rows, entry_index, entry, stop, target, config)
        trades.append({"date": day, "entry": round(entry, 2), "stop": round(stop, 2),
                       "target": round(target, 2), "outcome": outcome, "R": net_r,
                       "net_rupees": net_rupees})
    counts = {name: sum(trade["outcome"] == name for trade in trades)
              for name in ("target", "stop", "neither")}
    return {"sessions": len(sessions), "triggered": len(trades), **counts,
            "avg_R": round(statistics.mean([t["R"] for t in trades]), 4) if trades else 0,
            "avg_net_rupees": round(statistics.mean([t["net_rupees"] for t in trades]), 2) if trades else 0,
            "trades": trades}


def normalize_plan(raw):
    if raw.get("status") and raw.get("status") != "triggered":
        raise TMError("plan must come from a triggered entry")
    entry = raw.get("entry", raw.get("trigger", {}).get("price"))
    stop = raw.get("stop")
    target = raw.get("target")
    if entry is None or stop is None or target is None:
        raise TMError("plan needs entry, stop, and target")
    date = raw.get("date")
    if not date:
        date = raw.get("checked_at", "")[:10]
    return {"symbol": raw.get("symbol", ""), "date": date, "entry": float(entry),
            "stop": float(stop), "target": float(target),
            "entry_time": raw.get("entry_time", raw.get("trigger", {}).get("time", "")),
            "entry_bar": int(raw.get("entry_bar", raw.get("trigger", {}).get("bar_index", 3))),
            "flat_by": raw.get("flat_by", "15:15"),
            "opening_range": raw.get("opening_range", {}),
            "target_r": float(raw.get("target_r", (float(target) - float(entry)) /
                               (float(entry) - float(stop))))}


def lean(mc):
    decided = mc["target_first"] + mc["stop_first"]
    share = mc["target_first"] / decided if decided else 0
    even = 1 / (1 + mc["target_r"]) if mc.get("target_r") else 0.5
    return share - even, share, even


def verdict(mc):
    gap, _, _ = lean(mc)
    direction = "target" if gap > 0 else "stop"
    strength = "Close to a coin flip" if abs(gap) < 0.05 else (
        "Leans toward the %s" % direction if abs(gap) < 0.15 else
        "Strongly toward the %s" % direction)
    return "%s: net expected value %+.2f rupees (%+.3f R), based on simulation." % (
        strength, mc["avg_net_rupees"], mc["avg_R"])


def report(document):
    mc = document["mc"]
    history = document["history"]
    plan = document["plan"]
    return [
        "%s buy, %s: entry %.2f, stop %.2f, target %.2f" %
        (plan["symbol"], plan["date"], plan["entry"], plan["stop"], plan["target"]),
        "%s replays, seed %s, %s historical sessions" %
        (format(mc["replays"], ","), mc["seed"], history["sessions"]),
        "target first   %.1f %%   stop first %.1f %%   neither %.1f %%" %
        (mc["p_target"] * 100, mc["p_stop"] * 100, mc["p_neither"] * 100),
        "Average net EV: %+.2f rupees (%+.3f R); trading costs included." %
        (mc["avg_net_rupees"], mc["avg_R"]),
        verdict(mc),
        "This is a simulation, not a prediction. Historical candle moves cannot model news, gaps, halts, or future liquidity.",
    ]


def time_machine(document, plan, now=None, replays=DEFAULT_REPLAYS,
                 seed=DEFAULT_SEED, window=DEFAULT_WINDOW, config=None,
                 circuit_limit=None):
    config = config or india_common.load_config()
    now = india_common.to_ist(now)
    result = _chart_result(document if isinstance(document, dict) else json.loads(document))
    _, bars = parse_bars(result, now)
    sessions = split_sessions(bars)
    complete, skipped = full_sessions(sessions, plan["date"])
    current = sessions.get(plan["date"], {})
    if len(current) < SESSION_BARS:
        current_rows = [current[slot] for slot in sorted(current)]
    else:
        current_rows = [current[slot] for slot in range(SESSION_BARS)]
    entry_slot = int(plan.get("entry_bar", 3))
    last_slot = max(entry_slot, min(SESSION_BARS - 1,
                                    int((now.hour * 60 + now.minute - 9 * 60 - 15) // 5)))
    pool = build_pool(complete)
    if len(complete) < MIN_SESSIONS:
        raise TMError("need at least %d complete sessions; found %d" % (MIN_SESSIONS, len(complete)))
    mc = simulate(pool, plan["entry"], plan["stop"], plan["target"], entry_slot,
                  last_slot, replays, seed, window, config, circuit_limit)
    mc["target_r"] = plan["target_r"]
    rule = {"or_minutes": plan.get("opening_range", {}).get("minutes", 15),
            "stop_rule": "or_mid", "target_r": plan["target_r"]}
    history = history_replay(complete, rule, config)
    return {"plan": plan, "mc": mc, "history": history, "skipped": skipped,
            "verdict": verdict(mc), "warnings": [
                "Simulation only; not a prediction.",
                "NSE circuit limits were applied." if circuit_limit else
                "No circuit limit supplied; simulated prices were not band-capped.",
            ]}


def _load_document(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--plan", default=PLAN_PATH)
    run.add_argument("--offline")
    run.add_argument("--now")
    run.add_argument("--replays", type=int, default=DEFAULT_REPLAYS)
    run.add_argument("--seed", type=int, default=DEFAULT_SEED)
    run.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    run.add_argument("--circuit-limit", type=float)
    run.add_argument("--write", action="store_true")
    run.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command != "run":
            return 1
        plan = normalize_plan(_load_document(args.plan))
        if args.offline:
            document = _load_document(args.offline)
        else:
            query = urllib.parse.urlencode({"range": "60d", "interval": "5m"})
            url = YAHOO_URL % urllib.parse.quote(india_common.yahoo_symbol(plan["symbol"]), safe="") + "?" + query
            request = urllib.request.Request(url, headers={"User-Agent": "day-trader-skill-india/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                document = json.loads(response.read().decode("utf-8"))
        result = time_machine(document, plan, parse_now(args.now), args.replays, args.seed,
                              args.window, circuit_limit=args.circuit_limit)
        if args.write:
            os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
            with open(OUTPUT_PATH, "w", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2)
        print(json.dumps(result, indent=2) if args.json else "\n".join(report(result)))
        return 0
    except (TMError, OSError, ValueError, KeyError) as error:
        print("timemachine: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
