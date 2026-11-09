import json
import os
import tempfile
import unittest

from _load import load


news = load("india-news", "news")
facts = load("india-analyst", "facts")


class NewsTests(unittest.TestCase):
    def test_tags_and_new_items(self):
        item = news._normalise(
            {"id": "1", "headline": "Board meeting approves dividend and results",
             "published": "2026-11-09T10:00:00+05:30"},
            "RELIANCE", "nse")
        self.assertEqual(item["symbol"], "RELIANCE")
        self.assertIn("board meeting", item["tags"])
        self.assertIn("dividend", item["tags"])
        self.assertEqual(len(news.new_items([item], set())), 1)
        self.assertEqual(news.new_items([item], {item["id"]}), [])

    def test_collects_and_reports_source_failure(self):
        def fake(source, symbol):
            if source == "nse":
                raise news.NewsError("blocked")
            return [{"title": "New order", "id": "x"}]
        original = {"yahoo": news.yahoo_news, "nse": news.nse_announcements}
        news.yahoo_news = lambda symbol, offline=None, opener=None: fake("yahoo", symbol)
        news.nse_announcements = lambda symbol, offline=None, opener=None: fake("nse", symbol)
        try:
            items, errors = news.collect(["TCS"], ("yahoo", "nse"))
        finally:
            news.yahoo_news = original["yahoo"]
            news.nse_announcements = original["nse"]
        self.assertEqual(len(items), 1)
        self.assertEqual(len(errors), 1)

    def test_plan_style_new_state_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            news.save_seen({"a", "b"}, path)
            self.assertEqual(news.load_seen(path), {"a", "b"})


class FactsTests(unittest.TestCase):
    def test_quarterly_yoy_and_ttm(self):
        data = {"quarters": [
            {"period_end": "2026-09-30", "revenue": 130,
             "operating_income": 26, "net_income": 13, "eps": 1.3},
            {"period_end": "2026-06-30", "revenue": 120,
             "operating_income": 24, "net_income": 12, "eps": 1.2},
            {"period_end": "2026-03-31", "revenue": 110,
             "operating_income": 22, "net_income": 11, "eps": 1.1},
            {"period_end": "2025-12-31", "revenue": 100,
             "operating_income": 20, "net_income": 10, "eps": 1.0},
            {"period_end": "2025-09-30", "revenue": 100,
             "operating_income": 20, "net_income": 10, "eps": 1.0},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "facts.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            result = facts.facts("RELIANCE", offline=path)
        self.assertEqual(result["ttm"]["revenue"], 460)
        self.assertEqual(result["ttm"]["operating_margin"], 20)
        self.assertEqual(result["quarters"][0]["revenue_yoy_percent"], 30)

    def test_missing_source_is_explicit(self):
        with self.assertRaises(facts.FactsError):
            facts.facts("TCS", source="nse", offline={"quarters": []})


if __name__ == "__main__":
    unittest.main()
