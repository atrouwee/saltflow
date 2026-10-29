# The tests import saltflow from this checkout's src/, ahead of any installed copy, so plain
# `python3 -m unittest` from the repo root tests what is here.
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
