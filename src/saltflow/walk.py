"""The walk: every job through its flow, on the graph alone, no browser, no model.

For each flow and each job it serves, the walk tries every combination of the flow's world. From the entry step
it follows only moves whose `needs` hold, applies what a move `sets` (unless the run holds that condition fixed),
allows each move at most twice on one path, and records what it reached:

  done        an end step of the job was reached, and every step on the way is built
  kept        same, but the end step says the visit stays open as intended
  not-built   an end is reachable only through a step that is not built yet
  stuck       no end of the job is reachable; `at` names the deepest step with no way forward

A run also lists the job's features that no step in the flow offers (`missing`). A named run in the flow file is
the same walk with a name and an `expect`; the walk says whether they agree. Failed runs become notes of kind
"break" on the step where they fail, once each: a re-run never duplicates a note.
"""
import hashlib
import itertools
import json
import os
import subprocess
import time

from . import manifest as M
from . import model

LOOP_CAP = 2
STOP_KINDS = ("back", "cancel")       # a step whose only moves are these has no way forward


def product_head(root):
    try:
        return subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _load_flows(man):
    flows = []
    d = man.flows_dir()
    for name in sorted(os.listdir(d)):
        if name.endswith(".json"):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("schema") == "saltflow/v1/flow":
                flows.append(data)
    return flows


def _job_features(man):
    """job ref -> the features the job map says it needs."""
    if "jobs" not in man.sources:
        return {}
    return {"%s:jobs#%s" % (man.product, j["id"]): j.get("features", []) for j in man.records("jobs")}


def _holds(needs, world):
    return all(world.get(k) == v for k, v in needs.items())


def walk_one(flow, job, world, hold=()):
    """One job, one world. Returns the run record without its id, expect and verdict."""
    steps, moves = flow["steps"], flow["moves"]
    ends = set(job["ends"])
    by_from = {}
    for mv in moves:
        by_from.setdefault(mv["from"], []).append(mv)

    reached = []            # (end word, path, unbuilt steps on the path)
    dead_ends = []          # (step, path, forward moves taken to get there)
    seen = set()            # (step, world, moves taken): a state reached twice is walked once

    def go(step, world, path, taken, depth, mvs=()):
        state = (step, tuple(sorted((k, json.dumps(v)) for k, v in world.items())), tuple(sorted(taken.items())))
        if state in seen or len(seen) > 20000:
            return
        seen.add(state)
        unbuilt = sorted({s for s in path if not model.is_made(steps[s])}, key=path.index)   # ruled-out is never made
        if step in ends and "end" in steps[step]:
            reached.append((steps[step]["end"], path, unbuilt, list(mvs)))
            return
        forward = False
        for mv in by_from.get(step, []):
            if not _holds(mv.get("needs", {}), world):
                continue
            if any(k in hold for k in mv.get("sets", {})):
                continue                                  # a held condition cannot change
            if taken.get(mv["id"], 0) >= LOOP_CAP:
                continue
            ahead = mv["kind"] not in STOP_KINDS
            forward = forward or ahead
            nxt = dict(world, **mv.get("sets", {}))
            t = dict(taken)
            t[mv["id"]] = t.get(mv["id"], 0) + 1
            go(mv["to"], nxt, path + [mv["to"]], t, depth + (1 if ahead else 0), mvs + (mv["id"],))
        if not forward:
            dead_ends.append((step, path, depth, list(mvs)))

    go(flow["entry"], dict(world), [flow["entry"]], {}, 0)

    run = {"job": job["ref"], "world": world, "hold": list(hold)}
    built = [r for r in reached if not r[2]]
    if built:
        words = {r[0] for r in built}
        want = "done" if "done" in words else "kept"
        best = min((r for r in built if r[0] == want), key=lambda r: len(r[1]))     # the shortest way, no detours
        run.update(outcome=best[0], at=best[1][-1], path=best[1], moves=best[3])
        if len(words) > 1:
            run["also"] = sorted(words - {best[0]})
    elif reached:
        r = min(reached, key=lambda r: len(r[1]))
        run.update(outcome="not-built", at=r[2][0], path=r[1], moves=r[3],
                   why="%s is reachable only through %s, which %s" % (r[1][-1], ", ".join(r[2]),
                       "is ruled out" if all(model.step_status(steps[x]) == "ruled-out" for x in r[2]) else "is not built"))
    else:
        # The step furthest forward with no way on; going back and forth does not make a step deeper.
        s, p, _, mv = max(dead_ends, key=lambda d: (d[2], -len(d[1]))) if dead_ends else (flow["entry"], [flow["entry"]], 0, [])
        run.update(outcome="stuck", at=s, path=p, moves=mv,
                   why="from %s the only moves lead back; none of %s can be reached" % (s, ", ".join(sorted(ends))))
    return run


def walk_flow(flow, job_features):
    """Every job through every combination of the world; named runs keep their id and expect."""
    world = flow.get("world", {})
    keys = list(world)
    named = flow.get("runs", [])
    offered = set()
    for s in flow["steps"].values():
        offered.update(s.get("features", []))
    offered.update(o.get("feature") for o in flow.get("offers", []) if isinstance(o, dict))
    out = []
    for job in flow["jobs"]:
        missing = sorted(set(job_features.get(job["ref"], [])) - offered)
        for combo in itertools.product(*[world[k] for k in keys]) if keys else [()]:
            w = dict(zip(keys, combo))
            # .get: an invalid run (validate names it) must not stop the walk of the rest
            match = next((r for r in named if r.get("job") == job["ref"]
                          and all(w.get(k) == v for k, v in (r.get("world") or {}).items())), None)
            hold = match.get("hold", []) if match else []
            run = walk_one(flow, job, w, hold)
            run["flow"] = flow["id"]
            run["id"] = match["id"] if match else "%s/%s" % (job["ref"].split("#")[-1], ",".join("%s=%s" % (k, json.dumps(v)) for k, v in w.items()))
            # what the design reaches if every step were made; a step ruled out of the product stays out
            design = walk_one(dict(flow, steps={k: v if model.step_status(v) == "ruled-out" else dict(v, status="made") for k, v in flow["steps"].items()}), job, w, hold)
            run["design"] = design["outcome"]          # what the design reaches if every step were made
            if match:
                run["expect"] = match["expect"]
                if match.get("setup"):
                    run["setup"] = match["setup"]
                run["agrees"] = match["expect"] == run["outcome"]
                if match.get("why"):
                    run["asks"] = match["why"]
            if missing:
                run["missing"] = missing
            run["verdict"] = model.run_verdict(run)
            out.append(run)
    return out


def _note_id(*parts):
    return "n-" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:8]


def _existing_notes(path):
    ids = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ids.add(json.loads(line).get("id"))
                    except ValueError:
                        pass
    return ids


def break_notes(runs, head, now):
    """One note per failed named run and per job with features no step offers."""
    notes = []
    seen = set()
    for r in runs:
        named = "expect" in r
        # a step not made yet, on a path the design completes, is work to do, not a break (a
        # product is never finished); the run still reads "not built" and the bar counts it
        if named and model.run_verdict(r) == "break":
            nid = _note_id("walk", r["flow"], r["id"], r["outcome"], r["at"])
            notes.append({"id": nid, "kind": "break", "origin": "walk", "status": "open", "at": now, "commit": head,
                          "flow": r["flow"], "step": r["at"], "run": r["id"],
                          "text": "%s: expected %s, got %s at %s. %s" % (r["id"], r["expect"], r["outcome"], r["at"], r.get("why", "")),
                          "world": r["world"]})
        key = (r["flow"], r["job"])
        if r.get("missing") and key not in seen:
            seen.add(key)
            nid = _note_id("walk-missing", r["flow"], r["job"], ",".join(r["missing"]))
            notes.append({"id": nid, "kind": "break", "origin": "walk", "status": "open", "at": now, "commit": head,
                          "flow": r["flow"], "step": None, "job": r["job"],
                          "text": "no step in %s offers %s, which %s needs" % (r["flow"], ", ".join(r["missing"]), r["job"].split("#")[-1])})
    return notes


def walk(root, write=True):
    man = M.load(root)
    head = product_head(root)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    t0 = time.time()
    features = _job_features(man)
    runs = []
    for flow in _load_flows(man):
        runs.extend(walk_flow(flow, features))
    seconds = round(time.time() - t0, 3)
    notes = break_notes(runs, head, now)
    added = []
    if write:
        model.write_json(os.path.join(man.flows_dir(), "runs.json"),
                         {"schema": "saltflow/v1/runs", "at": now, "commit": head, "seconds": seconds, "runs": runs},
                         indent=1, ensure_ascii=False)
        npath = os.path.join(man.flows_dir(), "notes.jsonl")
        have = _existing_notes(npath)
        now_ids = {n["id"] for n in notes}
        stale = [n for n in _open_walk_notes(npath) if n["id"] not in now_ids]
        with open(npath, "a", encoding="utf-8") as f:
            for n in notes:
                if n["id"] not in have:
                    f.write(json.dumps(n, ensure_ascii=False) + "\n")
                    added.append(n)
            for n in stale:                      # the walk closes its own breaks once it no longer finds them
                f.write(json.dumps({"id": n["id"], "status": "done", "at": now,
                                    "reply": {"text": "the walk no longer finds this at %s" % head, "session": "walk", "at": now}},
                                   ensure_ascii=False) + "\n")
    return {"runs": runs, "notes": notes, "added": added, "closed": [n["id"] for n in stale] if write else [],
            "seconds": seconds, "commit": head}


def _open_walk_notes(path):
    merged = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    n = json.loads(line)
                except ValueError:
                    continue
                if isinstance(n, dict) and n.get("id"):
                    merged[n["id"]] = dict(merged.get(n["id"], {}), **n)
    return [n for n in merged.values() if n.get("origin") == "walk" and n.get("kind") == "break"
            and n.get("status") in ("open", "taken")]
