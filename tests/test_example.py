"""The example product in examples/saltpos stays valid, walks to the breaks its README names, and stays small."""
import json
import os
import shutil
import tempfile
import unittest

from saltflow import coverage as C
from saltflow import model
from saltflow import walk as W

EXAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "saltpos")


@unittest.skipUnless(os.path.isdir(EXAMPLE), "no examples/saltpos in this tree")
class Example(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls.tmp, "saltpos")
        shutil.copytree(EXAMPLE, cls.root)          # the walk writes runs.json and notes; never into the tree

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_valid(self):
        rep = model.validate(self.root)
        self.assertEqual([str(p) for p in rep.errors], [])
        self.assertEqual([str(p) for p in rep.warnings], [])

    def test_the_walk_finds_what_the_readme_says(self):
        runs = {(r["flow"], r["id"]): r for r in W.walk(self.root)["runs"] if "expect" in r}
        stuck = runs[("pay-on-leaving", "offline-card-guest-leaves")]
        self.assertEqual((stuck["outcome"], stuck["at"]), ("stuck", "bill-offline"))
        bar = runs[("send-to-the-bar", "leave-the-tab")]
        self.assertEqual((bar["outcome"], bar["at"], model.run_verdict(bar)), ("not-built", "bar-ticket", "ok"))      # expected: work to do, not a break
        self.assertIn("service-mode", runs[("open-a-tab", "from-the-room")]["missing"])
        self.assertEqual(W.walk(self.root)["added"], [])        # the shipped notes already hold every break

    def test_coverage_names_the_jobs_with_no_flow(self):
        rows = {r["job"]: r["level"] for r in C.coverage(self.root)["rows"]}
        self.assertEqual((rows["split-the-bill"], rows["close-the-day"]), ("error", "warning"))

    def test_every_capture_is_there_and_small(self):
        with open(os.path.join(EXAMPLE, "flows", "captures", "index.json"), encoding="utf-8") as f:
            ix = json.load(f)
        for key, e in ix["steps"].items():
            self.assertTrue(os.path.isfile(os.path.join(EXAMPLE, "flows", "captures", e["files"]["light"])), key)
        size = sum(os.path.getsize(os.path.join(d, n)) for d, _, ns in os.walk(EXAMPLE) for n in ns)
        self.assertLess(size, 4 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
