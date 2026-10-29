"""saltflow init in an empty folder: what it writes, that it says so, and the next three commands."""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock

from saltflow import cli
from saltflow import server as S


class Init(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo = os.path.join(self.tmp, "shop")
        os.makedirs(self.repo)
        self.home = os.path.join(self.tmp, "home")
        self.env = mock.patch.dict(os.environ, {"SALTFLOW_HOME": self.home})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_writes_the_skeleton_and_says_what(self):
        code, out = self.run_cli("--repo", self.repo, "init")
        self.assertEqual(code, 0)
        for rel in ("flows/saltflow.json", "flows/README.md", "flows/surfaces.json", ".gitignore"):
            self.assertTrue(os.path.isfile(os.path.join(self.repo, rel)), rel)
            self.assertIn(rel.split("/")[-1], out)
        with open(os.path.join(self.repo, "flows", "saltflow.json")) as f:
            self.assertEqual(json.load(f)["product"], "shop")
        for verb in ("saltflow validate", "saltflow walk", "saltflow "):
            self.assertIn(verb, out)

    def test_the_registry_is_named_when_written(self):
        code, out = self.run_cli("--repo", self.repo, "init")
        reg = os.path.join(self.home, "products.json")
        self.assertEqual(S.registry_path(), reg)
        self.assertIn(reg, out)
        with open(reg) as f:
            self.assertEqual(json.load(f), {"shop": os.path.abspath(self.repo)})

    def test_no_register_writes_nothing_outside_the_repo(self):
        code, out = self.run_cli("--repo", self.repo, "init", "--no-register")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.home))
        self.assertIn("--no-register", out)

    def test_a_second_init_keeps_the_manifest(self):
        self.run_cli("--repo", self.repo, "init", "--no-register")
        path = os.path.join(self.repo, "flows", "saltflow.json")
        with open(path, "w") as f:
            f.write('{"schema": "saltflow/v1/manifest", "product": "Mine", "flows": "flows"}\n')
        code, out = self.run_cli("--repo", self.repo, "init", "--no-register")
        with open(path) as f:
            self.assertEqual(json.load(f)["product"], "Mine")
        self.assertIn("left as it is", out)

    def test_no_product_names_init_and_demo(self):
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["--repo", self.repo, "validate"])
        self.assertIn("saltflow init", err.getvalue())
        self.assertIn("saltflow demo", err.getvalue())


if __name__ == "__main__":
    unittest.main()
