"""What saltFlow needs on this machine, and where it finds it.

Only Python is required. Node, the playwright package and its WebKit browser are for `saltflow capture` alone; git
for the walk's commit stamps and the hook; Xcode's xcresulttool and sips (macOS) for native capture alone.

Playwright is looked for in this order, and never in another product's repo:

  1. SALTFLOW_PLAYWRIGHT     a path to the playwright package
  2. the product's web app   its node_modules, from the web folder up to the repo root
  3. saltFlow's own cache    ~/.cache/saltflow/node_modules (`saltflow doctor --fix` installs it there)
  4. a global install        NODE_PATH, then `npm root -g`
"""
import os
import shutil
import subprocess
import sys

from . import manifest as M

FIX_PLAYWRIGHT = "saltflow doctor --fix (installs playwright into %s), or npm install playwright in the product's web app"


def cache_dir():
    """saltFlow's own folder for the node packages it needs: SALTFLOW_CACHE, else XDG_CACHE_HOME/saltflow, else ~/.cache/saltflow."""
    if os.environ.get("SALTFLOW_CACHE"):
        return os.environ["SALTFLOW_CACHE"]
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "saltflow")


def _pkg(d, loose=False):
    """d/playwright when d is a node_modules folder that has it, or d itself when d is the package (`loose`: any
    folder with a package.json and an index.js, for a path someone names by hand)."""
    c = os.path.join(d, "playwright")
    if os.path.isfile(os.path.join(c, "package.json")):
        return os.path.abspath(c)
    named = os.path.basename(os.path.normpath(d)) == "playwright"
    if os.path.isfile(os.path.join(d, "package.json")) and (named or (loose and os.path.isfile(os.path.join(d, "index.js")))):
        return os.path.abspath(d)
    return None


def _npm_root_g():
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        out = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def playwright(web=None, root=None):
    """(the package's folder, where it was found) or (None, why not)."""
    env = os.environ.get("SALTFLOW_PLAYWRIGHT")
    if env:
        p = _pkg(os.path.expanduser(env), loose=True)
        return (p, "SALTFLOW_PLAYWRIGHT") if p else (None, "SALTFLOW_PLAYWRIGHT=%s is not the playwright package" % env)
    if web:
        d = os.path.abspath(web)
        top = os.path.abspath(root) if root else d
        while True:
            p = _pkg(os.path.join(d, "node_modules"))
            if p:
                return p, "the product's web app"
            if d == top or os.path.dirname(d) == d or not d.startswith(top):
                break
            d = os.path.dirname(d)
    p = _pkg(os.path.join(cache_dir(), "node_modules"))
    if p:
        return p, "saltFlow's cache"
    for d in [x for x in os.environ.get("NODE_PATH", "").split(os.pathsep) if x] + [_npm_root_g()]:
        p = d and _pkg(d)
        if p:
            return p, "a global install"
    return None, "no playwright package found"


def browsers_dir():
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Caches", "ms-playwright")
    if sys.platform.startswith("win"):
        return os.path.join(os.environ.get("LOCALAPPDATA", home), "ms-playwright")
    return os.path.join(home, ".cache", "ms-playwright")


def webkit_installed():
    d = browsers_dir()
    return os.path.isdir(d) and any(n.startswith("webkit-") for n in os.listdir(d))


def _version(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 and (r.stdout or r.stderr).strip() else None


def _native(root):
    """Whether the product has a native surface: only then do the macOS tools matter."""
    if not root:
        return False
    try:
        from .server import Product
        return any(s.get("client") == "native" for s in Product(root).surfaces().values())
    except Exception:
        return False


def checks(start=None, which=shutil.which):
    """One dict per check: name, ok (True, False, or None when optional and absent), what was found, the fix.
    `required` marks the ones whose absence stops saltFlow; the rest only stop capture."""
    out = []
    add = lambda name, ok, found, fix="", required=False: out.append(
        {"name": name, "ok": ok, "found": found, "fix": fix, "required": required})
    v = sys.version_info
    add("python", v >= (3, 9), "%d.%d.%d at %s" % (v[0], v[1], v[2], sys.executable), "saltFlow needs Python 3.9 or newer", True)
    root = M.find(start)
    if root:
        try:
            man = M.load(root)
            add("product", True, "%s at %s" % (man.product or "(unnamed)", root))
        except ValueError as e:
            man = None
            add("product", False, "%s is not valid JSON: %s" % (M.NAME, e), "fix the manifest's JSON", True)
    else:
        man = None
        add("product", None, "not in a product: no %s here or above" % M.NAME,
            "saltflow init in the product's repo, or saltflow demo to see one")
    git = which("git")
    add("git", bool(git), _version([git, "--version"]) if git else "not on PATH",
        "install git; the walk stamps commits with it and the hook needs it")
    node = which("node")
    add("node", bool(node), _version([node, "--version"]) if node else "not on PATH",
        "install Node.js 18 or newer (https://nodejs.org); only capture needs it")
    web = man.path(man.data.get("web", "web")) if man else None
    pkg, where = playwright(web, root)
    add("playwright", bool(pkg), "%s (%s)" % (pkg, where) if pkg else where, FIX_PLAYWRIGHT % cache_dir())
    add("webkit", webkit_installed(), browsers_dir() if webkit_installed() else "no WebKit browser in %s" % browsers_dir(),
        "npx playwright install webkit")
    if _native(root):
        if sys.platform != "darwin":
            add("native", False, "native capture reads Xcode result bundles, which needs macOS", "run capture --xcresult on a Mac")
        else:
            xc = which("xcrun") and _version(["xcrun", "xcresulttool", "version"])
            add("xcresulttool", bool(xc), xc or "xcrun xcresulttool did not answer", "xcode-select --install, or install Xcode")
            add("sips", bool(which("sips")), which("sips") or "not on PATH", "sips ships with macOS; landscape screenshots stay turned without it")
    return out


def install_playwright(pkg=None, log=print):
    """npm install playwright into saltFlow's cache unless `pkg` names one already, then its WebKit browser.
    Returns the package's folder."""
    node = shutil.which("node")
    if not node:
        raise RuntimeError("no node on PATH: install Node.js 18 or newer (https://nodejs.org) first")
    if not pkg:
        npm = shutil.which("npm")
        if not npm:
            raise RuntimeError("no npm on PATH: it comes with Node.js (https://nodejs.org)")
        d = cache_dir()
        os.makedirs(d, exist_ok=True)
        log("npm install playwright into %s" % d)
        r = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--prefix", d, "playwright"])
        if r.returncode:
            raise RuntimeError("npm install failed (exit %d)" % r.returncode)
        pkg = _pkg(os.path.join(d, "node_modules"))
        if not pkg:
            raise RuntimeError("npm finished but %s/node_modules/playwright is not there" % d)
    log("playwright install webkit (into %s)" % browsers_dir())
    r = subprocess.run([node, os.path.join(pkg, "cli.js"), "install", "webkit"])
    if r.returncode:
        raise RuntimeError("playwright install webkit failed (exit %d)" % r.returncode)
    return pkg
