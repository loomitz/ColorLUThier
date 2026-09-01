# Internal Test UI end-to-end acceptance

This acceptance slice tests the disposable Internal Test UI as an external
operator would encounter it. It does not add production behavior, choose a
permanent UI toolkit, or claim product readiness.

Issue #57 owns acceptance code only. If a test exposes a production defect,
create a blocking child bug with the smallest sanitized public reproduction:
the exact command or rendered-form action, bounded non-private input, diagnostic
code, expected result, and actual result. Do not fix production from #57.

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
launcher. Stop it with Control-C. The test driver adds `--no-open` when it owns
a headless subprocess and launches that child with the same `sys.executable`
that is running the acceptance suite. The driver requests graceful SIGINT
shutdown on POSIX hosts and uses bounded process termination on Windows, where
SIGINT is not a portable `Popen.send_signal()` contract; a child that exits
before that controlled shutdown still fails acceptance. Both the initial wait
and any wait after forced termination have finite deadlines. A repeated timeout
leaves the driver visibly active and fails cleanup rather than claiming success.
Child output collected during shutdown never enters exception text; cleanup
failures report only the return code and non-sensitive byte counts.
The bounded readiness deadline is 60 seconds to absorb cold-start latency on
hosted macOS runners; each shutdown wait retains its independent 10-second
deadline.

## Acceptance commands

Run the headless intent-to-snapshot-to-render acceptance only:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -p 'test_internal_test_ui_e2e.py' -k Headless -v
```

Run the macOS real-surface smoke only:

```console
COLORLUTHIER_RUN_REAL_SURFACE_SMOKE=1 PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -p 'test_internal_test_ui_e2e.py' -k test_documented_command_opens_and_closes_only_its_real_surface -v
```

Run the complete issue #57 acceptance slice:

```console
PYTHONDONTWRITEBYTECODE=1 python3.12 -m unittest discover -s tests -p 'test_internal_test_ui_e2e.py' -v
```

## What is accepted

The headless and HTTP paths independently exercise these public behaviors:

- Synthetic Reference image and Portable Cube loading.
- Tetrahedral interpolation, bypass, and mix configuration.
- A complete color-context declaration submitted with all three hidden expected
  revisions, including an explicit Export color context independent of Proof
  and Display.
- Rejection of a stale rendered declaration basis followed by a committed
  submission from the newly rendered form.
- Preview submission, visible scanline progress, and terminal publication.
- Full-resolution progress and cancellation without partial publication or
  replacement of the last valid full-resolution result.
- Newest-before-oldest completion, with the older job visibly stale and the
  newest valid full-resolution result retained.
- Canonical Portable Cube inspection while ordinary export remains explicitly
  blocked.
- A malformed Reference command with its diagnostic code visible while every
  previously valid Reference, transformation, context, surface, job, and
  canonical-artifact value remains exact.

The HTML parser observes forms, hidden revision-basis fields, stable
`data-testid` regions, job states, and progress attributes. It does not infer
domain state from pixels or duplicate any color arithmetic. HTTP actions are
submitted from those rendered forms, including select defaults, selected
options, and checked checkboxes; duplicate field names fail closed. Readiness
and HTTP bodies require bounded, exact framing. The readiness reader uses one
non-blocking pipe owner with a monotonic deadline on every supported host; it
does not leave a worker accessing the pipe during timeout cleanup. Local-path
coverage reads only synthetic inputs in a temporary directory and verifies
their names, bytes, permissions, and modification times remain unchanged.

## macOS surface contract

The smoke runs the documented start command without `--no-open`. Its temporary
standard-library `BROWSER` wrapper asks Safari to create a new document for the
printed ephemeral URL; it never navigates or reuses an existing document. The
test inventories the complete multiset of Safari document URLs before launch,
requires the launch inventory to equal that multiset plus exactly the ephemeral
URL, requests the live server once, closes only that exact document, and
requires the original multiset to be restored. It never quits Safari or closes
unrelated windows or tabs. The wrapper is removed with its temporary directory.

The macOS host must provide `/Applications/Safari.app` and
`/usr/bin/osascript`, and its existing automation policy must permit the exact
window query and close operation. The test never grants or changes permissions.
Ordinary discovery skips only this real Safari surface test unless
`COLORLUTHIER_RUN_REAL_SURFACE_SMOKE=1`; the synthetic privacy and driver tests
still run. Once explicitly enabled, a non-macOS host, an Apple Events denial, a
prompt, or a timeout is a failing environmental gate rather than a skipped
success. The headless and HTTP helper paths themselves remain portable. A
control failure reports only the exact residual loopback URL plus non-sensitive
inventory counts and target presence; it stops the server, preserves every
other Safari document, and remains RED.

## Deliberate limits

This slice performs no screenshots, browser pixel comparison, host-application
qualification, color-value oracle calculation, artifact export, persistence,
or runtime dependency installation. Those absences must not be interpreted as
evidence for visual fidelity, colorimetric correctness, ordinary-export
readiness, or a permanent application architecture.
