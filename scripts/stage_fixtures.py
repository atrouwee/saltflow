"""saltFlow's own stage fixtures: what each of its components renders when staged, since saltFlow is a product too
and reviews itself. A snapshot of the test product (tests/fixtures/saltPOS), walked, with one decision asked, written to
flows/fixtures/<state>.json as the page's inline data plus `go`: which flow, step and decision a component opens on.

  python3 scripts/stage_fixtures.py        rewrite them
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
from saltflow import server as S, walk as W  # noqa: E402

FIXTURE = os.path.join(HERE, "..", "tests", "fixtures", "saltPOS")
OUT = os.path.join(HERE, "..", "flows", "fixtures")


def snapshot(root):
    p = S.Product(root)
    return {"product": p.summary(), "today": p.today(), "flows": {f["id"]: p.flow_bundle(f["id"]) for f in p.flows()}}


def main():
    tmp = tempfile.mkdtemp()
    try:
        root = os.path.join(tmp, "saltPOS")
        shutil.copytree(FIXTURE, root)
        W.walk(root)
        p = S.Product(root)
        runs = [r for r in p.runs().get("runs", []) if "expect" in r]
        bad = next((r for r in runs if r.get("verdict") == "break"), runs[0])
        d = p.add_note({"kind": "decision", "origin": "saltPOS", "title": "Receipt by default",
                        "text": "Should the till print a receipt unless the guest asks for none?",
                        "why": "Paper costs, and most guests leave it on the counter.", "area": "money",
                        "flow": bad["flow"], "step": bad["at"],
                        "options": [{"id": "ask", "label": "Ask each time", "rec": True, "then": "One more tap at every payment."},
                                    {"id": "never", "label": "Never, QR only", "then": "No paper; the QR shows on the reader."}]})
        p.add_note({"kind": "decision", "origin": "saltPOS", "title": "Tip on the reader", "area": "money",
                    "text": "Should the card reader offer a tip, or only the till?", "why": "Tips change what every guest sees at the end.",
                    "options": [{"id": "reader", "label": "On the reader", "rec": True, "then": "Guests choose in private."},
                                {"id": "till", "label": "Only at the till", "then": "The barista asks out loud."}],
                    "touches": [d["id"]]})
        os.makedirs(OUT, exist_ok=True)
        data = dict(snapshot(root), go={"flow": bad["flow"], "step": bad["at"], "decision": d["id"], "feed": "broke"})
        with open(os.path.join(OUT, "default.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        print("flows/fixtures/default.json: %s/%s, decision %s" % (bad["flow"], bad["at"], d["id"]))
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
