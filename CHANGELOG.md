# Changelog

All notable changes to saltFlow are written down here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and saltFlow uses
[semantic versioning](https://semver.org/). While saltFlow is 0.x, a change to the flow file format bumps the minor
version and comes with a note on how to update your flows.

## [Unreleased]

## [0.2.3]

### Added

- A platform switch on the page (Web, iPad, iPhone, Mac...): one choice sets which pictures the journey board, the
  step, the comparison and decisions show, remembered on that device. It appears once a product has pictures of
  more than one platform. A step without a picture for the chosen platform shows another one, marked as such.
  `capture.prefer` (a platform or a list) sets the default order.

### Changed

- Native captures are kept per platform: `flows/captures/native/<platform>.json`, pictures named
  `<step>.<platform>.png`, the platform read from the test device. Older layouts move there on the next import.

### Fixed

- The README's feature pictures were left out of 0.2.2. The release now fails when a document links to a file the
  export does not have.

## [0.2.2]

### Added

- The README is a product page: what saltFlow does, feature by feature, with screenshots of the example.
- A step captured both on the web and natively shows a switch between the two pictures (the choice is remembered on
  that device). `capture.prefer` in `flows/saltflow.json` (`"native"` or `"web"`) says which shows first; native by
  default.

### Fixed

- Web and native captures no longer overwrite each other: the native import writes `flows/captures/native.json`
  beside the web capture's `index.json`, and moves any native rows an older version left in `index.json`. The lint
  checks both.
- A capture with no commit (the bundled example) no longer reads "undefined" on its label.

## [0.2.1]

### Fixed

- CI: Python 3.9 is tested on macOS only, since GitHub's Ubuntu runners no longer carry it; Ubuntu tests 3.10
  and 3.13. The actions moved to their Node 24 versions.

## [0.2.0] - first public release

### Added

- **The journey board**: the review page opens on the product's journey, its stages as columns and its flows as
  tiles, grouped as the main path, common variations and edge cases. A product with more than one journey (say, the
  owner's and the object's own) gets a switch between them.
- **The flow map**: each flow drawn as a graph of steps and moves that branches, loops, goes back and fails. A step
  not built yet is drawn dashed. Tap a step to see its surface: a low-fidelity drawing first, the real screen one tap
  away, and the reasons (patterns, research, rulings) behind it.
- **The walk** (`saltflow walk`): every job on every flow tried under every combination of its conditions, with a
  verdict per named run (ok, work to do, or break). Breaks become notes.
- **Checks**: `saltflow validate` (every file against the model, naming the file and field), `saltflow lint` (no
  way back, an error move missing, unreachable steps, button words that differ from the flow, code that differs from
  the flow), `saltflow coverage`, `saltflow bar` (the product's level against the bar in `docs/bar.md`) and
  `saltflow needs` (the pictures the page still lacks). They report; only `validate` exits 1, when a file is wrong.
- **Capture for the web** (`saltflow capture`): builds the product, plays each flow in WebKit through Playwright and
  saves a crop of the surface at every step, light and dark, at the product's own device size. A product can stage
  each component alone (`stage`) so the page shows the real component from the product's code, and every control
  marked with `data-move` is read back and checked against the flows.
- **Capture for native apps** (`saltflow capture --xcresult`): reads the screenshots and view hierarchy that the
  product's own XCUITests attach at each step, and checks the controls' accessibility identifiers against the flows.
- **Sketches and the x-ray** for things that are not screens: physical parts, services, outside things.
- **Decisions** (`saltflow ask`): a product's agent puts a question to the founder with options and one recommended;
  the founder answers on the page with a tap or in their own words, and the answer is appended to
  `flows/notes.jsonl`.
- **Notes**: left on a step, a move, a flow or a region; taken and closed by the product's agent with the commit that
  answered them (`saltflow notes`). The file is append-only and readable by any script.
- **The commit hook** (`saltflow hook`): walk, lint, coverage and capture after each commit that touches the screens.
- **Phone layout**: the page works one pane at a time at phone width; `saltflow --lan` serves it to a phone or tablet
  on the same network.
- `saltflow init` sets a product up; `flows/README.md` is the guide its agent follows.
- `saltflow publish` writes the page as one static HTML file.
- `saltflow doctor` checks the machine and says how to fix what is missing; `saltflow demo` opens a bundled example.

[Unreleased]: https://github.com/atrouwee/saltflow/compare/v0.2.3...HEAD
[0.2.3]: https://github.com/atrouwee/saltflow/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/atrouwee/saltflow/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/atrouwee/saltflow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/atrouwee/saltflow/releases/tag/v0.2.0
