"""saltflow doctor: one line per check, each with a fix; only Python and a readable manifest are required."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from saltflow import cli
from saltflow import doctor as D


def _product(d, name="sample"):
    os.makedirs(os.path.join(d, "flows"))
    with open(os.path.join(d, "flows", "saltflow.json"), "w") as f:
        f.write('{"schema": "saltflow/v1/manifest", "product": "%s", "flows": "flows"}\n' % name)


class Doctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"SALTFLOW_CACHE": os.path.join(self.tmp, "cache"),
                                                "PLAYWRIGHT_BROWSERS_PATH": os.path.join(self.tmp, "browsers"),
                                                "NODE_PATH": ""})
        self.env.start()
        os.environ.pop("SALTFLOW_PLAYWRIGHT", None)
        self.npm = mock.patch.object(D, "_npm_root_g", return_value=None)   # no global install on this machine
        self.npm.start()

    def tearDown(self):
        self.npm.stop()
        self.env.stop()
        shutil.rmtree(self.tmp)

    def by_name(self, res):
        return {c["name"]: c for c in res}

    def test_node_missing_is_a_line_with_a_fix_and_not_required(self):
        _product(self.tmp)
        real = shutil.which
        res = self.by_name(D.checks(self.tmp, which=lambda n: None if n == "node" else real(n)))
        self.assertFalse(res["node"]["ok"])
        self.assertIn("nodejs.org", res["node"]["fix"])
        self.assertFalse(res["node"]["required"])
        self.assertTrue(res["python"]["ok"])
        self.assertTrue(res["product"]["ok"])

    def test_every_check_carries_a_fix(self):
        for c in D.checks(self.tmp, which=lambda n: None):
            self.assertTrue(c["fix"] or c["ok"], c)

    def test_no_product_is_not_required_and_names_init_and_demo(self):
        res = self.by_name(D.checks(self.tmp, which=lambda n: None))
        self.assertIsNone(res["product"]["ok"])          # outside a product is fine for a first look, not a failure
        self.assertFalse(res["product"]["required"])
        self.assertIn("saltflow init", res["product"]["fix"])
        self.assertIn("saltflow demo", res["product"]["fix"])

    def test_exit_code_follows_the_required_checks_only(self):
        _product(self.tmp)
        out = io.StringIO()
        with mock.patch.object(D.shutil, "which", return_value=None), redirect_stdout(out):
            code = cli.main(["--repo", self.tmp, "doctor"])
        self.assertEqual(code, 0)
        self.assertIn("node", out.getvalue())
        self.assertIn("fix:", out.getvalue())

    def test_fix_without_yes_and_no_terminal_installs_nothing(self):
        _product(self.tmp)
        out = io.StringIO()
        with mock.patch.object(D, "install_playwright") as inst, mock.patch.object(sys.stdin, "isatty", return_value=False), redirect_stdout(out):
            cli.main(["--repo", self.tmp, "doctor", "--fix"])
        inst.assert_not_called()
        self.assertIn("nothing installed", out.getvalue())

    def test_playwright_order_env_then_web_then_cache(self):
        def pkg(d):
            os.makedirs(d)
            with open(os.path.join(d, "package.json"), "w") as f:
                f.write("{}")
            return os.path.abspath(d)
        _product(self.tmp)
        self.assertEqual(D.playwright(os.path.join(self.tmp, "web"), self.tmp), (None, "no playwright package found"))
        cache = pkg(os.path.join(self.tmp, "cache", "node_modules", "playwright"))
        self.assertEqual(D.playwright(os.path.join(self.tmp, "web"), self.tmp), (cache, "saltFlow's cache"))
        web = pkg(os.path.join(self.tmp, "web", "node_modules", "playwright"))
        self.assertEqual(D.playwright(os.path.join(self.tmp, "web"), self.tmp), (web, "the product's web app"))
        own = pkg(os.path.join(self.tmp, "mine", "playwright"))
        with mock.patch.dict(os.environ, {"SALTFLOW_PLAYWRIGHT": own}):
            self.assertEqual(D.playwright(os.path.join(self.tmp, "web"), self.tmp), (own, "SALTFLOW_PLAYWRIGHT"))
        with mock.patch.dict(os.environ, {"SALTFLOW_PLAYWRIGHT": os.path.join(self.tmp, "nowhere")}):
            self.assertIsNone(D.playwright()[0])

    def test_playwright_is_never_looked_for_above_the_product(self):
        outer = os.path.join(self.tmp, "node_modules", "playwright")
        os.makedirs(outer)
        with open(os.path.join(outer, "package.json"), "w") as f:
            f.write("{}")
        root = os.path.join(self.tmp, "product")
        _product(root)
        self.assertIsNone(D.playwright(os.path.join(root, "web"), root)[0])


if __name__ == "__main__":
    unittest.main()
