"""The manifest: one file per product that names its sources, so the code stays product-neutral.

It lives at `<product repo>/flows/saltflow.json`, inside the one folder saltFlow may write in. A second product
is a second manifest, not new code.
"""
import json
import os
import subprocess

NAME = os.path.join("flows", "saltflow.json")


class Manifest:
    def __init__(self, root, data):
        self.root = root
        self.data = data
        self.product = data.get("product", "")
        self.sources = data.get("sources", {})
        self.primitives = data.get("primitives")      # the product's building-block words, or None

    def path(self, rel):
        return os.path.join(self.root, rel)

    def flows_dir(self):
        return self.path(self.data.get("flows", "flows"))

    def records(self, name):
        """The records of an ids source as a list of dicts, each with an "id": a list of records, or an object
        keyed by id, under the manifest's `list` key if it names one. [] when the source is absent."""
        import json
        path = self.source_path(name)
        if not path or not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        spec = self.sources[name]
        items = raw.get(spec["list"]) if spec.get("list") else raw
        if isinstance(items, dict):
            return [dict(v, id=k) if isinstance(v, dict) else {"id": k} for k, v in items.items()]
        key = spec.get("id", "id")
        return [dict(x, id=x.get(key)) for x in items if isinstance(x, dict)]

    def source_path(self, name):
        src = self.sources.get(name)
        return self.path(src["path"]) if src and "path" in src else None


def find(start=None):
    """The product repo saltFlow is standing in: the nearest folder upward with a flows/saltflow.json."""
    d = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isfile(os.path.join(d, NAME)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load(root):
    with open(os.path.join(root, NAME), encoding="utf-8") as f:
        return Manifest(root, json.load(f))


def reviewer(root=None):
    """Who answers on the page: SALTFLOW_REVIEWER, else git's user.name (the repo's, then the global one), else "you".
    A note or a decision with no origin or by is theirs."""
    name = os.environ.get("SALTFLOW_REVIEWER", "").strip()
    if name:
        return name
    try:
        r = subprocess.run(["git"] + (["-C", root] if root else []) + ["config", "user.name"],
                           capture_output=True, text=True, timeout=5)
        name = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        name = ""
    return name or "you"
