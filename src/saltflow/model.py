"""The model, as the validator reads it. docs/model.md says the same in words; this file is the one that runs.

A flow file is checked in three passes:
  1. its own shape: every field has the right kind of value and every word is one the model knows;
  2. its own graph: every move goes from a step to a step, every run asks for a world the flow declares;
  3. its refs out: every `<product>:<source>#<key>` names a source the manifest defines, and the key is found
     there when the source file exists. A source not written yet is reported as unchecked, never as wrong.

Every problem names the file and the field, so a session can fix it without reading this code.
"""
import glob
import json
import os
import re

from . import manifest as M

FLOW, MANIFEST, DRIVES = "saltflow/v1/flow", "saltflow/v1/manifest", "saltflow/v1/drives"
# The other files that share flows/: the registries saltFlow reads and the records it writes. A file in flows/ whose
# schema is none of these is reported, never skipped.
KNOWN = (MANIFEST, DRIVES, "saltflow/v1/surfaces", "saltflow/v1/patterns", "saltflow/v1/joins", "saltflow/v1/runs",
         "saltflow/v1/jobs", "saltflow/v1/iterations", "saltflow/v1/ledger")
# The source names a manifest may define. The code knows these names; the manifest gives each its path and kind.
SOURCE_NAMES = ("jobs", "graph", "grid", "decisions", "patterns", "surfaces", "files", "records")

# Where a surface comes from. `same` means the pane stays and its page changes (the pages inside the Pay sheet).
PLACES = ("home", "left", "right", "top", "zoom", "out", "overlay", "same")
BEHIND = ("none", "recede", "tile")             # home receding, home shrunk to a tile, nothing
SIZES = ("part", "whole")
# A step's `primitive` is one of the product's own building blocks, listed in its manifest ("primitives"); a manifest
# without the list leaves the field unchecked.
MOVE_KINDS = ("forward", "back", "loop", "error", "cancel", "system")
# What a run can end in: the job got done, the visit stays open as intended, stuck at a step, a step not built,
# a job feature that no step offers, the dummy disagrees with the file.
OUTCOMES = ("done", "kept", "stuck", "not-built", "no-step-offers", "dummy-disagrees")
ENDS = ("done", "kept")                       # what reaching an end step means: the job got done, or the visit stays open as meant
LINK_KINDS = ("evidence", "research", "ruling", "words", "measure", "pairing", "departs-from")
LINK_STATES = ("proposed", "ruled", "superseded")
SOURCE_KINDS = ("ids", "grid", "quotes", "files", "export")
DRIVE_DOES = ("click", "fill", "press", "drag", "longpress", "scan", "move")

REF = re.compile(r"^(?P<product>[A-Za-z][\w-]*):(?P<source>[a-z][\w-]*)#(?P<key>\S+)$")
ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class Problem:
    def __init__(self, file, field, text, level="error"):
        self.file, self.field, self.text, self.level = file, field, text, level

    def __str__(self):
        return f"{self.file}: {self.field}: {self.text}"


class Report:
    def __init__(self, root):
        self.root = root
        self.problems = []
        self.checked = []          # files read, relative to the product root

    def add(self, file, field, text, level="error"):
        self.problems.append(Problem(os.path.relpath(file, self.root), field, text, level))

    @property
    def errors(self):
        return [p for p in self.problems if p.level == "error"]

    @property
    def warnings(self):
        return [p for p in self.problems if p.level == "warning"]

    @property
    def unchecked(self):
        return [p for p in self.problems if p.level == "unchecked"]


# -- the sources a ref can point into -----------------------------------------------------------------------

class Sources:
    """Loads each source the manifest names once, and answers whether a key is in it."""

    def __init__(self, man):
        self.man = man
        self._cache = {}

    def lookup(self, source, key, quote=None):
        """None when found; a sentence when not; ("unchecked", why) when the source cannot be read yet."""
        spec = self.man.sources.get(source)
        if spec is None:
            return "no source called %r in the manifest (it has: %s)" % (source, ", ".join(sorted(self.man.sources)))
        path = self.man.source_path(source)
        if spec.get("kind") == "files":                   # the key is a path in the repo: findings/22-ux/money.md
            target = os.path.join(self.man.root, key.split("#")[0])
            if not os.path.exists(target):
                return "%r is not a file in the repo" % key
            if quote is None or not os.path.isfile(target) or not target.endswith(TEXT_FILES):
                return None
            if target not in self._cache:
                with open(target, encoding="utf-8", errors="replace") as f:
                    self._cache[target] = _loose(_uncomment(f.read()))
            if _loose(quote) in self._cache[target]:
                return None
            return ("warning", "the stored quote is not in %s (reworded, or quoted from somewhere else?)" % key.split("#")[0])
        if not path or not os.path.exists(path):
            return ("unchecked", "%s is not written yet" % spec.get("path", source))
        if spec.get("kind") == "export" and os.path.isdir(path):
            if source not in self._cache:
                self._cache[source] = _export_records(_export_folder(path), spec)
            return _export_lookup(self._cache[source], key, quote, spec["path"])
        data = self._load(source, spec, path)
        kind = spec.get("kind")
        if kind == "ids":
            return None if key in data else "%r is not an id in %s" % (key, spec["path"])
        if kind == "grid":
            return _grid_lookup(data, key, spec["path"])
        if kind == "quotes":
            if quote is None:
                return ("unchecked", "a ref into %s is checked by its stored quote, and this one has none" % spec["path"])
            return None if _squash(quote) in data else "the stored quote is not in %s (was it reworded?)" % spec["path"]
        if kind == "export":
            return _export_lookup(data, key, quote, spec["path"])
        return "the manifest gives %s the kind %r, which saltFlow cannot read" % (source, kind)

    def ids(self, source):
        """The id set of an ids source, read the one way."""
        spec = self.man.sources[source]
        return self._load(source, spec, self.man.source_path(source))

    def _load(self, source, spec, path):
        if source not in self._cache:
            with open(path, encoding="utf-8") as f:
                if spec["kind"] == "quotes":
                    self._cache[source] = _squash(f.read())
                else:
                    raw = json.load(f)
                    if spec["kind"] == "ids":
                        items = raw.get(spec["list"]) if spec.get("list") else raw
                        if isinstance(items, dict):          # an object keyed by id
                            self._cache[source] = set(items)
                        elif isinstance(items, list):        # a list of records with an id
                            self._cache[source] = {x.get(spec.get("id", "id")) for x in items if isinstance(x, dict)}
                        else:
                            raise ValueError("%s should hold a list of records with an id, or an object keyed by id%s" % (
                                spec["path"], " under %r" % spec["list"] if spec.get("list") else ""))
                    elif spec["kind"] == "export":
                        self._cache[source] = _export_records(raw, spec)
                    else:
                        self._cache[source] = raw
        return self._cache[source]


TEXT_FILES = (".md", ".txt", ".json", ".jsonl", ".html", ".py", ".ts", ".tsx", ".js", ".mjs", ".swift", ".css", ".yaml", ".yml")



def load_captures(flows_dir, prefer=None):
    """The captures of a product, web and native side by side. The web capture writes captures/index.json, the
    native import captures/native.json; neither touches the other. A step captured by both shows the preferred
    client's entry (the manifest's capture.prefer, else native) with the other under "alt"."""
    def read(name):
        p = os.path.join(flows_dir, "captures", name)
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as f:
            try:
                return json.load(f) or {}
            except ValueError:       # a broken index counts as no captures; capturing again rewrites it whole
                return {}
    web, nat = read("index.json"), read("native.json")
    order = ("web", "native") if prefer == "web" else ("native", "web")
    by = {"web": {}, "native": {}}
    for k, v in (web.get("steps") or {}).items():
        by[v.get("client") or "web"][k] = dict(v, client=v.get("client") or "web")   # an older import left native rows here
    for k, v in (nat.get("steps") or {}).items():
        by["native"][k] = dict(v, client="native")
    steps = {}
    for k in set(by["web"]) | set(by["native"]):
        have = [by[c][k] for c in order if k in by[c]]
        e = dict(have[0])
        if len(have) > 1:
            e["alt"] = [have[1]]
        steps[k] = e
    out = dict(web or nat)
    out["steps"] = steps
    out["disagree"] = (web.get("disagree") or []) + (nat.get("disagree") or [])
    out["errors"] = (web.get("errors") or []) + (nat.get("errors") or [])
    return out


def write_json(path, obj, **kw):
    """Write a whole file or none of it: the page reads these while a capture in another session is still writing."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, **kw)
        f.write("\n")
    os.replace(tmp, path)

def _export_records(raw, spec):
    """A JSON export of a live record store (an ops log, a decision log), as {"<collection>/<id>": squashed text}.
    The export is a file holding an object of collections, or a folder of them (_export_folder); each collection a list of records with an id (the record's fields may sit
    under "data", as some hosted databases export them) or an object keyed by id. `list` names the key holding the
    collections when they are not at the top."""
    if spec.get("list"):
        raw = raw.get(spec["list"], {})
    out = {}
    for coll, items in (raw.items() if isinstance(raw, dict) else []):
        if isinstance(items, dict):
            items = [dict(v, id=k) if isinstance(v, dict) else {"id": k, "value": v} for k, v in items.items()]
        if not isinstance(items, list):
            continue
        for rec in items:
            if isinstance(rec, dict) and rec.get("id") is not None:
                out["%s/%s" % (coll, rec["id"])] = _squash(" \n ".join(_strings(rec.get("data", rec))))
    return out


def _export_folder(path):
    """An export written as a folder: one folder per collection, one <id>.json per record (the shape some
    database tools write)."""
    raw = {}
    for coll in sorted(os.listdir(path)):
        cdir = os.path.join(path, coll)
        if not os.path.isdir(cdir):
            continue
        raw[coll] = {}
        for name in sorted(os.listdir(cdir)):
            if name.endswith(".json"):
                with open(os.path.join(cdir, name), encoding="utf-8") as f:
                    raw[coll][name[:-5]] = json.load(f)
    return raw


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from _strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from _strings(v)


def _export_lookup(records, key, quote, path):
    """`<collection>/<id>`: the record exists, and the stored quote is in one of its fields."""
    if key not in records:
        coll = key.split("/")[0]
        have = sorted({k.split("/")[0] for k in records})
        if coll not in have:
            return "%r is not a collection in %s (it has: %s)" % (coll, path, ", ".join(have))
        return "%r is not a record in %s (was it exported after the record was made?)" % (key, path)
    if quote is not None and _squash(quote) not in records[key]:
        return "the stored quote is not in %s, record %s (was it reworded?)" % (path, key)
    return None


def _squash(text):
    """Quotes are compared without line breaks, indentation or Markdown emphasis."""
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def _loose(text):
    """For quotes from any file: also without single-star emphasis, code ticks, or a line's quote marks."""
    return _squash(re.sub(r"[*`_\\]|^[ \t]*>[ \t]?", "", text, flags=re.M))


def _uncomment(text):
    """A quote from a code comment spans lines that each start with a comment mark; read it as the sentence it is."""
    return re.sub(r"(?m)^[ \t]*(#+|//+|/?\*+/?)[ \t]?", "", text)


def _grid_lookup(grid, key, path):
    """`F10`, `F10/decline-path`, or one product's cell `products/<product>/F10`."""
    areas = {f["id"]: f for f in grid.get("flows", [])}
    parts = key.split("/")
    if parts[0] == "products":
        slugs = {p["slug"] for p in grid.get("products", [])}
        if len(parts) != 3 or parts[1] not in slugs or parts[2] not in areas:
            return "%r is not a product cell in %s (products/<slug>/<area>)" % (key, path)
        return None
    area = areas.get(parts[0])
    if area is None:
        return "%r is not an area in %s (%s to %s)" % (parts[0], path, min(areas), max(areas))
    if len(parts) == 2 and parts[1] not in {p["id"] for p in area.get("patterns", [])}:
        return "%r is not a pattern of %s (%s); it has: %s" % (
            parts[1], parts[0], area.get("name"), ", ".join(p["id"] for p in area["patterns"]))
    if len(parts) > 2:
        return "%r has too many parts (<area> or <area>/<pattern>)" % key
    return None


# -- checks --------------------------------------------------------------------------------------------------

def _ref(rep, src, file, field, value, quote=None):
    if not isinstance(value, str) or not REF.match(value):
        rep.add(file, field, "%r is not a ref; a ref reads <product>:<source>#<key>" % (value,))
        return
    m = REF.match(value)
    if m["product"] != src.man.product:
        rep.add(file, field, "%r names the product %r, but this manifest is %r" % (value, m["product"], src.man.product))
        return
    why = src.lookup(m["source"], m["key"], quote)
    if isinstance(why, tuple):
        rep.add(file, field, "%s: %s" % (value, why[1]), why[0])
    elif why:
        rep.add(file, field, why)


def _one_of(rep, file, field, value, words):
    if value not in words:
        rep.add(file, field, "%r is not one of: %s" % (value, ", ".join(words)))


def _need(rep, file, where, obj, keys):
    ok = True
    for k in keys:
        if k not in obj:
            rep.add(file, "%s.%s" % (where, k) if where else k, "missing")
            ok = False
    return ok


def _world(rep, file, field, given, world, single):
    """`needs`, `sets` and a run's `world` may only use the conditions and values the flow declares."""
    if not isinstance(given, dict):
        rep.add(file, field, "should be an object of condition: value")
        return
    for k, v in given.items():
        if k not in world:
            rep.add(file, "%s.%s" % (field, k), "%r is not a condition in this flow's world (%s)" % (
                k, ", ".join(world) or "none declared"))
        elif single and v not in world[k]:
            rep.add(file, "%s.%s" % (field, k), "%r is not a value of %s (%s)" % (v, k, ", ".join(map(json.dumps, world[k]))))


def check_flow(rep, src, file, flow, surfaces, variants=None):
    if not _need(rep, file, "", flow, ("id", "name", "product", "jobs", "entry", "steps", "moves")):
        return set()
    if flow["product"] != src.man.product:
        rep.add(file, "product", "%r, but this manifest is %r" % (flow["product"], src.man.product))
    if not ID.match(str(flow["id"])):
        rep.add(file, "id", "%r should be lower-case words joined by hyphens" % flow["id"])
    elif os.path.splitext(os.path.basename(file))[0] != flow["id"]:
        rep.add(file, "id", "%r, but the file is called %s" % (flow["id"], os.path.basename(file)))

    # where the flow sits in the product's journey, and whether it is the happy path
    js = journeys_of(src.man.data)
    if "journey" in flow:
        _one_of(rep, file, "journey", flow["journey"], [j["id"] for j in js])
    mine = next((j for j in js if j["id"] == flow.get("journey")), js[0] if js else None)
    stages = [st.get("id") for st in (mine or {}).get("stages", []) if isinstance(st, dict)]
    if "stage" in flow:
        if not stages:
            rep.add(file, "stage", "the manifest names no journey; add \"journey\": [{id, name, says}] to it")
        else:
            _one_of(rep, file, "stage", flow["stage"], stages)
    elif stages:
        rep.add(file, "stage", "missing; the journey board puts this flow under Not placed yet", "warning")
    if "path" in flow:
        _one_of(rep, file, "path", flow["path"], PATHS)
    elif stages:
        rep.add(file, "path", "missing: happy, variation or edge", "warning")

    steps = flow["steps"] if isinstance(flow["steps"], dict) else {}
    world = flow.get("world", {})
    if not isinstance(world, dict) or not all(isinstance(v, list) and v for v in world.values()):
        rep.add(file, "world", "should be an object of condition: [the values the walk tries]")
        world = {}

    if not flow["jobs"]:
        rep.add(file, "jobs", "a flow serves at least one job")
    jobs = set()
    for i, j in enumerate(flow["jobs"]):
        f = "jobs[%d]" % i
        if _need(rep, file, f, j, ("ref", "ends")):
            jobs.add(j["ref"])
            _ref(rep, src, file, f + ".ref", j["ref"])
            for e in j["ends"]:
                if e not in steps:
                    rep.add(file, f + ".ends", "%r is not a step" % e)
                elif "end" not in steps[e]:
                    rep.add(file, f + ".ends", "%r is a step with no `end` (done or kept)" % e)

    for i, g in enumerate(flow.get("grid", [])):
        _ref(rep, src, file, "grid[%d]" % i, g)
    for i, link in enumerate(flow.get("links", [])):
        check_link(rep, src, file, "links[%d]" % i, link)

    for i, o in enumerate(flow.get("offers", [])):
        if not isinstance(o, dict) or not o.get("feature") or not o.get("how"):
            rep.add(file, "offers[%d]" % i, "a side effect the flow offers: {\"feature\": <job-map word>, \"how\": <where it happens>}")
    if flow["entry"] not in steps:
        rep.add(file, "entry", "%r is not a step (steps are: %s)" % (flow["entry"], ", ".join(steps)))

    for name, s in steps.items():
        f = "steps.%s" % name
        if not ID.match(name):
            rep.add(file, f, "a step name should be lower-case words joined by hyphens")
        if "flow" in s and "surface" not in s:
            # a step that is another flow: a lifecycle's "service at the shop" is the shop's own flow
            _need(rep, file, f, s, ("place",))
            _status(rep, file, f, s)
            continue
        if not _need(rep, file, f, s, ("surface", "place")):
            continue
        if surfaces is not None and s["surface"] not in surfaces:
            rep.add(file, f + ".surface", "%r is not in the surface registry (%s)" % (
                s["surface"], src.man.sources["surfaces"]["path"]))
        elif variants is not None and s.get("variant") and s["variant"] not in variants.get(s["surface"], {}):
            rep.add(file, f + ".variant", "%r is not a variant of %s in the registry (it has: %s)" % (
                s["variant"], s["surface"], ", ".join(variants.get(s["surface"], {})) or "none"))
        _one_of(rep, file, f + ".place", s["place"], PLACES)
        if "behind" in s:
            _one_of(rep, file, f + ".behind", s["behind"], BEHIND)
        if "size" in s:
            _one_of(rep, file, f + ".size", s["size"], SIZES)
        if "primitive" in s and src.man.primitives is not None:
            _one_of(rep, file, f + ".primitive", s["primitive"], src.man.primitives)
        _status(rep, file, f, s)
        if "end" in s:
            _one_of(rep, file, f + ".end", s["end"], ENDS)
        for k, p in enumerate(s.get("patterns", [])):
            _ref(rep, src, file, "%s.patterns[%d]" % (f, k), p)
        for k, link in enumerate(s.get("links", [])):
            check_link(rep, src, file, "%s.links[%d]" % (f, k), link)

    move_ids = set()
    for i, mv in enumerate(flow["moves"]):
        f = "moves[%d]" % i
        if not _need(rep, file, f, mv, ("id", "from", "to", "kind", "trigger")):
            continue
        f = "moves[%d] (%s)" % (i, mv["id"])
        if mv["id"] in move_ids:
            rep.add(file, f + ".id", "%r is used by an earlier move" % mv["id"])
        move_ids.add(mv["id"])
        for end in ("from", "to"):
            if mv[end] not in steps:
                rep.add(file, "%s.%s" % (f, end), "%r is not a step (steps are: %s)" % (mv[end], ", ".join(steps)))
        _one_of(rep, file, f + ".kind", mv["kind"], MOVE_KINDS)
        for k in ("needs", "sets"):
            if k in mv:
                _world(rep, file, "%s.%s" % (f, k), mv[k], world, True)
        if "drive" in mv:
            rep.add(file, f + ".drive", "drives live in flows/drives/<client>.json, keyed by move id, "
                                        "so the flow stays screen-agnostic")

    run_ids = set()
    for i, r in enumerate(flow.get("runs", [])):
        f = "runs[%d]" % i
        if not _need(rep, file, f, r, ("id", "job", "world", "expect")):
            continue
        f = "runs[%d] (%s)" % (i, r["id"])
        if r["id"] in run_ids:
            rep.add(file, f + ".id", "%r is used by an earlier run" % r["id"])
        run_ids.add(r["id"])
        if r["job"] not in jobs:
            rep.add(file, f + ".job", "%r is not one of this flow's jobs" % r["job"])
        _world(rep, file, f + ".world", r["world"], world, True)
        for h in r.get("hold", []):
            if h not in r["world"]:
                rep.add(file, f + ".hold", "%r is held, but the run's world does not set it" % h)
        _one_of(rep, file, f + ".expect", r["expect"], OUTCOMES)
    return move_ids


def _status(rep, file, f, s):
    """`status` (designed, making, made, ruled-out), or the older `built`; one of them, and they agree."""
    if "status" not in s and "built" not in s:
        rep.add(file, f, "missing `status` (designed, making, made or ruled-out)")
        return
    if "status" in s:
        _one_of(rep, file, f + ".status", s["status"], STATUSES)
    if "built" in s:
        if not isinstance(s["built"], bool) and s["built"] != "ruled-out":
            rep.add(file, f + ".built", "should be true, false, or \"ruled-out\"; or use `status`")
        elif "status" in s and s["status"] in STATUSES and step_status({"built": s["built"]}) != s["status"] and not (s["status"] == "making" and s["built"] is False):
            rep.add(file, f, "`status` %r and `built` %r disagree; `status` wins" % (s["status"], s["built"]), "warning")


def check_link(rep, src, file, field, link):
    if not _need(rep, file, field, link, ("kind", "ref", "quote", "state")):
        return
    _one_of(rep, file, field + ".kind", link["kind"], LINK_KINDS)
    _one_of(rep, file, field + ".state", link["state"], LINK_STATES)
    if not str(link["quote"]).strip():
        rep.add(file, field + ".quote", "empty; the quote is what still reads when the ref breaks")
    if link["kind"] in ("evidence", "research") and str(link["ref"]).startswith(("http://", "https://")):
        return                     # an outside citation is a URL, not a ref
    _ref(rep, src, file, field + ".ref", link["ref"], link["quote"])


def check_manifest(rep, man, file):
    d = man.data
    if d.get("schema") != MANIFEST:
        rep.add(file, "schema", "%r, expected %r" % (d.get("schema"), MANIFEST))
    _need(rep, file, "", d, ("product", "sources"))
    for name, spec in man.sources.items():
        f = "sources.%s" % name
        if name not in SOURCE_NAMES:
            rep.add(file, f, "%r is not a source saltFlow reads (%s)" % (name, ", ".join(SOURCE_NAMES)))
        if _need(rep, file, f, spec, ("path", "kind")):
            _one_of(rep, file, f + ".kind", spec["kind"], SOURCE_KINDS)
    if "surfaces" not in man.sources:
        rep.add(file, "sources.surfaces", "missing; every flow's steps point at the surface registry")
    stage = d.get("stage")
    if stage is not None and not (isinstance(stage, str) and "{surface}" in stage):
        rep.add(file, "stage", "a page of the build that renders one component: \"index.html?stage={surface}&state={state}\"")
    # the product's own read-only commands, run by the page for a terminal surface
    cmds = d.get("commands")
    if cmds is not None:
        if not isinstance(cmds, dict):
            rep.add(file, "commands", "should be {name: {run: [argv], env?: {}, says?: ...}}")
        else:
            for name, spec in cmds.items():
                f = "commands.%s" % name
                if not ID.match(str(name)):
                    rep.add(file, f, "a command's name is lower-case words joined by hyphens")
                if not isinstance(spec, dict) or not isinstance(spec.get("run"), list) or not spec["run"] or not all(isinstance(x, str) and x for x in spec["run"]):
                    rep.add(file, f + ".run", "the command as a list of words, never one shell string: [\"make\", \"status\"]")
                elif spec.get("env") is not None and not (isinstance(spec["env"], dict) and all(isinstance(v, str) for v in spec["env"].values())):
                    rep.add(file, f + ".env", "names to strings; {repo} stands for the product's folder")
    if man.primitives is not None and not (isinstance(man.primitives, list) and all(isinstance(x, str) for x in man.primitives)):
        rep.add(file, "primitives", "should be a list of the product's building-block words")
    journey = d.get("journey")
    if journey is not None and (not isinstance(journey, list) or not journey):
        rep.add(file, "journey", "should be the journey's stages in order: [{id, name, says}]")
    if d.get("journeys") is not None and not isinstance(d["journeys"], list):
        rep.add(file, "journeys", "should be a list of {id, name, says, stages}")
    seen = set()
    for k, j in enumerate(journeys_of(d)):
        f = "journey" if j["id"] == "journey" and journey else "journeys[%d]" % (k - (1 if journey else 0))
        if j["id"] in seen or not ID.match(str(j["id"])):
            rep.add(file, f + ".id", "%r should be a unique id of lower-case words joined by hyphens" % j["id"])
        seen.add(j["id"])
        if not j["stages"]:
            rep.add(file, f, "a journey needs its stages in order")
        for i, st in enumerate(j["stages"]):
            if _need(rep, file, "%s[%d]" % (f, i), st, ("id", "name")) and not ID.match(str(st["id"])):
                rep.add(file, "%s[%d].id" % (f, i), "%r should be lower-case words joined by hyphens" % st["id"])


def check_drives(rep, file, drives, move_ids, moves_by_id=None):
    """A drive key is `<flow>/<move>` for one flow's move, or a bare `<move>` shared by every flow whose move has that
    id and the same trigger. A value of null means no drive by nature (a system move nobody can click); [] means the
    step is already on screen."""
    if drives.get("schema") != DRIVES:
        rep.add(file, "schema", "%r, expected %r" % (drives.get("schema"), DRIVES))
    for key, actions in drives.get("moves", {}).items():
        f = "moves.%s" % key
        flow_id, _, mid = key.rpartition("/")
        if flow_id:
            if (flow_id, mid) not in {(fl, m) for fl, m in move_ids}:
                rep.add(file, f, "%r is not a move of %s" % (mid, flow_id))
        else:
            if mid not in {m for _, m in move_ids}:
                rep.add(file, f, "%r is not a move in any flow" % mid)
            elif moves_by_id and len({t for t in moves_by_id.get(mid, [])}) > 1:
                rep.add(file, f, "%r means different things in different flows (%s); key the drive per flow as <flow>/%s" % (
                    mid, "; ".join(sorted({t for t in moves_by_id[mid]})), mid), "warning")
        if actions is None:
            continue
        if not isinstance(actions, list):
            rep.add(file, f, "should be a list of actions, [] when the step is already on screen, or null when nothing can click it")
            continue
        for k, a in enumerate(actions):
            if "key" in a:
                continue
            if a.get("do") == "drag":
                by = a.get("by")
                if not (a.get("from") and (a.get("to") or (isinstance(by, list) and len(by) == 2 and all(isinstance(x, (int, float)) for x in by)))):
                    rep.add(file, "%s[%d]" % (f, k), "a drag names from, and to (css or role+name) or by: [dx, dy]; hold: true keeps the press")
                continue
            if a.get("do") == "press" and a.get("text") and not any(t in a for t in ("css", "role")):
                continue                     # a command typed into a terminal: no target on a page
            if not any(t in a for t in ("css", "role")):
                rep.add(file, "%s[%d]" % (f, k), "an action finds its target by css or by role and name, or presses a key")
            if "do" in a:
                _one_of(rep, file, "%s[%d].do" % (f, k), a["do"], DRIVE_DOES)
            else:
                rep.add(file, "%s[%d].do" % (f, k), "missing")


def _read(rep, path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except ValueError as e:
        rep.add(path, "(file)", "not valid JSON: %s" % e)
    return None


CLIENTS = ("page", "terminal", "native", "physical", "service", "outside")   # outside: another maker's thing, never built by us
SPACES = ("compact", "regular", "full")


def check_registry(rep, path, reg):
    """A surface's client (where it lives) and space (how it lays itself out for the room it is given)."""
    for sid, surf in (reg.get("surfaces") or {}).items() if isinstance(reg.get("surfaces"), dict) else []:
        if "client" in surf:
            _one_of(rep, path, "surfaces.%s.client" % sid, surf["client"], CLIENTS)
        for k in (surf.get("space") or {}):
            _one_of(rep, path, "surfaces.%s.space.%s" % (sid, k), k, SPACES)


PATHS = ("happy", "variation", "edge")

# A step's one status. The older `built` (true, false or "ruled-out") still reads: true is made, false is
# designed. `making` is begun, not yet usable. Everything that asks "is this step made?" asks is_made, nowhere else.
STATUSES = ("designed", "making", "made", "ruled-out")


def step_status(s):
    st = s.get("status")
    if st in STATUSES:
        return st
    b = s.get("built", False)
    return "made" if b is True else "ruled-out" if b == "ruled-out" else "designed"


def is_made(s):
    return step_status(s) == "made"


# A run's one verdict, decided by the walk and stored with the run; the page, the tiles and the notes only read it.
#   ok      reached what it expects (or names no expectation)
#   work    stops only at a step not made yet, on a path the design completes: work to do, not a break
#   break   anything else that misses its expectation
VERDICTS = ("ok", "work", "break")


def drivable(action):
    """An action a driver can perform: a target (css, role, a drag's ends) or a key. Anything else in a setup list
    (a product's own note to itself, e.g. which account) is skipped by capture and live, never interpreted."""
    return isinstance(action, dict) and bool(action.get("css") or action.get("role") or action.get("key")
                                             or action.get("from") or action.get("do") == "press")


def run_verdict(r):
    if r.get("verdict") in VERDICTS:
        return r["verdict"]
    if "expect" not in r or r.get("agrees", r.get("outcome") == r.get("expect")):
        return "ok"
    if r.get("outcome") == "not-built" and r.get("design") == r.get("expect"):
        return "work"
    return "break"


def journeys_of(data):
    """The manifest's journeys, in one shape: [{id, name, says, stages}]. `journey` (a list of stages) is the
    single-journey form and reads as the first; `journeys` carries several, e.g. an owner's journey and a made
    thing's own operation."""
    out = []
    if isinstance(data.get("journey"), list) and data["journey"]:
        out.append({"id": "journey", "name": "The journey", "says": "", "stages": data["journey"]})
    for j in data.get("journeys") or []:
        if isinstance(j, dict):
            out.append({"id": j.get("id"), "name": j.get("name") or j.get("id"), "says": j.get("says", ""), "stages": j.get("stages") or []})
    return out
NOTE_KINDS = ("question", "change", "bug", "story", "break", "decision")
NOTE_STATUSES = ("open", "taken", "done", "won't do", "decided")


def decision_problems(n):
    """What is wrong with a decision note's shape, as sentences; [] when it holds. A decision is a question for the
    reviewer with its options laid out, one of them recommended: one room per product, in the repo, answered on
    saltFlow's page."""
    out = []
    if not str(n.get("title") or "").strip():
        out.append("a decision needs a title: the few words a list shows")
    if not str(n.get("text") or "").strip():
        out.append("a decision needs text: the question, in a sentence")
    if not str(n.get("why") or "").strip():
        out.append("a decision needs why: what turns on it")
    opts = n.get("options")
    if not isinstance(opts, list) or len(opts) < 2:
        out.append("a decision needs two options or more")
        return out
    ids = [o.get("id") for o in opts if isinstance(o, dict)]
    if len(ids) != len(opts) or not all(isinstance(i, str) and ID.match(i) for i in ids):
        out.append("every option needs an id (lowercase words with dashes) and a label")
    elif len(set(ids)) != len(ids):
        out.append("two options share an id")
    if any(not str((o or {}).get("label") or "").strip() for o in opts if isinstance(o, dict)):
        out.append("every option needs a label")
    if sum(1 for o in opts if isinstance(o, dict) and o.get("rec")) != 1:
        out.append("exactly one option is recommended (\"rec\": true)")
    if any(not isinstance(o.get("then", ""), str) for o in opts if isinstance(o, dict)):
        out.append("an option's then is one line of words: what follows if it is chosen")
    t = n.get("touches")
    if t is not None and not (isinstance(t, list) and all(isinstance(x, str) and x for x in t)):
        out.append("touches is a list of other decisions' ids: the questions this answer changes")
    elif t and n.get("id") in t:
        out.append("a decision cannot touch itself")
    if n.get("status") == "decided" and n.get("choice") not in ids + [None, ""]:
        out.append("the choice %r is not one of the options (%s)" % (n.get("choice"), ", ".join(map(str, ids))))
    return out


def check_notes(rep, path):
    """notes.jsonl: each line JSON with an id; a note's kind and status are words the model knows; a decision holds
    its shape. Read with last-line-wins, the way every reader does."""
    merged = {}
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                n = json.loads(line)
            except ValueError:
                rep.add(path, "line %d" % i, "not JSON")
                continue
            if not isinstance(n, dict) or not n.get("id"):
                rep.add(path, "line %d" % i, "a note line needs an id")
                continue
            merged[n["id"]] = dict(merged.get(n["id"], {}), **n)
    for nid, n in merged.items():
        if n.get("kind") not in NOTE_KINDS:
            rep.add(path, nid + ".kind", "%r is not one of: %s" % (n.get("kind"), ", ".join(NOTE_KINDS)))
        if n.get("status") not in NOTE_STATUSES:
            rep.add(path, nid + ".status", "%r is not one of: %s" % (n.get("status"), ", ".join(NOTE_STATUSES)))
        if n.get("kind") == "decision":
            for why in decision_problems(n):
                rep.add(path, nid, why)
        elif n.get("status") == "decided":
            rep.add(path, nid + ".status", "only a decision is decided; a %s is done or won't do" % n.get("kind"))


def validate(root):
    """Every saltFlow file in the product repo at `root`. Returns a Report."""
    rep = Report(root)
    man = M.load(root)
    mfile = os.path.join(root, M.NAME)
    rep.checked.append(M.NAME)
    check_manifest(rep, man, mfile)
    src = Sources(man)

    surfaces, variants = None, None
    spath = man.source_path("surfaces")
    if spath and os.path.exists(spath):
        try:
            surfaces = src.ids("surfaces")
            reg = _read(rep, spath) or {}
            check_registry(rep, spath, reg)
            variants = {}
            for sid, surf in (reg.get("surfaces") or {}).items() if isinstance(reg.get("surfaces"), dict) else []:
                v = surf.get("variants") or {}
                variants[sid] = v if isinstance(v, dict) else {}
                for vid, vv in variants[sid].items():
                    if not isinstance(vv, (str, dict)):
                        rep.add(spath, "surfaces.%s.variants.%s" % (sid, vid), "a variant is a sentence, or an object with says and built")
        except (ValueError, AttributeError, TypeError) as e:
            rep.add(spath, "(file)", "cannot be read as a registry of ids: %s" % e)

    npath = os.path.join(man.flows_dir(), "notes.jsonl")
    if os.path.exists(npath):
        rep.checked.append(os.path.relpath(npath, root))
        check_notes(rep, npath)
        import subprocess
        tracked = subprocess.run(["git", "-C", root, "ls-files", "--error-unmatch", os.path.relpath(npath, root)],
                                 capture_output=True, text=True)
        if tracked.returncode and os.path.isdir(os.path.join(root, ".git")):
            rep.add(npath, "(file)", "not in git; the notes are the truth between sessions, so commit them", "warning")

    move_ids = set()            # (flow id, move id)
    triggers = {}               # move id -> the triggers it carries across flows
    _nested, _flow_ids = [], []
    fdir = man.flows_dir()
    for path in sorted(glob.glob(os.path.join(fdir, "*.json"))):
        data = _read(rep, path)
        if data is None:
            continue
        schema = data.get("schema") if isinstance(data, dict) else None
        if schema in KNOWN:
            continue                                  # the manifest, the registries, the records: not flows
        rep.checked.append(os.path.relpath(path, root))
        if schema != FLOW:
            rep.add(path, "schema", "%r; a flow starts with \"schema\": %r (the other files in flows/ carry: %s)" % (
                schema, FLOW, ", ".join(k.split("/")[-1] for k in KNOWN)))
            continue
        ids = check_flow(rep, src, path, data, surfaces, variants)
        _flow_ids.append(data.get("id"))
        if any("flow" in st for st in (data.get("steps") or {}).values() if isinstance(st, dict)):
            _nested.append((path, data))
        move_ids |= {(data["id"], m) for m in ids}
        for mv in data.get("moves", []):
            if isinstance(mv, dict) and mv.get("id"):
                triggers.setdefault(mv["id"], []).append(mv.get("trigger", ""))
        if surfaces is None:
            rep.add(path, "steps.*.surface", "not checked: the manifest's surface registry is not written yet",
                    "unchecked")

    flow_ids = {fl for fl, _ in move_ids} | set(_flow_ids)
    for path, fl in _nested:
        for sid, st in fl["steps"].items():
            if "flow" in st and st["flow"] not in flow_ids:
                rep.add(path, "steps.%s.flow" % sid, "%r is not a flow in this product (%s)" % (st["flow"], ", ".join(sorted(flow_ids))))
    for path in sorted(glob.glob(os.path.join(fdir, "drives", "*.json"))):
        data = _read(rep, path)
        if isinstance(data, dict):
            rep.checked.append(os.path.relpath(path, root))
            check_drives(rep, path, data, move_ids, triggers)
    return rep


def reach(flow, drives, target):
    """The shortest way from the entry to `target` through made steps and moves that have a drive, for a step no run
    passes (so a dialog off every walked path is still captured). Returns (path, move ids), or
    None when no such way exists. Ignores the world: the product's own dummy decides whether the way plays."""
    from collections import deque
    has = lambda mv: ("%s/%s" % (flow["id"], mv["id"])) in drives or mv["id"] in drives
    steps, start = flow["steps"], flow["entry"]
    if target == start:
        return [start], []
    q, seen = deque([(start, [start], [])]), {start}
    while q:
        at, path, mvs = q.popleft()
        for mv in flow["moves"]:
            if mv["from"] != at or mv["to"] in seen or not has(mv) or not is_made(steps.get(mv["to"], {})):
                continue
            if drives.get("%s/%s" % (flow["id"], mv["id"]), drives.get(mv["id"])) is None:
                continue                                    # null: nothing can drive it by nature
            nxt = (mv["to"], path + [mv["to"]], mvs + [mv["id"]])
            if mv["to"] == target:
                return nxt[1], nxt[2]
            seen.add(mv["to"])
            q.append(nxt)
    return None
