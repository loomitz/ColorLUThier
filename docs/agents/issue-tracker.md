# Issue tracker: GitHub

Issues and planning artifacts for this repository live in GitHub Issues. Use the `gh` CLI for operations.

## Conventions

- Create, read, edit, comment on, label, assign, and close issues using `gh`.
- Infer `loomitz/ColorLUThier` from the repository remote.
- Pull requests are not treated as a triage request surface.

## Wayfinding operations

- A Wayfinder map is one issue labelled `wayfinder:map`.
- Decision tickets are native sub-issues labelled `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`.
- Use GitHub's native issue dependencies for blocking relationships.
- The frontier consists of the map's open, unblocked, and unassigned child issues, in map order.
- Claim a ticket by assigning it to the active developer before doing any work.
- Resolve a ticket by posting its answer as a comment, closing it, and appending a concise linked pointer to the map's "Decisions so far" section.
- If native sub-issues or dependencies are unavailable, use a task list in the map and explicit `Part of` / `Blocked by` references in ticket bodies.
