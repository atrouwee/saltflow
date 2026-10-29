# Contributing to saltFlow

Thank you for wanting to help. Bug reports, ideas, docs fixes and code are all welcome.

## Before you start

- **The CLA.** Every contribution comes in under the [contributor licence agreement](CLA.md). You keep your
  copyright; you give the project a licence to use your work, including under commercial terms. Tick the box in the
  pull request template to agree.
  Why: saltFlow is free for non-commercial use and the project sells commercial licences. Without the CLA your code
  would arrive under the non-commercial licence only, and the project could not offer one version of saltFlow to
  everyone. That is the only reason it is there.
- **Bigger changes.** Open an issue first and say what you have in mind, so nobody spends a weekend on something that
  will not fit.
- **Be kind.** The [code of conduct](CODE_OF_CONDUCT.md) applies everywhere in the project.

## Set up

You need Python 3.9 or newer and git. Nothing else, unless you work on `saltflow capture` (then Node.js 20 or newer).

    git clone https://github.com/atrouwee/saltflow
    cd saltflow
    python3 -m unittest -q              # from the repo root: it finds tests/, which imports saltflow from src/

To run the command from your checkout, either:

    pip install -e .                    # puts `saltflow` on your PATH, pointing at this checkout
    PYTHONPATH=src python3 -m saltflow.cli --help     # or no install at all

The tests always use this checkout's `src/`, even with another copy of saltFlow installed. For the command, use
`PYTHONPATH=src` (or `pip install -e .`) so it runs this checkout and not the other copy. Run the tests from the repo
root: from anywhere else `unittest` finds no tests and still says OK.

For capture work:

    npm i playwright
    npx playwright install webkit

## The layout

| Path | What |
|---|---|
| `src/saltflow/` | the package: `cli.py` (every verb), `model.py` (the model as code), `walk.py`, `lint.py`, `capture.py` and `capture.mjs`, `native.py`, `server.py` and `page.html` (the review page) |
| `src/saltflow/flows-guide.md` | the guide `saltflow init` installs into a product as `flows/README.md` |
| `docs/` | the model in words (`model.md`) and the bar (`bar.md`) |
| `examples/` | the bundled example product, which `saltflow demo` opens |
| `tests/` | `unittest` tests and their fixtures |

## Style

- **Standard library only.** saltFlow has no runtime dependencies and stays that way. Do not add one. Capture's Node
  side needs only Playwright, and only when someone captures.
- Match the code around you: short functions, terse comments that say why, plain words.
- The model has one source of truth: `src/saltflow/model.py`. If you change what a flow file may say, change
  `docs/model.md` and `src/saltflow/flows-guide.md` in the same pull request.
- Every control on the page that makes a move carries `data-move="<move id>"`, and `data-words` when its text is
  data. If you change `page.html`, run `saltflow capture` and then `saltflow lint` on the example and keep them at
  zero `code-differs` and `trigger-words`.
- The page must work at phone width as well as on a desktop.

## Tests

Every change to behaviour comes with a test. A bug fix comes with a test that fails before the fix.

    python3 -m unittest -q

CI runs the tests on Linux and macOS with Python 3.9 and 3.13, and a separate capture job in WebKit.

## Pull requests

- One change per pull request, with a short description of what and why.
- Tests pass locally.
- Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md) if users will notice the change.
- Tick the CLA box.

## How releases work

This public repository is published from the maintainer's source repository. When your pull request is accepted, the
maintainer brings it into the source repository (your authorship is kept in the commit), and it reaches this
repository with the next release. So your pull request may be closed as "merged upstream" rather than merged here;
that is normal.

The maintainer releases versions with [semantic versioning](https://semver.org/). While saltFlow is 0.x, a change
to the flow file format bumps the minor version and comes with a note on how to update your flows.
