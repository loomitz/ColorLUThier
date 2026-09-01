# Internal Test UI end-to-end acceptance

This acceptance slice tests the disposable Internal Test UI as an external
operator would encounter it. It does not add production behavior, choose a
permanent UI toolkit, or claim product readiness.

The tests use only Python's standard library and public ColorLUThier packages.
They do not import engine internals, the Portable Cube harness, test-only
executors from the engine, or the prototype's private modules. They create no
reference, LUT, screenshot, or artifact output outside temporary directories.

## Start the disposable UI

From the repository root, run:

```console
python3.12 -m internal_test_ui_prototype
```

The command binds only to `127.0.0.1`, chooses an ephemeral port by default,
prints the exact URL to stdout, and opens it with the standard-library browser
launcher. Stop it with Control-C. For a headless manual launch, use:

```console
python3.12 -m internal_test_ui_prototype --no-open
```

## Acceptance commands

Run the headless intent-to-snapshot-to-render acceptance only:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -p 'test_internal_test_ui_e2e.py' -k Headless -v
```

Run the real loopback HTTP acceptance only:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -p 'test_internal_test_ui_e2e.py' -k Http -v
```

Run the macOS real-surface smoke only:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -p 'test_internal_test_ui_e2e.py' -k MacOs -v
```

Run the complete issue #57 acceptance slice:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -p 'test_internal_test_ui_e2e.py' -v
```

Run the complete repository suite:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -v
```

## What is accepted

The headless and HTTP paths independently exercise these public behaviors:

- Synthetic Reference image and Portable Cube loading.
- Tetrahedral interpolation, bypass, and mix configuration.
- A complete color-context declaration submitted with all three hidden expected
  revisions, including an explicit Export color context independent of Proof
  and Display.
- Preview submission, visible scanline progress, and terminal publication.
- Full-resolution progress and cancellation without partial publication.
- Newest-before-oldest completion, with the older job visibly stale and the
  newest valid full-resolution result retained.
- Canonical Portable Cube inspection while ordinary export remains explicitly
  blocked.
- A malformed Reference command with its diagnostic code visible while every
  previously valid Reference, transformation, context, surface, job, and
  canonical-artifact value remains exact.

The HTML parser observes forms, hidden revision-basis fields, stable
`data-testid` regions, job states, and progress attributes. It does not infer
domain state from pixels or duplicate any color arithmetic.

## macOS surface contract

The smoke runs the documented start command without `--no-open`. It forces the
standard-library browser launcher to open Safari, waits boundedly until Safari
reports exactly the printed ephemeral URL, requests that live server once, and
closes only the Safari document whose URL is exactly equal to that URL. It never
quits Safari or closes unrelated windows or tabs, and it does not rely on a
pre-existing tab.

The macOS host must provide `/Applications/Safari.app`, `/usr/bin/open`, and
`/usr/bin/osascript`, and its existing automation policy must permit the exact
window query and close operation. The test never grants or changes permissions.
A non-macOS host, an Apple Events denial, a prompt, or a timeout is a failing
environmental gate rather than a skipped success. The headless and HTTP helper
paths themselves remain portable.

## Deliberate limits

This slice performs no screenshots, browser pixel comparison, host-application
qualification, color-value oracle calculation, artifact export, persistence,
or runtime dependency installation. Those absences must not be interpreted as
evidence for visual fidelity, colorimetric correctness, ordinary-export
readiness, or a permanent application architecture.
