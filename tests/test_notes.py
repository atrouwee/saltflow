"""The notes file is the contract: append-only, a note's last line wins, closes are appended lines.

A product's own scripts read the same file with ten lines of Python; this test keeps the two readers agreeing.
"""
import json
import os
import shutil
import tempfile
import unittest

from saltflow import manifest as M
from saltflow import server as S
from saltflow import walk as W

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "saltPOS")


def saltpos_reader(path):
    """A product-side reader, verbatim in its rule: last line wins, fields merged, open or taken is open."""
    notes = {}
    with open(path) as f:
        lines = f.read().splitlines()
    for line in lines:
        line = line.strip()
        if line:
            n = json.loads(line)
            notes[n["id"]] = {**notes.get(n["id"], {}), **n}
    return [n for n in notes.values() if n.get("status") in ("open", "taken")]


class Notes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "saltPOS")
        shutil.copytree(FIXTURE, self.root)
        W.walk(self.root)                      # leaves the break notes
        self.p = S.Product(self.root)
        self.path = self.p.notes_path()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def lines(self):
        with open(self.path) as f:
            return [l for l in f if l.strip()]

    def test_a_close_is_one_appended_line_and_both_readers_agree(self):
        before = len(self.lines())
        nid = next(n["id"] for n in self.p.notes() if n["step"] == "bill-offline")
        self.p.update_note(nid, {"status": "done", "commit": "abc1234", "session": "saltPOS"})
        self.assertEqual(len(self.lines()), before + 1)
        last = json.loads(self.lines()[-1])
        self.assertEqual((last["id"], last["status"], last["commit_done"]), (nid, "done", "abc1234"))
        merged = next(n for n in self.p.notes() if n["id"] == nid)
        self.assertEqual(merged["status"], "done")
        self.assertEqual(merged["text"][:26], "offline-card-guest-leaves:")      # the text survives the merge
        self.assertEqual({n["id"] for n in saltpos_reader(self.path)}, {n["id"] for n in self.p.notes() if n["status"] in ("open", "taken")})
        self.assertNotIn(nid, {n["id"] for n in saltpos_reader(self.path)})

    def test_a_note_from_the_page_is_appended_and_a_rerun_walk_leaves_it(self):
        n = self.p.add_note({"kind": "question", "text": "Why no account option here?", "flow": "pay-on-leaving", "step": "bill"})
        self.assertEqual(n["origin"], M.reviewer(self.root))     # a note from the page is the reviewer's
        self.assertIn(n["id"], {x["id"] for x in saltpos_reader(self.path)})
        W.walk(self.root)
        self.assertIn(n["id"], {x["id"] for x in self.p.notes()})
        self.assertEqual(len([x for x in self.p.notes() if x["kind"] == "break"]), 2)

    def test_unknown_note_and_bad_status(self):
        with self.assertRaises(KeyError):
            self.p.update_note("n-nope", {"status": "done"})
        nid = self.p.notes()[0]["id"]
        with self.assertRaises(ValueError):
            self.p.update_note(nid, {"status": "closed"})


if __name__ == "__main__":
    unittest.main()


class Decisions(unittest.TestCase):
    """A decision is a session's question for the owner with options, one recommended (one room per product, the
    repo file the truth, answered on saltFlow's page). The answer and the ruling are later lines."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "saltPOS")
        shutil.copytree(FIXTURE, self.root)
        self.p = S.Product(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def ask(self, **kw):
        body = {"kind": "decision", "origin": "saltPOS", "title": "Receipt by default", "text": "Print a receipt?",
                "why": "Paper costs.", "options": [{"id": "ask", "label": "Ask each time", "rec": True},
                                                   {"id": "never", "label": "Never"}]}
        body.update(kw)
        return self.p.add_note(body)

    def test_asked_waits_then_decided_then_ruled(self):
        from saltflow import model
        d = self.ask(flow="pay-on-leaving", step="paid")
        self.assertTrue(d["id"].startswith("d-"))
        self.assertEqual([w["id"] for w in self.p.today()["waiting"] if w["kind"] == "decision"], [d["id"]])
        with self.assertRaises(ValueError):
            self.p.update_note(d["id"], {"ruling": "saltPOS:decisions#x"})     # not decided yet
        self.p.update_note(d["id"], {"status": "decided", "choice": "never", "words": "QR only."})
        a = [x for x in self.p.today()["answered"] if x["id"] == d["id"]][0]
        self.assertIn("not yet a ruling", a["sub"])
        self.p.update_note(d["id"], {"ruling": "saltPOS:decisions#2026-10-12"})
        n = [x for x in self.p.notes() if x["id"] == d["id"]][0]
        self.assertEqual((n["choice"], n["words"], n["ruling"], n["status"]), ("never", "QR only.", "saltPOS:decisions#2026-10-12", "decided"))
        self.assertEqual([str(e) for e in model.validate(self.root).errors], [])

    def test_a_decision_needs_its_shape(self):
        for kw, says in ((dict(options=[{"id": "a", "label": "A", "rec": True}]), "two options"),
                         (dict(options=[{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]), "exactly one option"),
                         (dict(why=""), "needs why")):
            with self.assertRaises(ValueError) as e:
                self.ask(**kw)
            self.assertIn(says, str(e.exception))

    def test_an_option_says_what_follows_and_a_decision_names_what_it_touches(self):
        first = self.ask()
        d = self.ask(title="Paper roll", text="Which roll?", options=[{"id": "a", "label": "A", "rec": True, "then": "every close waits on it"}, {"id": "b", "label": "B"}],
                     touches=[first["id"]])
        row = [w for w in self.p.today()["waiting"] if w["id"] == d["id"]][0]
        self.assertEqual((row["options"][0]["then"], row["touches"]), ("every close waits on it", [first["id"]]))
        for kw, says in ((dict(title="T2", text="q2", touches="d-1"), "touches is a list"), (dict(title="T3", text="q3", options=[{"id": "a", "label": "A", "rec": True, "then": 3}, {"id": "b", "label": "B"}]), "then is one line")):
            with self.assertRaises(ValueError) as e:
                self.ask(**kw)
            self.assertIn(says, str(e.exception))

    def test_the_choice_must_be_an_option(self):
        d = self.ask()
        with self.assertRaises(ValueError):
            self.p.update_note(d["id"], {"status": "decided", "choice": "sometimes"})
        self.p.update_note(d["id"], {"status": "decided", "words": "Only for invoices."})   # words alone hold

    def test_validate_names_a_broken_line(self):
        from saltflow import model
        with open(self.p.notes_path(), "a") as f:
            f.write(json.dumps({"id": "d-x", "kind": "decision", "status": "open", "text": "?", "title": "t", "why": "w",
                                "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]}) + "\n")
        errs = [str(e) for e in model.validate(self.root).errors]
        self.assertTrue(any("d-x" in e and "exactly one option" in e for e in errs), errs)
