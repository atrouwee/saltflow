"""The walk finds, with no model and no browser, the two breaks in pay on leaving.

Happy reports done; decline-then-another-card reports not built at "declined";
offline-card-guest-leaves reports stuck at "bill-offline" plus features with no step; offline-account-guest-leaves
reports done. Each break is a note carrying its run.
"""
import json
import os
import shutil
import tempfile
import unittest

from saltflow import walk as W

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "saltPOS")


class PayOnLeaving(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls.tmp, "saltPOS")
        shutil.copytree(FIXTURE, cls.root)
        cls.res = W.walk(cls.root)
        cls.named = {r["id"]: r for r in cls.res["runs"] if "expect" in r}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_happy_is_done(self):
        r = self.named["happy"]
        self.assertEqual((r["outcome"], r["at"]), ("done", "closed"))
        self.assertEqual(r["path"], ["tab", "bill", "reader", "paid", "closed"])
        self.assertTrue(r["agrees"])

    def test_decline_is_not_built(self):
        r = self.named["decline-then-another-card"]
        self.assertEqual((r["outcome"], r["at"]), ("not-built", "declined"))
        self.assertFalse(r["agrees"])

    def test_offline_card_guest_is_stuck_at_the_bill(self):
        r = self.named["offline-card-guest-leaves"]
        self.assertEqual((r["outcome"], r["at"]), ("stuck", "bill-offline"))
        self.assertIn("pay-link", r["missing"])
        self.assertIn("manual-card", r["missing"])

    def test_offline_account_guest_is_done(self):
        r = self.named["offline-account-guest-leaves"]
        self.assertEqual((r["outcome"], r["at"]), ("done", "closed"))

    def test_every_combination_is_walked(self):
        # 3 jobs × 2 × 2 × 2 conditions
        self.assertEqual(len(self.res["runs"]), 24)

    def test_breaks_are_notes_once(self):
        kinds = {(n["flow"], n.get("step"), n.get("run")) for n in self.res["notes"]}
        # the decline run stops at a step not built yet on a path the design completes: work to do, not a break
        self.assertEqual((self.named["decline-then-another-card"]["outcome"], self.named["decline-then-another-card"]["design"]), ("not-built", "done"))
        self.assertNotIn(("pay-on-leaving", "declined", "decline-then-another-card"), kinds)
        self.assertIn(("pay-on-leaving", "bill-offline", "offline-card-guest-leaves"), kinds)
        path = os.path.join(self.root, "flows", "notes.jsonl")
        with open(path) as f:
            first = [json.loads(l) for l in f if l.strip()]
        again = W.walk(self.root)
        self.assertEqual(again["added"], [])
        with open(path) as f:
            second = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(len(first), len(second))

    def test_the_walk_closes_its_own_break_once_it_is_gone(self):
        path = os.path.join(self.root, "flows", "notes.jsonl")
        with open(path, "a") as f:            # a break an older walk filed, which this walk no longer finds
            f.write(json.dumps({"id": "n-old", "kind": "break", "origin": "walk", "status": "open", "text": "old"}) + "\n")
            f.write(json.dumps({"id": "n-mine", "kind": "question", "origin": "a reviewer", "status": "open", "text": "mine"}) + "\n")
        res = W.walk(self.root)
        self.assertEqual(res["closed"], ["n-old"])
        with open(path) as f:
            last = json.loads([l for l in f if l.strip()][-1])
        self.assertEqual((last["id"], last["status"]), ("n-old", "done"))
        self.assertNotIn("commit_done", last)          # closed by the walk, not by a commit: the bar does not count it

    def test_runs_file_is_written(self):
        with open(os.path.join(self.root, "flows", "runs.json")) as f:
            data = json.load(f)
        self.assertEqual(data["schema"], "saltflow/v1/runs")
        self.assertEqual(len(data["runs"]), 24)


if __name__ == "__main__":
    unittest.main()


class RuledOut(unittest.TestCase):
    """A step ruled out of the product is never made: neither the build walk nor the design walk passes it
    (a ruled-out step once still let the design walk reach done)."""
    def test_design_stops_at_ruled_out(self):
        from saltflow import walk as W
        flow = {"id": "f", "entry": "a", "world": {}, "steps": {
            "a": {"built": True}, "b": {"built": "ruled-out"}, "c": {"built": True, "end": "done"}},
            "moves": [{"id": "ab", "from": "a", "to": "b", "kind": "forward"}, {"id": "bc", "from": "b", "to": "c", "kind": "forward"}]}
        job = {"ref": "p:jobs#j", "ends": ["c"]}
        self.assertEqual(W.walk_one(flow, job, {})["outcome"], "not-built")
        self.assertIn("ruled out", W.walk_one(flow, job, {})["why"])
        design = W.walk_one(dict(flow, steps={k: v if v.get("built") == "ruled-out" else dict(v, built=True) for k, v in flow["steps"].items()}), job, {})
        self.assertEqual(design["outcome"], "not-built")
