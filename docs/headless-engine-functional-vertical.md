# Provisional headless engine functional vertical

This document describes the reconstructed first three execution gates of
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
- `RequestPreview`;
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

Three revision counters have distinct meanings:

- `DocumentRevision` identifies committed authored intent. Opening a different
  reference, loading a different transformation, or changing an effective
  transformation setting advances it. Job lifecycle changes do not.
- `TransformationRevision` identifies a loaded or reconfigured Color
  transformation. Opening a reference does not advance it.
- `SnapshotRevision` identifies every externally observable publication or job
  transition, including progress. Reading a snapshot does not advance it.

Revisions and identifiers are monotonic within one `ColorDocument` and are
never reused. A no-op command does not create a revision. Previously returned
snapshots are immutable and remain a record of what the caller observed.

Every processing job captures a `RevisionBasis` containing the document,
reference, and transformation revisions used to produce its candidate result.
A preview publishes an original/processed surface pair with one shared basis.
A canonical Cube artifact records the basis that produced it. A job may
publish only when both conditions remain true at completion:

1. its captured basis is still the current basis; and
2. it is still the latest request for its output purpose.

Otherwise, it terminates as `stale` and publishes nothing. This rule covers an
authored change during processing as well as out-of-order completion of two
requests for the same purpose.

Jobs move through `queued`, `running`, and one terminal state: `succeeded`,
`failed`, `cancelled`, or `stale`. Progress is an integer pair with a fixed,
positive total. Completed units remain in the closed interval from zero
through the total and increase monotonically. Preview work reports one unit per
source row plus one completion/publication unit. Canonical export uses one
serialization unit plus one validation/publication unit.

Cancellation marks a non-terminal job as `cancelled` before publication. A
controlled executor can therefore prove cancellation both before the first
step and after one or more progress steps. No clock or timing threshold is part
of the contract.

Immediate commands are transactional: a rejected decode, parse, or validation
operation leaves the last valid document state unchanged. Processing is also
transactional: candidates remain private until complete validation and a final
staleness check. Failure, cancellation, and stale completion do not replace a
previously published valid preview or export. A later authored revision clears
derived outputs because their basis no longer describes the current document.

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
  _processing.py    cooperative preview and canonical-export work plans
```

Only `ColorDocument.apply()` mutates engine state. `snapshot()` observes it.
The leading-underscore modules are implementation details and are not product
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
| Retained job history | 128 records |
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
not an ordinary color-managed export: Gates 1–3 have no typed Export color
context, and `ordinary_export_status` remains
`blocked-pending-explicit-color-contexts`. The optional filesystem adapter
stages, flushes, and atomically replaces one explicitly requested target:

The `RequestCanonicalPortableCubeExport`, `canonical_cube_export`, and
`--export-output` names deliberately identify the revision-bound output
operation required by Gate 3. They do not relax that fail-closed status or
reserve the future ordinary export contract; Gate 4 must introduce the typed
Export color context before such an operation can exist.

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

ADR 0001 remains authoritative. Typed Source, Working, Proof, Display, and
Export color contexts and ICC versus OCIO/ACES lane enforcement belong to Gate
4. Until then, unknown source context, unmanaged preview, and lattice-only
canonicalization are visibly provisional. Ordinary export remains blocked and
neither surface may be presented as color-managed authoring or professional
export.

The vertical also excludes a stable project format, full-resolution/batch
execution, a generic authoring graph, new UIs, platform-specific state,
professional codec dependencies, concrete ICC/OCIO integration, GPU execution,
additional LUT dialects, and formulas inferred from qualitative or private
issue #13 evidence.
