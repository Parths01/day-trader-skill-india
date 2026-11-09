import datetime
import unittest

from _load import load

tm = load("india-timemachine", "timemachine")


def sessions(count=20):
    result = []
    for day_index in range(count):
        day = "2026-01-%02d" % (day_index + 1)
        rows = []
        price = 100 + day_index
        for slot in range(tm.SESSION_BARS):
            close = price + slot * 0.1
            rows.append({"date": day, "slot": slot, "start": "09:15",
                         "o": close, "h": close + 0.2, "l": close - 0.2,
                         "c": close, "v": 1000})
        result.append((day, rows))
    return result


class TimeMachineTests(unittest.TestCase):
    def test_simulation_is_repeatable_and_net_costs_are_present(self):
        pool = tm.build_pool(sessions())
        first = tm.simulate(pool, 105, 100, 110, 3, 20, replays=200, seed=5,
                            config=tm.india_common.load_config())
        second = tm.simulate(pool, 105, 100, 110, 3, 20, replays=200, seed=5,
                             config=tm.india_common.load_config())
        self.assertEqual(first, second)
        self.assertIn("avg_net_rupees", first)
        self.assertIn("costs", first["cost_model"])

    def test_circuit_limit_caps_moves_and_history_replays(self):
        pool = tm.build_pool(sessions())
        result = tm.simulate(pool, 100, 90, 120, 3, 20, replays=20, seed=1,
                             circuit_limit=1, config=tm.india_common.load_config())
        self.assertTrue(all(close <= 101 for close in [result["median_close"]]))
        history = tm.history_replay(sessions(), {"or_minutes": 15, "stop_rule": "or_mid",
                                                  "target_r": 1})
        self.assertIn("trades", history)

    def test_verdict_names_simulation_and_net_value(self):
        mc = {"target_first": 60, "stop_first": 40, "target_r": 1,
              "avg_net_rupees": 12.5, "avg_R": 0.125}
        text = tm.verdict(mc)
        self.assertIn("12.50 rupees", text)
        self.assertIn("simulation", text)


if __name__ == "__main__":
    unittest.main()
