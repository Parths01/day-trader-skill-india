import datetime
import json
import os
import tempfile
import unittest

from _load import load

budget = load("india-budget", "size")
risk = load("india-risk", "check")


CONFIG = {
    "capital": 100000, "max_loss_per_trade": 1000, "max_position_pct": 50,
    "max_order_value": 30000, "cash_buffer_pct": 10, "max_trades_per_day": 2,
    "entry_window": ["09:30", "15:00"], "max_daily_loss": 2000,
    "min_reward_risk": 1, "require_stop": True, "paper": True,
    "allow_margin": False, "blocked": [], "circuit_limit_stocks": [],
    "asm_gsm_stocks": [], "allow_short": False, "allow_fno": False,
    "allow_options": False,
}


class BudgetTests(unittest.TestCase):
    def test_four_limits_and_bracket(self):
        sizing = budget.size_plan({"symbol": "RELIANCE", "entry": 100,
                                   "stop": 90, "target": 120}, budget.load_config(
                                       self._config_path()), cash=50000)
        self.assertEqual(sizing["qty"], 100)
        self.assertEqual(sizing["bound_by"], "max loss")
        self.assertEqual(budget.bracket_order(sizing)["qty"], "100")

    def test_refuses_when_one_share_exceeds_risk(self):
        with self.assertRaises(budget.SizeError):
            budget.size_plan({"symbol": "ABC", "entry": 100, "stop": 1, "target": 120},
                             dict(budget.DEFAULTS, capital=10000,
                                  max_loss_per_trade=10, max_order_value=10000))

    def _config_path(self):
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
        json.dump(CONFIG, handle)
        handle.close()
        self.addCleanup(lambda: os.unlink(handle.name))
        return handle.name


class RiskTests(unittest.TestCase):
    def order(self, **overrides):
        order = {"symbol": "RELIANCE", "side": "buy", "qty": "5",
                 "plan": {"entry": 100, "stop": 90, "target": 120}}
        order.update(overrides)
        return order

    def test_passes_and_records_exact_verdict(self):
        result = risk.check([self.order()], CONFIG,
                            datetime.datetime(2026, 11, 9, 10, tzinfo=risk.india_common.IST),
                            holidays=set())
        self.assertEqual(result["passed"], 1)
        self.assertEqual(len(result["results"][0]["fingerprint"]), 16)

    def test_blocks_safety_lists_and_allows_exits(self):
        blocked = dict(CONFIG, blocked=["RELIANCE"], asm_gsm_stocks=["ABC"])
        result = risk.check([self.order(), self.order(symbol="ABC"),
                             self.order(kind="exit", reduce_only=True, side="sell")],
                            blocked, datetime.datetime(2026, 11, 9, 10,
                            tzinfo=risk.india_common.IST), holidays=set())
        self.assertEqual([row["verdict"] for row in result["results"]],
                         ["BLOCK", "BLOCK", "PASS"])

    def test_daily_loss_blocks_entries_but_not_exits(self):
        config = dict(CONFIG, daily_loss_limit=100)
        result = risk.check([self.order(), self.order(kind="exit", reduce_only=True, side="sell")],
                            config, datetime.datetime(2026, 11, 9, 10,
                            tzinfo=risk.india_common.IST), holidays=set(),
                            state={"daily_loss": 60})
        self.assertEqual([row["verdict"] for row in result["results"]], ["BLOCK", "PASS"])


if __name__ == "__main__":
    unittest.main()
