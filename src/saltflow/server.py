"""The local server: the page, and a small JSON API over the product's files.

Standard library only, local only. Every request reads the files again, so the page is never stale and nothing is
cached to go wrong. The one write it accepts is a note (and a note's status). `saltflow` run bare starts it and
opens the page; `saltflow publish` writes the same page with its data inlined, for anyone without the repo.
"""
import json
import mimetypes
import os
import subprocess
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote

from . import manifest as M
from . import walk as W
from . import lint as L
from . import coverage as C
from . import model

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 5318


# -- the products saltFlow knows ------------------------------------------------------------------------------

def registry_path():
    """The one file saltFlow keeps outside a product: the list the page's product switcher reads. SALTFLOW_HOME
    moves it (default ~/.saltflow)."""
    home = os.environ.get("SALTFLOW_HOME") or os.path.join(os.path.expanduser("~"), ".saltflow")
    return os.path.join(home, "products.json")


def registry():
    """name -> repo root, for every product saltFlow was run in on this machine; roots that vanished are dropped."""
    data = _json(registry_path(), {}) or {}
    return {k: v for k, v in data.items() if os.path.isfile(os.path.join(v, M.NAME))}


def registered(root):
    """The name a product is listed under, or None."""
    root = os.path.abspath(root)
    return next((k for k, v in registry().items() if os.path.abspath(v) == root), None)


def register(root):
    root = os.path.abspath(root)
    name = M.load(root).product
    data = registry()
    if data.get(name) not in (None, root):
        # a second copy of a product (a test, a worktree) never takes the name from the one already registered
        name = "%s (%s)" % (name, os.path.basename(root))
    data[name] = root
    path = registry_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return name


# -- reading the product -------------------------------------------------------------------------------------

def _json(path, default=None):
    """A broken file reads as missing, said once in the log, so one bad file never takes the whole page down."""
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            try:
                return json.load(f)
            except ValueError as e:
                if path not in BROKEN:
                    BROKEN.add(path)
                    print("saltflow: %s does not read as JSON (%s); showing the page without it" % (path, e), flush=True)
    return default


def _jsonl_all(path):
    """Every line as it is, oldest first (iterations are records, never merged)."""
    out = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    return out


def _jsonl(path):
    """The notes file is append-only: one JSON object per line, and a note's last line wins, with its fields merged
    over the earlier ones. So an appended {"id", "status": "done", "commit_done"} closes a note, and any reader
    with ten lines of Python (the product's own reader) sees the same notes this server does."""
    notes = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    n = json.loads(line)
                except ValueError:
                    continue
                if isinstance(n, dict) and n.get("id"):
                    notes[n["id"]] = dict(notes.get(n["id"], {}), **n)
    return list(notes.values())


class Product:
    """One product, read fresh on every call."""

    def __init__(self, root):
        self.root = root
        self.man = M.load(root)
        self.head = W.product_head(root)

    def flows(self):
        out = []
        d = self.man.flows_dir()
        for name in sorted(os.listdir(d)):
            if name.endswith(".json"):
                data = _json(os.path.join(d, name))
                if isinstance(data, dict) and data.get("schema") == "saltflow/v1/flow":
                    out.append(data)
        return out

    def flow(self, fid):
        return next((f for f in self.flows() if f["id"] == fid), None)

    def surfaces(self):
        return (_json(self.man.source_path("surfaces")) or {}).get("surfaces", {})

    def own_patterns(self):
        return {p["id"]: p for p in (_json(self.man.source_path("patterns")) or {}).get("patterns", [])}

    def grid(self):
        return _json(self.man.source_path("grid"))

    def jobs(self):
        return {j["id"]: j for j in self.man.records("jobs")} if "jobs" in self.man.sources else {}

    def runs(self):
        return _json(os.path.join(self.man.flows_dir(), "runs.json")) or {"runs": [], "at": None, "commit": None}

    def notes_path(self):
        return os.path.join(self.man.flows_dir(), "notes.jsonl")

    def notes(self):
        return _jsonl(self.notes_path())

    def iterations(self):
        return _jsonl_all(os.path.join(self.man.flows_dir(), "iterations.jsonl"))

    def captures(self):
        return _json(os.path.join(self.man.flows_dir(), "captures", "index.json")) or {}

    def sketches(self):
        """A product with no screen draws its surfaces: flows/sketches/<surface>.svg, a state of one step at
        <flow>/<step>.svg, a glyph at icons/<surface>.svg, one question on a step that carries several at
        decisions/<decision id>.svg, and an example of each answer at decisions/<decision id>/<option id>.svg, .png,
        .jpg or .webp."""
        d = os.path.join(self.man.flows_dir(), "sketches")
        out = {"surfaces": {}, "steps": {}, "icons": {}, "decisions": {}, "examples": {}}
        if not os.path.isdir(d):
            return out
        for dirpath, _, files in os.walk(d):
            for f in sorted(files):
                rel = os.path.relpath(os.path.join(dirpath, f), d).replace(os.sep, "/")
                stem, ext = os.path.splitext(rel)
                parts = stem.split("/")
                if parts[0] == "decisions" and len(parts) == 3 and ext.lower() in PICTURE_EXT:
                    out["examples"].setdefault(parts[1], {})[parts[2]] = rel
                    continue
                if ext != ".svg":
                    continue
                if len(parts) == 1:
                    out["surfaces"][parts[0]] = rel
                elif parts[0] == "icons" and len(parts) == 2:
                    out["icons"][parts[1]] = rel
                elif parts[0] == "decisions" and len(parts) == 2:
                    out["decisions"][parts[1]] = rel
                elif len(parts) == 2:
                    out["steps"]["%s/%s" % tuple(parts)] = rel
        return out

    def sketch_for(self, fid, sid, step, sk=None):
        sk = sk or self.sketches()
        return sk["steps"].get("%s/%s" % (fid, sid)) or sk["surfaces"].get(step.get("surface") or "")

    def joins(self):
        return (_json(os.path.join(self.man.flows_dir(), "joins.json")) or {}).get("joins", [])

    def drives(self):
        d = os.path.join(self.man.flows_dir(), "drives")
        out = {}
        if os.path.isdir(d):
            for name in os.listdir(d):
                if name.endswith(".json"):
                    out.update((_json(os.path.join(d, name)) or {}).get("moves", {}))
        # A product that stages its components marks each control with data-move="<move id>": the drive is derived
        # from the code, never written by hand. A written drive still wins; a system move happens by itself and is never clicked.
        if self.man.data.get("stage"):
            for f in self.flows():
                for mv in f["moves"]:
                    k = "%s/%s" % (f["id"], mv["id"])
                    if mv.get("kind") != "system" and k not in out and mv["id"] not in out:
                        # a control the move passes through first (a tab) says data-move-via; tapped when it is there
                        out[k] = [{"css": '[data-move-via~="%s"]' % mv["id"], "optional": True}, {"do": "move", "id": mv["id"], "css": '[data-move~="%s"]' % mv["id"]}]
        return out

    # -- the pieces the page shows --

    def pattern(self, ref):
        """A pattern ref resolved for Why: the pattern, its area, the area's other patterns with their counts, the
        product's stance and reason, and the links it rests on."""
        P = self.man.product
        src, _, key = ref.partition("#")
        src = src.split(":")[-1]
        grid = self.grid()
        areas = {f["id"]: f for f in grid.get("flows", [])} if grid else {}
        direction = (grid or {}).get("direction", {}).get("flows", {})
        out = {"ref": ref, "name": key, "others": [], "links": []}
        if src == "grid":
            aid, _, pid = key.partition("/")
            area = areas.get(aid)
            if not area:
                return dict(out, missing="%s is not an area of the grid" % aid)
            d = direction.get(aid, {})
            chosen = next((p for p in area["patterns"] if p["id"] == pid), None)
            out.update(area=aid, area_name=area["name"], of=area.get("of"),
                       name=(chosen or {}).get("label", pid), desc=(chosen or {}).get("desc", ""),
                       n=(chosen or {}).get("n"), who=(chosen or {}).get("who", ""), kind=(chosen or {}).get("kind"),
                       stance=d.get("stance"), reason=d.get("reason"), direction=d.get("pattern"),
                       others=[{"id": p["id"], "name": p["label"], "n": p["n"], "kind": p["kind"]} for p in area["patterns"]])
        elif src == "patterns":
            own = self.own_patterns().get(key)
            if not own:
                return dict(out, missing="%s is not in the product's own patterns" % key)
            aid = own.get("area", "").split("#")[-1]
            area = areas.get(aid, {})
            out.update(area=aid, area_name=own.get("area_name", area.get("name")), of=area.get("of"),
                       name=own.get("name", key), desc=own.get("reason", ""), stance=own.get("stance"),
                       reason=own.get("reason"), own=True, steps=own.get("steps", []),
                       others=[{"id": p["id"], "name": p["label"], "n": p["n"], "kind": p["kind"]} for p in area.get("patterns", [])],
                       links=own.get("links", []))
        return out

    def flow_bundle(self, fid):
        flow = self.flow(fid)
        if not flow:
            return None
        surfaces = self.surfaces()
        # the page reads one status per step and one verdict per run, whatever form the files are in
        flow = dict(flow, steps={k: dict(v, status=model.step_status(v), made=model.is_made(v)) for k, v in flow["steps"].items()})
        used = {s["surface"] for s in flow["steps"].values() if "surface" in s}
        runs = [dict(r, verdict=model.run_verdict(r)) for r in self.runs()["runs"] if r.get("flow") == fid]
        notes = [n for n in self.notes() if n.get("flow") == fid]
        refs = set()
        for s in flow["steps"].values():
            refs.update(s.get("patterns", []))
        jobs = self.jobs()
        job_names = {j["ref"]: jobs.get(j["ref"].split("#")[-1], {}).get("name", j["ref"]) for j in flow["jobs"]}
        grid = self.grid() or {}
        areas = {a["id"]: {"name": a["name"], "of": a.get("of")} for a in grid.get("flows", [])}
        return {"flow": flow, "surfaces": {k: v for k, v in surfaces.items() if k in used},
                "patterns": {r: self.pattern(r) for r in sorted(refs)}, "runs": runs, "notes": notes,
                "jobs": job_names, "areas": {g.split("#")[-1]: areas.get(g.split("#")[-1], {"name": g}) for g in flow.get("grid", [])},
                "drives": {m["id"]: d for m in flow["moves"] for d in [self.drives().get("%s/%s" % (fid, m["id"]), self.drives().get(m["id"]))] if d is not None},
                "lint": [f for f in L.lint(self.root) if f.get("flow") == fid], "head": self.head,
                "captures": {k.split("/", 1)[1]: v for k, v in (self.captures().get("steps") or {}).items() if k.startswith(fid + "/")},
                "xray": self.sketches()["surfaces"].get("xray"),
                "sketches": {sid: r for sk in [self.sketches()] for sid, st in flow["steps"].items() for r in [self.sketch_for(fid, sid, st, sk)] if r},
                "iterations": [it for it in self.iterations() if fid in (it.get("flows") or [])][-20:],
                "product": self.man.product, "root": self.root}

    def summary(self):
        runs = self.runs()
        jobs = self.jobs()
        caps = (self.captures() or {}).get("steps", {})
        sk = self.sketches()
        flows = []
        for f in self.flows():
            rs = [r for r in runs["runs"] if r.get("flow") == f["id"]]
            named = [r for r in rs if "expect" in r]
            flows.append({"id": f["id"], "name": f["name"], "says": f.get("says", ""), "steps": len(f["steps"]),
                          "moves": len(f["moves"]), "jobs": len(f["jobs"]), "runs": len(rs),
                          # a run that stops only at a step not made yet, on a path the design completes, is work, not a break
                          "breaks": sum(1 for r in named if model.run_verdict(r) == "break"),
                          "unbuilt": sum(1 for s in f["steps"].values() if model.step_status(s) in ("designed", "making")),
                          "area": flow_area(f, jobs), "stage": f.get("stage"), "path": f.get("path"), "journey": f.get("journey"), "inner": [st["flow"] for st in f["steps"].values() if st.get("flow")],
                          "thumb": thumb(f, caps), "sketch": first_sketch(self, f, sk), "job": (jobs.get(f["jobs"][0]["ref"].split("#")[-1], {}) if f.get("jobs") else {}).get("name")})
        notes = self.notes()
        return {"product": self.man.product, "head": self.head, "says": self.man.data.get("says", ""),
                "flows": flows, "walked_at": runs.get("at"), "walked_commit": runs.get("commit"),
                "notes_open": sum(1 for n in notes if n.get("status") == "open"),
                "breaks": sum(1 for n in notes if n.get("status") == "open" and n.get("kind") == "break"),
                "look": self.man.data.get("look", {}), "journeys": model.journeys_of(self.man.data),
                # what the product calls its work-in-progress build, in the page's words
                "calls_it": self.man.data.get("capture", {}).get("calls_it", "the build"),
                "reviewer": M.reviewer(self.root)}

    def today(self):
        """What is waiting on the reviewer, what broke, what changed, what was answered. All from files."""
        notes = self.notes()
        me = M.reviewer(self.root)
        jobs = self.jobs()
        sk = self.sketches()
        flows = {f["id"]: f for f in self.flows()}
        waiting, broke, answered, working = [], [], [], []
        for j in self.joins():
            if j.get("flows") and j.get("state") == "proposed":
                waiting.append({"kind": "pair", "flow": j["flows"][0], "job": j["job"], "text": j["name"],
                                "sub": "proposed job pair · %s" % flows.get(j["flows"][0], {}).get("name", j["flows"][0])})
        for n in notes:
            row = {"kind": n["kind"], "flow": n.get("flow"), "step": n.get("step"), "id": n["id"], "text": n["text"],
                   "when": n.get("at", ""), "origin": n.get("origin", ""), "status": n.get("status")}
            if n.get("kind") == "decision":
                row.update(title=n.get("title"), why=n.get("why"), options=n.get("options", []), choice=n.get("choice"),
                           words=n.get("words"), ruling=n.get("ruling"), area=n.get("area"), touches=n.get("touches") or [],
                           sketch=sk["decisions"].get(n["id"]), examples=sk["examples"].get(n["id"], {}))
                if n.get("status") in ("open", "taken"):
                    waiting.append(dict(row, sub="decision from %s%s" % (n.get("origin", "a session"), " · " + n["area"] if n.get("area") else "")))
                elif n.get("status") == "decided":
                    label = next((o.get("label") for o in n.get("options", []) if o.get("id") == n.get("choice")), None)
                    answered.append(dict(row, sub="decided: %s%s" % (label or "in your words", "" if n.get("ruling") else " · not yet a ruling")))
                continue
            if n.get("status") == "open" and n.get("kind") == "break":
                broke.append(row)
            elif n.get("status") == "open" and n.get("kind") == "question" and n.get("origin") != me:
                waiting.append(dict(row, sub="question from %s" % n.get("origin", "a session")))
            elif n.get("status") in ("done", "won't do"):
                answered.append(dict(row, sub="%s · %s" % (n.get("status"), n.get("commit") or (n.get("reply") or {}).get("text", ""))))
            elif n.get("status") == "taken":
                working.append(dict(row, sub="taken by %s" % ((n.get("reply") or {}).get("session") or "a session")))
        for f in L.lint(self.root):
            broke.append({"kind": "lint", "flow": f["flow"], "step": f["at"], "text": f["text"], "sub": f["kind"]})
        runs = self.runs()
        changed = []
        for it in reversed(self.iterations()[-12:]):
            if it.get("touched") == "nothing":
                continue
            changed.append({"kind": "iteration", "commit": it["commit"], "subject": it.get("subject", ""), "steps": it.get("steps", []),
                            "files": (it.get("web_files") or []) + (it.get("flow_files") or []), "flow": (it.get("flows") or [None])[0], "step": (it.get("steps") or ["/"])[0].split("/", 1)[-1] if it.get("steps") else None,
                            "text": "%s · %s" % (it["commit"], it.get("subject", "")),
                            "sub": "%d step%s in %s" % (len(it.get("steps", [])), "" if len(it.get("steps", [])) == 1 else "s", ", ".join(it.get("flows", [])) or "no flow"),
                            "when": it.get("at")})
        if runs.get("at") and not changed:
            changed.append({"kind": "walk", "text": "Walked %d runs at %s" % (len(runs["runs"]), runs.get("commit")),
                            "sub": runs["at"].replace("T", " ")})
        return {"working": working, "waiting": waiting, "broke": broke, "changed": changed, "answered": answered,
                "jobs": {k: v.get("name") for k, v in jobs.items()}}

    # -- the one write --

    def add_note(self, body):
        kind = body.get("kind", "question")
        if kind not in model.NOTE_KINDS:
            raise ValueError("kind should be one of: %s" % ", ".join(model.NOTE_KINDS))
        text = (body.get("text") or "").strip()
        if not text:
            raise ValueError("a note needs text")
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        origin = body.get("origin") or M.reviewer(self.root)
        prefix = "d-" if kind == "decision" else "n-"
        nid = body.get("id") or prefix + W.hashlib.sha1(("%s|%s|%s|%s|%s" % (origin, body.get("flow"), body.get("step"), text, now)).encode()).hexdigest()[:8]
        if any(n["id"] == nid for n in self.notes()):
            raise ValueError("a note %s is already there" % nid)
        note = {"id": nid, "kind": kind, "origin": origin, "status": "open", "at": now,
                "commit": self.head, "flow": body.get("flow"), "step": body.get("step"), "text": text}
        for k in ("region", "move"):
            if body.get(k):
                note[k] = body[k]
        if kind == "decision":
            note.update(title=(body.get("title") or "").strip(), why=(body.get("why") or "").strip(),
                        options=body.get("options") or [])
            for k in ("area", "links", "touches"):
                if body.get(k):
                    note[k] = body[k]
            bad = model.decision_problems(note)
            if bad:
                raise ValueError("; ".join(bad))
        with open(self.notes_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
        return note

    def update_note(self, nid, body):
        """Appends one line with the fields that change; never rewrites the file (the file is the contract
        between sessions). A decision is answered with status decided, the option chosen and the reviewer's
        own words; the session that turns it into a ruling appends `ruling` (a ref into its rulings)."""
        hit = next((n for n in self.notes() if n["id"] == nid), None)
        if not hit:
            raise KeyError("no note %s" % nid)
        status = body.get("status")
        if status and status not in model.NOTE_STATUSES:
            raise ValueError("status should be one of: %s" % ", ".join(model.NOTE_STATUSES))
        line = {"id": nid, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if status:
            line["status"] = status
        if status == "decided":
            if hit.get("kind") != "decision":
                raise ValueError("only a decision is decided")
            choice = body.get("choice") or None
            words = (body.get("words") or "").strip()
            ids = [o.get("id") for o in hit.get("options", [])]
            if choice is not None and choice not in ids:
                raise ValueError("%r is not one of the options (%s)" % (choice, ", ".join(ids)))
            if choice is None and not words:
                raise ValueError("pick an option, or say it in your own words")
            line.update(choice=choice, words=words, by=body.get("by") or M.reviewer(self.root), commit_decided=self.head)
        if body.get("ruling"):
            if hit.get("kind") != "decision" or (hit.get("status") != "decided" and status != "decided"):
                raise ValueError("only a decided decision becomes a ruling")
            line["ruling"] = body["ruling"]
        if body.get("commit"):
            line["commit_done"] = body["commit"]
        if body.get("reply"):
            line["reply"] = {"text": body["reply"], "session": body.get("session", ""), "at": line["at"]}
        if body.get("session"):
            line["by"] = body["session"]
        with open(self.notes_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return dict(hit, **line)


def flow_area(flow, jobs):
    """The area a flow sits under on the page's left: its first job's area, else its line, else its moment. Jobs differ per product; the first field a product's jobs carry wins."""
    for ref in flow.get("jobs", []):
        j = jobs.get(ref["ref"].split("#")[-1], {})
        for k in ("area", "line", "moment"):
            if j.get(k):
                return j[k]
    return None


TERMINAL_READS = ("notes", "notes --all", "lint", "coverage", "validate")


def terminal(root, cmd):
    """A read-only saltflow command run in the product's repo, its output as plain text: what a terminal surface
    looks like live. Only commands that write nothing run here; taking or closing a note stays a session's act."""
    import re
    import sys
    declared = (M.load(root).data.get("commands") or {})
    if cmd in declared:
        # the product's own read-only command, declared by name in its manifest; nothing from the request reaches the
        # words run, no shell, a short timeout, output capped. The manifest says it writes nothing.
        spec = declared[cmd]
        env = dict(os.environ, NO_COLOR="1", COLUMNS="110")
        env.update({k: v.replace("{repo}", root) for k, v in (spec.get("env") or {}).items()})
        try:
            r = subprocess.run(list(spec["run"]), cwd=root, capture_output=True, text=True, timeout=min(int(spec.get("timeout", 15)), 30), env=env)
            out, code = (r.stdout or "") + (r.stderr or ""), r.returncode
        except (OSError, subprocess.TimeoutExpired) as e:
            out, code = str(e), -1
        out = re.sub(r"\x1b\[[0-9;]*m", "", out)
        return {"command": " ".join(spec["run"]), "output": out[:100000], "code": code}
    if cmd not in TERMINAL_READS:
        raise ValueError("only saltFlow's own reads (%s) or a command the product's manifest names run from the page" % ", ".join(TERMINAL_READS))
    r = subprocess.run([sys.executable, "-m", "saltflow.cli"] + cmd.split(), cwd=root, capture_output=True, text=True,
                       timeout=60, env=dict(os.environ, NO_COLOR="1", COLUMNS="110"))
    out = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout or "") + (r.stderr or ""))
    return {"command": "saltflow " + cmd, "output": out, "code": r.returncode}


def thumb(flow, caps):
    """The tile's picture on the journey board: the crop of the first captured step along the flow, from its entry."""
    order = [flow["entry"]] + [mv["to"] for mv in flow["moves"] if mv.get("kind") == "forward"]
    for sid in order:
        c = caps.get("%s/%s" % (flow["id"], sid))
        if c and c.get("files"):
            return c["files"]
    return None


def first_sketch(p, flow, sk):
    """The tile's drawing when there is no crop: the first sketched step along the flow, from its entry."""
    order = [flow["entry"]] + [mv["to"] for mv in flow["moves"] if mv.get("kind") == "forward"]
    for sid in order:
        r = p.sketch_for(flow["id"], sid, flow["steps"].get(sid, {}), sk)
        if r:
            return r
    return None


def stage_url(man, flow, sid, surfaces):
    """The product's own component for this step, rendered alone in its build. The manifest's "stage" is a page of the build with {surface} and {state} in it, e.g.
    "index.html?stage={surface}&state={state}"; a step's "state" names the fixture (default "default"). None when the
    product has no stage, the step is not made, or its surface is a terminal or says "stage": false."""
    tpl = man.data.get("stage")
    st = flow["steps"].get(sid, {})
    surf = surfaces.get(st.get("surface") or "", {})
    if not tpl or not st.get("surface") or not model.is_made(st) or surf.get("client") == "terminal" or surf.get("stage") is False:
        return None
    return tpl.replace("{surface}", quote(st["surface"])).replace("{state}", quote(st.get("state") or "default")) \
              .replace("{flow}", quote(flow["id"])).replace("{step}", quote(sid))


def live_path(p, fid, step):
    """What the page plays in the product's dummy to arrive at `step` live: the setup, then one list of drive actions
    per move, along the first named run that passes the step (else the shortest walk). Stops early, and says why,
    where a move has no drive or a step on the way is not built."""
    flow = p.flow(fid)
    if not flow or step not in flow["steps"]:
        raise KeyError("no step %s in %s" % (step, fid))
    surf = p.surfaces().get(flow["steps"][step].get("surface"), {})
    if surf.get("command"):
        return {"steps": [step], "actions": [], "stop": None, "terminal": surf["command"]}
    runs = [r for r in p.runs().get("runs", []) if r.get("flow") == fid and step in r.get("path", [])]
    runs.sort(key=lambda r: ("expect" not in r, r["path"].index(step)))
    drives = p.drives()
    by_id = {mv["id"]: mv for mv in flow["moves"]}
    pairs = {}
    for mv in flow["moves"]:
        pairs.setdefault((mv["from"], mv["to"]), mv)
    clean = lambda acts: [a for a in acts if model.drivable(a)]
    way = None if runs else model.reach(flow, drives, step)
    if way:
        path, moves, setup = way[0], way[1], clean(flow.get("setup", []))
    elif not runs:
        path, moves, setup = [flow["entry"]], [], clean(flow.get("setup", []))
        if step != flow["entry"]:
            return {"steps": path, "actions": [setup], "stop": "no way to %s through made steps with drives, and no walk passes it" % step}
    else:
        r = runs[0]
        i = r["path"].index(step)
        path, moves = r["path"][:i + 1], (r.get("moves") or [])[:i]
        setup = clean(r.get("setup", flow.get("setup", [])))
    actions, stop = [setup], None
    for i in range(1, len(path)):
        mv = by_id.get(moves[i - 1]) if len(moves) >= i else pairs.get((path[i - 1], path[i]))
        key = "%s/%s" % (fid, mv["id"]) if mv else None
        d = drives.get(key) if key in drives else drives.get(mv["id"]) if mv else None
        if not model.is_made(flow["steps"][path[i]]):
            stop = "%s is not built yet" % path[i]
        elif d is None and mv and (key in drives or mv["id"] in drives):
            stop = "nothing can drive the move %s by nature (its drive is null)" % mv["id"]
        elif d is None:
            stop = "no drive for the move %s (%s)" % (mv["id"] if mv else "?", mv["trigger"] if mv else "")
        if stop:
            path = path[:i]
            break
        actions.append(d)
    return {"steps": path, "actions": actions, "stop": stop, "run": runs[0]["id"] if runs else ("the shortest drivable way" if way else None)}


def version(root):
    """What the page polls: the newest change under flows/ and the product's head. Cheap enough every two seconds."""
    man = M.load(root)
    newest = 0.0
    for dirpath, _, files in os.walk(man.flows_dir()):
        if "captures" in dirpath:
            continue
        for name in files:
            try:
                newest = max(newest, os.stat(os.path.join(dirpath, name)).st_mtime)
            except OSError:
                pass
    return {"files": round(newest, 3), "head": W.product_head(root), "code": code_stamp()}


def code_stamp():
    """The newest change to saltFlow's own code (the page, its styles, the Python). The page reloads itself when it
    moves, and the server restarts itself when a .py moves, so a page left open is never behind the code."""
    newest = 0.0
    for dirpath, _, files in os.walk(HERE):
        for name in files:
            if name.endswith((".py", ".html", ".css", ".mjs")):
                try:
                    newest = max(newest, os.stat(os.path.join(dirpath, name)).st_mtime)
                except OSError:
                    pass
    return round(newest, 3)


def _py_stamp():
    return max((os.stat(os.path.join(d, n)).st_mtime for d, _, fs in os.walk(HERE) for n in fs if n.endswith(".py")), default=0)


def _restart_on_change(httpd):
    """Watch saltFlow's Python; when it changes and still compiles, close the socket and start this same command
    again in place, so the port and the address stay the same."""
    import py_compile
    import sys
    import threading
    start = _py_stamp()

    def loop():
        while True:
            time.sleep(1.5)
            if _py_stamp() <= start:
                continue
            try:
                for d, _, fs in os.walk(HERE):
                    for n in fs:
                        if n.endswith(".py"):
                            py_compile.compile(os.path.join(d, n), doraise=True)
            except py_compile.PyCompileError as e:
                print("saltflow: not restarting, the code does not compile: %s" % e, flush=True)
                time.sleep(3)
                continue
            print("saltflow: the code changed; restarting", flush=True)
            httpd.server_close()
            # by module, not by argv[0]: a server started with -m has cli.py there, which cannot import relatively
            os.execv(sys.executable, [sys.executable, "-m", "saltflow.cli"] + sys.argv[1:])
    threading.Thread(target=loop, daemon=True).start()


# -- the page -------------------------------------------------------------------------------------------------

def page_html(inline=None):
    """page.html with the vendored stylesheets inlined, and with `inline` (a dict) written into it for publish."""
    with open(os.path.join(HERE, "page.html"), encoding="utf-8") as f:
        html = f.read()
    for name in ("tokens", "glass", "saltflow"):
        with open(os.path.join(HERE, "vendor", name + ".css"), encoding="utf-8") as f:
            html = html.replace("__%s_CSS__" % name.upper(), f.read())
    html = html.replace("__INLINE__", json.dumps(inline, ensure_ascii=False) if inline else "null")
    return html


# -- the server -----------------------------------------------------------------------------------------------

def _icon_of(root):
    """The product's icon: look.icon in its manifest, a png, jpeg, webp or svg inside its repo; None when it names none."""
    try:
        rel = M.load(root).data.get("look", {}).get("icon")
    except Exception:
        return None
    if not rel:
        return None
    path = os.path.abspath(os.path.join(root, rel))
    if path.startswith(os.path.abspath(root) + os.sep) and path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")) and os.path.isfile(path):
        return path
    return None


PICTURE_EXT = (".svg", ".png", ".jpg", ".jpeg", ".webp")
SEEN = set()
BROKEN = set()


def make_handler(default_root, default_name=None):
    default_name = default_name or M.load(default_root).product

    def products():
        roots = registry()
        roots[default_name] = default_root
        return roots

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _seen(self, a, ok):
            """Say once per address that a device on the network reached the page, so a phone that can't is told apart from one that never arrived."""
            if a.is_loopback or a in SEEN:
                return
            SEEN.add(a)
            print("saltflow: %s %s from %s (%s)" % ("answered" if ok else "refused", self.path.split("?")[0], a,
                  (self.headers.get("User-Agent") or "")[:80]), flush=True)

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else (json.dumps(body, ensure_ascii=False) if ctype.startswith("application/json") else body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _root(self, q):
            name = q.get("product", [default_name])[0]
            roots = products()
            if name not in roots:
                raise KeyError("no product called %r; run saltflow once inside its repo (known: %s)" % (name, ", ".join(sorted(roots))))
            return roots[name]

        def _near(self):
            """Only this machine and the local network (a tablet on the same wifi); never the internet."""
            import ipaddress
            try:
                a = ipaddress.ip_address(self.client_address[0].split("%")[0])
            except ValueError:
                return False
            a = getattr(a, "ipv4_mapped", None) or a
            ok = a.is_loopback or a.is_private or a.is_link_local
            self._seen(a, ok)
            if ok:
                return True
            self._send(403, {"error": "saltFlow answers this machine and the local network only"})
            return False

        def do_GET(self):
            if not self._near():
                return
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                if u.path == "/manifest.webmanifest":
                    # Add to Home Screen on a tablet: a full-screen app, landscape first
                    return self._send(200, json.dumps({"name": "saltFlow", "short_name": "saltFlow", "start_url": "/",
                                                       "display": "standalone", "orientation": "landscape",
                                                       "background_color": "#f3f5f8", "theme_color": "#1d3754",
                                                       "icons": [{"src": "/icon.png", "sizes": "512x512", "type": "image/png"}]}),
                                      "application/manifest+json")
                if u.path in ("/icon.png", "/icon.svg"):
                    path = os.path.join(HERE, u.path[1:])
                    if not os.path.isfile(path):
                        return self._send(404, {"error": "no %s in this install of saltFlow" % u.path[1:]})
                    with open(path, "rb") as f:
                        return self._send(200, f.read(), "image/png" if u.path.endswith(".png") else "image/svg+xml")
                if u.path == "/":
                    if q.get("stage"):
                        # saltFlow's own stage: the page renders one of its components on its test fixture
                        # (saltFlow is a product too)
                        state = q.get("state", ["default"])[0]
                        fx = os.path.join(HERE, "..", "..", "flows", "fixtures", "%s.json" % state)
                        if not model.ID.match(state) or not os.path.isfile(fx):
                            return self._send(404, {"error": "no stage fixture %r" % state})
                        with open(fx, encoding="utf-8") as f:
                            return self._send(200, page_html(json.load(f)), "text/html; charset=utf-8")
                    return self._send(200, page_html(), "text/html; charset=utf-8")
                if u.path == "/api/products":
                    out = []
                    for name, r in sorted(products().items()):
                        try:
                            sm = Product(r).summary()
                            look = M.load(r).data.get("look", {})
                            out.append({"name": name, "root": r, "head": sm["head"], "flows": len(sm["flows"]),
                                        "breaks": sm["breaks"], "notes_open": sm["notes_open"], "default": name == default_name,
                                        "look": {k: look[k] for k in ("accent", "deep") if k in look}, "icon": bool(_icon_of(r))})
                        except Exception as e:
                            out.append({"name": name, "root": r, "error": str(e), "default": name == default_name})
                    return self._send(200, out)
                if u.path == "/api/icon":
                    # the product's own icon (manifest look.icon, a file in its repo) for the switcher's tile
                    path = _icon_of(self._root(q))
                    if not path:
                        return self._send(404, {"error": "this product names no icon (look.icon in flows/saltflow.json)"})
                    with open(path, "rb") as f:
                        return self._send(200, f.read(), mimetypes.guess_type(path)[0] or "application/octet-stream")
                if u.path.startswith("/live/"):
                    # the product's built dummy, served from its dist/ on this origin so the page can drive it
                    name, _, rel = unquote(u.path[len("/live/"):]).partition("/")
                    root = self._root({"product": [name]})
                    man = M.load(root)
                    dist = os.path.abspath(os.path.join(man.path(man.data.get("web", "web")), man.data.get("capture", {}).get("dist", "dist")))
                    path = os.path.abspath(os.path.join(dist, rel or "index.html"))
                    if path.startswith(dist + os.sep) and os.path.isfile(path):
                        with open(path, "rb") as f:
                            return self._send(200, f.read(), mimetypes.guess_type(path)[0] or "application/octet-stream")
                    return self._send(404, {"error": "no built dummy file %s" % rel})
                root = self._root(q)
                p = Product(root)
                if u.path == "/api/version":
                    return self._send(200, version(root))
                if u.path == "/api/product":
                    return self._send(200, p.summary())
                if u.path == "/api/today":
                    return self._send(200, p.today())
                if u.path.startswith("/api/flow/"):
                    b = p.flow_bundle(u.path[len("/api/flow/"):])
                    return self._send(200, b) if b else self._send(404, {"error": "no such flow"})
                if u.path == "/api/notes":
                    ns = p.notes()
                    if q.get("flow"):
                        ns = [n for n in ns if n.get("flow") == q["flow"][0]]
                    return self._send(200, ns)
                if u.path == "/api/coverage":
                    return self._send(200, C.coverage(root))
                if u.path.startswith("/api/live/"):
                    fid, _, step = u.path[len("/api/live/"):].partition("/")
                    web = p.man.path(p.man.data.get("web", "web"))
                    dist = os.path.join(web, p.man.data.get("capture", {}).get("dist", "dist"))
                    out = live_path(p, fid, step)
                    live_url = p.man.data.get("live") or p.man.data.get("capture", {}).get("live")
                    out["has_dummy"] = bool(live_url) or os.path.isfile(os.path.join(dist, "index.html"))
                    base = "/live/%s/" % quote(q.get("product", [default_name])[0])
                    # "live" in the manifest's capture block: an address on this server ("/#product"), or a page in
                    # the dummy's dist ("index.html?bare=1") that drops its harness and device frame
                    out["url"] = (live_url if live_url.startswith("/") else base + live_url) if live_url else base + "index.html"
                    out["viewport"] = p.man.data.get("capture", {}).get("viewport", [1240, 940])
                    cap = p.man.data.get("capture", {})
                    flow = p.flow(fid)
                    out["pane"], out["root"] = cap.get("pane", "[role=dialog]"), cap.get("root")
                    out["place"] = flow["steps"][step].get("place")
                    out["css"] = p.surfaces().get(flow["steps"][step].get("surface"), {}).get("css")
                    st = stage_url(p.man, flow, step, p.surfaces())
                    if st:                               # the component itself, in its state: nothing to drive
                        out.update(url=st if st.startswith("/") else base + st, steps=[step], actions=[[]], stop=None, run=None, stage=True,
                                   css='[data-surface="%s"]' % flow["steps"][step]["surface"])
                    return self._send(200, out)
                if u.path == "/api/terminal":
                    return self._send(200, terminal(root, q.get("cmd", ["notes"])[0]))
                if u.path.startswith("/api/sketch/"):
                    d = os.path.abspath(os.path.join(p.man.flows_dir(), "sketches"))
                    path = os.path.abspath(os.path.join(d, unquote(u.path[len("/api/sketch/"):])))
                    if path.startswith(d + os.sep) and os.path.splitext(path)[1].lower() in PICTURE_EXT and os.path.isfile(path):
                        with open(path, "rb") as f:
                            return self._send(200, f.read(), mimetypes.guess_type(path)[0] or "image/svg+xml")
                    return self._send(404, {"error": "not sketched yet"})
                if u.path.startswith("/api/crop/"):
                    rel = u.path[len("/api/crop/"):]
                    path = os.path.join(p.man.flows_dir(), "captures", rel)
                    if os.path.isfile(path) and os.path.abspath(path).startswith(os.path.abspath(p.man.flows_dir())):
                        with open(path, "rb") as f:
                            return self._send(200, f.read(), "image/png")
                    return self._send(404, {"error": "not captured yet"})
                return self._send(404, {"error": "no such path"})
            except KeyError as e:
                return self._send(404, {"error": str(e).strip("'")})
            except Exception as e:                       # the page shows the sentence; the server never dies
                return self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})

        def do_POST(self):
            if not self._near():
                return
            u = urlparse(self.path)
            q = parse_qs(u.query)
            try:
                root = self._root(q)
                p = Product(root)
                body = self._body()
                if u.path == "/api/notes":
                    return self._send(201, p.add_note(body))
                if u.path.startswith("/api/notes/"):
                    return self._send(200, p.update_note(u.path[len("/api/notes/"):], body))
                if u.path == "/api/walk":
                    res = W.walk(root)
                    named = [r for r in res["runs"] if "expect" in r]
                    return self._send(200, {"runs": len(res["runs"]), "named": len(named),
                                            "disagree": sum(1 for r in named if not r["agrees"]),
                                            "new_notes": len(res["added"]), "closed": len(res.get("closed", [])),
                                            "flows": len({r.get("flow") for r in res["runs"]}),
                                            "broken": sum(1 for r in named if model.run_verdict(r) == "break"),
                                            "unbuilt": sum(1 for r in named if model.run_verdict(r) == "work"), "seconds": res["seconds"], "commit": res["commit"]})
                return self._send(404, {"error": "no such path"})
            except (ValueError, KeyError) as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                return self._send(500, {"error": "%s: %s" % (type(e).__name__, e)})

    return Handler


def lan_urls(port):
    """How another device on the same network reaches this machine: its Bonjour name (macOS), then its address."""
    import socket
    import sys
    out = []
    try:
        host = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True).stdout.strip() \
            if sys.platform == "darwin" else ""
        if host:
            out.append("http://%s.local:%d/" % (host, port))
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))                     # no packet is sent; it only picks the outward address
        out.append("http://%s:%d/" % (s.getsockname()[0], port))
        s.close()
    except OSError:
        pass
    return out


LAN_WARNING = ("saltflow: --lan has no password: anyone on this network can read the flows, write notes and run the "
               "commands the manifest declares")


def serve(root, port=PORT, open_page=True, lan=False, register_it=True):
    """`register_it` lists the product in the registry (and says so the first time); the demo passes False."""
    if register_it:
        new = registered(root) is None
        name = register(root)
        if new:
            print("saltflow: listed %s in %s for the page's product switcher (SALTFLOW_HOME moves it)" % (name, registry_path()), flush=True)
    else:
        name = M.load(root).product
    httpd = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), make_handler(root, name))
    url = "http://127.0.0.1:%d/" % port
    if lan:
        print(LAN_WARNING, flush=True)
        print("saltflow: on the local network at %s (this machine and the network only)" % "  ·  ".join(lan_urls(port)), flush=True)
    _restart_on_change(httpd)
    if open_page and not os.environ.get("SALTFLOW_RESTARTED"):
        os.environ["SALTFLOW_RESTARTED"] = "1"
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return url
