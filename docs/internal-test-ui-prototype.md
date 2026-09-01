# Disposable browser Internal Test UI

This prototype asks one question:

> Can a disposable, single-process browser surface make the accepted Internal
> Test UI adapter operable and visible without duplicating domain state?

It is an engine-testing surface, not product UI, a native application shell, or
a permanent browser-toolkit decision. Its banner keeps that status visible on
every rendered page.

## Start on macOS

From the repository root, run:

```console
python3.12 -m internal_test_ui_prototype
```

The command binds an HTTP server to `127.0.0.1` on an ephemeral port, prints the
exact URL, and opens it with Python's standard-library browser controller. Use
Ctrl-C to stop the server. A fixed loopback port is available when necessary:

```console
python3.12 -m internal_test_ui_prototype --port 8765
```

`--no-open` starts the same surface without opening a browser and exists for
deterministic tests and local smoke checks. The server never binds a non-loopback
address.

## In-memory boundary

One `PrototypeApplication` owns exactly one `InternalTestUiAdapter` and one
bounded `ManualExecutor`. The adapter continues to own the sole
`ColorDocument`. The manual executor implements the public `WorkExecutor` shape
outside the engine and holds work steps until a Step or Run action advances
them. It does not import the engine test executor.

The HTTP layer has no sessions, cookies, local storage, database, persistence,
second Python runtime, or domain IPC. Each request performs one action and each
response renders the complete frame from exactly one read of `adapter.current`.
The UI does not copy jobs, contexts, surfaces, or artifacts into another domain
model.

## Actions and inputs

The UI can:

- open the embedded wholly synthetic 2×2 PPM Reference image;
- load the embedded accepted identity Portable Cube;
- read an explicitly selected PPM, PNG, or Cube local path without writing it;
- select trilinear or tetrahedral interpolation and change bypass or mix;
- submit a complete synthetic ICC declaration containing independent Working,
  Proof, Display, and Export Color contexts;
- request preview, bounded full-resolution evaluation, and canonical artifact
  inspection;
- step, run, or cancel pending work;
- run a deterministic stale demonstration that completes the newer job before
  the older job; and
- submit a malformed Reference input to expose the stable diagnostic while
  preserving last-valid engine values.

The Color-context form carries the interpretation, viewing, and export
revisions rendered with that form. The application constructs the expected
`ColorContextRevisionBasis` from those submitted values; it never silently
substitutes the current basis for a stale page.

## Render contract

Every frame shows the snapshot and document revisions, exact Reference and
transformation metadata, declared contexts and their semantic revisions, job
purpose/state/progress, stable diagnostic code with bounded message and context,
and the canonical artifact's exact metadata and bytes.

Original and processed surfaces remain diagnostic presentations. The UI shows
their identifiers, revision basis, dimensions, stride, encoding, pixel-byte
count, and a bounded hexadecimal byte prefix. It performs no color conversion,
color arithmetic, or image/LUT/domain parsing, evaluation, or serialization.
Every surface remains visibly labeled `provisional-unmanaged` or `diagnostic
visualization`.

Ordinary export remains visibly and immutably
`blocked-pending-explicit-color-contexts`. The canonical artifact is inspection
evidence and is never written as an ordinary export.

## #56 validation boundary

The minimal component tests use no sleeps:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest \
  tests.test_internal_test_ui_prototype -v
```

They cover action mapping, one-snapshot rendering, the independent Export Color
context, manual progress/cancellation/reverse order, malformed-input
last-valid preservation, loopback start/request/shutdown, and import boundaries.
Complete browser automation, the full end-to-end flow, and the macOS
create-and-close acceptance smoke belong exclusively to issue #57.

The Python sources and embedded synthetic data are GPL-3.0-or-later with SPDX
headers. This documentation is CC-BY-4.0 through the repository's REUSE mapping.
No third-party fixture, toolkit, or runtime dependency is introduced.
