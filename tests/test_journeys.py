"""Several journeys on one product: the single-journey form reads as the first."""
import unittest

from saltflow import model


class Journeys(unittest.TestCase):
    def test_single_form_reads_as_first(self):
        js = model.journeys_of({"journey": [{"id": "buy", "name": "Buy"}],
                                "journeys": [{"id": "operation", "name": "The parcel on its way", "stages": [{"id": "load", "name": "Load"}]}]})
        self.assertEqual([j["id"] for j in js], ["journey", "operation"])
        self.assertEqual(js[1]["stages"][0]["id"], "load")

    def test_none(self):
        self.assertEqual(model.journeys_of({}), [])


if __name__ == "__main__":
    unittest.main()


class StatusAndVerdict(unittest.TestCase):
    def test_step_status_reads_both_forms(self):
        self.assertEqual(model.step_status({"built": True}), "made")
        self.assertEqual(model.step_status({"built": False}), "designed")
        self.assertEqual(model.step_status({"built": "ruled-out"}), "ruled-out")
        self.assertEqual(model.step_status({"status": "making", "built": False}), "making")
        self.assertFalse(model.is_made({"status": "ruled-out"}))

    def test_run_verdict(self):
        self.assertEqual(model.run_verdict({"expect": "done", "outcome": "done", "agrees": True}), "ok")
        self.assertEqual(model.run_verdict({"expect": "done", "outcome": "not-built", "design": "done", "agrees": False}), "work")
        self.assertEqual(model.run_verdict({"expect": "done", "outcome": "stuck", "design": "stuck", "agrees": False}), "break")

    def test_drivable(self):
        self.assertFalse(model.drivable({"account": "demo"}))
        self.assertTrue(model.drivable({"css": ".item", "do": "click"}))
