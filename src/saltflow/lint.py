"""The structural checks, on the graph alone. They report and never block.

  no-way-back      a step with no back or cancel move out of it, that is not an end, the entry, or on home, and
                   that does not say how it is left by nature ("leave": "tap another row")
  no-error-move    a step of a primitive the product names in "lint": {"needs_error_move": [...]} where something
                   happens by itself (a system move out) but nothing is designed for it going wrong (no error move out)
  unreachable      a step no move leads to and that is not the entry
  place-differs    a sheet's declared place is not where the product's code puts that sheet kind
  no-reason        a pattern of the product's own (stance diverge or new) with no reason or no link
  code-differs     a staged component offers a control (data-move) the flow has no move for, or the flow has a
                   move out of the step the component has no control for (read from the last capture; a native step
                   reads accessibilityIdentifier "move.<id>" from its UI test instead)
  trigger-words    a move's trigger does not carry the words its control shows in the code (not for a move that happens
                   by itself, an error or system move, whose control is a stand-in)

The place check reads where the product's own code puts each sheet kind, so the map is never typed twice. The
manifest's "places" names the file and the default place, and may name the two patterns that read it:
"map", a regex whose first group is the map's body (default: a `const PLACE = { ... }` object), and "pair", a
regex with two groups, kind then place (default: `kind: 'place'`). With no "places" the check is off.
"""
import json
import os
import re

from . import manifest as M

STOP_KINDS = ("back", "cancel")
MAP = r"const PLACE[^=]*=\s*\{([^}]*)\}"        # the map's body
PAIR = r"(\w+):\s*'(\w+)'"                       # kind: 'place'


def _flows(man):
    out = []
    d = man.flows_dir()
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("schema") == "saltflow/v1/flow":
                out.append(data)
    return out


def code_places(man):
    """sheet kind -> place, read from the code; None when the manifest names no places file."""
    spec = man.data.get("places")
    if not spec:
        return None
    path = man.path(spec["file"])
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(spec.get("map") or MAP, src)
    if not m:
        return None
    places = dict(re.findall(spec.get("pair") or PAIR, m.group(1)))
    places["*"] = spec.get("default", "zoom")
    return places


def _norm(s):
    return " ".join(re.sub(r"[^\w€]+", " ", s.lower()).split())


def lint(root):
    man = M.load(root)
    findings = []

    def add(kind, flow, where, text):
        findings.append({"kind": kind, "flow": flow, "at": where, "text": text})

    surfaces = {}
    spath = man.source_path("surfaces")
    if spath and os.path.exists(spath):
        with open(spath, encoding="utf-8") as f:
            surfaces = json.load(f).get("surfaces", {})
    places = code_places(man)
    lint_cfg = man.data.get("lint")
    needs_error = set((lint_cfg or {}).get("needs_error_move", []))

    cpath = os.path.join(man.flows_dir(), "captures", "index.json")
    caps = {}
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            try:
                caps = (json.load(f) or {}).get("steps") or {}
            except ValueError:       # a broken index counts as no captures; capturing again rewrites it whole
                pass
    all_flows = _flows(man)
    by_surface = {}                  # a component's controls serve every flow that uses it
    for fl in all_flows:
        for mv in fl["moves"]:
            sf = fl["steps"].get(mv["from"], {}).get("surface")
            if sf:
                by_surface.setdefault(sf, set()).add(mv["id"])
    every_move = {mv["id"] for fl in all_flows for mv in fl["moves"]}
    nulls = set()                    # a drive set null: nothing can make the move by nature, so no control is owed
    ddir = os.path.join(man.flows_dir(), "drives")
    if os.path.isdir(ddir):
        for name in os.listdir(ddir):
            if name.endswith(".json"):
                with open(os.path.join(ddir, name), encoding="utf-8") as f:
                    for k, v in ((json.load(f) or {}).get("moves") or {}).items():
                        # null by nature, or typed into a terminal (a press with words and no target): no control owed
                        if v is None or (isinstance(v, list) and v and all(a.get("do") == "press" and a.get("text") and not (a.get("css") or a.get("role")) for a in v if isinstance(a, dict))):
                            nulls.add(k)
    for flow in all_flows:
        fid, steps, moves = flow["id"], flow["steps"], flow["moves"]
        for sid in steps:
            cap = caps.get("%s/%s" % (fid, sid)) or {}
            code = cap.get("moves_in_code")
            if code is None:
                continue
            chrome = set(cap.get("moves_in_chrome") or [])        # the page's own strip or tab bar, outside the component
            if surfaces.get(steps[sid].get("surface"), {}).get("client") == "terminal":
                continue                     # a terminal step's moves are typed, not tapped
            typed = lambda m: surfaces.get(steps.get(m["to"], {}).get("surface"), {}).get("client") == "terminal"
            # a system or error move is made by the world (a timer, a wrong PIN, a refusal): no control is owed for it
            drawn = {m["id"] for m in moves if m["from"] == sid and m.get("kind") not in ("system", "error") and not typed(m)
                     and m["id"] not in nulls and "%s/%s" % (fid, m["id"]) not in nulls}
            for m in sorted(drawn - set(code) - chrome):
                mark = ('accessibilityIdentifier "move.%s"' if cap.get("client") == "native" else 'data-move="%s"') % m
                add("code-differs", fid, sid, "%s: the flow has the move %s, and nothing on screen is marked %s" % (sid, m, mark))
            said = cap.get("move_words") or {}
            for mv in moves:
                w = said.get(mv["id"])
                # an error or a system move happens by itself: a control for it (a practice "Simulate tap") stands in, and owes no words
                if mv["from"] == sid and w and mv.get("kind") not in ("error", "system") and _norm(w) not in _norm(mv.get("trigger", "")):
                    add("trigger-words", fid, sid, "%s: the control for %s says \"%s\"; the flow's trigger says \"%s\"" % (sid, mv["id"], w, mv.get("trigger", "")))
            # a control whose move no flow has at all: the code does something the flows never drew (a control for a
            # move drawn from a neighbouring surface, like the menu beside the tab card, is not a disagreement)
            for m in sorted(set(code) - every_move):
                add("code-differs", fid, sid, "%s: the component offers %s, and no flow has that move" % (sid, m))
        out, into = {}, {}
        for mv in moves:
            out.setdefault(mv["from"], []).append(mv)
            into.setdefault(mv["to"], []).append(mv)
        for name, s in steps.items():
            kinds = {m["kind"] for m in out.get(name, [])}
            if name != flow["entry"] and name not in into:
                add("unreachable", fid, name, "no move leads to %s" % name)
            if ("end" not in s and name != flow["entry"] and s.get("place") != "home" and not s.get("oneway")
                    and not s.get("leave")
                    and not kinds & set(STOP_KINDS)):           # the entry is where the person came from
                add("no-way-back", fid, name, "%s has no back or cancel move out of it" % name)
            if s.get("primitive") in needs_error and "system" in kinds and "error" not in kinds:
                add("no-error-move", fid, name, "something happens by itself at %s (a system move) but nothing is designed for it failing" % name)
            surf = surfaces.get(s.get("surface"), {})
            if places and surf.get("sheet") and s.get("place") != "same":
                coded = places.get(surf["sheet"], places["*"])
                if coded != s.get("place"):
                    add("place-differs", fid, name, "%s says the sheet arrives from %r; the code puts a %r sheet at %r" % (
                        name, s.get("place"), surf["sheet"], coded))

    ppath = man.source_path("patterns")
    if ppath and os.path.exists(ppath):
        with open(ppath, encoding="utf-8") as f:
            for p in json.load(f).get("patterns", []):
                if p.get("stance") in ("diverge", "new") and not (p.get("reason") and p.get("links")):
                    add("no-reason", None, p["id"], "%s departs from the field with no reason or no link" % p["id"])
    return findings
