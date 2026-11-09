import json
import os
import tempfile
import unittest

from _load import load


disclosures = load("india-disclosures", "disclosures")


class DisclosureTests(unittest.TestCase):
    def test_bulk_row_is_clean_and_delay_is_calendar_days(self):
        rows = disclosures.parse_bulk({
            "as_on_date": "09-Nov-2026",
            "BULK_DEALS_DATA": [{
                "buySell": "BUY", "clientName": "Example Fund",
                "symbol": "RELIANCE", "qty": "1,000", "watp": "2500.50",
                "date": "06-Nov-2026",
            }]
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["side"], "buy")
        self.assertEqual(rows[0]["quantity"], 1000)
        self.assertEqual(rows[0]["price"], 2500.50)
        self.assertEqual(rows[0]["days_to_disclose"], 3)

    def test_insider_and_watchlist(self):
        rows = disclosures.parse_insider({"data": [{
            "personName": "Promoter A", "symbol": "TCS.NS",
            "tdpTransactionType": "SELL", "numberOfSecurities": 50,
            "valuePerSecurity": 3500, "dateOfTransaction": "2026-11-07",
            "dateOfDisclosure": "2026-11-08",
        }]})
        disclosures.mark_watchlist(rows, {"TCS"})
        self.assertEqual(rows[0]["symbol"], "TCS")
        self.assertTrue(rows[0]["watchlist"])
        self.assertEqual(rows[0]["days_to_disclose"], 1)

    def test_flows_preserve_market_values(self):
        rows = disclosures.parse_flows({"data": [{
            "category": "FII", "date": "09-Nov-2026",
            "buyValue": "100", "sellValue": "80", "netValue": "20",
        }]})
        self.assertEqual(rows[0]["kind"], "fii_dii_flow")
        self.assertEqual(rows[0]["net_value"], 20)
        self.assertEqual(rows[0]["symbol"], "")

    def test_seen_state_and_offline_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, value in (
                ("bulk", {"data": [{"symbol": "INFY", "buySell": "SELL",
                                    "qty": 2, "watp": 100}]}),
                ("block", {"data": []}), ("insider", {"data": []}),
                ("flows", {"data": []})):
                with open(os.path.join(directory, name + ".json"), "w",
                          encoding="utf-8") as handle:
                    json.dump(value, handle)
            rows, errors = disclosures.collect(directory, ("bulk", "block",
                                                            "insider", "flows"))
            state = os.path.join(directory, "state.json")
            disclosures.save_seen({rows[0]["id"]}, state)
            self.assertEqual(len(rows), 1)
            self.assertEqual(errors, [])
            self.assertEqual(disclosures.new_rows(rows, disclosures.load_seen(state)), [])


if __name__ == "__main__":
    unittest.main()
