"""Native capture: the steps of a native app, read from its own XCUITests' result bundle. saltFlow never drives it.

The product's UI tests walk the flows and, at each step a flow names, attach two things (lifetime .keepAlways):

  "saltflow <flow> <step> hierarchy"   XCTAttachment(string: app.debugDescription), the element tree as text
  "saltflow <flow> <step> screen"      the screenshot ("... screen dark" for the dark one)

The app marks each screen element accessibilityIdentifier("surface.<id>") and each control "move.<id>" (several
moves space-separated, as data-move on the web; " = <words>" after the ids gives a control whose label is data its
fixed words, as data-words does); keypad keys are "key.N", input inside a step and not moves.
`saltflow capture --xcresult <bundle>` exports the attachments with xcresulttool and writes the same
captures/native/<platform>.json (ipad, iphone...), beside the web capture's index.json: each platform keeps its own,
and a step captured on several shows a platform switch,
so the page, lint and needs read native steps as they read web ones: the moves on
screen become moves_in_code, their labels move_words, and agrees says whether the flow's surface is on screen.

macOS only: xcresulttool comes with Xcode, and sips (which turns a landscape screenshot upright) with macOS. An
export already made (a folder with its manifest.json) is read on any platform; screenshots then stay as exported.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from . import manifest as M
from . import model
from . import walk as W

# xcresulttool's suggested file names drop the slash ("pay-on-leavingreader") or swap spaces for underscores; the
# flow and the step are told apart by the flows the product has
NAME = re.compile(r"saltflow[ _](\S+?(?: \S+?)?)[ _](hierarchy|screen)(?:[ _](dark))?(?:_\d+_[0-9A-F-]+)?(?:\.\w+)?$", re.I)
WINDOW = re.compile(r"Window[^,]*, 0x[0-9a-f]+, \{\{[-\d.]+, [-\d.]+\}, \{([\d.]+), ([\d.]+)\}\}")
ATTR = r"%s: '((?:[^'\\]|\\.)*)'"


def _attr(line, name):
    m = re.search(ATTR % name, line)
    return m.group(1).replace("\\'", "'") if m else None


def parse_hierarchy(text):
    """The element subtree of app.debugDescription -> the moves on screen, their labels, the surfaces on screen."""
    moves, words, surfaces = [], {}, []
    body = text.split("Element subtree:", 1)[-1]
    for line in body.splitlines():
        if line and not line[0].isspace() and not line.startswith("→"):
            if moves or surfaces:            # the next section (Path to element, Query chain) ends the tree
                break
            continue
        ident = _attr(line, "identifier")
        if not ident:
            continue
        label = _attr(line, "label")
        ident, _, fixed = ident.partition(" = ")     # "move.tap-tile = a tile": the fixed words of a control whose label is data
        label = fixed or label
        if ident.startswith("surface."):
            surfaces.append(ident[len("surface."):])
        elif ident.startswith("move."):
            for mid in ident[len("move."):].split():
                if mid not in moves:
                    moves.append(mid)
                if label and mid not in words:
                    words[mid] = label
    return {"moves": moves, "words": words, "surfaces": surfaces}


def _size(png):
    """A png's pixel width and height, from its header."""
    with open(png, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or len(head) < 24:
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def upright(png, window):
    """A device screenshot of a landscape app comes out portrait, turned 90°. With the test's orientation set to
    .landscapeLeft (checked on a tablet), a quarter turn anticlockwise sets it upright. Needs sips (macOS); elsewhere
    the screenshot is left as it came."""
    size = _size(png)
    if not size or not window or (size[0] > size[1]) == (window[0] > window[1]):
        return False
    if not shutil.which("sips"):
        return False
    subprocess.run(["sips", "-r", "270", png], capture_output=True)
    _drop_exif(png)
    return True


def _drop_exif(png):
    """Take out the eXIf chunk and the XMP: the device writes an orientation (8) into both, which browsers honour, and
    it would turn the now-upright pixels a second time."""
    with open(png, "rb") as f:
        d = f.read()
    out, i = [d[:8]], 8
    while i + 8 <= len(d):
        n = int.from_bytes(d[i:i + 4], "big")
        kind = d[i + 4:i + 8]
        if kind != b"eXIf" and not (kind == b"iTXt" and d[i + 8:i + 25] == b"XML:com.adobe.xmp"):
            out.append(d[i:i + 12 + n])
        i += 12 + n
    with open(png, "wb") as f:
        f.write(b"".join(out))


def export(bundle, out):
    """xcresulttool's attachments export of a bundle into out; returns the manifest's entries."""
    if os.path.isfile(os.path.join(bundle, "manifest.json")):       # an export already made
        out = bundle
    else:
        if not os.path.exists(os.path.join(bundle, "Info.plist")):
            raise RuntimeError("%s is not a finished result bundle (no Info.plist)" % bundle)
        if sys.platform != "darwin" or not shutil.which("xcrun"):
            raise RuntimeError("reading a result bundle needs Xcode's xcresulttool, on macOS (%s here); export its attachments on a Mac "
                               "(xcrun xcresulttool export attachments --path <bundle> --output-path <folder>) and pass that folder" % sys.platform)
        r = subprocess.run(["xcrun", "xcresulttool", "export", "attachments", "--path", bundle, "--output-path", out],
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError("xcresulttool failed: %s" % (r.stderr or r.stdout)[-600:])
    with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
        return out, json.load(f)


def split_key(key, flows):
    """'pay-on-leaving reader' (the form to use), '.../reader', '..._reader' or '...reader' -> (flow, step)."""
    for sep in " /:_":
        if sep in key:
            f, _, st = key.partition(sep)
            if f in flows and st in flows[f]["steps"]:
                return f, st
    for f in sorted(flows, key=len, reverse=True):
        if key.startswith(f) and key[len(f):] in flows[f]["steps"]:
            return f, key[len(f):]
    f, _, st = key.replace(":", "/").replace("_", "/").partition("/")
    return f, st or "?"


def attachments(entries, flows):
    """manifest entries -> {(flow, step): {"hierarchy": file, "light": file, "dark": file, "test": id}}, last one wins."""
    found = {}
    for t in entries:
        for a in sorted(t.get("attachments", []), key=lambda a: a.get("timestamp") or 0):
            m = NAME.search(a.get("suggestedHumanReadableName") or "")
            if not m:
                continue
            e = found.setdefault(split_key(m.group(1), flows), {"test": t.get("testIdentifier")})
            e["hierarchy" if m.group(2).lower() == "hierarchy" else (m.group(3) or "light").lower()] = a["exportedFileName"]
            e["device"] = a.get("deviceName") or e.get("device")
    return found


def _read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        try:
            return json.load(f) or {}
        except ValueError:       # a broken index is rewritten whole
            return {}


def migrate(out):
    """Move native rows out of the web index (before 0.2.2) and out of native.json (0.2.2) into their platform's
    own index. Their picture files stay where they are; each row names its own."""
    moved = {}
    wip = os.path.join(out, "index.json")
    web = _read(wip)
    rows = {k: v for k, v in (web.get("steps") or {}).items() if v.get("client") == "native"}
    if rows:
        web["steps"] = {k: v for k, v in web["steps"].items() if k not in rows}
        model.write_json(wip, web, indent=1, ensure_ascii=False)
        moved.update(rows)
    nip = os.path.join(out, "native.json")
    if os.path.exists(nip):
        moved.update(_read(nip).get("steps") or {})
    by = {}
    for k, v in moved.items():
        by.setdefault(model.platform_of(dict(v, client="native")), {})[k] = dict(v, client="native")
    for plat, rows in by.items():
        p = os.path.join(out, "native", "%s.json" % plat)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        ix = _read(p) or {"schema": "saltflow/v1/captures"}
        ix.setdefault("steps", {})
        for k, v in rows.items():
            ix["steps"].setdefault(k, dict(v, platform=plat))
        model.write_json(p, ix, indent=1, ensure_ascii=False)
    if os.path.exists(nip):
        os.remove(nip)


def capture(root, bundle, log=print):
    man = M.load(root)
    from .server import Product
    flows = {f["id"]: f for f in Product(root).flows()}
    t0 = time.time()
    out = os.path.join(man.flows_dir(), "captures")
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="saltflow-xcr-")
    try:
        src, entries = export(bundle, tmp)
        found = attachments(entries, flows)
        log("%d steps attached in %s" % (len(found), os.path.basename(bundle.rstrip("/"))))
        # each platform keeps its own index (captures/native/<platform>.json), so a web capture, an iPad run and an
        # iPhone run never overwrite one another; rows an older version left elsewhere move to theirs first
        migrate(out)
        device = next((x.get("device") for x in found.values() if x.get("device")), None)
        plat = model.platform_of({"client": "native", "device": device})
        oip = os.path.join(out, "native", "%s.json" % plat)
        os.makedirs(os.path.dirname(oip), exist_ok=True)
        old = _read(oip)
        head = W.product_head(root)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        steps, disagree, errors = dict(old.get("steps") or {}), [], []
        for (fid, sid), a in sorted(found.items()):
            flow = flows.get(fid)
            if not flow or sid not in flow["steps"]:
                errors.append({"flow": fid, "run": a.get("test"), "error": "attached step %s/%s is in no flow" % (fid, sid)})
                continue
            seen, window = {"moves": None, "words": {}, "surfaces": []}, None
            if a.get("hierarchy"):
                with open(os.path.join(src, a["hierarchy"]), encoding="utf-8", errors="replace") as f:
                    text = f.read()
                seen = parse_hierarchy(text)
                w = WINDOW.search(text)
                window = (float(w.group(1)), float(w.group(2))) if w else None
            files = {}
            for sch in ("light", "dark"):
                if a.get(sch):
                    rel = "%s/%s.%s%s.png" % (fid, sid, plat, "" if sch == "light" else ".dark")
                    os.makedirs(os.path.join(out, fid), exist_ok=True)
                    shutil.copyfile(os.path.join(src, a[sch]), os.path.join(out, rel))
                    upright(os.path.join(out, rel), window)
                    files[sch] = rel
            want = flow["steps"][sid].get("surface")
            agrees = (want in seen["surfaces"]) if (want and a.get("hierarchy")) else None
            e = {"flow": fid, "step": sid, "commit": head, "at": now, "device": a.get("device") or "native",
                 "client": "native", "platform": plat, "files": files, "agrees": agrees, "aria": " ".join(seen["surfaces"]) or None,
                 "title": None, "how": "xcuitest %s" % (a.get("test") or "")}
            if seen["moves"] is not None:
                e["moves_in_code"] = seen["moves"]
            if seen["words"]:
                e["move_words"] = seen["words"]
            steps["%s/%s" % (fid, sid)] = e
            if agrees is False:
                disagree.append({"flow": fid, "step": sid, "run": a.get("test"), "aria": e["aria"], "title": None, "wanted": want})
        index = dict(old, schema="saltflow/v1/captures", at=now, commit=head, steps=steps,
                     says=old.get("says") or "Crops of the product's work-in-progress build at this commit, never the design.",
                     disagree=disagree, errors=errors, seconds=round(time.time() - t0, 1))
        index.setdefault("undriven", [])
        model.write_json(oip, index, indent=1, ensure_ascii=False)
        return {"index": index, "steps": len(found) - len(errors), "seconds": index["seconds"]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
