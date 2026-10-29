## What and why

<!-- One change per pull request. What does it change, and why? Link the issue if there is one. -->

## Checklist

- [ ] I agree to `CLA.md` (in the repo root) for this and my later contributions.
- [ ] `python3 -m unittest -q` passes locally (with `PYTHONPATH=src` if another saltflow is installed).
- [ ] New or changed behaviour has a test.
- [ ] No new runtime dependency.
- [ ] If I changed `page.html`: every control that makes a move has `data-move`, `saltflow capture` then
      `saltflow lint` on the example show no `code-differs` or `trigger-words`, and the page works at phone width.
- [ ] If I changed the flow file format: `model.py`, `docs/model.md` and `flows-guide.md` agree.
- [ ] A line under **Unreleased** in CHANGELOG.md, if users will notice.
