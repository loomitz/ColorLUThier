# Internal Test UI adapter

The `internal_test_ui_adapter` package is a framework-neutral boundary between
future Internal Test UI rendering and the public headless-engine seam. It is a
deep module: callers dispatch a small set of immutable UI intents and render one
immutable state, while the adapter hides command construction, document
ownership, job coordination, snapshot ordering, and executor callbacks.

## Public contract

`InternalTestUiAdapter` owns exactly one `ColorDocument`. Its public operations
are:

- `dispatch(intent)`, which translates one frozen UI intent into one public
  engine command and returns a `RenderUpdate`;
- `accept_snapshot(snapshot)`, which applies the adapter's snapshot watermark;
  and
- `current`, which returns the current immutable `RenderState`.

The intent vocabulary covers opening a Reference image, loading and configuring
a Portable Cube transformation, replacing a complete Color-context declaration,
requesting preview or full-resolution evaluation, inspecting the canonical
Portable Cube artifact, and cancelling a job. `DeclareColorContextsIntent`
carries both the complete `ColorContextDeclaration` and the exact
`ColorContextRevisionBasis` from which it was prepared.

There is deliberately no ordinary-export intent. `RenderState` always reports
`blocked-pending-explicit-color-contexts`, preserving the engine's current public
capability chain. Canonical Portable Cube bytes remain inspectable through the
exact artifact retained by the `DocumentSnapshot`; this is not ordinary export.

## Snapshot and feedback rules

`RenderState` retains the exact `DocumentSnapshot` instance accepted by the
adapter. Authored Color contexts, jobs, surfaces, and artifacts are never copied
into a parallel UI model. Render-only feedback consists of the last command
status, submitted job identifier, public `Diagnostic`, and ordinary-export
capability. Consumers classify errors with `Diagnostic.code` and read bounded
details from `Diagnostic.context`; they do not parse English messages.

The snapshot revision is the rendering watermark. A lower revision is rejected
without replacing `current`. At the same or a higher revision, the candidate
must also equal the immutable current snapshot of the `ColorDocument` owned by
this adapter; otherwise it is rejected as not owned and cannot poison the
watermark or feedback. An equal owned revision is accepted, because a rejected
command can legitimately update render feedback while engine state remains at
the same revision. A higher owned revision replaces the current snapshot.

## Serialization and work delivery

One reentrant lock serializes `dispatch`, `accept_snapshot`, `current`, and every
engine work-step callback. The adapter wraps the caller-supplied public
`WorkExecutor` (or an `InlineExecutor` by default), runs each step under that
same lock, and automatically refreshes `current` after every step. This makes
scanline progress and terminal state observable without polling the document,
and it prevents stale publication from replacing the latest valid result.

The production adapter imports only the public `colorluthier_engine` package
root. It has no parser, evaluator, serializer, harness, UI toolkit, event-loop,
GPU, export-runtime, or other runtime dependency. Deterministic tests may inject
the public test-only `ControlledExecutor`; production code never imports it.

Run the public acceptance tests with:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest \
  tests.test_internal_test_ui_adapter -v
```
