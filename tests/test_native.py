"""Native capture reads a UI test's attachments into the same index the web capture writes, and the lint reads it.

The export below is shaped like `xcresulttool export attachments`: a manifest.json naming each attachment's exported
file and suggested name, beside the files. The hierarchy is app.debugDescription's element subtree.
"""
import json
import os
import shutil
import tempfile
import unittest

from saltflow import lint as L
from saltflow import native as N

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "saltPOS")

TREE = """Attributes: Application, 0x1, pid: 812, label: 'saltPOS'
Element subtree:
 →Application, 0x1, pid: 812, label: 'saltPOS'
    Window (Main), 0x2, {{0.0, 0.0}, {1210.0, 834.0}}
      Other, 0x3, {{0.0, 0.0}, {1210.0, 834.0}}, identifier: 'surface.pay.choose'
        Button, 0x4, {{20.0, 700.0}, {200.0, 60.0}}, identifier: 'move.card', label: 'Card'
        Button, 0x5, {{240.0, 700.0}, {200.0, 60.0}}, identifier: 'move.to-account to-account-offline', label: 'Charge to account'
        Button, 0x6, {{460.0, 700.0}, {200.0, 60.0}}, identifier: 'move.made-up', label: 'Guest\\'s choice'
        Button, 0x7, {{20.0, 600.0}, {60.0, 60.0}}, identifier: 'key.1', label: '1'
        Button, 0x8, {{20.0, 500.0}, {60.0, 60.0}}, identifier: 'move.tap-tile = a tile', label: 'Espresso, €3,20'
Path to element:
 →Application, 0x1, pid: 812, label: 'saltPOS'
Query chain:
 →Find: Target Application 'com.example.saltpos'
"""


class Hierarchy(unittest.TestCase):
    def test_reads_moves_words_and_surfaces(self):
        h = N.parse_hierarchy(TREE)
        self.assertEqual(h["surfaces"], ["pay.choose"])
        self.assertEqual(h["moves"], ["card", "to-account", "to-account-offline", "made-up", "tap-tile"])   # keys are not moves
        self.assertEqual(h["words"]["tap-tile"], "a tile")                                       # fixed words over a data label
        self.assertEqual(h["words"]["to-account-offline"], "Charge to account")
        self.assertEqual(h["words"]["made-up"], "Guest's choice")

    def test_names_survive_xcresulttool_renaming(self):
        flows = {"pay-on-leaving": {"steps": {"bill": {}, "reader": {}}}}
        found = N.attachments([{"testIdentifier": "RoundAndPayTests/testPay()", "attachments": [
            {"exportedFileName": "a.txt", "suggestedHumanReadableName": "saltflow pay-on-leaving_bill hierarchy_0_AB12.txt", "deviceName": "iPad Pro"},
            {"exportedFileName": "b.png", "suggestedHumanReadableName": "saltflow_pay-on-leaving_bill_screen_0_CD34.png"},
            {"exportedFileName": "c.png", "suggestedHumanReadableName": "saltflow pay-on-leaving/bill screen dark_0_EF56.png"},
            {"exportedFileName": "d.png", "suggestedHumanReadableName": "Screenshot_0_X.png"},
            {"exportedFileName": "e.txt", "suggestedHumanReadableName": "saltflow pay-on-leavingreader hierarchy_0_5F2DBBDB-9DCC.txt"},
            {"exportedFileName": "f.png", "suggestedHumanReadableName": "saltflow pay-on-leaving reader screen_0_5F2DBBDB-9DCC.png"}]}], flows)
        self.assertEqual(sorted(found), [("pay-on-leaving", "bill"), ("pay-on-leaving", "reader")])   # the slash dropped, or spaces
        self.assertEqual((found[("pay-on-leaving", "reader")]["hierarchy"], found[("pay-on-leaving", "reader")]["light"]), ("e.txt", "f.png"))
        e = found[("pay-on-leaving", "bill")]
        self.assertEqual((e["hierarchy"], e["light"], e["dark"], e["device"]), ("a.txt", "b.png", "c.png", "iPad Pro"))


class Import(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "saltPOS")
        shutil.copytree(FIXTURE, self.root)
        ex = os.path.join(self.tmp, "export")
        os.makedirs(ex)
        with open(os.path.join(ex, "h.txt"), "w") as f:
            f.write(TREE)
        with open(os.path.join(ex, "s.png"), "wb") as f:
            f.write(b"\x89PNG\r\n")
        with open(os.path.join(ex, "manifest.json"), "w") as f:
            json.dump([{"testIdentifier": "RoundAndPayTests/testPay()", "attachments": [
                {"exportedFileName": "h.txt", "suggestedHumanReadableName": "saltflow pay-on-leaving/bill hierarchy_0_A.txt"},
                {"exportedFileName": "s.png", "suggestedHumanReadableName": "saltflow pay-on-leaving/bill screen_0_B.png"},
                {"exportedFileName": "h.txt", "suggestedHumanReadableName": "saltflow pay-on-leaving/nowhere hierarchy_0_C.txt"}]}], f)
        self.res = N.capture(self.root, ex, log=lambda t: None)
        self.ix = self.res["index"]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_writes_the_web_index_shape(self):
        e = self.ix["steps"]["pay-on-leaving/bill"]
        self.assertTrue(e["agrees"])
        self.assertEqual(e["client"], "native")
        self.assertEqual(e["files"], {"light": "pay-on-leaving/bill.native.png"})
        self.assertTrue(os.path.exists(os.path.join(self.root, "flows", "captures", e["files"]["light"])))
        self.assertIn("card", e["moves_in_code"])

    def test_a_step_in_no_flow_is_an_error(self):
        self.assertEqual([x["error"] for x in self.ix["errors"]], ["attached step pay-on-leaving/nowhere is in no flow"])

    def test_lint_reads_native_steps(self):
        found = [f for f in L.lint(self.root) if f["at"] == "bill" and f["kind"] in ("code-differs", "trigger-words")]
        texts = " | ".join(f["text"] for f in found)
        self.assertIn("offers made-up", texts)                  # a control no flow has
        self.assertNotIn("move card,", texts)                   # the Card control is there


if __name__ == "__main__":
    unittest.main()


class SideBySide(unittest.TestCase):
    """Web and native captures of one step live in their own index and both reach the page and the lint."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fd = os.path.join(self.tmp, "flows")
        os.makedirs(os.path.join(self.fd, "captures"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, name, steps):
        with open(os.path.join(self.fd, "captures", name), "w") as f:
            json.dump({"schema": "saltflow/v1/captures", "steps": steps}, f)

    def test_both_kept_native_shown_first(self):
        from saltflow import model
        self.write("index.json", {"f/a": {"files": {"light": "f/a.png"}}, "f/b": {"files": {"light": "f/b.png"}},
                                  "f/c": {"client": "native", "files": {"light": "f/c.native.png"}}})
        self.write("native.json", {"f/a": {"client": "native", "files": {"light": "f/a.native.png"}}})
        steps = model.load_captures(self.fd)["steps"]
        self.assertEqual(steps["f/a"]["client"], "native")
        self.assertEqual([x["client"] for x in steps["f/a"]["alt"]], ["web"])
        self.assertEqual(steps["f/b"]["client"], "web")
        self.assertEqual(steps["f/c"]["client"], "native")            # an older import's row in the web index
        self.assertEqual(model.load_captures(self.fd, prefer="web")["steps"]["f/a"]["client"], "web")
