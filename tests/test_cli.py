"""The reviewer's name, the demo's example, and the verbs: nothing in the code names a person."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from saltflow import cli
from saltflow import demo as Dm
from saltflow import manifest as M
from saltflow import server as S

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def _product(d, name="sample"):
    os.makedirs(os.path.join(d, "flows"), exist_ok=True)
    with open(os.path.join(d, "flows", "saltflow.json"), "w") as f:
        json.dump({"schema": "saltflow/v1/manifest", "product": name, "flows": "flows"}, f)
    return d


def _git(d, *args):
    subprocess.run(["git", "-C", d] + list(args), check=True, capture_output=True)


class Reviewer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.path.join(self.tmp, "gitconfig"),
                                                "GIT_CONFIG_NOSYSTEM": "1"})
        self.env.start()
        os.environ.pop("SALTFLOW_REVIEWER", None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def test_env_wins(self):
        with mock.patch.dict(os.environ, {"SALTFLOW_REVIEWER": "Sam"}):
            self.assertEqual(M.reviewer(self.tmp), "Sam")

    @unittest.skipUnless(shutil.which("git"), "no git")
    def test_then_git_user_name(self):
        _git(self.tmp, "init", "-q")
        _git(self.tmp, "config", "user.name", "Robin Doe")
        self.assertEqual(M.reviewer(self.tmp), "Robin Doe")

    def test_else_you(self):
        self.assertEqual(M.reviewer(self.tmp), "you")
        with mock.patch.object(M.subprocess, "run", side_effect=OSError("no git")):
            self.assertEqual(M.reviewer(self.tmp), "you")

    def test_a_note_and_a_decision_without_a_name_are_the_reviewers(self):
        root = _product(os.path.join(self.tmp, "p"))
        p = S.Product(root)
        with mock.patch.dict(os.environ, {"SALTFLOW_REVIEWER": "Sam"}):
            n = p.add_note({"kind": "question", "text": "Why here?"})
            self.assertEqual(n["origin"], "Sam")
            self.assertNotIn(n["id"], [w["id"] for w in p.today()["waiting"]])   # your own question never waits on you
            self.assertEqual(p.summary()["reviewer"], "Sam")
            d = p.add_note({"kind": "decision", "origin": "a session", "title": "Receipt", "text": "Print one?", "why": "paper",
                            "options": [{"id": "yes", "label": "Yes", "rec": True}, {"id": "no", "label": "No"}]})
            self.assertEqual(p.update_note(d["id"], {"status": "decided", "choice": "yes"})["by"], "Sam")
        # a note someone else wrote still waits
        q = p.add_note({"kind": "question", "text": "And this?", "origin": "a session"})
        self.assertIn(q["id"], [w["id"] for w in p.today()["waiting"]])

    def test_existing_notes_keep_their_origin(self):
        root = _product(os.path.join(self.tmp, "p"))
        with open(os.path.join(root, "flows", "notes.jsonl"), "w") as f:
            f.write(json.dumps({"id": "n-old", "kind": "question", "origin": "Kim", "status": "open", "text": "mine"}) + "\n")
        p = S.Product(root)
        with mock.patch.dict(os.environ, {"SALTFLOW_REVIEWER": "Kim"}):
            self.assertEqual(p.today()["waiting"], [])
        with mock.patch.dict(os.environ, {"SALTFLOW_REVIEWER": "Sam"}):
            self.assertEqual([w["id"] for w in p.today()["waiting"]], ["n-old"])


class Demo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.pop("SALTFLOW_EXAMPLE", None)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_env_first(self):
        ex = _product(os.path.join(self.tmp, "ex"))
        with mock.patch.dict(os.environ, {"SALTFLOW_EXAMPLE": ex}):
            self.assertEqual(Dm.example_root(), ex)
        with mock.patch.dict(os.environ, {"SALTFLOW_EXAMPLE": os.path.join(self.tmp, "nowhere")}):
            self.assertIsNone(Dm.example_root())

    def test_packaged_then_the_clone(self):
        pkg = os.path.join(self.tmp, "clone", "src", "saltflow")
        os.makedirs(pkg)
        self.assertIsNone(Dm.example_root(pkg))
        clone = _product(os.path.join(self.tmp, "clone", "examples", "saltpos"))
        self.assertEqual(Dm.example_root(pkg), clone)
        packaged = _product(os.path.join(pkg, "example"))
        self.assertEqual(Dm.example_root(pkg), packaged)

    @unittest.skipUnless(os.path.isfile(os.path.join(REPO, "examples", "saltpos", "flows", "saltflow.json")), "no examples/saltpos yet")
    def test_this_clone_finds_its_example(self):
        self.assertEqual(os.path.realpath(Dm.example_root()), os.path.realpath(os.path.join(REPO, "examples", "saltpos")))

    def test_the_copy_leaves_the_example_alone(self):
        ex = _product(os.path.join(self.tmp, "ex"))
        for name in ("notes.jsonl", "runs.json"):
            with open(os.path.join(ex, "flows", name), "w") as f:
                f.write("{}\n")
        os.makedirs(os.path.join(ex, "flows", "captures"))
        dst = Dm.prepare(ex)
        try:
            self.assertTrue(os.path.isfile(os.path.join(dst, "flows", "saltflow.json")))
            for name in ("notes.jsonl", "captures"):            # the example's notes and screens are its content
                self.assertTrue(os.path.exists(os.path.join(dst, "flows", name)), name)
            self.assertFalse(os.path.exists(os.path.join(dst, "flows", "runs.json")))     # the demo walks again
        finally:
            shutil.rmtree(os.path.dirname(dst))

    def test_demo_serves_the_copy_and_never_registers_it(self):
        ex = _product(os.path.join(self.tmp, "ex"))
        with mock.patch.dict(os.environ, {"SALTFLOW_EXAMPLE": ex, "SALTFLOW_HOME": os.path.join(self.tmp, "home")}), \
                mock.patch.object(S, "serve") as serve, mock.patch("sys.stdout"):
            self.assertEqual(cli.main(["demo", "--no-open", "--port", "5999"]), 0)
        (root, port), kw = serve.call_args
        self.assertNotEqual(root, ex)
        self.assertEqual(port, 5999)
        self.assertEqual(kw, {"open_page": False, "register_it": False})
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "home")))
        shutil.rmtree(os.path.dirname(root))


class Page(unittest.TestCase):
    def test_the_page_inlines_every_stylesheet(self):
        html = S.page_html()
        self.assertNotRegex(html, r"__[A-Z]+_CSS__")
        self.assertIn(".gl-tabbar", html)


class Verbs(unittest.TestCase):
    def test_every_verb_runs_and_none_points_at_a_plan(self):
        for verb, help_ in cli.VERBS.items():
            self.assertIsInstance(help_, str)
            self.assertNotIn("plan", help_)
        self.assertIn("doctor", cli.VERBS)
        self.assertIn("demo", cli.VERBS)

    def test_lan_warns_that_anyone_can_write(self):
        self.assertIn("anyone on this network", S.LAN_WARNING)
        self.assertIn("notes", S.LAN_WARNING)


if __name__ == "__main__":
    unittest.main()
