# Provisional headless engine functional vertical

This document describes reconstructed execution Gates 1 through 5 of
[issue #49](https://github.com/loomitz/ColorLUThier/issues/49). The vertical is
an implementation checkpoint, not a stable project format, professional image
pipeline, color-managed display contract, or Host-application compatibility
claim.

The engine requires Python 3.12 and uses only the Python standard library. It
does not require a display server and does not import AppKit, Qt, Tk, WinUI, a
GPU API, or a concrete concurrency framework.

## Gate reconstruction

### Gate 1: baseline adoption

The production package preserves the accepted Portable Cube subset in an
implementation that is independent from `portable_cube_harness`. The harness
remains a test-only oracle and production code does not import it. Existing
synthetic fixtures remain the deterministic evidence corpus.

Every shortcut introduced for the end-to-end path is named as provisional:

- reference decoding accepts only bounded RGB8 PPM P6 and PNG data;
- source color context remains `unknown`; the current preview and lattice-only
  export path is explicitly provisional rather than color-managed behavior;
- preview surfaces are unmanaged and are not reference display output;
- preview mix and bypass are a minimal imported-LUT operation, not the future
  authoring model; and
- canonical Cube artifact generation reserializes the imported Portable Cube
  lattice and does not bake mix or bypass. Its `ordinary_export_status` is
  `blocked-pending-explicit-color-contexts`.

Gate 1 exits only when both the inherited corpus and the engine suite pass on
redistributable synthetic inputs. Licensed or private issue #13 executables,
captures, recordings, screenshots, or LUTs are not inputs to this gate.

### Gate 2: single engine seam

`ColorDocument` is the sole public acceptance facade. A caller submits an
immutable command with `ColorDocument.apply(command)` and reads complete
immutable state with `ColorDocument.snapshot()`. Commands, snapshots,
diagnostics, surfaces, artifacts, and job records are value objects; none
exposes parser, evaluator, serializer, UI, or mutable internal state.

The supported vertical commands are:

- `OpenReferenceImage`;
- `LoadPortableCube`;
- `ConfigureColorTransformation`;
- `DeclareColorContexts`;
- `RequestPreview`;
- `RequestFullResolutionEvaluation`;
- `RequestCanonicalPortableCubeExport`; and
- `CancelJob`.

The name may later evolve to `EngineSession`, but clients must continue to use
one facade during any migration. A UI shell is an adapter that translates user
intent into these commands and renders snapshots. It must not parse LUTs,
evaluate interpolation, serialize exports, or maintain parallel authored
state.

No provisional UI source was present in the transferred Git tree, so this
reconstruction cannot claim an adapter-compatibility test that does not exist.
It changes no UI and keeps the facade suitable for a recovered or future thin
adapter; compatibility with any missing client remains explicitly unverified.

`WorkExecutor` is the narrow scheduling seam. `InlineExecutor` is the default
deterministic headless adapter. `colorluthier_engine.testing.ControlledExecutor`
lets acceptance tests advance specific jobs without threads, clocks, sleeps,
or races. Executor callbacks and calls into one `ColorDocument` must be
serialized; this gate does not promise concurrent method safety.

### Gate 3: revision and job model

The original three revision counters have distinct meanings:

- `DocumentRevision` identifies committed document changes that affect authored
  interpretation. Opening a different reference, loading a different
  transformation, changing an effective transformation setting, or changing
  the selected lane or Working color context advances it. Proof-, Display-, or
  Export-only declarations and job lifecycle changes do not.
- `TransformationRevision` identifies a loaded or reconfigured Color
  transformation. Opening a reference does not advance it.
- `SnapshotRevision` identifies every externally observable publication or job
  transition, including progress. Reading a snapshot does not advance it.

Revisions and identifiers are monotonic within one `ColorDocument` and are
never reused. A no-op command does not create a revision. Previously returned
snapshots are immutable and remain a record of what the caller observed.

Every processing job captures a `RevisionBasis` containing the document,
reference, transformation, interpretation, viewing, and export revisions
present when its candidate work began. The document revision records
provenance; it is not a universal output-validity key. Publication compares
only the revisions on which that output purpose depends:

- preview depends on reference, transformation, interpretation, and viewing;
- full-resolution evaluation depends on reference, transformation, and
  interpretation, but not viewing or export;
- canonical Portable Cube artifact generation depends only on transformation;
  and
- a future ordinary export will depend on transformation and export.

A preview publishes an original/processed surface pair with one shared basis.
A canonical Cube artifact records the basis that produced it. A job may
publish only when both conditions remain true at completion:

1. its purpose-specific captured revisions are still current; and
2. it is still the latest request for its output purpose.

Otherwise, it terminates as `stale` and publishes nothing. This rule covers an
authored change during processing as well as out-of-order completion of two
requests for the same purpose.

Jobs move through `queued`, `running`, and one terminal state: `succeeded`,
`failed`, `cancelled`, or `stale`. Progress is an integer pair with a fixed,
positive total. Completed units remain in the closed interval from zero
through the total and increase monotonically. Preview work reports one unit per
source row plus one completion/publication unit. Canonical export uses one
serialization unit plus one validation/publication unit. Full-resolution work
uses the same one-unit-per-source-row plan plus one validation/publication unit.

Cancellation marks a non-terminal job as `cancelled` before publication. A
controlled executor can therefore prove cancellation both before the first
step and after one or more progress steps. No clock or timing threshold is part
of the contract.

Immediate commands are transactional: a rejected decode, parse, or validation
operation leaves the last valid document state unchanged. Processing is also
transactional: candidates remain private until complete validation and a final
staleness check. Failure, cancellation, and stale completion do not replace a
previously published valid preview, full-resolution result, or export. A later
authored revision clears only the derived outputs whose purpose-specific
revisions it changes. An unrelated change may leave a valid output with an
older document revision in its recorded provenance.

### Gate 4A: explicit Color-context scaffold

Gate 4A defines an immutable, declaration-only scaffold for explicit Color
contexts. It introduces role-specific value types for Source, Working, Proof,
and Display color contexts, plus a standalone `ExportColorContext`. Every known
context belongs to exactly one explicitly selected `icc-still-image` or
`ocio-aces` Color-management lane. ICC identity requires exact profile content.
OCIO/ACES identity requires an exact color-space name and a content-addressed
manifest covering the configuration, every resolved resource, and every
context-variable binding. Sample interpretation is identified separately by
an explicit encoding-specification identity. A label, path, role, or default is
never sufficient identity and never selects a lane. A known Display color
context additionally requires a content-identified viewing interpretation.

The initial document has no selected lane and remains inspection-only. That
status is derived by the Gate 4A projection rather than supplied as mutable or
parallel state. The current bootstrap PPM and PNG formats retain an unknown
Source color context; no Source identity is inferred from their encoding. Proof
and Display color contexts are absent rather than synthesized. Unknown or
incomplete identities
continue to block color-dependent authoring, managed viewing, validation, and
ordinary export.

`ExportColorContext` is declared independently from Working, Proof, and Display
state. It requires explicit, known input and output color identities and
encodings, numeric domain and range, interpolation convention, and Host or
format profile. Its structure has no Proof or Display reference, so neither
viewing leg can be inherited by or baked into an ordinary export.

This scaffold adds no color-context configuration command, CMM, conversion,
image operation, runtime dependency, or dependency adapter. It does not change
the provisional canonical Cube artifact, its bytes or digest, or the headless
CLI success JSON. Canonicalization remains imported-lattice inspection data and
ordinary export remains blocked.

The legacy `source_color_context_status` and `interpretation_status` fields
remain available and serializable on `ReferenceImageSnapshot`; construction
validates that they agree with the structured Source context. The deterministic
headless smoke test pins the existing CLI JSON and canonical Cube digests.

Gate 4A stops at the typed scaffold. Gate 4B adds its transactional declaration
and revision behavior without changing these identity requirements.

### Gate 4B: revision-aware whole-value declaration

`DeclareColorContexts` accepts one immutable `ColorContextDeclaration` and an
expected `ColorContextRevisionBasis` through `ColorDocument.apply()`. The
declaration replaces the complete caller-owned value in one transaction:
selected Color-management lane, Working, Proof, Display, and Export color
contexts. `None` explicitly removes an optional Proof, Display, or Export color
context; there is no patch or role-specific configuration command that could
expose a partially updated declaration.

Source color context is deliberately absent from `ColorContextDeclaration`.
It remains owned by its `ReferenceImageSnapshot` and cannot be reassigned or
carried into another Reference image by this command. Reopening the exact same
encoded Reference image and format is unchanged. Opening a different Reference
image replaces the Reference-owned Source color context with the value supplied
by `ColorDocument`, currently explicit unknown because the bootstrap image
adapter exposes no color metadata, while preserving the caller-owned
declaration.

The immutable value types enforce static lane invariants before publication.
Every known Working, Proof, or Display color context must use the explicitly
selected Color-management lane. A declared Export color context requires a
selected lane, and its already-known input and output identities must use that
same lane. Unknown identities remain inspection-only; they do not select a
default or authorize relabeling or Cross-lane conversion. Proof and Display
remain structurally absent from `ExportColorContext`.

Once selected, a Color-management lane cannot be removed or replaced inside
the same `ColorDocument`. Such a change requires a new authoring scope; Gate 4B
does not reinterpret an existing Color transformation or imply a Cross-lane
conversion.

The expected basis supplies optimistic conflict detection for whole-value
replacement. If the requested declaration already equals the current value,
the command returns `unchanged` before conflict checking, so an exact retry is
idempotent and advances no revision. Otherwise, the expected interpretation,
viewing, and export revisions must all match the current basis. A mismatch is
rejected with `COLOR_CONTEXT_REVISION_CONFLICT`; rejection leaves the document,
outputs, jobs, and revisions unchanged.

Three monotonic document-local counters describe independent semantics:

- `InterpretationRevision` advances when the selected lane or Working color
  context changes, and when a different Reference image establishes a new
  Source color-context binding;
- `ViewingRevision` advances when Proof or Display color context changes; and
- `ExportRevision` advances when Export color context changes.

One declaration may advance more than one of these counters. A committed
declaration advances `DocumentRevision` once only when interpretation changes;
viewing-only and export-only state remain outside authored interpretation.
Every committed declaration advances `SnapshotRevision` once, regardless of
how many semantic counters changed. An unchanged or rejected declaration
advances none. Job lifecycle publications continue to advance only
`SnapshotRevision`.

Invalidation follows the purpose-specific revision rules established in Gate
3. Interpretation or viewing changes clear a published preview and make
affected in-flight preview candidates stale at their publication check. An
export-only declaration does neither. Color-context declarations and Reference
image changes preserve canonical Portable Cube artifacts and do not stale
canonicalization jobs because those artifacts depend only on the Color
transformation. A future ordinary export will be invalidated only by its
transformation or Export color-context revision; it will not inherit Working,
Proof, Display, or Reference state.

Gate 4B remains declaration and revision infrastructure. It adds no CMM,
conversion, managed image operation, UI, GPU path, runtime dependency, project
schema, or ordinary-export command. `inspection_only` therefore remains true,
and ordinary export remains blocked. The provisional canonical Cube bytes,
their digest, and the exact headless CLI success JSON remain unchanged.

### Gate 5: bounded full-resolution evaluation

`RequestFullResolutionEvaluation` adds a distinct job and result purpose
through the existing `ColorDocument.apply()` and `snapshot()` seam. It is not a
renamed preview and does not create an executor, cache, or resource-management
API. Admission, scanline planning, storage accounting, job history, and result
retention remain private implementation policy.

The job evaluates the complete current Reference image at its Source
resolution. It uses the same Source RGB8 normalization, selected Portable Cube
interpolation, bypass, mix, binary64 arithmetic order, and binary32 storage as
the processed preview. It publishes one `processed-full-resolution` surface;
the authored Reference image already owns the source values, so Gate 5 does not
retain a duplicate original surface. Proof and Display are viewing state and
are neither evaluated nor baked. Export color context is also outside this
purpose.

Work is deterministic: each source scanline is one cooperative unit and one
final unit validates staleness and publishes the complete immutable result.
Progress is monotonic and bounded. A result publishes only if its captured
reference, transformation, and interpretation revisions remain current and it
is still the latest full-resolution request. Viewing-only and export-only
declarations neither clear nor stale it. Reference, transformation, or
interpretation changes invalidate a published result and make an in-flight
candidate stale.

Storage admission is overflow-safe and occurs before a job record is created.
The provisional pixel ceiling is intentionally lower than the Reference-image
ceiling so boundary evidence remains practical. Output bytes and the temporary
mutable buffer that coexists during conversion to immutable bytes are accounted
separately. Failure, cancellation, and stale out-of-order completion publish
nothing and preserve the latest still-valid result. Successful publication
replaces that single retained derived result deterministically; authored state
is never an eviction target.

Gate 5 remains a bounded CPU evidence path. It adds no batch API, ordinary
export, CMM, Proof or Display conversion, GPU path, UI, project schema, runtime
dependency, or production import of the deterministic test executor.

## Public module surface

The package layout keeps deep implementation modules behind the facade:

```text
colorluthier_engine/
  __init__.py       public commands, snapshots, executor seam, ColorDocument
  __main__.py       headless filesystem and JSON adapter
  _limits.py        shared executable resource limits
  document.py       transactional state, revisions, jobs, publication gates
  execution.py      framework-neutral WorkExecutor and InlineExecutor
  testing.py        deterministic ControlledExecutor for acceptance tests
  _image_source.py  replaceable image-source port and stdlib adapter
  _reference.py     provisional bounded synthetic-image adapter
  _portable_cube.py production Portable Cube adapter
  _processing.py    cooperative preview, full-resolution, and export plans
```

Caller-authored intent changes only through `ColorDocument.apply()`.
Executor-owned work steps may publish job transitions and completed derived
results; `snapshot()` only observes the resulting immutable projection. The
leading-underscore modules are implementation details and are not product
integration seams.

## Derived surfaces and provisional arithmetic

Preview publication creates two complete `DerivedSurfaceSnapshot` values:
`original-preview` and `processed-preview`. Both use `rgb-f32be`: tightly packed
big-endian IEEE 754 binary32 RGB components with a row stride of
`width * 12`. The representation is toolkit-independent and preserves finite
out-of-range LUT results instead of silently clamping them for an 8-bit widget.

Source RGB8 components are normalized by division by 255. The current processed
preview is provisional and uses binary64 evaluation followed by
`source + mix * (evaluated - source)`, then stores binary32 components. Bypass
copies the normalized source values. This behavior does not define global
adjustments, compositing, masks, a display transform, or future export baking.
Full-resolution evaluation shares that arithmetic implementation but publishes
only the processed surface. Its result is source-resolution processing evidence,
not a display-ready surface or ordinary export.

Portable Cube parsing and evaluation retain the existing strict contract:
Basic Latin text, LF canonical output, exactly one `LUT_3D_SIZE` from 2 through
65, red-fastest sample order, finite binary32 table samples, implicit closed
domain `[0,1]`, explicit trilinear or tetrahedral interpolation, fixed
provisional CPU arithmetic order, and `.9g` canonical serialization. Unsupported
directives fail closed. A canonical export is reparsed and compared before its
in-memory artifact can be published.

## Bounded resources and safe diagnostics

Current limits are deliberately conservative bootstrap limits:

| Boundary | Provisional limit |
| --- | --- |
| Reference encoded input | 32 MiB |
| Reference dimension | 4096 pixels per axis |
| Reference pixel count | 4,194,304 pixels |
| PPM | P6, RGB8, `maxval` 255, exact raster length |
| PNG | RGB/RGBA, 8-bit, non-interlaced, standard filters, bounded inflate |
| Portable Cube encoded input | 16 MiB |
| Portable Cube lattice | 2 through 65 samples per axis |
| Active document jobs | 4 |
| Queued work | 8,194 remaining scanline/publication units |
| Retained job history | 128 records |
| Full-resolution pixels | 262,144 pixels |
| Full-resolution immutable output | 3 MiB |
| Full-resolution conversion scratch | 3 MiB |
| Retained full-resolution results | 1, latest only |
| Controlled test-executor default queue | 16 jobs |

PNG chunk structure, CRCs, dimensions, decompressed length, scanline filters,
and trailing data are validated before publication. Reference and LUT payloads
are immutable bytes. Diagnostics carry stable English classifier codes plus
bounded factual context. They do not contain absolute paths, payload bytes,
exception representations, timestamps, secrets, or private-evidence
identifiers.

No third-party runtime dependency is introduced by this vertical. That avoids
prejudging redistribution and security decisions for the professional image-I/O
and GPU foundations. Repository source and synthetic test material remain
subject to the repository's declared REUSE licensing metadata.

## Headless command-line adapter

The CLI runs the complete open, load, preview, and canonical-export path through
the public `ColorDocument` seam:

```console
python3.12 -m colorluthier_engine \
  --reference reference.ppm \
  --cube input.cube \
  --interpolation tetrahedral
```

Use `--reference-format ppm-p6-rgb8` or `--reference-format png-rgb8` to select
a decoder explicitly; the default `auto` inspects only the encoded signature.
`--mix` and `--bypass` configure the provisional preview operation.

The command emits one deterministic, English JSON record to stdout on success.
It reports revisions, identifiers, dimensions, progress, and result status but
does not emit paths, input payloads, surface pixels, or content digests. Failures
emit one bounded JSON diagnostic to stderr. Exit status `0` is success, `2` is
a command, validation, input, or publication failure, and `3` is an unexpected
internal failure.

The engine result is an immutable in-memory canonicalization artifact. It is
not an ordinary color-managed export. Gates 4A and 4B provide a typed, separately
declared Export color context, but no ordinary-export command or
representability validation. `ordinary_export_status` therefore remains
`blocked-pending-explicit-color-contexts`. The optional filesystem adapter
stages, flushes, and atomically replaces one explicitly requested target:

The `RequestCanonicalPortableCubeExport`, `canonical_cube_export`, and
`--export-output` names deliberately identify the revision-bound output
operation required by Gate 3. They do not relax that fail-closed status or
reserve the future ordinary export contract. A later gate must implement the
ordinary-export command and validation against the declared Export color
context before such an operation can exist.

```console
python3.12 -m colorluthier_engine \
  --reference reference.png \
  --cube input.cube \
  --interpolation trilinear \
  --export-output canonical.cube
```

Input paths are opened once, verified from the open descriptor as regular
files, and use no-follow open semantics on platforms that provide them. The
output parent must already exist. A filesystem failure removes the temporary
file and emits no success record. This edge operation is for deterministic
inspection and corpus workflows; it is not a stable export-format, ordinary
product-export, or project-publication API.

## macOS verification commands

From the repository root, use the selected Python 3.12 interpreter:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -v
python3.12 -m compileall -q colorluthier_engine portable_cube_harness tests
```

Run the independent Portable Cube corpus in fresh generated directories:

```console
python3.12 tests/materialize_portable_cube_corpus.py \
  --output-dir build/portable-cube-inputs
python3.12 -m portable_cube_harness \
  --descriptor tests/fixtures \
  --cube build/portable-cube-inputs \
  --output-dir build/portable-cube-corpus
```

A redistributable, one-pixel headless smoke input can be generated without an
image library:

```console
SMOKE_DIR="$(mktemp -d)"
python3.12 - "$SMOKE_DIR/reference.ppm" <<'PY'
from pathlib import Path
import sys

Path(sys.argv[1]).write_bytes(b"P6\n1 1\n255\n" + bytes((64, 128, 192)))
PY
python3.12 -m colorluthier_engine \
  --reference "$SMOKE_DIR/reference.ppm" \
  --cube tests/fixtures/identity-2/input.cube \
  --interpolation tetrahedral \
  --export-output "$SMOKE_DIR/canonical.cube" \
  > "$SMOKE_DIR/report.json"
python3.12 -m json.tool "$SMOKE_DIR/report.json"
```

Record the exact macOS version, architecture, Python executable and version,
test counts, exit statuses, corpus aggregate digest, and CLI JSON when closing
the gate. Do not substitute documentation claims for live verification.

## Deferred decisions and scope boundaries

This vertical deliberately leaves irreversible choices to their Wayfinder
issues:

- [#8](https://github.com/loomitz/ColorLUThier/issues/8) defines the first
  professional macOS release boundary. This vertical makes no release or
  replacement claim.
- [#9](https://github.com/loomitz/ColorLUThier/issues/9) defines project,
  preset, history, undo/redo, and reproducibility semantics. No engine snapshot
  in this vertical is a project file.
- [#10](https://github.com/loomitz/ColorLUThier/issues/10) selects permanent
  application and platform boundaries. Python package layout and executor
  adapters here do not select a final UI stack or production toolchain.
- [#12](https://github.com/loomitz/ColorLUThier/issues/12) defines external-LUT
  representability. Only the accepted Portable Cube subset is implemented; no
  new dialect, domain, shaper, decomposition, mask, or inferred edit is added.
- [#14](https://github.com/loomitz/ColorLUThier/issues/14) defines authoring
  operations and composition. Imported LUT evaluation, interpolation, bypass,
  and provisional mix do not imply global adjustments, curves, matching, masks,
  or a generic graph.
- [#20](https://github.com/loomitz/ColorLUThier/issues/20) selects the
  professional reference-image dependency envelope. The standard-library PPM
  and PNG decoder remains a bounded synthetic-fixture adapter.
- [#22](https://github.com/loomitz/ColorLUThier/issues/22) selects a GPU viewport
  only after measured parity. This vertical is CPU-only and defines no display,
  HDR/EDR, or platform-surface backend.

ADR 0001 remains authoritative. Gates 4A and 4B provide typed Source, Working,
Proof, Display, and Export color contexts, ICC versus OCIO/ACES lane
enforcement, and declaration revision infrastructure. The bootstrap adapter's
Source color context remains explicitly unknown, preview remains unmanaged,
and canonicalization remains lattice-only. Ordinary export remains blocked and
no derived surface may be presented as color-managed authoring or professional
export.

The vertical also excludes a stable project format, batch execution, a generic
authoring graph, new UIs, platform-specific state,
professional codec dependencies, concrete ICC/OCIO integration, GPU execution,
additional LUT dialects, and formulas inferred from qualitative or private
issue #13 evidence.
