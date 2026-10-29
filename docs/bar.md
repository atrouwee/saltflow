# The bar: what a well-covered product looks like

The bar is the standard every product saltFlow views is held to, in levels. It was learned from the first product
saltFlow reviewed, a till with a few dozen flows and well over a hundred steps.
`saltflow coverage` computes it from the files; nothing here is a judgment call, and nothing blocks.

A level is reached when every measure in it is full. A product shows its level and, for the next level, which
measures are short and by how much.

| Level | Name | Measures |
|---|---|---|
| 0 | Nothing | no flows/, or nothing validates |
| 1 | Written | the manifest names its building blocks and sources; every flow validates; every step points at a registered surface with regions; every flow serves a job from the product's job map |
| 2 | Covered | every first-release job that happens in service has a flow; every unbuilt step carries a design line; every move the design knows the code does differently carries `built_as` |
| 3 | Reasoned | every pattern on a step has a reason (a direction, a ruling or research) and every ruling link quotes its source verbatim; every job on a flow has at least one named run whose `expect` is the design; every built step is reachable by a drive, or the move into it says why nothing can click it |
| 4 | Seen | every built step has a capture at the product's head commit, and the capture agrees with the surface the flow names (`dummy_disagrees` is zero) |
| 5 | Closed | at least one note was taken by the product's session and closed with the commit that answered it; no break note older than the last two commits that touched the screens |

What the levels mean to the founder:

- At **Written** the map draws, but what it shows may be a sketch.
- At **Covered** the map is complete for what the product must do on day one, and it is honest about what is not
  built.
- At **Reasoned** every step can answer "why", and the walk is a test of the design, not of the code.
- At **Seen** the real panes are on the card and the code is checked against the flows on every commit.
- At **Closed** the loop runs: what the founder leaves on the page comes back as a commit.

## Measures, as the tool counts them

- `jobs_first_release`: the job map's jobs on the first-release list (`"switch": true` on a job in the `graph`
  source, or `"first_release": true` on a job in the `jobs` source) that happen in service; `jobs_covered` the ones with a flow.
- `steps`, `steps_with_surface` (the surface is in the registry and has regions), `steps_unbuilt`,
  `steps_unbuilt_with_design`.
- `moves_with_built_as`: counted, not judged; the measure is that a drift is written, which the tool cannot know
  by itself, so level 2 takes this as "present where the walk disagrees with a named run".
- `patterns_on_steps`, `patterns_with_reason` (the ref resolves to a pattern that has a stance and a reason, or the
  step carries a link).
- `rulings`, `rulings_quoted` (validate's quote check passes).
- `jobs_with_named_run`.
- `built_steps`, `built_steps_drivable` (every move into the step has a drive, or the drive is null with a reason).
- `captures` and `dummy_disagrees` come with `saltflow capture`.
- `notes_closed_with_commit`, `breaks_stale`.

The bar is the same for every product. What differs is the manifest: which list is "first release", which words
are the building blocks, where the rulings live. A product with no job map stops at level 1 until it has one;
for a new product, that is the first thing to write.
