# The model

saltFlow describes a product with nine pieces. They are written as plain JSON files in the product's own repo, in
`flows/`, and checked by `saltflow validate`. This page says what each piece is. `src/saltflow/model.py` is the same
model as code, and when the two disagree the code is right and this page is wrong.

This page gives the shape. The working version for a building session is src/saltflow/flows-guide.md, which
`saltflow init` installs into the product's repo as flows/README.md: saltFlow is a shell that stores nothing of a
product.

## Where the files are

Everything saltFlow reads about a product, and everything it writes, sits in one folder in that product's repo:

| File | What it holds | Who writes it |
|---|---|---|
| `flows/saltflow.json` | the manifest: the product's name, its building-block words, and the sources saltFlow reads | once, by hand |
| `flows/<flow>.json` | one flow: a job's path through the steps | the session that builds the screens |
| `flows/drives/<client>.json` | how one client (say, the web build) performs each move, keyed by move id | the same session |
| `flows/surfaces.json` | the surface registry, so a surface is described once | the same session |
| `flows/patterns.json` | the product's own patterns, the ones the market grid lacks | computed by a script of the product's, or by hand |
| `flows/joins.json` | which jobs each flow serves, proposed or ruled | computed, then ruled by the founder |
| `flows/runs.json` | what the last walk reached | `saltflow walk` |
| `flows/notes.jsonl` | notes, one per line | the page, the walk, and sessions closing them |

The manifest sits in `flows/` rather than at the repo root so that saltFlow writes nowhere else in the product's
repo. Every file in `flows/` carries a `schema` line that says what it is; a flow starts with
`"schema": "saltflow/v1/flow"`, and a file in `flows/` with a schema the validator does not know is an error, never
a silent skip.

## The manifest

```json
{
  "schema": "saltflow/v1/manifest",
  "product": "saltPOS",
  "primitives": ["stock", "resources", "product", "visit", "money", "signals", "rules", "surfaces"],
  "sources": {
    "jobs":      { "path": "research/jobs.json", "kind": "ids" },
    "grid":      { "path": "research/grid.json", "kind": "grid" },
    "decisions": { "path": "decisions.md", "kind": "quotes" },
    "surfaces":  { "path": "flows/surfaces.json", "kind": "ids", "list": "surfaces" }
  },
  "places": { "file": "web/src/Sheets.tsx", "default": "zoom" }
}
```

- The source **names** are a fixed vocabulary the code knows: `jobs`, `graph`, `grid`, `decisions`, `patterns`,
  `surfaces`, `files`, `records`. The manifest gives each its path and kind; an unknown name is an error; `surfaces`
  is required.
- The **kinds**: `ids` (a list of records, or an object keyed by id), `grid`, `quotes` (a text file the quote must be
  in), `files` (the key is a path in the repo; a quote into a text file is checked, and a miss is a warning, since
  a quote may come from a file's history), and `export` (a JSON export of a live record store, such as a project
  tracker's database: an object of collections, each a list of records with an `id`, their fields under `data` or not,
  or an object keyed by id; or a folder with one folder per collection and one `<id>.json` per record, the shape
  some database tools save). A ref into an export reads `<collection>/<id>`, `bike:records#decisions/d-frame`,
  and its quote must be in one of that record's fields. The product's own session writes the export; saltFlow
  only reads it.
- `primitives` are the product's own building-block words, which a step's `primitive` field must use. Without the
  list the field is not checked. This is what makes the code product-neutral: a till brings its eight, saltFlow
  brings its nine, a bicycle brings its own.
- `journey` is the product's journey in order, an abstract version of it: `[{"id": "arrive", "name": "Arrive",
  "says": "a guest comes in and sits or queues"}, ...]`. For a venue it is the guest's visit inside the venue's day.
  Each flow names its `stage` (one of these ids) and its `path`: `happy` (the main path), `variation` (a common
  turn off it) or `edge` (rare, still worth designing). The product's session tags them; the page opens on the
  journey as a board, stages as columns and flows as tiles. A flow whose steps are two or more whole inner
  flows is the journey itself: it shows as a band across the stages its inner flows sit in, above the tiles, not as
  a tile (a bicycle's whole life, say).
- `journeys` carries more than one journey: `[{"id": "owner", "name": "...", "says": "...", "stages": [...]},
  {"id": "operation", "name": "The bike at work", "stages": [...]}]`. A made thing has, beside its owner's
  journey, the journey of its own operation: what the object must do, in order, for a person to use it. A flow names its `journey` (the first one when it names none); its `stage` is one of that journey's.
  `journey` and `journeys` may both be there; `journey` reads as the first, with the id `journey`. The board has a
  switch between them. Without a journey, neither is checked;
  with one, a missing tag is a warning.
- `lint`: `{"needs_error_move": ["money"]}` names the primitives whose steps, when something happens by itself
  there (a system move out), must also have an error move designed. Empty unless the product names it.
- `capture.calls_it`: what the product calls its work-in-progress build, in the page's words ("the prototype"); the
  default is "the build". A setup action the driver cannot perform (no css, role, key or drag) is skipped, so a
  product may keep its own notes in a setup list.
- A product may keep a ledger, `flows/ledger.json` with `"schema": "saltflow/v1/ledger"`: every past decision, input,
  open question, risk and correction with its one primary place (a link on a step, an open decision, open until
  measured, ruled out, or out of scope with a reason). validate reads it as a record, not a flow; showing its counts
  on the board is the next step.
- `places` names the code file whose `PLACE` map says where each sheet kind arrives from, for the lint check.

## A ref

Files point at each other, and at the product's research, with one form:

    <product>:<source>#<key>        saltPOS:jobs#take-payment-on-leaving
                                    saltPOS:grid#F10/decline-path
                                    saltPOS:decisions#2026-10-09-later

The validator reads each source in one of three ways:

- **ids**: a file of records with an id. The records are either a list (`[{"id": ...}, ...]`) or an object keyed
  by id (`{"home.tab-card": {...}}`); `list` names the key they sit under, `id` the field that holds the id
  (default `id`). The key must be one of them.
- **grid**: a table of patterns by product, grouped in areas. The key is an area (`F10`, which the page always shows by its full name,
  "Take payment"), an area and one of its patterns (`F10/decline-path`), or one product's cell
  (`products/acme/F10`).
- **files**: the repo itself; the key is a path (`saltPOS:files#research/money.md`) that must exist. For
  research that lives in a file rather than a registry.
- **quotes**: a Markdown file of rulings. Rulings have no ids yet, so the key is only a label, and the check is
  that the link's stored quote still appears in the file. A reworded ruling therefore fails loudly.

A source whose file is not written yet is reported as *unchecked*, which never fails validation.

## The nine pieces

**Job** is imported from the product (its job map, the manifest's `jobs` source) and never owned, so it is not one of
the nine.

1. **Surface**: a UX component with one job and its states, never a whole screen: build them
   without regard to screen boundaries. It may carry `client` (page, terminal, native, physical, service) and `space`
   (how it lays itself out: compact, regular, full). Described once in the registry. An entry
   has `name`, `file` and `component` (where it comes from), `place` (where it arrives from, the first time),
   `aria` (the pane's aria-label) or `title` (the h3 inside), `sheet` (the sheet kind, for the place check),
   `size`, `regions` (the low-fidelity drawing: role, label, x, y, w, h in percent of the surface), `variants`
   (named states of the same surface, such as the bill offline), `depends` (the files whose change makes a step
   stale), and `built: false` for a surface that is only designed.
2. **Step**: one surface arriving in one flow, or a whole inner flow (`"flow": "<id>"` in place of `surface`), so a
   lifecycle can hold flows inside flows. A step has:
   - `surface`, a name in the registry;
   - `place`, where it arrives from: `home`, `left`, `right`, `top`, `zoom` (grows from what was tapped), `out`
     (the zoomed-out day), `overlay`, or `same` (the pane stays and its page changes);
   - `status`: `designed` (drawn, not begun), `making` (begun, not usable yet), `made` (built, or for a physical
     thing made and working), or `ruled-out` (out of the product by a ruling, with its link). Only `made` counts as
     made anywhere: the walk, capture, coverage and the page all ask one helper. The older `built` (true, false or
     "ruled-out") still reads, true as made and false as designed; when both are there `status` wins. A step not
     made is drawn dashed, which is how a flow runs ahead of the code;
   - optionally `end`: `done` (the job got done) or `kept` (the visit stays open, as meant), with `says` in words;
     `behind` (`none`, `recede`, `tile`), `size` (`part`, `whole`), `primitive` (one of the manifest's words),
     `features` (the job-map words this step offers), `patterns` (refs), `links`, `variant`, `design`.
3. **Move**: a way from one step to another, with `id`, `from`, `to`, `trigger` in plain words, and a `kind`:
   `forward`, `back`, `loop`, `error`, `cancel`, or `system` (nobody taps it: a card declines, the wifi drops).
   `needs` says which conditions must hold, `sets` what it changes, `built_as` what the code does when it differs
   from the design. A move never carries its clicks; those are in the drives file, keyed by move id, and an empty
   list there means the step is already on screen.
4. **Flow**: one job's path. `id` (the file's name), `name`, `says` (one sentence), `product`, `jobs` (each a ref
   and the end steps it may finish at), `grid` (the pattern groups it draws on), `links`, `world`, `setup`,
   `entry`, `steps`, `moves`, `runs`.
5. **Pattern**: a reusable interface decision, either from the grid or from `patterns.json`. Its stance is stick,
   diverge or new.
6. **Link**: one reason. `kind` (`evidence`, `research`, `ruling`, `words`, `measure`, `pairing`, `departs-from`),
   `ref` (or a URL for an outside citation), `quote` (what still reads if the ref breaks), `state` (`proposed`,
   `ruled`, `superseded`). A ruling stays ruled.
7. **Run**: one job walked through one flow under one set of conditions. In the flow file a run is a named
   scenario: `id`, `job` (one of the flow's jobs), `world` (one value per condition), `hold` (conditions that may
   not change on the way), `expect`, `why`. The walk writes the rest (below).
8. **Note**: anything left on a step, a move, a flow or a region. One line in notes.jsonl: `id`, `kind`
   (`question`, `change`, `bug`, `story`, `break`, `decision`), `origin` (the person on the page, `walk`, `lint`, `capture`, or a session),
   `status` (`open`, `taken`, `done`, `won't do`), `at`, `commit` (the product's head when it was written), `flow`,
   `step`, optional `move` or `region` (by role), `text`, and once answered a `reply` (text, session, at) and
   `commit_done`. A question closes with a reply and no commit.
   **The file is the contract**: it is append-only, a note's last line
   wins with its fields merged over the earlier ones, and `open` or `taken` count as open. Closing a note is one
   appended line, `{"id": ..., "status": "done", "commit_done": ...}`. Any ten lines of Python read it the same
   way the page does; nothing depends on a message between sessions. These six
   field names stay stable: `id`, `status`, `kind`, `flow`, `step`, `text`.
   **A decision** is a session's question for the founder, laid out so it can be answered in one tap. Decisions are per product, and the truth is the repo's file, never a
   message or a page elsewhere. It adds `title` (the few
   words a list shows), `why` (what turns on it), `options` (two or more, each `id`, `label`, optional `desc`,
   optional `then` — one line on what follows if it is chosen — and exactly one with `"rec": true`), optional
   `touches` (the ids of other decisions whose question this answer changes; the page links both ways), and
   optional `area`; `flow` and `step` may be null for a question about the
   whole product. The founder answers on the page, which appends `{"id", "status": "decided", "choice": <option
   id or null>, "words": <their own words>, "by": <who answered>, "commit_decided"}`; words alone are an answer. The asking
   session then quotes the words into its rulings and appends `{"id", "ruling": <ref>}`. A decided decision without
   a ruling is the founder's word not yet merged, and the page shows it as such. Ask with `saltflow ask`, close with
   `saltflow notes ruled <id> --ruling <ref>`.
9. **Iteration**: a commit that touched the screens or the flows, and what it changed. Written by `saltflow iterate`, which the commit hook runs.

## The world, and how the walk reads it

A flow's `world` lists the conditions the walk tries in every combination, each with its values:

    "world": { "online": [true, false], "card": ["ok", "declined"], "settles": ["now", "account"] }

A move's `needs` and `sets`, and a run's `world`, may only use these conditions and values. That is what lets the
walk be a script: it never has to guess what "offline" means.

The walk's rules, so nobody has to read the code to predict it:

- For each job on a flow, every combination of the world is walked once. A named run with the same job and world
  lends its id, `expect` and `hold`; the others are unnamed and sit only in runs.json.
- From the entry step, every move whose `needs` hold is followed, so a fork is every branch, not a choice. What a
  move `sets` carries into the rest of that path. A move that would set a held condition is not taken at all.
- Each move may be taken at most twice on one path (the loop cap), so loops are seen but never run forever.
- A step in the job's `ends` stops the path and yields that step's `end` word. A step with no forward move out of
  it (only back or cancel moves, or none) is a dead end.
- The outcome is the first of: `done` if an end with `end: done` is reachable with every step on the way built;
  else `kept` if such an end with `end: kept` is; else `not-built` at the first unbuilt step on the way to an end;
  else `stuck` at the dead end furthest forward (going back and forth does not make a step deeper).
- `missing` lists the job's features (from the job map) that no step in the flow offers in its `features`. It is
  reported beside the outcome and never instead of it: a run can be done and still miss features.
- Every named run gets one `verdict`, decided here and stored with it, which the page, the tiles and the notes only
  read: `ok` (it reached its `expect`), `work` (it stops only at a step not made yet, on a path the design completes:
  work to do, not a break), or `break` (anything else that misses). The design walk is the same walk with every step
  made except those ruled out.
- Every named run whose verdict is `break`, and every job with missing features, becomes one note of
  kind `break` with origin `walk`. A note's id is computed from what it says, so a re-run never duplicates one.

## What validate checks

- the manifest names only known sources, each with a path and a kind it can read, and names `surfaces`;
- every file in flows/ has a schema the model knows; every flow has its required fields, its file is named after
  its id, and every word (place, kind, end, outcome, primitive) is one of the model's or the manifest's;
- every move goes from a step to a step, every job ends at a step that carries an `end`, move and run ids are
  unique;
- every run's world, every `needs` and `sets` uses the flow's own conditions and values; held conditions are set;
- every ref names this product and a source in the manifest, and its key is found there;
- no move carries a drive; every drive belongs to a move that exists (keyed `<flow>/<move>`, or by a bare move id
  shared by flows whose move means the same thing, else a warning); a step's variant is one the registry names;
  a flow's `offers` are well formed.

It reports and never blocks a commit. `saltflow lint` adds the structural checks (no way back, a money step with a
system move but no error move, unreachable steps, a sheet's place against the code's PLACE map, an own pattern with
no reason) and `saltflow coverage` says which jobs still have no flow. None of them blocks anything.
