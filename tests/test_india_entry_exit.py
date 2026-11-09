import datetime
import json
import os
import tempfile
import unittest
from decimal import Decimal

from _load import load

entry = load("india-entry", "entry")
exitp = load("india-exit", "exit")


def chart():
    base = datetime.datetime(2026, 11, 9, 9, 15, tzinfo=entry.india_common.IST)
    closes = [100, 101, 100.5, 101, 102, 103]
    highs = [101, 102, 101.5, 102, 103, 105]
    lows = [99, 100, 99.5, 100, 101, 102]
    timestamps = [int((base + datetime.timedelta(minutes=5 * i)).timestamp())
                  for i in range(len(closes))]
    return entry.parse_chart({"chart": {"result": [{"meta": {"regularMarketPrice": 104},
        "timestamp": timestamps, "indicators": {"quote": [{"open": closes,
        "high": highs, "low": lows, "close": closes, "volume": [100] * 6}]}}]}}, "RELIANCE")


class EntryTests(unittest.TestCase):
    def test_waits_then_triggers_and_writes(self):
        result = entry.evaluate(chart(), entry.parse_now("2026-11-09 09:29"))
        self.assertEqual(result["status"], "waiting")
        result = entry.evaluate(chart(), entry.parse_now("2026-11-09 09:50"))
        self.assertEqual(result["status"], "triggered")
        self.assertEqual(result["trigger"]["price"], 103.0)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "entry.json")
            entry.write_entry(result, path)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["side"], "buy")

    def test_volume_and_level(self):
        self.assertEqual(entry.evaluate(chart(), entry.parse_now("2026-11-09 15:01"),
                                        min_volume_x=2)["status"], "expired")
        result = entry.evaluate(chart(), entry.parse_now("2026-11-09 09:50"), level=102)
        self.assertEqual(result["status"], "triggered")


class ExitTests(unittest.TestCase):
    def test_tick_rounded_stops_targets_and_warning(self):
        config = entry.india_common.load_config()
        plan = exitp.compute(103, "or_mid", None, "r", Decimal("1"),
                             103, 99, symbol="RELIANCE", config=config,
                             planned_exit_time="15:30")
        self.assertEqual(plan["entry"], Decimal("103.00"))
        self.assertEqual(plan["stop"], Decimal("101.00"))
        self.assertEqual(plan["target"], Decimal("105.00"))
        self.assertIsNotNone(plan["warning"])

    def test_refuses_unsafe_stop_and_untriggered_entry(self):
        with self.assertRaises(exitp.PlanError):
            exitp.compute(100, "price", Decimal("100"), "r", Decimal("1"),
                          None, None)
        with self.assertRaises(exitp.PlanError):
            exitp.plan_from_entry({"status": "waiting"}, "or-mid", "1R")


if __name__ == "__main__":
    unittest.main()
