# saltPOS, an example product

An example product: saltPOS, an iPad till for a coffee bar where guests order, sit, order again and pay when they
leave. Five of its flows are here, cut down so they read on their own, with screenshots of the iPad app in a practice
mode (made-up guests, a test card) for the steps that have one. Nothing here needs the till itself: the screens are
already taken.

## Open it

    saltflow demo

or, from a clone of saltFlow:

    cd examples/saltpos
    saltflow                 # the review page, at http://127.0.0.1:5318/
    saltflow validate        # every file against the model
    saltflow walk            # every job through its flow, on the graph alone
    saltflow lint            # the structural checks
    saltflow coverage        # which jobs have a flow

`walk` writes `flows/runs.json` (git ignores it) and appends any new break to `flows/notes.jsonl`;
`git checkout examples/saltpos` puts the notes back. `saltflow demo` serves a fresh copy, so it changes nothing here.

## What is in it

| File | What it holds |
|---|---|
| `flows/saltflow.json` | the manifest: where the sources are, the journey's stages, the product's building blocks |
| `flows/jobs.json` | the job map: ten jobs a barista needs done, and the features each one needs |
| `flows/surfaces.json` | every surface the steps point at: a sheet, a pane, a toast, drawn as percent boxes |
| `flows/patterns.json` | the till's own patterns, and where it departs from what most tills do |
| `flows/<flow>.json` | five flows: open a tab, ring a coffee, send a round to the bar, void a line, pay on leaving |
| `flows/notes.jsonl` | review notes, three open decisions with their options, and the breaks the walk found |
| `flows/runs.json` | the last walk, written by the first `walk` (not shipped) |
| `flows/captures/` | one screen per step, from the till's UI test, with `index.json` |
| `decisions.md` | the rulings the flows quote word for word |

## What to look for

- **A break.** Pay on leaving: a guest paying by card with the wifi down cannot leave paid. The walk finds it stuck at
  the offline bill, and an open decision asks how to fix it.
- **Work to do.** Send to the bar: the till half is built, the bar screen is not. The walk stops there and calls it
  not built, not broken.
- **A missing feature.** Open a tab: the job needs a service mode, and no step offers one.
- **Jobs with no flow.** Split the bill and close the day are on the switch list with no flow yet; `coverage` names them.
- **Code against the flow.** `lint` lists the moves the flow draws that the screen does not mark yet.
