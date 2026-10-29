"""The bundled example product, to see the page before a product of your own has flows.

Found in this order: SALTFLOW_EXAMPLE (a product folder), saltflow/example/ inside an installed wheel (setup.py
copies examples/saltpos there when it builds), then examples/saltpos in the clone saltFlow runs from.
The demo serves a copy in a temporary folder, so notes written on the page never land in the example itself.
"""
import os
import shutil
import tempfile

from . import manifest as M

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join("examples", "saltpos")


def _is_product(d):
    return bool(d) and os.path.isfile(os.path.join(d, M.NAME))


def example_root(here=HERE):
    """The example product's folder, or None."""
    env = os.environ.get("SALTFLOW_EXAMPLE")
    if env:
        env = os.path.abspath(os.path.expanduser(env))
        return env if _is_product(env) else None
    packaged = os.path.join(here, "example")
    if _is_product(packaged):
        return packaged
    d = here
    while True:
        c = os.path.join(d, EXAMPLE)
        if _is_product(c):
            return c
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def prepare(src):
    """A fresh copy of the example to serve, without the last walk's runs (the demo walks it again). Its screens and
    notes are part of the example, so they come along."""
    dst = os.path.join(tempfile.mkdtemp(prefix="saltflow-demo-"), os.path.basename(src.rstrip(os.sep)) or "example")
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("runs.json", "__pycache__", ".git", ".gitignore"))
    return dst
