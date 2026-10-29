# Writing flows for saltFlow

This file is installed into a product's `flows/` by `saltflow init` (as `flows/README.md`). It is for the session that
builds the product: what to write, where, and the rules. saltFlow reads these files and shows them; it never edits
them. The full model is in saltFlow's docs/model.md; this is the working version.

## The files, all under flows/

| File | What | You write it? |
|---|---|---|
| `saltflow.json` | the manifest: the product's name, its building-block words, the sources saltFlow reads | once; edit when a source moves |
| `<flow>.json` | one flow: a job's path through the steps, one file per flow, named after its id | yes, beside the screen you build |
| `surfaces.json` | every surface the flows point at, described once | yes, add a surface when a flow needs one |
| `drives/<client>.json` | how one client performs each move (clicks, keys), keyed by move id | yes, when a step is built |
| `patterns.json`, `joins.json` | the product's own patterns and the job-to-flow pairs | no: computed by a seed script, never by hand |
| `runs.json` | what the last walk reached | no: `saltflow walk` |
| `notes.jsonl` | review notes, one per line, append-only | you append a close; the page appends the founder's notes and answers |
| `captures/` | crops of the real panes | no: `saltflow capture`; ignored by git |

## The words

A **surface** is the thing that arrives on screen, never the whole screen (the bill, not "the till with the bill
open"). A **step** is one surface arriving in one flow. A **move** is a way from one step to another. A **flow** is
one job's path. A **job** comes from the product's job map and is only referenced. A **pattern** is a reusable
interface decision, from the market grid or the product's own. A **link** is one reason (a ruling, evidence, a quote).
A **run** is one job walked under one set of conditions. A **note** is anything left on a step. An **iteration** is a
commit that touched the screens or the flows.

## Writing a flow

```json
{ "schema": "saltflow/v1/flow", "id": "pay-on-leaving", "name": "Pay on leaving",
  "says": "one sentence", "product": "<as in the manifest>",
  "jobs": [{ "ref": "<product>:jobs#<job id>", "ends": ["closed"] }],
  "world": { "online": [true, false] },
  "entry": "tab",
  "steps": { "tab": { "surface": "home.tab-card", "place": "home", "built": true },
             "closed": { "surface": "home.toast", "place": "overlay", "built": true, "end": "done" } },
  "moves": [{ "id": "open-bill", "from": "tab", "to": "closed", "kind": "forward", "trigger": "Pay", "needs": { "online": true } }],
  "runs": [{ "id": "happy", "job": "<product>:jobs#<job id>", "world": { "online": true }, "expect": "done" }] }
```

- `place` is where the surface arrives from: `home`, `left`, `right`, `top`, `zoom` (grows from the tap), `out`,
  `overlay`, or `same` (the pane stays, its page changes).
- `built` is true or false. Write the step before the screen exists; a flow may run ahead of the code. Say in
  `design` what it should be.
- A step that ends a job carries `end`: `done` (the job got done) or `kept` (the visit stays open on purpose).
- `kind` of a move: `forward`, `back`, `loop`, `error`, `cancel`, or `system` (nobody taps it).
- `world` names the conditions the walk tries in every combination; `needs` and `sets` on moves, and `world` on
  runs, use only those words. `hold` on a run keeps a condition fixed for the whole walk.
- `features` on a step are the job map's words this step offers; the walk reports a job's features no step offers.
- `patterns` and `links` carry the reasons: refs into the grid (`<product>:grid#F10/decline-path`), the product's
  own patterns, or rulings with the verbatim quote.
- A move never carries its clicks. Those go in `drives/<client>.json`, keyed `<flow>/<move>` for this flow's move,
  or by the bare move id when every flow that uses that id means the same gesture (validate warns when they don't).
  An empty list means the step is already on screen; `null` means nothing can click it (a system move). Actions:
  `click`, `fill` (with `text`), `press`, `drag` (with `from` and `to`), `longpress`, `scan`, or `{"key": "Escape"}`.
- `built_as` on a move says what the code does when it differs from the design. That is how a drift is written
  down, not hidden.
- A run's `expect` is what the **design** should reach, never what the code reaches today. When the walk disagrees,
  that disagreement is the finding; do not bend `expect` to make a run pass.
- A run may carry its own `setup` (the tab to open, say) when its path needs a different start than the flow's.
- A step's `variant` must be a variant the registry names on that surface. A variant that is only designed is an
  object: `"by-payer": {"says": "the bill grouped by payer", "built": false}`.
- A job feature that no single step offers but the flow does as a side effect (a count draining on the tile) goes
  on the flow: `"offers": [{"feature": "cartridge", "how": "the tile's count falls on the sale"}]`. The walk counts
  it as offered.
- A link may point at a research file by its path when the manifest names a `files` source:
  `{"kind": "research", "ref": "<product>:files#research/money.md", "quote": "..."}`.

## A surface

```json
"pay.choose": { "name": "The bill", "file": "web/src/Sheets.tsx", "component": "Pay",
  "place": "right", "aria": "Pay", "sheet": "pay", "size": "part",
  "regions": [{ "role": "title", "label": "Pay · tab · items", "x": 12, "y": 0, "w": 88, "h": 9 },
              { "role": "action", "label": "Card · amount", "x": 0, "y": 88, "w": 100, "h": 12 }],
  "depends": ["web/src/Sheets.tsx"] }
```

Regions are percent boxes of the surface, for the low-fidelity drawing; roles `action`, `confirm`, `danger`,
`cancel`, `option` draw as buttons, the rest as lines. `aria` is the pane's aria-label (keep it steady while the pane's
pages change). `depends` are the files whose change makes a step stale.

## Components, space, and things that are not screens

A surface is a UX component with one job and its states, not a screen: it lays itself out for
the space it is given. Say how with `"space": {"compact": "...", "regular": "...", "full": "..."}`; a device or a
split view only changes the space, never the component. Say where it lives with `"client"`: `page`, `terminal`,
`native`, `physical` (a part of a made thing: its regions are its controls and interfaces, `built` means made, a
drive is a hand) or `service` (a person or a shop doing the work).

A step that cannot be undone (a cut frame tube, a shipped parcel, a charge) says so with `"oneway": "<why>"`, and
lint stops asking for a way back. A step that is left by nature, with no control of its own (tap another row, pick another
tab), says how with `"leave": "<how>"`, and lint stops asking too. `"built": "ruled-out"` (with a link) marks a step out of the product by ruling.
Another maker's thing (another shop, an old pump, a courier) is a surface with `"client": "outside"`. Every run also
reports `design`: what the design reaches if every step were made, beside the outcome of what is built.

A step may be a whole other flow: `{"flow": "service-at-the-shop", "place": "zoom", "built": false}` instead of a
`surface`. That is how a lifecycle (order → build → ride → service) holds the flows inside it; the page opens the
inner flow when the step is tapped.

## The pictures saltFlow shows, and who makes them

saltFlow shows the product; it never draws it. Your session makes what the page shows, in the same commit as the
surface, by where the surface lives (`client`). `saltflow needs` lists what is missing; a commit that touches a part without its picture is held (rule 7).

- **A screen** (`page`, `native`), best: **the component itself, from your code**, the actual UI code rendered in
  saltFlow. Give your build one page that renders a single surface's component, alone, in a named
  state from your fixtures, and name it in flows/saltflow.json: `"stage": "index.html?stage={surface}&state={state}"`.
  Put `data-surface="<surface id>"` on the component's root element; saltFlow clips to it. A step says which state it
  shows with `"state": "<name>"` (default `default`). Then the live view, decision mode and `saltflow capture` all load
  the component straight from your code: no drives to write, no sketches to draw, and it is never out of date. A
  surface that cannot stand alone says `"stage": false` and falls back to the build below. A surface that takes time to
  arrive (it animates, it plays) says `"settle": <ms>` and capture waits that long before the picture. To make it work, lift each
  surface into a component that takes its state as props (no reach into a global store), and keep a fixture per state.
  The moves come from the code too (actions, events and click paths are derived from the actual code):
  mark each control that makes a move with `data-move="<move id>"` (several ids, space-separated, when one control
  makes several: the move and its error). A move's trigger carries the words its control shows; a control whose
  text is data (a tile showing a flow's name) says its fixed words in `data-words="a flow's tile"`. lint reports
  `trigger-words` where they part. A move that passes through another control first (a tab, then a row) marks that
  control `data-move-via="<move id>"`; the derived drive taps it when it is on screen. A move made by a key (Escape,
  ⌘Z) is declared on the component that answers it: `data-move-keys="close:Escape undo:Meta+z"`; the derived drive
  presses it. A move nothing can make by nature keeps a null drive, and lint owes it no control, and saltFlow derives its drive (a click on it);
  a written drive in flows/drives/ still wins. When a move happens in code, clicked or by itself (a timer, the last
  unit selling), post `parent.postMessage({saltflow: "move", id: "<move id>", to: "<step id>"}, "*")` from the stage
  and the live view says so. `saltflow capture` reads every `data-move` each component renders, and `saltflow lint`
  reports `code-differs` where the flow and the code disagree.
- **A screen**, otherwise: the product's own build. Point `"web"` (built into `dist/`) or `"live"` (a page
  that shows only the product, e.g. `index.html?bare=1`) at it in flows/saltflow.json, and give each surface its
  `aria` or `css` so the page can clip to it. `saltflow capture` crops every made step; run it after a commit that
  touches the screens. Say the device the product is used on: `"capture": {"viewport": [1194, 834],
  "device": "iPad 11″, landscape", "touch": true}` takes every picture there, with touch and no hover. `"capture": {"calls_it": "the prototype"}` names the build in the page's words.
- **A native app** (`native`; saltFlow reads the product's own UI tests, never drives the app): mark
  each screen element `.accessibilityIdentifier("surface.<surface id>")` with `.accessibilityElement(children:
  .contain)` (without it the container's identifier hides every control inside), and each control that makes a move
  `"move.<move id>"` (several ids space-separated, as with `data-move`); a control whose label is data (a tile
  showing "Espresso, 3.20") adds its fixed words after ` = `, as `data-words` does: `"move.tap-plain-tile = a tile
  without choices"`. Ids never contain a space or a dot. Keypad
  keys and other input inside a step are `"key.<n>"`, not moves; the container they sit in carries the move they
  complete. Your XCUITests walk the flows and, at each step a flow names, attach (lifetime `.keepAlways`)
  `"saltflow <flow> <step> hierarchy"` (`XCTAttachment(string: app.debugDescription)`) and `"saltflow <flow> <step>
  screen"` (`XCUIScreen.main.screenshot()`, with the orientation set to `.landscapeLeft` in setUp for a landscape app;
  saltFlow turns the portrait picture upright; `"... screen dark"` for dark). Spaces, not a slash: xcresulttool drops
  the slash from attachment names. Then `saltflow capture --xcresult <bundle>` files the pictures under the platform the tests ran on (iPad, iPhone...), beside the web ones, and files the
  screens and reads each control's identifier and label, and `saltflow lint` checks them as it checks `data-move`.
- **A terminal**: a read-only `"command"` on the surface (a `saltflow` verb the page runs to show real output), or a
  sketch of what it prints.
- **A physical part** (`physical`): a sketch, and a place in the x-ray.
  - `flows/sketches/<surface>.svg`: a line drawing of the part as a hand meets it.
  - `flows/sketches/xray.svg`: one see-through drawing of the whole made thing. Wrap each part in
    `<g data-surface="<surface id> [more ids]">`; each step box on the map lights its part and fades the rest, so a
    flow reads as a path through the thing. Chunky strokes (6 to 10 in a 400×300 box), parts well apart; check
    each part lit alone at 120×90. A physical surface that is a whole other thing, not a part, says `"xray": false`.
- **A service or an outside thing** (`service`, `outside`): a sketch, the wireframe of what the person meets.
- **Any step or decision**, optionally: `flows/sketches/<flow>/<step>.svg` for a state of a surface that looks
  different (the counter at zero, the door locked); `flows/sketches/decisions/<decision id>.svg` when one step carries
  several questions; `flows/sketches/icons/<surface>.svg`, a 24px glyph.
- **Each answer of a decision**, when the answers look different (show examples of
  each answer beside the decision): `flows/sketches/decisions/<decision id>/<option id>.png` (or `.svg`, `.jpg`,
  `.webp`). Decision mode then shows the answers side by side in the middle, and a tap picks one. The option ids are
  the ones in the decision's line in flows/notes.jsonl. Use the real thing for an answer that is built (a capture
  of the page), and a mock-up or sketch for one that is not; say which in the option's `desc`.
- **The product's icon**: its own app icon, the file it already ships (a square png, jpeg, webp or svg, 512px is
  plenty), named in flows/saltflow.json as `"look": {"icon": "<path from the repo root>"}`. It heads saltFlow's
  product switcher; without it the switcher shows the product's initial on `look.deep`. Give
  `look.accent` and `look.deep` too: the switcher and the page take the product's colours from them.

Sketches are SVG, a 400×300 viewBox, `stroke="currentColor"` on a transparent ground (they take the page's ink in
light and dark), no fill colours, words only as short labels. Put `class="focus"` on the group a step or decision is
about; the page draws it in the live colour. A two-option decision may be drawn as two halves. A sketch shows where
parts sit, never how the thing looks: say "sketch", never "design", until the look is ruled.

A decision's options each carry `then`: one plain line on what follows if it is chosen. A decision that changes
another names it in `touches`.

## The rules

1. Write the flow beside the screen, in the same commit, once. Then `saltflow validate`; it names the file and
   field of anything wrong.
2. Edit the flow when the screen changes. `built_as` is for what the code does differently today, on purpose or
   not; a flow is the design, not a mirror of the code.
3. Never edit `patterns.json`, `joins.json`, `runs.json`, or rewrite `notes.jsonl`. Close a note by appending one
   line: `{"id": "<id>", "status": "done", "commit_done": "<hash>"}`, or `saltflow notes done <id> --commit <hash>`.
4. Before each change to the screens, read the open notes (`saltflow notes`, or the product's own reader). Take one
   with `saltflow notes take <id>`.
5. When you need the founder's call, ask it as a decision, not in chat: `saltflow ask "<the question>" --title
   "<a few words>" --why "<what turns on it>" --option "<label>: <one line>*" --option "<label>" --flow <flow>
   --step <step> --session <your name>`. The `*` marks the one you recommend; leave out flow and step for a
   question about the whole product. The founder answers on the page, which appends the answer to notes.jsonl.
   Read answers with `saltflow notes --all`; quote the founder's words into your rulings, then
   `saltflow notes ruled <id> --ruling <ref>`. notes.jsonl is tracked in git: the page appends to it without
   committing, so commit it with your next commit.
6. Say the thing, not the code: a step's trigger is the words on the button; a flow's name is what the guest or the
   barista does.
7. One thing holds a commit: a part it adds or changes without its picture (a sketch, its place in the x-ray, a
   `then` on each new decision's options), checked by the pre-commit hook `saltflow hook` installs: a
   missing picture blocks. Captures come after a commit and never hold it. Every other check reports.
8. After a change, run `saltflow needs` and make what it lists for the surfaces you touched: a capture, a sketch,
   the part's place in the x-ray, a `then`.

`saltflow` run bare in the repo opens the page; it reads the files on every request and notices changes by itself.
