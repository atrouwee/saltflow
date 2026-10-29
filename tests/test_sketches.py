import os
import shutil
import tempfile
import unittest

from saltflow import server as S
from saltflow import walk as W

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "saltPOS")


class Sketches(unittest.TestCase):
    """A product with no screen draws its surfaces; the step's own drawing wins over its surface's."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "p")
        shutil.copytree(FIXTURE, self.root)
        W.walk(self.root)
        self.p = S.Product(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def put(self, rel):
        path = os.path.join(self.p.man.flows_dir(), "sketches", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 30"><rect class="focus" width="10" height="10"/></svg>')

    def test_surface_then_step_then_tile(self):
        self.assertEqual(self.p.sketches(), {"surfaces": {}, "steps": {}, "icons": {}, "decisions": {}, "examples": {}})
        f = self.p.flows()[0]
        sid = f["entry"]
        surface = f["steps"][sid]["surface"]
        self.put("%s.svg" % surface)
        self.put("icons/%s.svg" % surface)
        self.assertEqual(self.p.flow_bundle(f["id"])["sketches"][sid], "%s.svg" % surface)
        self.put("%s/%s.svg" % (f["id"], sid))
        self.assertEqual(self.p.flow_bundle(f["id"])["sketches"][sid], "%s/%s.svg" % (f["id"], sid))
        self.assertEqual(self.p.sketches()["icons"], {surface: "icons/%s.svg" % surface})
        self.put("decisions/d-x.svg")
        self.assertEqual(self.p.sketches()["decisions"], {"d-x": "decisions/d-x.svg"})
        self.assertNotIn("decisions/d-x", self.p.sketches()["steps"])
        self.put("decisions/d-x/two-line.png")         # an example of each answer, a picture or a drawing
        self.put("decisions/d-x/table.svg")
        self.assertEqual(self.p.sketches()["examples"], {"d-x": {"two-line": "decisions/d-x/two-line.png", "table": "decisions/d-x/table.svg"}})
        self.assertEqual(self.p.sketches()["decisions"], {"d-x": "decisions/d-x.svg"})
        tile = [x for x in self.p.summary()["flows"] if x["id"] == f["id"]][0]
        self.assertEqual(tile["sketch"], "%s/%s.svg" % (f["id"], sid))

    def test_needs_names_what_is_missing(self):
        from saltflow import needs as N
        kinds = {i["kind"] for i in N.needs(self.root)}
        self.assertTrue(kinds <= {"build", "capture", "sketch", "xray", "then", "guide"}, kinds)

    def test_a_commit_touching_a_part_without_its_picture_is_held(self):
        import json
        import subprocess
        from saltflow import needs as N
        g = lambda *a: subprocess.run(["git", "-C", self.root] + list(a), capture_output=True, check=True)
        g("init", "-q"); g("add", "-A"); g("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base")
        self.assertEqual(N.blocking(self.root), [])                 # nothing staged
        sp = os.path.join(self.p.man.flows_dir(), "surfaces.json")
        with open(sp) as f:
            d = json.load(f)
        sid = next(iter(d["surfaces"]))
        d["surfaces"][sid]["client"] = "physical"
        with open(sp, "w") as f:
            json.dump(d, f)
        g("add", "-A")
        bad = N.blocking(self.root)
        self.assertTrue(any("sketch it" in b for b in bad), bad)
        self.assertTrue(any("x-ray" in b for b in bad), bad)
        self.put("%s.svg" % sid)
        with open(os.path.join(self.p.man.flows_dir(), "sketches", "xray.svg"), "w") as f:
            f.write('<svg viewBox="0 0 4 3"><g data-surface="%s"/></svg>' % sid)
        self.assertTrue(N.blocking(self.root))                      # drawn but not staged still holds
        g("add", "-A")
        self.assertEqual(N.blocking(self.root), [])

    def test_a_product_command_runs_by_name_only(self):
        import json
        mp = os.path.join(self.p.man.flows_dir(), "saltflow.json")
        with open(mp) as f:
            m = json.load(f)
        m["commands"] = {"hello": {"run": ["python3", "-c", "import os; print('hi', os.environ['HOME_X'])"], "env": {"HOME_X": "{repo}/fixtures"}}}
        with open(mp, "w") as f:
            json.dump(m, f)
        r = S.terminal(self.root, "hello")
        self.assertEqual((r["output"].strip(), r["code"]), ("hi %s/fixtures" % self.root, 0))
        with self.assertRaises(ValueError):
            S.terminal(self.root, "python3 -c 1")
        from saltflow import model
        m["commands"] = {"bad": {"run": "rm -rf /"}}
        with open(mp, "w") as f:
            json.dump(m, f)
        self.assertTrue(any("commands.bad.run" in str(e) for e in model.validate(self.root).errors))

    def test_reach_finds_a_side_step_through_drivable_moves(self):
        from saltflow import model
        flow = {"id": "f", "entry": "a", "steps": {"a": {"status": "made"}, "b": {"status": "made"}, "c": {"status": "made"}, "d": {"status": "designed"}},
                "moves": [{"id": "ab", "from": "a", "to": "b"}, {"id": "bc", "from": "b", "to": "c"},
                          {"id": "ad", "from": "a", "to": "d"}, {"id": "dc", "from": "d", "to": "c"}]}
        self.assertEqual(model.reach(flow, {"ab": [], "f/bc": [{"css": "x"}], "ad": [], "dc": []}, "c"), (["a", "b", "c"], ["ab", "bc"]))
        self.assertIsNone(model.reach(flow, {"ab": [], "ad": [], "dc": []}, "c"))       # bc has no drive; d is not made
        self.assertIsNone(model.reach(flow, {"ab": [], "bc": None}, "c"))               # null: not drivable by nature

    def test_the_stage_renders_a_made_step_from_its_component(self):
        from saltflow import server as S2
        f = next(f for f in self.p.flows() if any(st.get("surface") for st in f["steps"].values()))
        sid = next(k for k, st in f["steps"].items() if st.get("surface"))
        f["steps"][sid]["status"] = "made"
        f["steps"][sid]["state"] = "declined"
        self.assertIsNone(S2.stage_url(self.p.man, f, sid, self.p.surfaces()))          # no stage: no url
        self.p.man.data["stage"] = "index.html?stage={surface}&state={state}"
        self.assertEqual(S2.stage_url(self.p.man, f, sid, self.p.surfaces()),
                         "index.html?stage=%s&state=declined" % f["steps"][sid]["surface"])
        f["steps"][sid]["status"] = "designed"
        self.assertIsNone(S2.stage_url(self.p.man, f, sid, self.p.surfaces()))          # nothing to render yet

    def test_moves_come_from_the_code(self):
        import json
        from saltflow import lint as L
        f = self.p.flows()[0]
        mv = next(m for m in f["moves"] if m.get("kind") != "system")
        self.assertNotIn("%s/%s" % (f["id"], mv["id"]), self.p.drives())             # no stage: nothing derived
        mp = os.path.join(self.p.man.flows_dir(), "saltflow.json")
        with open(mp) as fh:
            m = json.load(fh)
        m["stage"] = "index.html?stage={surface}&state={state}"
        with open(mp, "w") as fh:
            json.dump(m, fh)
        p = S.Product(self.root)
        d = p.drives()
        if mv["id"] not in d:
            self.assertEqual(d["%s/%s" % (f["id"], mv["id"])], [{"css": '[data-move-via~="%s"]' % mv["id"], "optional": True}, {"css": '[data-move~="%s"]' % mv["id"]}])
        cdir = os.path.join(p.man.flows_dir(), "captures")
        os.makedirs(cdir, exist_ok=True)
        with open(os.path.join(cdir, "index.json"), "w") as fh:
            json.dump({"steps": {"%s/%s" % (f["id"], mv["from"]): {"moves_in_code": ["not-in-the-flow"]}}}, fh)
        said = [x["text"] for x in L.lint(self.root) if x["kind"] == "code-differs"]
        self.assertTrue(any("offers not-in-the-flow" in x for x in said), said)
        self.assertTrue(any("has the move %s" % mv["id"] in x for x in said), said)
        with open(os.path.join(cdir, "index.json"), "w") as fh:          # the move on screen elsewhere; its words differ
            json.dump({"steps": {"%s/%s" % (f["id"], mv["from"]): {"moves_in_code": [], "moves_in_chrome": [mv["id"]],
                                                                   "move_words": {mv["id"]: "Something else entirely"}}}}, fh)
        found = L.lint(self.root)
        self.assertFalse(any(x["kind"] == "code-differs" and "has the move %s," % mv["id"] in x["text"] for x in found))
        if mv.get("kind") != "error":
            self.assertTrue(any(x["kind"] == "trigger-words" and "Something else entirely" in x["text"] for x in found))


if __name__ == "__main__":
    unittest.main()
