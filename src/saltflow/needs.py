"""What saltFlow needs from the product's session to show the product, by where each surface lives. Reports, never
blocks: the session editing the product is taught by the install to produce the assets saltFlow shows.
flows/README.md says how to make each one.

  a screen (page, native)   the product's own build to open live, and a capture of every made step
  a terminal                a read-only `command` saltFlow can run, or a sketch of what it prints
  a physical part           a sketch, and its place in the x-ray (flows/sketches/xray.svg, data-surface)
  a service or an outside   a sketch: the wireframe of what the person meets
  every open decision       a `then` on each option
  the guide                 flows/README.md as saltFlow ships it today (`saltflow init` refreshes it)
"""
import os
import re

SCREEN = ("page", "native")


def _xray_surfaces(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return {s for group in re.findall(r'data-surface="([^"]*)"', text) for s in group.split()}


def needs(root):
    from . import server as S
    p = S.Product(root)
    surfaces, sk, flows = p.surfaces(), p.sketches(), p.flows()
    caps = (p.captures() or {}).get("steps") or {}
    web = p.man.path(p.man.data.get("web", "web"))
    dist = os.path.join(web, p.man.data.get("capture", {}).get("dist", "dist"))
    has_build = bool(p.man.data.get("live") or p.man.data.get("capture", {}).get("live")) or os.path.isfile(os.path.join(dist, "index.html"))
    xray = _xray_surfaces(os.path.join(p.man.flows_dir(), "sketches", "xray.svg"))
    used = {}
    for f in flows:
        for sid, st in f["steps"].items():
            if st.get("surface"):
                used.setdefault(st["surface"], []).append((f["id"], sid, st))
    out = []

    def need(kind, what, why, **at):
        out.append(dict(kind=kind, what=what, why=why, **at))

    guide = os.path.join(p.man.flows_dir(), "README.md")
    with open(os.path.join(os.path.dirname(__file__), "flows-guide.md"), encoding="utf-8") as f:
        ships = f.read()
    have = open(guide, encoding="utf-8").read() if os.path.isfile(guide) else ""
    if have != ships:
        need("guide", "the current guide", "flows/README.md is %s saltFlow's; run saltflow init to refresh it (it keeps "
             "the manifest and surfaces)" % ("missing from" if not have else "behind"))
    def sketched_(s):
        return s in sk["surfaces"] or any("%s/%s" % (fid, sid) in sk["steps"] for fid, sid, _ in used[s])

    # a screen sketched counts: a page that does not exist yet has no build to point at
    screens = [s for s in used if surfaces.get(s, {}).get("client", "page") in SCREEN and not sketched_(s)]
    if screens and not has_build:
        need("build", "a build saltFlow can open", "%d screen surface%s and no build: set \"web\" (built into dist/) or "
             "\"live\" in flows/saltflow.json, or sketch them" % (len(screens), "" if len(screens) == 1 else "s"))
    from . import model
    for s in sorted(used):
        surf = surfaces.get(s, {})
        client = surf.get("client", "page")
        sketched = s in sk["surfaces"] or any("%s/%s" % (fid, sid) in sk["steps"] for fid, sid, _ in used[s])
        if client in SCREEN:
            for fid, sid, st in used[s]:
                if has_build and model.is_made(st) and "%s/%s" % (fid, sid) not in caps:
                    if S.stage_url(p.man, next(fl for fl in flows if fl["id"] == fid), sid, surfaces):
                        need("capture", "a capture of %s/%s" % (fid, sid), "run saltflow capture: the stage renders it", surface=s, flow=fid, step=sid)
                        continue
                    stop = (S.live_path(p, fid, sid) or {}).get("stop") or ""
                    if "not built" in stop or "by nature" in stop:   # unbuilt on the way, or a drive set null on purpose
                        continue                     # reached only through a step not made yet: nothing to capture today
                    need("capture", "a capture of %s/%s" % (fid, sid), stop or "made, not captured: run saltflow capture", surface=s, flow=fid, step=sid)
        elif client == "terminal":
            if not surf.get("command") and not sketched:
                need("sketch", "a command or a sketch of %s" % (surf.get("name") or s), "a terminal with nothing to show", surface=s)
        elif client == "physical":
            if not sketched:
                need("sketch", "a sketch of %s" % (surf.get("name") or s), "a part of the made thing, drawn", surface=s)
            if xray is None:
                pass
            elif s not in xray and surf.get("xray") is not False:      # "xray": false, a whole other thing, not a part
                need("xray", "%s in the x-ray" % (surf.get("name") or s), "no data-surface group lights it", surface=s)
        else:
            if not sketched:
                need("sketch", "a sketch of %s" % (surf.get("name") or s), "what the person meets, as a wireframe", surface=s)
    if xray is None and any(surfaces.get(s, {}).get("client") == "physical" for s in used):
        need("xray", "an x-ray of the made thing", "flows/sketches/xray.svg: one drawing, each part a data-surface group")
    for n in p.notes():
        if n.get("kind") == "decision" and n.get("status") in ("open", "taken"):
            bare = [o.get("label") for o in n.get("options", []) if not o.get("then")]
            if bare:
                need("then", "what follows from %s" % ", ".join(map(str, bare)), "an option with no then", decision=n["id"], title=n.get("title"))
    return out


# ── the commit requirement: a commit waits for its pictures ──
# A commit that adds or changes a surface, a step, or a decision without its picture is refused by the pre-commit hook.
# Only what the commit touches is checked, and only what can exist before the commit: a sketch, the part's place in the
# x-ray, a `then` on each option. Captures are taken after a commit, so they never block. `git commit --no-verify`
# skips the hook, as any hook.

def _git(root, *args):
    import subprocess
    r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _json_at(root, rev, rel):
    import json
    text = _git(root, "show", "%s:%s" % (rev, rel))
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None


def blocking(root):
    """What the staged commit touches and leaves without its picture, as sentences; [] lets the commit through."""
    import json
    from . import server as S
    p = S.Product(root)
    rel_flows = os.path.relpath(p.man.flows_dir(), root).replace(os.sep, "/")
    staged = [x for x in (_git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR") or "").splitlines() if x]
    if not staged:
        return []
    src = (p.man.data.get("sources", {}).get("surfaces") or {}).get("path", rel_flows + "/surfaces.json")
    touched = set()
    if src in staged:
        old = ((_json_at(root, "HEAD", src) or {}).get("surfaces") or {})
        new = ((_json_at(root, "", src) or {}).get("surfaces") or {})
        touched |= {s for s, v in new.items() if old.get(s) != v}
    for f in staged:
        if f.startswith(rel_flows + "/") and f.endswith(".json") and f.count("/") == rel_flows.count("/") + 1:
            new = _json_at(root, "", f) or {}
            if new.get("schema") != "saltflow/v1/flow":
                continue
            old = ((_json_at(root, "HEAD", f) or {}).get("steps") or {})
            touched |= {st["surface"] for sid, st in new.get("steps", {}).items() if st.get("surface") and old.get(sid) != st}
    index = set((_git(root, "ls-files", rel_flows + "/sketches") or "").splitlines())
    sketch_has = lambda rel: "%s/sketches/%s" % (rel_flows, rel) in index
    xray_text = _git(root, "show", ":%s/sketches/xray.svg" % rel_flows)
    xray = {s for g in re.findall(r'data-surface="([^"]*)"', xray_text or "") for s in g.split()} if xray_text else None
    surfaces = p.surfaces()
    web = p.man.path(p.man.data.get("web", "web"))
    dist = os.path.join(web, p.man.data.get("capture", {}).get("dist", "dist"))
    has_build = bool(p.man.data.get("live") or p.man.data.get("capture", {}).get("live")) or os.path.isfile(os.path.join(dist, "index.html"))
    out = []
    for s in sorted(touched):
        surf = surfaces.get(s, {})
        client, name = surf.get("client", "page"), surf.get("name") or s
        drawn = sketch_has(s + ".svg")
        if client in SCREEN:
            if not has_build and not drawn:
                out.append("%s is a screen with no build to open: sketch it at flows/sketches/%s.svg" % (name, s))
        elif client == "terminal":
            if not surf.get("command") and not drawn:
                out.append("%s is a terminal: give it a read-only \"command\", or sketch it at flows/sketches/%s.svg" % (name, s))
        elif client == "physical":
            if not drawn:
                out.append("%s is a physical part: sketch it at flows/sketches/%s.svg" % (name, s))
            if surf.get("xray") is not False:
                if xray is None:
                    out.append("%s is a physical part and there is no x-ray yet: flows/sketches/xray.svg" % name)
                elif s not in xray:
                    out.append("%s has no place in the x-ray: add data-surface=\"%s\" to its group" % (name, s))
        elif not drawn:
            out.append("%s: sketch what the person meets at flows/sketches/%s.svg" % (name, s))
    notes_rel = rel_flows + "/notes.jsonl"
    if notes_rel in staged:
        added = [l[1:] for l in (_git(root, "diff", "--cached", "-U0", "--", notes_rel) or "").splitlines() if l.startswith("+") and not l.startswith("+++")]
        ids = set()
        for line in added:
            try:
                n = json.loads(line)
            except ValueError:
                continue
            if isinstance(n, dict) and (n.get("kind") == "decision" or "options" in n):
                ids.add(n.get("id"))
        for n in p.notes():
            if n.get("id") in ids and n.get("kind") == "decision" and n.get("status") in ("open", "taken"):
                bare = [o.get("label") for o in n.get("options", []) if not o.get("then")]
                if bare:
                    out.append("decision %s (%s): say what follows from %s, as \"then\"" % (n["id"], n.get("title"), ", ".join(map(str, bare))))
    return out
