"""Coverage: which of the product's jobs have a flow, in three levels.

  error        a service job on the switch list with no flow
  warning      a setup or close job on the switch list with no flow
  information  any other job with no flow

The switch list and the moments come from the product's job map; the pairs from flows/joins.json and the flow
files themselves. Nothing here blocks anything.
"""
import glob
import json
import os

from . import manifest as M
from . import model


def coverage(root):
    man = M.load(root)
    jobs = man.records("jobs") if "jobs" in man.sources else []
    switch = {j["id"] for j in man.records("graph") if j.get("switch")} if "graph" in man.sources else set()
    served = {}
    for path in glob.glob(os.path.join(man.flows_dir(), "*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("schema") == "saltflow/v1/flow":
            for j in data["jobs"]:
                served.setdefault(j["ref"].split("#")[-1], []).append(data["id"])
    rows = []
    for j in jobs:
        flows = served.get(j["id"], [])
        on_switch = j["id"] in switch
        if flows:
            level = "covered"
        elif on_switch and j.get("moment") == "service":
            level = "error"
        elif on_switch and j.get("moment") in ("setup", "close", "open"):
            level = "warning"
        else:
            level = "information"
        rows.append({"job": j["id"], "name": j.get("name", j["id"]), "moment": j.get("moment"), "switch": on_switch,
                     "flows": flows, "level": level})
    counts = {}
    for r in rows:
        counts[r["level"]] = counts.get(r["level"], 0) + 1
    return {"rows": rows, "counts": counts}


# -- the bar (docs/bar.md) -----------------------------------------------------------------------------------

def bar(root):
    """The product's level against the bar, and every measure behind it. Read from the files; judges nothing."""
    from . import model as MD
    from . import walk as W
    man = M.load(root)
    rep = MD.validate(root)
    flows = []
    d = man.flows_dir()
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("schema") == "saltflow/v1/flow":
                flows.append(data)
    surfaces = {}
    sp = man.source_path("surfaces")
    if sp and os.path.exists(sp):
        with open(sp, encoding="utf-8") as f:
            surfaces = (json.load(f) or {}).get("surfaces", {})
    patterns = {p["id"] for p in man.records("patterns")} if "patterns" in man.sources else set()
    drives = {}
    dd = os.path.join(d, "drives")
    if os.path.isdir(dd):
        for name in os.listdir(dd):
            if name.endswith(".json"):
                with open(os.path.join(dd, name), encoding="utf-8") as f:
                    drives.update((json.load(f) or {}).get("moves", {}))
    cov = coverage(root)
    runs = {}
    rp = os.path.join(d, "runs.json")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            runs = json.load(f)
    notes = W._existing_notes  # noqa: F841  (the ids helper; the merged notes come from the server's reader)
    from .server import _jsonl
    notes = _jsonl(os.path.join(d, "notes.jsonl"))

    m = {}
    m["validates"] = not rep.errors
    m["flows"] = len(flows)
    m["manifest_complete"] = bool(man.primitives) and "jobs" in man.sources and "surfaces" in man.sources
    flagged = {j["id"] for j in man.records("jobs") if j.get("first_release")} if "jobs" in man.sources else set()
    first = [r for r in cov["rows"] if (r["switch"] and r["moment"] == "service") or r["job"] in flagged]
    m["jobs_first_release"] = len(first)
    m["jobs_covered"] = sum(1 for r in first if r["flows"])
    steps = [(fl, sid, s) for fl in flows for sid, s in fl["steps"].items()]
    m["steps"] = len(steps)
    m["steps_with_surface"] = sum(1 for _, _, s in steps if ("flow" in s and "surface" not in s) or (s.get("surface") in surfaces and surfaces[s["surface"]].get("regions")))
    unbuilt = [(fl, sid, s) for fl, sid, s in steps if model.step_status(s) in ("designed", "making")]
    m["steps_unbuilt"] = len(unbuilt)
    m["steps_unbuilt_with_design"] = sum(1 for fl, sid, s in unbuilt if s.get("design") or surfaces.get(s.get("surface"), {}).get("design"))
    m["flows_with_job"] = sum(1 for fl in flows if fl.get("jobs"))
    pats = [(fl, sid, p) for fl, sid, s in steps for p in s.get("patterns", [])]
    m["patterns_on_steps"] = len(pats)
    def reasoned(fl, sid, ref):
        src, _, key = ref.partition("#")
        if src.endswith(":patterns"):
            return key in patterns
        if src.endswith(":grid"):
            return True              # the grid carries a direction with a reason for every area
        return bool(fl["steps"][sid].get("links")) or bool(fl.get("links"))
    m["patterns_with_reason"] = sum(1 for fl, sid, p in pats if reasoned(fl, sid, p))
    rul = [l for fl in flows for l in fl.get("links", []) + [l for s in fl["steps"].values() for l in s.get("links", [])] if l.get("kind") == "ruling"]
    m["rulings"] = len(rul)
    m["rulings_quoted"] = len(rul) - sum(1 for p in rep.errors if ".ref" in p.field and "quote" in p.text)
    jobs_on_flows = {(fl["id"], j["ref"]) for fl in flows for j in fl.get("jobs", [])}
    named = {(fl["id"], r["job"]) for fl in flows for r in fl.get("runs", [])}
    m["jobs_on_flows"] = len(jobs_on_flows)
    m["jobs_with_named_run"] = len(jobs_on_flows & named)
    built = [(fl, sid) for fl, sid, s in steps if model.is_made(s)]
    m["built_steps"] = len(built)
    def drivable(fl, sid):
        into = [mv for mv in fl["moves"] if mv["to"] == sid]
        if not into:
            return sid == fl["entry"]
        return all(("%s/%s" % (fl["id"], mv["id"]) in drives) or (mv["id"] in drives) for mv in into)
    m["built_steps_drivable"] = sum(1 for fl, sid in built if drivable(fl, sid))
    rs = runs.get("runs", [])
    m["runs"] = len(rs)
    m["runs_disagree"] = sum(1 for r in rs if "expect" in r and not r.get("agrees", True))
    m["runs_break"] = sum(1 for r in rs if model.run_verdict(r) == "break")
    ix = model.load_captures(d)
    built_keys = {"%s/%s" % (fl["id"], sid) for fl, sid in built}
    m["captures"] = sum(1 for k in (ix.get("steps") or {}) if k in built_keys)
    m["captures_at_head"] = sum(1 for k, v in (ix.get("steps") or {}).items() if k in built_keys and v.get("commit") == W.product_head(root))
    m["dummy_disagrees"] = len(ix.get("disagree") or [])
    m["notes_closed_with_commit"] = sum(1 for n in notes if n.get("status") == "done" and n.get("commit_done"))
    m["breaks_open"] = sum(1 for n in notes if n.get("status") == "open" and n.get("kind") == "break")

    full = lambda a, b: m[b] == 0 or m[a] >= m[b]  # noqa: E731
    levels = [
        ("Written", m["validates"] and m["flows"] > 0 and m["manifest_complete"] and full("steps_with_surface", "steps") and m["flows_with_job"] == m["flows"]),
        ("Covered", full("jobs_covered", "jobs_first_release") and full("steps_unbuilt_with_design", "steps_unbuilt")),
        ("Reasoned", full("patterns_with_reason", "patterns_on_steps") and full("rulings_quoted", "rulings") and full("jobs_with_named_run", "jobs_on_flows") and full("built_steps_drivable", "built_steps")),
        ("Seen", m["captures_at_head"] > 0 and m["captures_at_head"] >= m["built_steps"] and m["dummy_disagrees"] == 0),
        ("Closed", m["notes_closed_with_commit"] > 0),
    ]
    level, name, short = 0, "Nothing", []
    for i, (nm, ok) in enumerate(levels, 1):
        if ok and level == i - 1:
            level, name = i, nm
    nxt = levels[level][0] if level < len(levels) else None
    if nxt:
        checks = {
            "Written": [("validates", None), ("steps_with_surface", "steps"), ("flows_with_job", "flows")],
            "Covered": [("jobs_covered", "jobs_first_release"), ("steps_unbuilt_with_design", "steps_unbuilt")],
            "Reasoned": [("patterns_with_reason", "patterns_on_steps"), ("rulings_quoted", "rulings"), ("jobs_with_named_run", "jobs_on_flows"), ("built_steps_drivable", "built_steps")],
            "Seen": [("captures_at_head", "built_steps"), ("dummy_disagrees", None)],
            "Closed": [("notes_closed_with_commit", None)],
        }[nxt]
        for a, b in checks:
            if b is None:
                if (a == "validates" and not m[a]) or (a == "dummy_disagrees" and m[a]) or (a == "notes_closed_with_commit" and not m[a]):
                    short.append({"measure": a, "have": m[a]})
            elif m[b] and m[a] < m[b]:
                short.append({"measure": a, "have": m[a], "of": m[b]})
    return {"level": level, "name": name, "next": nxt, "short": short, "measures": m}
