"""The validator passes the pay-on-leaving example and fails hand-broken copies, naming the field each time.

A dangling ref, a move to an unknown step and a bad place each fail with a
message that names the field. Run with `python3 -m unittest` from the repo root, or pytest.
"""
import json
import os
import shutil
import tempfile
import unittest

from saltflow import model

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "saltPOS")


class Broken(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(tempfile.mkdtemp(), "saltPOS")
        shutil.copytree(FIXTURE, self.root)
        self.flow_path = os.path.join(self.root, "flows", "pay-on-leaving.json")
        with open(self.flow_path) as f:
            self.flow = json.load(f)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.root))

    def errors_after(self, change):
        change(self.flow)
        with open(self.flow_path, "w") as f:
            json.dump(self.flow, f)
        return [str(p) for p in model.validate(self.root).errors]

    def one_error(self, change, *expect):
        errs = self.errors_after(change)
        self.assertEqual(len(errs), 1, errs)
        for e in expect:
            self.assertIn(e, errs[0])
        return errs[0]

    def test_the_example_is_valid(self):
        rep = model.validate(self.root)
        self.assertEqual([str(p) for p in rep.errors], [])
        self.assertIn("flows/pay-on-leaving.json", rep.checked)

    def test_dangling_ref(self):
        def f(flow):
            flow["steps"]["declined"]["patterns"] = ["saltPOS:grid#F10/decline-paths"]
        self.one_error(f, "steps.declined.patterns[0]", "'decline-paths' is not a pattern of F10 (Take payment)")

    def test_move_to_an_unknown_step(self):
        def f(flow):
            flow["moves"][2]["to"] = "terminal"
        self.one_error(f, "moves[2] (card).to", "'terminal' is not a step")

    def test_bad_place(self):
        def f(flow):
            flow["steps"]["bill"]["place"] = "sideways"
        self.one_error(f, "steps.bill.place", "'sideways' is not one of: home, left, right")

    def test_job_not_in_the_job_map(self):
        def f(flow):
            flow["jobs"][0]["ref"] = "saltPOS:jobs#take-payment-when-leaving"
            flow["runs"][0]["job"] = "saltPOS:jobs#take-payment-when-leaving"
        self.one_error(f, "jobs[0].ref", "'take-payment-when-leaving' is not an id")

    def test_reworded_ruling(self):
        def f(flow):
            flow["links"][0]["quote"] = "Guests pay when they leave."
        self.one_error(f, "links[0].ref", "the stored quote is not in decisions.md")

    def test_run_asks_for_a_world_the_flow_lacks(self):
        def f(flow):
            flow["runs"][0]["world"]["card"] = "expired"
        self.one_error(f, "runs[0] (happy).world.card", "'expired' is not a value of card")

    def test_drive_left_in_the_flow(self):
        def f(flow):
            flow["moves"][0]["drive"] = [{"css": ".tabcard .pay", "do": "click"}]
        self.one_error(f, "moves[0] (open-bill).drive", "flows/drives/")

    def test_drive_for_a_move_that_does_not_exist(self):
        def f(flow):
            flow["moves"] = [m for m in flow["moves"] if m["id"] != "decline"]
            flow["steps"]["declined"]["built"] = False
        errs = self.errors_after(f)
        self.assertEqual(errs, ["flows/drives/web.json: moves.decline: 'decline' is not a move in any flow"])


if __name__ == "__main__":
    unittest.main()


class Records(Broken):
    """A records source is a JSON export of a live store (an ops log); a ref names <collection>/<id> and its
    quote must be in one of that record's fields. A quote into a cited file is checked as a warning."""

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.root, "room.json"), "w") as f:
            json.dump({"decisions": [{"id": "d-window", "data": {"status": "decided",
                                       "outcome": "Two floating\nglass panels, inspector right."}}],
                       "progress": {"p4": {"title": "Phase 4", "items": ["Review sync, Get Info."]}}}, f)
        with open(os.path.join(self.root, "note.py"), "w") as f:
            f.write("# The device entry knew the name;\n# the file did *not*.\n")
        mpath = os.path.join(self.root, "flows", "saltflow.json")
        with open(mpath) as f:
            man = json.load(f)
        man["sources"]["records"] = {"path": "room.json", "kind": "export"}
        man["sources"]["files"] = {"path": ".", "kind": "files"}
        with open(mpath, "w") as f:
            json.dump(man, f)

    def link(self, ref, quote):
        def f(flow):
            flow["links"].append({"kind": "words", "ref": ref, "state": "ruled", "quote": quote})
        return f

    def test_a_record_and_its_quote(self):
        self.assertEqual(self.errors_after(self.link("saltPOS:records#decisions/d-window", "Two floating glass panels")), [])

    def test_a_keyed_collection(self):
        self.assertEqual(self.errors_after(self.link("saltPOS:records#progress/p4", "Review sync, Get Info.")), [])

    def test_a_reworded_record(self):
        self.one_error(self.link("saltPOS:records#decisions/d-window", "Three floating panels"),
                       "links[1].ref", "not in room.json, record decisions/d-window")

    def test_a_missing_record(self):
        self.one_error(self.link("saltPOS:records#decisions/d-slice", "x"), "'decisions/d-slice' is not a record")

    def test_a_missing_collection(self):
        self.one_error(self.link("saltPOS:records#cards/fr-1", "x"), "'cards' is not a collection", "decisions, progress")

    def test_a_quote_from_a_code_comment(self):
        self.errors_after(self.link("saltPOS:files#note.py", "The device entry knew the name; the file did not."))
        self.assertEqual(model.validate(self.root).warnings, [])

    def test_a_quote_not_in_its_file_warns(self):
        self.errors_after(self.link("saltPOS:files#note.py", "The device forgot the name."))
        warns = [str(p) for p in model.validate(self.root).warnings]
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("the stored quote is not in note.py", warns[0])

    def test_an_export_folder(self):
        os.makedirs(os.path.join(self.root, "room", "decisions"))
        with open(os.path.join(self.root, "room", "decisions", "d-slice.json"), "w") as f:
            json.dump({"outcome": "34pt slice with the name written up it."}, f)
        mpath = os.path.join(self.root, "flows", "saltflow.json")
        with open(mpath) as f:
            man = json.load(f)
        man["sources"]["records"]["path"] = "room"
        with open(mpath, "w") as f:
            json.dump(man, f)
        self.assertEqual(self.errors_after(self.link("saltPOS:records#decisions/d-slice", "34pt slice with the name")), [])
