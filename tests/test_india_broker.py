import datetime
import json
import os
import tempfile
import unittest

from _load import load


broker = load("india-broker", "ticket")


class BrokerTests(unittest.TestCase):
    def setUp(self):
        self.order = {
            "symbol": "RELIANCE", "side": "buy", "qty": 10,
            "type": "market", "time_in_force": "day",
            "plan": {"entry": 100, "stop": 95, "target": 110},
        }
        self.today = datetime.datetime(2026, 11, 9, 10, 0,
                                       tzinfo=broker.india_common.IST)
        self.risk = {"date": "2026-11-09", "results": [{
            "fingerprint": broker.fingerprint(self.order), "verdict": "PASS"}]}

    def test_plain_ticket_contains_risk_and_charges(self):
        text = broker.plain_ticket(self.order)
        self.assertIn("RELIANCE", text)
        self.assertIn("Maximum loss at stop: Rs 50.00", text)
        self.assertIn("Estimated round-trip charges", text)

    def test_only_exact_pass_is_ready(self):
        self.assertEqual(len(broker.ready_orders([self.order], self.risk,
                                                 self.today)), 1)
        blocked = dict(self.risk)
        blocked["results"] = [dict(blocked["results"][0], verdict="BLOCK")]
        self.assertEqual(broker.ready_orders([self.order], blocked, self.today), [])

    def test_exact_yes_and_result_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            orders = os.path.join(directory, "orders.json")
            risk = os.path.join(directory, "risk.json")
            state = os.path.join(directory, "state.json")
            with open(orders, "w", encoding="utf-8") as handle:
                json.dump({"orders": [self.order]}, handle)
            with open(risk, "w", encoding="utf-8") as handle:
                json.dump(self.risk, handle)
            self.assertEqual(broker.main(["approve", "--index", "1",
                "--reply", "yes", "--orders", orders, "--risk", risk,
                "--state", state, "--now", "2026-11-09T10:00:00+05:30"]), 0)
            self.assertEqual(broker.main(["result", "--index", "1",
                "--status", "simulated", "--orders", orders, "--risk", risk,
                "--state", state, "--now", "2026-11-09T10:00:00+05:30"]), 0)
            self.assertEqual(broker.main(["approve", "--index", "1", "--reply", "sure",
                                          "--orders", orders, "--risk", risk,
                                          "--state", state]), 2)

    def test_flatten_is_reduce_only_exit(self):
        order = broker.flatten_order("TCS.NS", 7, flat_by="15:15")
        self.assertEqual(order["side"], "sell")
        self.assertTrue(order["reduce_only"])
        self.assertEqual(order["kind"], "exit")
        self.assertEqual(order["flat_by"], "15:15")


if __name__ == "__main__":
    unittest.main()
