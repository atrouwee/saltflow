# AGENTS.md

Notes for AI coding agents working on saltFlow itself. (If you are an agent writing flows for a product that saltFlow
reviews, read that product's `flows/README.md` instead; it comes from `src/saltflow/flows-guide.md`.)

## What saltFlow is

A Python CLI plus a local review page. It reads a product's flow files (JSON under the product's `flows/`), checks
them (`validate`, `lint`), walks them (`walk`), takes screenshots (`capture`), and serves a page (`server.py`,
`page.html`) where a founder reviews flows, leaves notes and answers decisions. It stores nothing of a product and
writes only inside the product's `flows/`.

## Layout

- `src/saltflow/cli.py`: every verb, plain argparse.
- `src/saltflow/model.py`: the model as code. `docs/model.md` is the same model in words; when they disagree the code
  is right, so fix the doc.
- `src/saltflow/manifest.py`: finds and reads `flows/saltflow.json`.
- `src/saltflow/walk.py`, `lint.py`, `coverage.py`, `needs.py`, `iterate.py`: the checks and the commit hook.
- `src/saltflow/capture.py` + `capture.mjs`: web screenshots through Playwright WebKit. `native.py`: reads an Xcode
  result bundle (`--xcresult`).
- `src/saltflow/server.py` + `page.html`: the review page, one HTML file, no build step. `vendor/` holds its
  stylesheets.
- `src/saltflow/flows-guide.md`: installed into each product as `flows/README.md`. Product agents read it; keep it
  in step with `model.py`.
- `examples/`: the bundled example product. `tests/`: `unittest` tests and fixtures.

## Commands

    PYTHONPATH=src python3 -m unittest -q          # all tests, from the repo root
    PYTHONPATH=src python3 -m saltflow.cli --help  # the CLI from this checkout

Always set `PYTHONPATH=src`: another installed copy of saltflow would otherwise be the one that runs.

## Rules

- Standard library only. Never add a runtime dependency or a build step. Python 3.9 must keep working.
- Every control on the page that makes a move carries `data-move="<move id>"` (and `data-words` when its text is
  data, `data-move-via` when it passes through another control first). No control without it.
- After changing `page.html`, open it on the example (`saltflow demo`) at desktop and phone width, light and dark, and
  check that `saltflow lint` in `examples/saltpos` reports no new findings.
- Every behaviour change comes with a test. Run the whole suite before you finish.
- If you change what a flow file may say, update `model.py`, `docs/model.md` and `flows-guide.md` together, and
  add a CHANGELOG line.
- saltFlow never edits a product's files outside `flows/`, and never rewrites `flows/notes.jsonl` (it is append-only).
- Match the surrounding style: terse comments that say why, plain words, no new abstractions for one use.
- Do not commit screenshots, `node_modules/` or anything under a product's `flows/captures/`. The one exception is
  `examples/saltpos/flows/captures/`, the example's own screens, which ship with it.
- Contributions are under the CLA (CLA.md). Do not paste code from elsewhere unless its licence allows it and you say
  where it came from.
