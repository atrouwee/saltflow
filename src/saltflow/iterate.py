"""Iterate: what the commit hook runs. A commit never starts a model; this is scripts only.

For the product's head commit it reads what changed since the last iteration, finds the surfaces whose `depends`
include a changed file and the steps and flows that use them, runs the walk, lint and coverage, captures the
touched flows if a changed file is under the web app, and appends one line to flows/iterations.jsonl: the
Iteration piece of the model. A commit that touches neither the screens nor flows/ writes one "no surface touched"
line. `saltflow hook install` writes the product's post-commit hook, which runs this detached.
"""
import json
import os
import subprocess
import sys
import time

from . import manifest as M
from . import walk as W
from . import lint as L


def _git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True).stdout.strip()


def last_iteration(path):
    last = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        last = json.loads(line)
                    except ValueError:
                        pass
    return last


def iterate(root, do_capture=True, log=print):
    man = M.load(root)
    t0 = time.time()
    head = W.product_head(root)
    ipath = os.path.join(man.flows_dir(), "iterations.jsonl")
    prev = (last_iteration(ipath) or {}).get("commit")
    base = prev if prev and _git(root, "cat-file", "-t", prev) == "commit" else head + "~1"
    changed = [f for f in _git(root, "diff", "--name-only", base, head).splitlines() if f]
    subject = _git(root, "log", "-1", "--format=%s", head)
    web = man.data.get("web", "web").rstrip("/") + "/"
    flows_dir = os.path.relpath(man.flows_dir(), root).rstrip("/") + "/"
    touched_web = [f for f in changed if f.startswith(web)]
    touched_flows = [f for f in changed if f.startswith(flows_dir) and not f.startswith(flows_dir + "captures/")
                     and not f.endswith(("runs.json", "notes.jsonl", "iterations.jsonl"))]
    rec = {"commit": head, "since": base, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "subject": subject,
           "files": len(changed), "web_files": touched_web, "flow_files": touched_flows}
    if not touched_web and not touched_flows:
        rec.update(touched="nothing", seconds=round(time.time() - t0, 2))
        with open(ipath, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    from .server import Product
    p = Product(root)
    surfaces = p.surfaces()
    hit_surfaces = sorted(sid for sid, s in surfaces.items() if set(s.get("depends", [])) & set(changed))
    steps, flows = [], set()
    for fl in p.flows():
        for sid, s in fl["steps"].items():
            if s.get("surface") in hit_surfaces or ("%s/%s.json" % (flows_dir.rstrip("/"), fl["id"])) in touched_flows:
                steps.append("%s/%s" % (fl["id"], sid))
                flows.add(fl["id"])
    rec.update(surfaces=hit_surfaces, steps=steps, flows=sorted(flows))

    res = W.walk(root)
    named = [r for r in res["runs"] if "expect" in r]
    rec["walk"] = {"runs": len(res["runs"]), "disagree": sum(1 for r in named if not r["agrees"]), "new_notes": len(res["added"])}
    rec["lint"] = len(L.lint(root))
    if do_capture and touched_web and flows:
        from . import capture as Cp
        cap_res = []
        for fid in sorted(flows):
            try:
                c = Cp.capture(root, only=fid, schemes=("light", "dark"), build=True, log=lambda t: None)
                cap_res.append({"flow": fid, "steps": len(c["index"]["steps"]), "disagree": len(c["index"]["disagree"]), "new_notes": len(c["added"])})
            except Exception as e:
                cap_res.append({"flow": fid, "error": str(e)[:300]})
        rec["capture"] = cap_res
    rec["seconds"] = round(time.time() - t0, 2)
    with open(ipath, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


HOOK = """#!/bin/sh
# saltFlow's post-commit hook (saltflow hook install). Runs iterate detached: the commit never waits, never fails.
# Output: flows/captures/iterate.log. Remove this file to uninstall.
cd "$(git rev-parse --show-toplevel)" || exit 0
mkdir -p flows/captures
nohup {python} -m saltflow.cli iterate >> flows/captures/iterate.log 2>&1 </dev/null &
exit 0
"""


PRE = """#!/bin/sh
# saltFlow's pre-commit hook (saltflow hook). A commit that touches a part without its picture is held
# (a commit waits for its pictures). Captures come after a commit and never hold one.
cd "$(git rev-parse --show-toplevel)" || exit 0
exec {python} -m saltflow.cli needs --staged
"""


def install_hook(root):
    hooks = os.path.join(_git(root, "rev-parse", "--git-path", "hooks"))
    if not os.path.isabs(hooks):
        hooks = os.path.join(root, hooks)
    os.makedirs(hooks, exist_ok=True)
    path = os.path.join(hooks, "post-commit")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            if "saltflow" not in f.read():
                raise RuntimeError("%s exists and is not saltFlow's; not touching it" % path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(HOOK.format(python=sys.executable))
    os.chmod(path, 0o755)
    pre = os.path.join(hooks, "pre-commit")
    if os.path.exists(pre):
        with open(pre, encoding="utf-8") as f:
            if "saltflow" not in f.read():
                raise RuntimeError("%s exists and is not saltFlow's; add `python3 -m saltflow.cli needs --staged` to it yourself" % pre)
    with open(pre, "w", encoding="utf-8") as f:
        f.write(PRE.format(python=sys.executable))
    os.chmod(pre, 0o755)
    return path + " and " + pre
