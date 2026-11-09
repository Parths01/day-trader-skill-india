import datetime
import json
import os
import tempfile
import unittest

from _load import ROOT

import india_common


class IndiaCommonTests(unittest.TestCase):
    def test_timezone_and_symbol(self):
        utc = datetime.datetime(2026, 1, 1, 3, 45, tzinfo=datetime.timezone.utc)
        self.assertEqual(india_common.to_ist(utc).hour, 9)
        self.assertEqual(india_common.to_ist(utc).minute, 15)
        self.assertEqual(india_common.yahoo_symbol("reliance"), "RELIANCE.NS")

    def test_market_hours_and_weekend(self):
        holidays = set()
        self.assertFalse(india_common.is_market_open(
            datetime.datetime(2026, 1, 5, 9, 10), holidays=holidays
        ))
        self.assertTrue(india_common.is_market_open(
            datetime.datetime(2026, 1, 5, 9, 10),
            holidays=holidays, include_pre_open=True
        ))
        self.assertFalse(india_common.is_market_open(
            datetime.datetime(2026, 1, 5, 15, 30), holidays=holidays
        ))
        self.assertFalse(india_common.is_market_open(
            datetime.datetime(2026, 1, 4, 10), holidays=holidays
        ))

    def test_next_open_skips_holiday(self):
        result = india_common.next_open(
            datetime.datetime(2026, 1, 2, 16), holidays={datetime.date(2026, 1, 5)}
        )
        self.assertEqual(result.date(), datetime.date(2026, 1, 6))
        self.assertEqual(result.time(), datetime.time(9, 15))

    def test_config_tick_and_costs(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"tick_sizes": {"RELIANCE": 0.10},
                           "trading_costs": {
                               "brokerage": {"percent": 0.001, "max_per_order": 20},
                               "stt": {"sell_percent": 0.001},
                               "exchange_charges": {"percent": 0.001},
                               "sebi_fees": {"per_crore": 10},
                               "stamp_duty": {"buy_percent": 0.0001},
                               "gst": {"percent": 0.18}}}, handle)
            config = india_common.load_config(path)
        self.assertEqual(india_common.round_to_tick("100.05", "RELIANCE", config),
                         india_common.Decimal("100.1"))
        costs = india_common.calculate_trading_costs(10000, 11000, config)
        self.assertEqual(costs["brokerage"], 21)
        self.assertEqual(costs["total"], india_common.Decimal("61.58478"))


if __name__ == "__main__":
    unittest.main()
