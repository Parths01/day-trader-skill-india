import datetime
import json
import os
import tempfile
import unittest

from _load import ROOT, load

scan = load("india-scanner", "scan")


class IndianScannerTests(unittest.TestCase):
    def test_eq_universe_and_nifty500_parsers(self):
        text = "SYMBOL,SERIES,NAME OF COMPANY\nAAA,EQ,Alpha\nBBB,BE,Debt\n"
        self.assertEqual(scan.parse_equity_csv(text), [{"symbol": "AAA", "name": "Alpha"}])
        nifty = "Company Name,Symbol\nAlpha,AAA\nBeta,BBB\n"
        self.assertEqual(len(scan.parse_nifty500_csv(nifty)), 2)

    def test_daily_setups_and_orb(self):
        closes = [(datetime.date(2026, 1, index + 1), float(index)) for index in range(1, 23)]
        self.assertIn("breakout_20d", scan.daily_setups(closes))
        base = datetime.datetime(2026, 1, 5, 9, 15, tzinfo=scan.india_common.IST)
        rows = []
        for index, close in enumerate((100, 101, 100, 102, 105)):
            when = base + datetime.timedelta(minutes=index * 5)
            rows.append({"timestamp": when.timestamp(), "close": close,
                         "high": close + 1, "low": close - 1})
        result = scan.orb_breakout(rows, base + datetime.timedelta(minutes=35))
        self.assertEqual(result["close"], 105.0)
        self.assertEqual(result["range_high"], 102.0)

    def test_offline_daily_writes_watchlist_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = {"chart": {"result": [{"meta": {"regularMarketPrice": 100,
                "regularMarketVolume": 1000000}, "timestamp": [1767600000],
                "indicators": {"quote": [{"close": [100]}]}}]}}
            with open(os.path.join(directory, "AAA.json"), "w", encoding="utf-8") as handle:
                json.dump(fixture, handle)
            universe = os.path.join(directory, "universe.json")
            with open(universe, "w", encoding="utf-8") as handle:
                json.dump({"symbols": [{"symbol": "AAA"}, {"symbol": "MISSING"}]}, handle)
            output = os.path.join(directory, "watchlist.json")
            self.assertEqual(scan.main(["daily", "--universe", universe, "--offline", directory,
                                        "--output", output, "--min-price", "0", "--min-volume", "0"]), 1)
            with open(output, encoding="utf-8") as handle:
                self.assertEqual(len(json.load(handle)["failed"]), 1)


if __name__ == "__main__":
    unittest.main()
