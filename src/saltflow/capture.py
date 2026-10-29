"""Capture: the real pane at every built step, cropped from the product's web build, and the check that it agrees.

Builds the product's web app, serves its dist/ on a spare port, and hands capture.mjs (Playwright WebKit, found as
doctor.py says) one job: every named run's path, with the drive for each move. A fresh page per path, so the
shots are independent of each other. After each drive it crops the topmost pane, or the surface's css, or the
place's box; it records the pane's aria-label and title and says whether they agree with the surface the flow
names. Crops land in flows/captures/<flow>/<step>[.dark].png (ignored by git) with an index.json beside them;
a disagreement becomes a note of kind break with origin capture.

The manifest may carry "capture": {"build": "npm run build", "dist": "dist", "viewport": [1240, 940],
"pane": "[role=dialog]", "root": ".app"}; the first four are the defaults, "root" is the app's element inside any
device frame the page draws (home crops are taken relative to it).
"""
import http.server
import json
import os
import shutil
import socket
import subprocess
import threading
import time

from . import doctor as D
from . import manifest as M
from . import model
from . import walk as W

HERE = os.path.dirname(os.path.abspath(__file__))
# where the arriving surface sits on the screen, by place (the same boxes the page draws with), in percent
BOX = {"right": (52, 4, 45, 92), "left": (3, 4, 45, 92), "top": (3, 4, 94, 60), "zoom": (20, 10, 60, 80),
       "out": (10, 8, 80, 84), "overlay": (25, 78, 50, 14), "same": (52, 4, 45, 92), "home": (72, 4, 25, 92)}


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _serve(directory, port):
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=directory, **k)  # noqa: E731
    handler_cls = type("Quiet", (http.server.SimpleHTTPRequestHandler,), {"log_message": lambda *a: None})
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), lambda *a, **k: handler_cls(*a, directory=directory, **k))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd


def build_job(man, flows, drives, surfaces, runs, out, url, viewport, pane, schemes, only=None, root=None):
    paths = []
    for flow in flows:
        if only and flow["id"] != only:
            continue
        steps = flow["steps"]
        moves = {}
        for mv in flow["moves"]:
            moves.setdefault((mv["from"], mv["to"]), mv)
        flow_setup = [a for a in flow.get("setup", []) if model.drivable(a)]
        by_id = {mv["id"]: mv for mv in flow["moves"]}
        if man.data.get("stage"):
            # every made step straight from the product's own component in its state; no drives, no runs
            from .server import stage_url
            for sid, s in steps.items():
                st = stage_url(man, flow, sid, surfaces)
                if not st:
                    continue
                surf = surfaces.get(s.get("surface"), {})
                paths.append({"flow": flow["id"], "run": "stage", "url": url.rstrip("/") + st if st.startswith("/") else url + st, "actions": [[]],
                              "steps": [{"id": sid, "surface": s.get("surface"), "aria": surf.get("aria"), "title": surf.get("title"),
                                         "css": '[data-surface="%s"]' % s["surface"], "box": [0, 0, 100, 100], "place": s.get("place"),
                                         "built": True, "client": surf.get("client"), "stage": True}]})
        for r in ([] if man.data.get("stage") else runs):     # staged: the runs' paths are not needed for pictures
            setup = [a for a in r.get("setup", flow_setup) if model.drivable(a)]   # a run may open its own start
            if r.get("flow") != flow["id"] or "expect" not in r:
                continue
            path = r["path"]
            infos, actions = [], []
            for i, sid in enumerate(path):
                s = steps[sid]
                surf = surfaces.get(s.get("surface"), {})
                box = BOX.get("home" if s.get("place") == "home" and s.get("size") != "whole" else s.get("place"), BOX["home"])
                if s.get("place") == "home" and s.get("size") == "whole":
                    box = (0, 0, 100, 100)
                infos.append({"id": sid, "surface": s.get("surface"), "aria": surf.get("aria"), "title": surf.get("title"),
                              "css": surf.get("css"), "box": list(box), "place": s.get("place"), "built": model.is_made(s),
                              "client": surf.get("client")})
                if i == 0:
                    actions.append(setup)
                else:
                    # the move the walk took, by id; older runs.json without moves fall back to the pair
                    mv = by_id.get(r["moves"][i - 1]) if r.get("moves") and len(r["moves"]) >= i else moves.get((path[i - 1], sid))
                    key = "%s/%s" % (flow["id"], mv["id"]) if mv else None
                    d = drives.get(key) if key in drives else drives.get(mv["id"]) if mv else None
                    actions.append(d if (mv and (key in drives or mv["id"] in drives)) else None if mv is None else ("missing"))
            # cut the path at the first unbuilt step or missing drive: nothing to capture beyond
            cut = len(path)
            for i in range(len(path)):
                if not infos[i]["built"] or actions[i] == "missing":
                    cut = i
                    break
            if cut == 0:
                continue
            paths.append({"flow": flow["id"], "run": r["id"], "steps": infos[:cut], "actions": [a if a != "missing" else None for a in actions[:cut]]})
        # made steps no run reaches: the shortest way through made steps with drives (model.reach)
        covered = {s["id"] for pa in paths if pa["flow"] == flow["id"] for s in pa["steps"]}
        for sid, s in steps.items():
            if sid in covered or not model.is_made(s):
                continue
            way = model.reach(flow, drives, sid)
            if not way:
                continue
            infos, actions = [], [flow_setup]
            for i, x in enumerate(way[0]):
                st = steps[x]
                surf = surfaces.get(st.get("surface"), {})
                box = (0, 0, 100, 100) if st.get("place") == "home" and st.get("size") == "whole" else BOX.get("home" if st.get("place") == "home" else st.get("place"), BOX["home"])
                infos.append({"id": x, "surface": st.get("surface"), "aria": surf.get("aria"), "title": surf.get("title"),
                              "css": surf.get("css"), "box": list(box), "place": st.get("place"), "built": True, "client": surf.get("client"),
                              "snap": x == sid, "settle": surf.get("settle")})              # a way to one step pictures that step only; the rest were pictured their own way
                if i:
                    actions.append(drives.get("%s/%s" % (flow["id"], way[1][i - 1]), drives.get(way[1][i - 1])))
            covered.update(way[0])
            paths.append({"flow": flow["id"], "run": "reach:" + sid, "steps": infos, "actions": actions})
    return {"url": url, "web": man.path(man.data.get("web", "web")), "viewport": viewport, "schemes": schemes,
            "pane": pane, "root": root, "out": out, "report": os.path.join(out, "report.json"), "paths": paths}


def capture(root, only=None, schemes=("light", "dark"), build=True, log=print, app_root=None):
    man = M.load(root)
    opts = dict({"build": "npm run build", "dist": "dist", "viewport": [1240, 940], "pane": "[role=dialog]", "root": None,
                 "device": "the build's default device"}, **man.data.get("capture", {}))
    if app_root:
        opts["root"] = app_root
    web = man.path(man.data.get("web", "web"))
    if not os.path.isdir(web):
        raise RuntimeError("no web app at %s (the manifest's \"web\")" % web)
    dist = os.path.join(web, opts["dist"])
    node = shutil.which("node")
    if not node:
        raise RuntimeError("capture needs Node.js on PATH (18 or newer, https://nodejs.org); saltflow doctor checks the rest")
    pkg, why = D.playwright(web, root)
    if not pkg:
        raise RuntimeError("capture needs the playwright package: %s. Fix: %s; then npx playwright install webkit" % (
            why, D.FIX_PLAYWRIGHT % D.cache_dir()))
    t0 = time.time()
    own_page = opts.get("serve") == "saltflow"       # saltFlow capturing itself: its page server is the product
    if own_page:
        pass
    elif build or not os.path.isdir(dist):
        log("building %s" % opts["build"])
        r = subprocess.run(opts["build"], shell=True, cwd=web, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("build failed: %s" % (r.stderr or r.stdout)[-800:])
    port = _free_port()
    if own_page:
        import http.server as HS
        from .server import make_handler
        httpd = HS.ThreadingHTTPServer(("127.0.0.1", port), make_handler(root))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    else:
        httpd = _serve(dist, port)
    try:
        from .server import Product
        p = Product(root)
        flows = p.flows()
        drives = p.drives()
        surfaces = p.surfaces()
        runs = p.runs().get("runs", [])
        if not runs and not man.data.get("stage"):
            raise RuntimeError("no runs.json: run `saltflow walk` first; capture plays the named runs' paths")
        out = os.path.join(man.flows_dir(), "captures")
        os.makedirs(out, exist_ok=True)
        live = opts.get("live") or ""
        start = "http://127.0.0.1:%d/" % port
        job = build_job(man, flows, drives, surfaces, runs, out, start, opts["viewport"], opts["pane"], list(schemes), only, opts["root"])
        # keep the previous crop of every step about to be retaken at a different commit
        old = {}
        oip = os.path.join(out, "index.json")
        if os.path.exists(oip):
            with open(oip, encoding="utf-8") as f:
                try:
                    old = (json.load(f) or {}).get("steps", {})
                except ValueError:   # a broken index is rewritten whole by this capture
                    pass
        head_now = W.product_head(root)
        prev_of = {}
        for pth in job["paths"]:
            for st in pth["steps"]:
                key = "%s/%s" % (pth["flow"], st["id"])
                o = old.get(key)
                if o and o.get("commit") != head_now and "prev" not in o:
                    files = {}
                    for sch, rel in o.get("files", {}).items():
                        src_f = os.path.join(out, rel)
                        if os.path.exists(src_f):
                            dst = rel.replace(".png", ".prev.png")
                            shutil.copyfile(src_f, os.path.join(out, dst))
                            files[sch] = dst
                    if files:
                        prev_of[key] = {"commit": o["commit"], "at": o.get("at"), "files": files}
                elif o and o.get("prev") and o.get("commit") != head_now:
                    prev_of[key] = o["prev"]
        job["touch"] = bool(opts.get("touch"))       # a touch device (a tablet): no hover, taps not clicks
        if own_page and live.startswith("/"):
            job["url"] = start.rstrip("/") + live         # the page the manifest's live names on this server
        job["playwright"] = pkg
        jpath = os.path.join(out, "job.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=1)
        log("%d paths to play in WebKit" % len(job["paths"]))
        r = subprocess.run([node, os.path.join(HERE, "capture.mjs"), jpath], cwd=web, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("capture.mjs failed: %s" % (r.stderr or r.stdout)[-1200:])
        with open(job["report"], encoding="utf-8") as f:
            report = json.load(f)
    finally:
        httpd.shutdown()
    head = W.product_head(root)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    kept = {k: v for k, v in old.items() if not any(k == "%s/%s" % (pth["flow"], st["id"]) for pth in job["paths"] for st in pth["steps"])}
    index = {"schema": "saltflow/v1/captures", "at": now, "commit": head, "device": opts["device"], "viewport": opts["viewport"],
             "says": "Crops of the product's work-in-progress build at this commit, on its default device, never the design.",
             "steps": kept, "disagree": report["disagree"],
             "undriven": report["undriven"], "errors": report["errors"], "seconds": round(time.time() - t0, 1)}
    for c in report["captured"]:
        key = "%s/%s" % (c["flow"], c["step"])
        e = index["steps"].setdefault(key, {"flow": c["flow"], "step": c["step"], "commit": head, "at": now, "device": opts["device"], "files": {}, "agrees": True})
        if key in prev_of:
            e["prev"] = prev_of[key]
        e["files"][c["scheme"]] = c["file"]
        e["aria"], e["title"], e["how"] = c["aria"], c["title"], c["how"]
        e["agrees"] = e["agrees"] and c["agrees"]
        if c.get("moves") is not None:
            e["moves_in_code"] = c["moves"]
        if c.get("chrome") is not None:
            e["moves_in_chrome"] = c["chrome"]
        if c.get("words"):
            e["move_words"] = c["words"]
    model.write_json(os.path.join(out, "index.json"), index, indent=1, ensure_ascii=False)
    # a disagreement is a break note, once
    notes = []
    seen = set()
    for d in report["disagree"]:
        key = (d["flow"], d["step"])
        if key in seen:
            continue
        seen.add(key)
        nid = W._note_id("capture", d["flow"], d["step"], str(d.get("aria")), str(d.get("wanted")))
        notes.append({"id": nid, "kind": "break", "origin": "capture", "status": "open", "at": now, "commit": head,
                      "flow": d["flow"], "step": d["step"], "run": d["run"],
                      "text": "%s: the build shows %r (%s), the flow names %s %r" % (
                          d["step"], d.get("aria") or d.get("title"), "aria" if d.get("aria") else "title", "surface", d.get("wanted"))})
    npath = os.path.join(man.flows_dir(), "notes.jsonl")
    have = W._existing_notes(npath)
    added = []
    with open(npath, "a", encoding="utf-8") as f:
        for n in notes:
            if n["id"] not in have:
                f.write(json.dumps(n, ensure_ascii=False) + "\n")
                added.append(n)
    return {"index": index, "report": report, "added": added, "paths": len(job["paths"]), "seconds": index["seconds"]}
