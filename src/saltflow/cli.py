"""`saltflow` -- the one command.

Plain argparse. Run bare inside a product repo it opens the page; everything else is a verb with a help line that
says what it does in a sentence. Run from anywhere inside the product repo: it finds flows/saltflow.json by looking
upward, or takes --repo. `init`, `doctor` and `demo` work outside a product.
"""
import argparse
import os
import sys

from . import __version__
from . import manifest as M
from .console import receipt, note, step, fail

# verb: help
VERBS = {
    "init":     "install saltFlow into this product's repo: the manifest skeleton and flows/README.md, the taxonomy a building session follows",
    "doctor":   "check what saltFlow needs on this machine (python, git, node, playwright, webkit), one line and one fix each; --fix installs playwright",
    "demo":     "open the page on the bundled example product, to see saltFlow before your own product has flows",
    "validate": "check every flow file, the manifest and the drives against the model; touch nothing",
    "walk":     "walk each flow's jobs through every combination of its world and write what each run reached",
    "needs":    "what saltFlow needs from this product's session to show it: a build, captures, sketches, the x-ray, then lines",
    "lint":     "the structural checks: no way back, money with no error move, unreachable steps, places",
    "coverage": "which of the product's jobs have a flow, and which first-release service jobs still have none",
    "bar":      "the product's level against the bar (docs/bar.md): written, covered, reasoned, seen, closed",
    "capture":  "build the product's web app, play each flow in it, and crop the pane that arrived at every step; --xcresult reads a native app's UI tests instead",
    "iterate":  "what the commit hook runs: walk, lint, coverage, capture if a screen changed, then the record",
    "hook":     "install the product repo's post-commit hook, which runs iterate in the background",
    "notes":    "list open notes, or mark one taken, done or open again, with the commit or reply that answered it",
    "ask":      "put a decision to the reviewer: a question, why it matters, and options with one recommended",
    "publish":  "write a static snapshot of the page, one HTML file for anyone without the repo",
}


def _root(a):
    root = M.find(a.repo)
    if root is None:
        fail("no product here", "saltFlow looks upward for %s; run inside a product repo or pass --repo" % M.NAME,
             "start one here with `saltflow init`, or see the example with `saltflow demo`")
    try:
        M.load(root)
    except ValueError as e:
        fail("%s is not valid JSON" % M.NAME, str(e))
    return root


def cmd_init(a):
    import json
    import shutil
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(a.repo or os.getcwd())
    flows = os.path.join(root, "flows")
    step("saltflow init  ·  %s" % root)
    if not os.path.isdir(os.path.join(flows, "drives")):
        os.makedirs(os.path.join(flows, "drives"))
        receipt("folder", "flows/ and flows/drives/ made", "good")
    mpath = os.path.join(flows, "saltflow.json")
    if os.path.exists(mpath):
        receipt("manifest", "flows/saltflow.json is already there; left as it is", "quiet")
    else:
        name = os.path.basename(root)
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump({
                "schema": "saltflow/v1/manifest", "product": name,
                "says": "The sources saltFlow reads in this repo. saltFlow writes only inside flows/.",
                "flows": "flows",
                "primitives": [],
                "sources": {
                    "jobs": {"path": "flows/jobs.json", "kind": "ids", "list": "jobs"},
                    "decisions": {"path": "decisions.md", "kind": "quotes"},
                    "surfaces": {"path": "flows/surfaces.json", "kind": "ids", "list": "surfaces"},
                },
            }, f, indent=2, ensure_ascii=False)
            f.write("\n")
        receipt("manifest", "flows/saltflow.json written for %r; fill in primitives and the sources" % name, "good")
    guide = os.path.join(flows, "README.md")
    shutil.copyfile(os.path.join(here, "flows-guide.md"), guide)
    receipt("taxonomy", "flows/README.md written (from saltFlow %s); the building session reads it" % __version__, "good")
    spath = os.path.join(flows, "surfaces.json")
    if not os.path.exists(spath):
        with open(spath, "w", encoding="utf-8") as f:
            json.dump({"schema": "saltflow/v1/surfaces", "says": "Every surface the flows point at, described once.", "surfaces": {}}, f, indent=2)
            f.write("\n")
        receipt("surfaces", "flows/surfaces.json written, empty", "good")
    gi = os.path.join(root, ".gitignore")
    have = ""
    if os.path.exists(gi):
        with open(gi, encoding="utf-8") as f:
            have = f.read()
    if "flows/captures/" not in have:
        with open(gi, "a", encoding="utf-8") as f:
            f.write(("" if have.endswith("\n") or not have else "\n") + "flows/captures/\n")
        receipt("gitignore", "flows/captures/ added to .gitignore (crops stay out of git)", "good")
    from . import server as S
    if getattr(a, "no_register", False):
        receipt("switcher", "not listed (--no-register); nothing written outside this repo", "quiet")
    else:
        try:
            name = S.register(root)
            receipt("switcher", "%s listed in %s, the one file saltFlow keeps outside a repo: the page's product switcher reads it (--no-register skips it, SALTFLOW_HOME moves it)" % (name, S.registry_path()), "good")
        except Exception as e:
            receipt("switcher", "not listed: %s" % e, "bad")
    note("tell the product's agent, in its AGENTS.md or CLAUDE.md: read flows/README.md; write the flow beside the screen;")
    note("read the open notes (saltflow notes) before a change to the screens and close them with the commit; optional: saltflow hook")
    step("next")
    receipt("1", "saltflow validate   check the manifest and the flows", "quiet")
    receipt("2", "saltflow walk       walk every flow and write the runs", "quiet")
    receipt("3", "saltflow            open the page", "quiet")
    return 0


def cmd_validate(a):
    from . import model
    root = _root(a)
    rep = model.validate(root)
    step("saltflow validate  ·  %s" % root)
    receipt("read", "%d file%s" % (len(rep.checked), "" if len(rep.checked) == 1 else "s"))
    for f in rep.checked:
        note(f)
    for p in rep.errors:
        receipt("wrong", str(p), "bad")
    for p in rep.warnings:
        receipt("warning", str(p), "accent")
    for p in rep.unchecked:
        receipt("unchecked", str(p), "quiet")
    if rep.errors:
        receipt("verdict", "%d problem%s" % (len(rep.errors), "" if len(rep.errors) == 1 else "s"), "bad")
        return 1
    receipt("verdict", "valid" + (", %d ref%s not checkable yet" % (
        len(rep.unchecked), "" if len(rep.unchecked) == 1 else "s") if rep.unchecked else ""), "good")
    return 0


def cmd_walk(a):
    from . import walk as W
    from . import model as M2
    root = _root(a)
    res = W.walk(root)
    step("saltflow walk  ·  %s  ·  %s" % (root, res["commit"]))
    flows = {}
    for r in res["runs"]:
        flows.setdefault(r["flow"], []).append(r)
    for flow, runs in flows.items():
        receipt("flow", "%s: %d runs" % (flow, len(runs)))
        for r in runs:
            if "expect" not in r:
                continue                      # the sweep is in runs.json; the named runs are what a reader checks
            verdict = M2.run_verdict(r)
            tone = "good" if r["agrees"] else "accent" if verdict == "work" else "bad"
            text = "%s → %s at %s" % (r["id"], r["outcome"], r["at"])
            if not r["agrees"]:
                text += " (expected %s%s)" % (r["expect"], "; the design gets there once it is built, so work to do, "
                                              "not a break" if verdict == "work" else "")
            if r.get("missing"):
                text += "; no step offers " + ", ".join(r["missing"])
            receipt("run", text, tone)
        sweep = [r for r in runs if "expect" not in r]
        bad = [r for r in sweep if r["outcome"] in ("stuck", "not-built")]
        if sweep:
            note("and %d other combinations of the flow's world, no run named: %d reach an end, %d do not (runs.json has each)"
                 % (len(sweep), len(sweep) - len(bad), len(bad)))
    receipt("notes", "%d break%s, %d new" % (len(res["notes"]), "" if len(res["notes"]) == 1 else "s", len(res["added"])),
            "bad" if res["added"] else "quiet")
    receipt("took", "%.3f s, no model" % res["seconds"], "quiet")
    return 0


def cmd_coverage(a):
    from . import coverage as C
    root = _root(a)
    res = C.coverage(root)
    step("saltflow coverage  ·  %s" % root)
    c = res["counts"]
    receipt("covered", "%d job%s with a flow" % (c.get("covered", 0), "" if c.get("covered", 0) == 1 else "s"), "good")
    for level, tone, what in (("error", "bad", "service jobs on the switch list with no flow"),
                              ("warning", "accent", "setup, open or close jobs on the switch list with no flow"),
                              ("information", "quiet", "other jobs with no flow")):
        rows = [r for r in res["rows"] if r["level"] == level]
        receipt(level, "%d %s" % (len(rows), what), tone)
        if level != "information":
            for r in rows:
                note("%s: %s" % (r["job"], r["name"]))
    return 0


def cmd_bar(a):
    from . import coverage as C
    root = _root(a)
    b = C.bar(root)
    step("saltflow bar  ·  %s" % root)
    receipt("level", "%d · %s" % (b["level"], b["name"]), "good" if b["level"] >= 3 else "accent")
    if b["next"]:
        receipt("next", b["next"], "quiet")
        for s_ in b["short"]:
            note("%s: %s%s" % (s_["measure"], s_["have"], " of %s" % s_["of"] if "of" in s_ else ""))
    m = b["measures"]
    note("flows %d · steps %d (%d unbuilt) · jobs %d of %d · patterns %d/%d reasoned · rulings %d/%d quoted · built %d/%d drivable · captures %d · notes closed %d" % (
        m["flows"], m["steps"], m["steps_unbuilt"], m["jobs_covered"], m["jobs_first_release"], m["patterns_with_reason"], m["patterns_on_steps"],
        m["rulings_quoted"], m["rulings"], m["built_steps_drivable"], m["built_steps"], m["captures"], m["notes_closed_with_commit"]))
    return 0


def cmd_capture(a):
    from . import capture as Cp
    root = _root(a)
    step("saltflow capture  ·  %s" % root)
    if getattr(a, "xcresult", None):
        from . import native as N
        try:
            res = N.capture(root, os.path.abspath(a.xcresult), log=lambda t: note(t))
        except RuntimeError as e:
            fail(str(e))
        ix = res["index"]
        receipt("captured", "%d native steps from the tests' result bundle in %.0f s" % (res["steps"], res["seconds"]), "good")
        for d in ix["disagree"][:12]:
            receipt("disagrees", "%s/%s: the screen shows %r, the flow names %r" % (d["flow"], d["step"], d.get("aria"), d.get("wanted")), "bad")
        for e in ix["errors"][:8]:
            receipt("error", "%s: %s" % (e["flow"], e["error"]), "bad")
        return 0
    try:
        res = Cp.capture(root, only=getattr(a, "flow", None), schemes=("light",) if getattr(a, "light", False) else ("light", "dark"),
                         build=not getattr(a, "no_build", False), log=lambda t: note(t), app_root=getattr(a, "root", None))
    except RuntimeError as e:
        fail(str(e))
    ix = res["index"]
    receipt("captured", "%d steps from %d paths, light and dark, in %.0f s" % (len(ix["steps"]), res["paths"], res["seconds"]), "good")
    for d in ix["disagree"][:12]:
        receipt("disagrees", "%s/%s: the build shows %r, the flow names %r" % (d["flow"], d["step"], d.get("aria") or d.get("title"), d.get("wanted")), "bad")
    if ix["undriven"]:
        receipt("undriven", "%d path%s stop where a move has no drive" % (len(ix["undriven"]), "" if len(ix["undriven"]) == 1 else "s"), "quiet")
    for e in ix["errors"][:8]:
        receipt("error", "%s/%s: %s" % (e["flow"], e["run"], e["error"]), "bad")
    receipt("notes", "%d new" % len(res["added"]), "bad" if res["added"] else "quiet")
    return 0


def cmd_iterate(a):
    from . import iterate as I
    root = _root(a)
    rec = I.iterate(root, do_capture=not getattr(a, "no_capture", False), log=lambda t: note(t))
    step("saltflow iterate  ·  %s  ·  %s" % (root, rec["commit"]))
    if rec.get("touched") == "nothing":
        receipt("commit", "%s: no surface touched (%d files)" % (rec["subject"], rec["files"]), "quiet")
    else:
        receipt("commit", rec["subject"])
        receipt("touched", "%d surface%s, %d step%s, %d flow%s" % (len(rec["surfaces"]), "" if len(rec["surfaces"]) == 1 else "s",
                len(rec["steps"]), "" if len(rec["steps"]) == 1 else "s", len(rec["flows"]), "" if len(rec["flows"]) == 1 else "s"))
        receipt("walk", "%d runs · %d disagree · %d new notes" % (rec["walk"]["runs"], rec["walk"]["disagree"], rec["walk"]["new_notes"]),
                "bad" if rec["walk"]["new_notes"] else "good")
        for c in rec.get("capture", []):
            receipt("capture", "%s: %s" % (c["flow"], c.get("error") or "%d steps · %d disagree · %d new notes" % (c["steps"], c["disagree"], c["new_notes"])),
                    "bad" if c.get("error") or c.get("disagree") else "good")
    receipt("took", "%s s, no model" % rec["seconds"], "quiet")
    return 0


def cmd_hook(a):
    from . import iterate as I
    root = _root(a)
    try:
        path = I.install_hook(root)
    except RuntimeError as e:
        fail(str(e))
    step("saltflow hook  ·  %s" % root)
    receipt("installed", path, "good")
    note("every commit runs `saltflow iterate` detached (log: flows/captures/iterate.log), and is held first if it touches a part without its picture (saltflow needs --staged); delete the files to uninstall")
    return 0


def cmd_lint(a):
    from . import lint as L
    root = _root(a)
    findings = L.lint(root)
    step("saltflow lint  ·  %s" % root)
    for f in findings:
        receipt(f["kind"], ("%s: " % f["flow"] if f["flow"] else "") + f["text"], "bad")
    receipt("verdict", "%d finding%s; nothing blocks" % (len(findings), "" if len(findings) == 1 else "s"),
            "bad" if findings else "good")
    return 0


def cmd_needs(a):
    from . import needs as N
    root = _root(a)
    if getattr(a, "staged", False):
        bad = N.blocking(root)
        if bad:
            step("saltflow needs --staged  ·  the commit is held: these touched parts have no picture yet")
            for b in bad:
                receipt("missing", b, "bad")
            note("make them and stage them (flows/README.md says how), then commit again; git commit --no-verify skips this")
            return 1
        return 0
    items = N.needs(root)
    step("saltflow needs  ·  %s" % root)
    by = {}
    for i in items:
        by.setdefault(i["kind"], []).append(i)
    for kind, xs in by.items():
        for i in xs[:12]:
            receipt(kind, "%s · %s" % (i["what"], i["why"]), "bad")
        if len(xs) > 12:
            receipt(kind, "and %d more" % (len(xs) - 12), "quiet")
    receipt("verdict", "nothing missing" if not items else "%d to make; flows/README.md says how" % len(items),
            "good" if not items else "bad")
    return 0


def cmd_doctor(a):
    from . import doctor as D
    step("saltflow doctor  ·  saltflow %s" % __version__)
    res = D.checks(a.repo)
    for c in res:
        tone = "good" if c["ok"] else "bad" if c["required"] else "quiet" if c["ok"] is None else "accent"
        mark = "ok  " if c["ok"] else "--  " if c["ok"] is None else "!!  " if c["required"] else "no  "
        receipt(c["name"], mark + (c["found"] if c["ok"] else "%s  ·  fix: %s" % (c["found"], c["fix"])), tone)
    missing = [c["name"] for c in res if not c["ok"] and c["name"] in ("playwright", "webkit")]
    if getattr(a, "fix", False) and missing:
        pkg = D.playwright()[0] if "playwright" not in missing else None
        what = ("WebKit for the playwright at %s" % pkg) if pkg else "playwright into %s, then its WebKit browser" % D.cache_dir()
        ok = getattr(a, "yes", False)
        if not ok:
            try:
                ok = sys.stdin.isatty() and input("  install %s (a few hundred MB)? (y/N) " % what).strip().lower() in ("y", "yes")
            except EOFError:
                ok = False
        if not ok:
            receipt("fix", "nothing installed", "quiet")
        else:
            try:
                receipt("installed", D.install_playwright(pkg, log=note), "good")
            except RuntimeError as e:
                fail("not installed", str(e))
    elif getattr(a, "fix", False):
        receipt("fix", "nothing to install", "quiet")
    if not getattr(a, "fix", False) and missing:
        note("capture only: saltflow doctor --fix installs what is missing (it asks first)")
    broken = [c["name"] for c in res if c["ok"] is False and c["required"]]
    if broken:
        note("saltFlow cannot run until %s is fixed (exit 1)" % " and ".join(broken))
    else:
        note("saltFlow runs: the page, validate, walk, lint and coverage need nothing more; a \"no\" line only stops capture")
    return 1 if broken else 0


def cmd_demo(a):
    from . import demo as Dm
    from . import walk as W
    from . import server as S
    src = Dm.example_root()
    if not src:
        fail("no example product found",
             "the demo serves examples/saltpos from a clone of saltFlow, or saltflow/example/ in a wheel built with it",
             "set SALTFLOW_EXAMPLE to a product folder to use another")
    root = Dm.prepare(src)
    W.walk(root)
    port = getattr(a, "port", None) or S.PORT
    step("saltflow demo  ·  %s" % M.load(root).product)
    receipt("example", "a copy of %s in %s; notes written on the page stay in the copy" % (src, root), "quiet")
    receipt("page", "http://127.0.0.1:%d/  ·  ctrl-c stops it" % port)
    note("your own product next: saltflow init in its repo")
    S.serve(root, port, open_page=not getattr(a, "no_open", False), register_it=False)
    return 0


def cmd_page(a):
    from . import server as S
    root = _root(a)
    port = getattr(a, "port", None) or S.PORT
    step("saltflow  ·  %s" % root)
    receipt("page", "http://127.0.0.1:%d/  ·  reads the files on every request; ctrl-c stops it" % port)
    if getattr(a, "lan", False):
        for u in S.lan_urls(port):
            receipt("network", "%s  ·  open it on a tablet; Share, Add to Home Screen makes it an app" % u, "good")
    S.serve(root, port, open_page=not getattr(a, "no_open", False), lan=getattr(a, "lan", False))
    return 0


def cmd_notes(a):
    from . import server as S
    root = _root(a)
    p = S.Product(root)
    if a.action == "list":
        notes = [n for n in p.notes() if a.all or n.get("status") in ("open", "taken")]
        step("saltflow notes  ·  %s  ·  %d" % (root, len(notes)))
        for n in notes:
            where = "/".join(x for x in (n.get("flow"), n.get("step")) if x) or "(no step)"
            receipt(n["id"], "%s · %s · %s · %s" % (n.get("status"), n["kind"], where, n.get("title") or n["text"]),
                    "bad" if n["kind"] == "break" else "accent" if n.get("status") == "open" else "quiet")
        if not notes:
            note("nothing open")
        return 0
    if a.action == "ruled":
        if not a.ruling:
            fail("notes ruled needs --ruling", "the ref of the ruling the decision became, e.g. myproduct:decisions#2026-10-12")
        body = {"ruling": a.ruling}
    elif a.action == "decide":
        body = {"status": "decided", "choice": a.choice, "words": a.words or "", "by": a.session or M.reviewer(root)}
    else:
        body = {"status": {"take": "taken", "done": "done", "open": "open", "wont": "won't do"}[a.action]}
    if a.commit:
        body["commit"] = a.commit
    if a.reply:
        body["reply"], body["session"] = a.reply, a.session or ""
    try:
        n = p.update_note(a.id, body)
    except (KeyError, ValueError) as e:
        fail(str(e).strip("'\""))
    receipt(n["id"], "%s · %s" % (n["status"], n.get("title") or n["text"]), "good")
    return 0


def cmd_ask(a):
    """A session's question for the reviewer, in the room's shape. Options are labels; the one ending in * is the
    recommendation; `label: desc` adds a line under it."""
    from . import server as S
    import re as _re
    root = _root(a)
    p = S.Product(root)
    opts = []
    for raw in a.option or []:
        rec = raw.rstrip().endswith("*")
        raw = raw.rstrip().rstrip("*").rstrip()
        raw, _, then = raw.partition(" -> ")
        label, _, desc = raw.partition(": ")
        oid = _re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "option"
        if len(oid) > 40:                                   # cut at a word, never inside one
            oid = oid[:41].rsplit("-", 1)[0]
        o = {"id": oid, "label": label.strip()}
        if desc.strip():
            o["desc"] = desc.strip()
        if then.strip():
            o["then"] = then.strip()
        if rec:
            o["rec"] = True
        opts.append(o)
    body = {"kind": "decision", "title": a.title, "text": a.question, "why": a.why, "options": opts,
            "origin": a.session or "a session", "flow": a.flow, "step": a.step, "area": a.area, "id": a.id}
    if a.touches:
        body["touches"] = a.touches
    try:
        n = p.add_note(body)
    except ValueError as e:
        fail("not asked", str(e))
    step("saltflow ask  ·  %s" % root)
    receipt(n["id"], "%s · %s" % (n["title"], "/".join(x for x in (p.man.product, n.get("flow"), n.get("step")) if x)), "good")
    note("open on the page under Waiting on you; the answer lands in flows/notes.jsonl as a later line of %s" % n["id"])
    return 0


def cmd_publish(a):
    from . import server as S
    root = _root(a)
    p = S.Product(root)
    data = {"product": p.summary(), "today": p.today(), "flows": {f["id"]: p.flow_bundle(f["id"]) for f in p.flows()}}
    out = a.out or os.path.join(p.man.flows_dir(), "saltflow-snapshot.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(S.page_html(data))
    step("saltflow publish  ·  %s" % root)
    receipt("wrote", "%s (%d KB)" % (out, os.path.getsize(out) // 1024), "good")
    note("one file; every flow, run and note inlined; crops left out until capture runs")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="saltflow", description="A review tool for products: the flow as the timeline.")
    ap.add_argument("--version", action="version", version="saltflow " + __version__)
    ap.add_argument("--repo", help="the product repo (default: the nearest folder upward with %s)" % M.NAME)
    sub = ap.add_subparsers(dest="cmd")
    ap.add_argument("--port", type=int, help="the page's port (default %d)" % 5318)
    ap.add_argument("--no-open", action="store_true", help="start the server without opening the browser")
    ap.add_argument("--lan", action="store_true", help="also answer the local network (a tablet on the same wifi), with no password; never the internet")
    for verb, help_ in VERBS.items():
        p = sub.add_parser(verb, help=help_, description=help_[0].upper() + help_[1:] + ".")
        p.add_argument("--repo", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        if verb == "notes":
            p.add_argument("action", nargs="?", default="list", choices=["list", "take", "done", "open", "wont", "decide", "ruled"],
                           help="list (default), or take / done / open / wont one note by id; decide or ruled a decision")
            p.add_argument("id", nargs="?", help="the note's id, as the list prints it")
            p.add_argument("--commit", help="the commit that answered it")
            p.add_argument("--reply", help="the answer, for a question")
            p.add_argument("--session", help="who answers")
            p.add_argument("--all", action="store_true", help="list closed notes too")
            p.add_argument("--choice", help="decide: the option's id")
            p.add_argument("--words", help="decide: the reviewer's own words")
            p.add_argument("--ruling", help="ruled: the ref of the ruling the decision became")
        if verb == "init":
            p.add_argument("--no-register", action="store_true", help="do not list the product in the page's switcher (~/.saltflow/products.json)")
        if verb == "doctor":
            p.add_argument("--fix", action="store_true", help="install playwright and WebKit into saltFlow's cache; asks first")
            p.add_argument("--yes", action="store_true", help="with --fix: do not ask")
        if verb == "demo":
            p.add_argument("--port", type=int, default=argparse.SUPPRESS, help="the page's port (default %d)" % 5318)
            p.add_argument("--no-open", action="store_true", default=argparse.SUPPRESS, help="start the server without opening the browser")
        if verb == "needs":
            p.add_argument("--staged", action="store_true", help="only what the staged commit touches; exit 1 if a picture is missing (the pre-commit hook)")
        if verb == "ask":
            p.add_argument("question", help="the question, in a sentence")
            p.add_argument("--title", required=True, help="the few words a list shows")
            p.add_argument("--why", required=True, help="what turns on it")
            p.add_argument("--option", action="append", help="an option label (repeat); end the recommended one with *; 'label: desc' adds a line; ' -> then' says what follows if it is chosen")
            p.add_argument("--flow", help="the flow it is about")
            p.add_argument("--step", help="the step it is about")
            p.add_argument("--touches", action="append", help="another decision's id this answer changes (repeat)")
            p.add_argument("--area", help="a word for grouping: release, look, data")
            p.add_argument("--session", help="who asks (the session's name)")
            p.add_argument("--id", help="keep an id the question already has elsewhere (else d-<hash>)")
        if verb == "capture":
            p.add_argument("--flow", help="one flow only")
            p.add_argument("--light", action="store_true", help="light only")
            p.add_argument("--no-build", action="store_true", help="use the dist/ that is there")
            p.add_argument("--root", help="the app's css root inside any device frame (else the manifest's capture.root)")
            p.add_argument("--xcresult", help="a native app (macOS, Xcode): read its XCUITests' result bundle instead of driving a web build")
        if verb == "iterate":
            p.add_argument("--no-capture", action="store_true", help="skip capture even when a screen changed")
        if verb == "publish":
            p.add_argument("--out", help="where to write the snapshot (default flows/saltflow-snapshot.html)")
    a = ap.parse_args(argv)
    if a.cmd == "notes" and a.action != "list" and not a.id:
        ap.error("notes %s needs a note id" % a.action)
    if a.cmd is None:
        return cmd_page(a)
    built = {"init": cmd_init, "doctor": cmd_doctor, "demo": cmd_demo, "validate": cmd_validate, "walk": cmd_walk, "coverage": cmd_coverage, "lint": cmd_lint, "needs": cmd_needs, "bar": cmd_bar, "capture": cmd_capture, "iterate": cmd_iterate, "hook": cmd_hook,
             "notes": cmd_notes, "ask": cmd_ask, "publish": cmd_publish}
    return built[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
