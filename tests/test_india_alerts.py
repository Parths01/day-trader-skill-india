import datetime
import json
import os
import tempfile
import unittest

from _load import load


alerts = load("india-alerts", "alerts")
NOW = datetime.datetime(2026, 11, 9, 15, 15, tzinfo=alerts.india_common.IST)


def chart(price=101, previous=100):
    return {
        "chart": {"result": [{
            "timestamp": [1794000600, 1794004200],
            "meta": {"regularMarketPrice": price, "previousClose": previous},
            "indicators": {"quote": [{"close": [previous, price]}]},
        }], "error": None}
    }


class IndiaAlerts(unittest.TestCase):
    def test_parse_yahoo_and_percent(self):
        result = alerts.parse_yahoo(chart(102, 100), "reliance")
        self.assertEqual(result["symbol"], "RELIANCE")
        self.assertEqual(result["yahoo_symbol"], "RELIANCE.NS")
        self.assertEqual(result["percent_change"], 2)

    def test_price_and_time_rules_ring_once(self):
        rules = [
            {"id": "above", "symbol": "RELIANCE", "type": "above", "price": 100},
            {"id": "flat", "type": "flat_by", "at": "15:15"},
        ]
        result = alerts.check(
            rules, NOW, fetcher=lambda symbol, offline=None: alerts.parse_yahoo(
                chart(101, 100), symbol), holidays=set())
        self.assertEqual([item["id"] for item in result["rang"]], ["above", "flat"])
        self.assertTrue(all(rule["fired"] for rule in rules))
        again = alerts.check(
            rules, NOW, fetcher=lambda symbol, offline=None: alerts.parse_yahoo(
                chart(101, 100), symbol), holidays=set())
        self.assertEqual(again["rang"], [])

    def test_open_and_percent_down(self):
        now = datetime.datetime(2026, 11, 9, 9, 15, tzinfo=alerts.india_common.IST)
        rules = [
            {"id": "open", "type": "opening_bell"},
            {"id": "down", "symbol": "TCS", "type": "pct_move",
             "pct": 3, "direction": "down"},
        ]
        result = alerts.check(
            rules, now, fetcher=lambda symbol, offline=None: alerts.parse_yahoo(
                chart(97, 100), symbol), holidays=set())
        self.assertEqual({item["id"] for item in result["rang"]}, {"open", "down"})

    def test_plan_rules(self):
        rules = alerts.rules_from_plan({
            "symbol": "RELIANCE.NS", "date": "2026-11-09",
            "stop": 99.95, "target": 105, "flat_by": "15:15",
        })
        self.assertEqual([rule["type"] for rule in rules],
                         ["stop", "target", "flat_by"])
        self.assertEqual(rules[0]["symbol"], "RELIANCE")

    def test_offline_quote_and_prices_file(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = os.path.join(directory, "RELIANCE.json")
            with open(fixture, "w", encoding="utf-8") as handle:
                json.dump(chart(101, 100), handle)
            output = os.path.join(directory, "prices.json")
            result = alerts.fetch_quote("RELIANCE", offline=fixture)
            alerts.write_prices({result["symbol"]: result}, output)
            with open(output, encoding="utf-8") as handle:
                saved = json.load(handle)
        self.assertEqual(saved["quotes"]["RELIANCE"]["price"], 101)

    def test_failed_quote_does_not_ring(self):
        rules = [{"id": "bad", "symbol": "MISSING", "type": "above", "price": 1}]
        result = alerts.check(
            rules, NOW, fetcher=lambda symbol, offline=None:
            (_ for _ in ()).throw(alerts.AlertError("offline missing")),
            holidays=set())
        self.assertEqual(result["rang"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertNotIn("fired", rules[0])


if __name__ == "__main__":
    unittest.main()
