# Provisional headless engine evidence

[Issue #59](https://github.com/loomitz/ColorLUThier/issues/59) collects
reproducible evidence for the public ColorLUThier engine on native macOS,
Windows, and Linux. The collector is repository tooling outside the production
engine and uses Python 3.12 and the standard library only.

This evidence remains **provisional**. It does not complete formal Gate 7,
qualify a Host application, establish security or an audit result, demonstrate
benchmark-wide coverage, or establish professional product readiness. The
broader program [#49](https://github.com/loomitz/ColorLUThier/issues/49) remains
open. Ordinary-export validation
[#58](https://github.com/loomitz/ColorLUThier/issues/58) remains blocked by the
separate representability and authoring decisions in #12 and #14. Internal Test
UI v0 remains a disposable provisional test interface, not a professional UI.

## Collect on one native host

From the repository root, select a Python 3.12 interpreter. On hosts where the
command is named `python3.12`, substitute that name for `python` below:

```console
python -B -m headless_engine_evidence collect --output-dir /explicit/artifact-directory/native-evidence
```

Replace the example output path with a new directory outside the repository.
On Windows, use an explicit Windows path. The collector requires no UI,
display server, browser, dependency installation, secrets, or private runner.
The full discovery suite includes headless Internal Test UI tests; the existing
real Safari surface smoke remains intentionally disabled. Its skip is recorded
as a skip, never as a passing surface test.

The command runs focused engine acceptance, full test discovery, temporary
`compileall`, the independent Portable Cube materializer and corpus command,
positive and negative public engine CLI smokes, and preview/full-resolution
parity evidence. Scratch inputs, canonical artifacts, corpus outputs, and
bytecode live only in temporary directories. The explicit output directory
contains only the comparison records:

- `deterministic.json`: canonical deterministic results and content digests;
- `evidence.json`: the same deterministic evidence plus normalized environment
  metadata.

Both files are versioned, ASCII JSON with sorted keys and a final LF. Only
normalized OS family, architecture, and required version information belong in
environment metadata. Python executable paths, operating-system build strings,
usernames, hostnames, timestamps, raw subprocess output, payloads, and private
identifiers do not belong in either record. Captured output is inspected within
explicit bounds and is never copied into a failure diagnostic.

Schema version `1` gives `evidence.json` exactly three root fields:
`schema_version`, `deterministic`, and `environment`. The environment has only
`os_family` (`linux`, `macos`, or `windows`), `architecture` (`arm64` or
`x86_64`), and numeric `python_version` (`3.12.x`). The deterministic object
has its own schema version, `evidence: "provisional"`, fixed limitations, test
summaries, compilation status, corpus digest, CLI smoke framing, canonical
artifact digest, and parity-suite evidence.

Test summaries record actual run, pass, skip, failure, error, and unexpected
outcome counts plus a SHA-256 of the sorted test inventory. The parity section
identifies the existing six-test `test_preview_full_resolution_parity` suite
and its independent analytic binary32 expectations. It records execution of
that suite, not a newly measured pixel digest. Failed tests, altered test
inventories across hosts, and unrecognized skip outcomes are observable.

Collection exits `0` only after successful checks and record publication.
Expected collection or comparison rejection exits `2` with a bounded JSON
error containing only a fixed code and stage; an unexpected internal exception
exits `3` without exposing its message. A successful comparison exits `0` and
prints its provisional status, the three platforms, and the shared
deterministic-record SHA-256.

An incomplete or failed collection exits unsuccessfully and cannot stand in for
successful native evidence. Keep the exit status together with the files; file
presence alone is not acceptance.

## Execution and data limits

The collector imposes these provisional tooling limits:

| Boundary | Limit |
| --- | ---: |
| Each focused, full, or parity suite command | 600 seconds |
| Other child commands | 120 seconds |
| Captured stdout and stderr | 1 MiB each |
| Individual scratch file | 64 MiB |
| Scratch tree | 128 MiB and 4096 entries |
| Individual published JSON record | 64 KiB |
| Each cleanup wait | 10 seconds |

Pipe readers drain both streams concurrently with bounded capture. A deadline
also applies to silent children. Temporary-file budgets are observed during
execution at bounded intervals and checked again before evidence is accepted;
this is a collector limit, not a filesystem quota. A process may exceed the
disk budget between observations, which makes the run fail. No timing or
elapsed-duration measurement is included in deterministic evidence.

## Repeatability and protected values

Run the same command again into a different new output directory, then compare
the two `deterministic.json` files byte for byte. CI performs both collections
and rejects an empty or different deterministic record before upload. The
environment is separate so architecture and Python patch-version differences
do not become engine-result differences.

The inherited baseline at `8d268138bbef041355454782def4d29311c7c7c4` has
122 discovered tests: 121 pass and one intentional Safari skip. New collector
tests increase the full count. Recorded counts describe tests actually run;
missing tests, failures, unexpected skips, and failed commands cannot be
represented by empty successful results.

These existing contractual bytes are unchanged:

| Evidence | Bytes | SHA-256 |
| --- | ---: | --- |
| Complete Portable Cube report | 3150 | `b8e0144c08d6a768d1cda17d7fe2bbc5c7117e9199856eca9061ae8a6e29b2a6` |
| Positive public CLI JSON | 837 | `bbe13ab9256575ba6c2cb2759a3710225ac2d20e91eb6f95ea003fc7ec04f0a2` |
| Canonical imported-lattice artifact | 62 | `c8bce4299c8606d5ca59a4724f46e484e430c42d506cfc2a3f30bbe84d5199cc` |

The canonical artifact is imported-lattice inspection. It is not an ordinary
export and does not bake provisional mix, bypass, Proof, or Display state.
The independent Portable Cube harness and its #34 evidence remain separate
from the production engine. The collector invokes their public subprocess
contracts without importing their implementation or changing their fixtures.

The comparable CLI negative uses unavailable or invalid regular input. Local
macOS QA also checks symlink rejection: exit 2, `CLI_INPUT_UNAVAILABLE`, empty
stdout, and no artifact. The existing CLI uses no-follow open semantics only
where the operating system provides them; this collector does not turn that
local check into a cross-platform symlink guarantee. It neither changes that
protected engine boundary nor reports unperformed Windows symlink rejection
as successful evidence.

## Native CI and comparison

The existing `Portable Cube conformance` workflow retains its independent
acceptance step. Its Python 3.12 matrix runs the collector twice on
`ubuntu-latest`, `macos-latest`, and `windows-latest`, then uploads one artifact
from each successful platform. Each artifact contains both JSON files:

```text
headless-engine-evidence-linux/
  deterministic.json
  evidence.json
headless-engine-evidence-macos/
  deterministic.json
  evidence.json
headless-engine-evidence-windows/
  deterministic.json
  evidence.json
```

A dependent job runs even when a matrix job fails. It downloads matching
artifacts without merging their platform directories, then runs:

```console
python -B -m headless_engine_evidence compare --artifacts-dir /explicit/download-directory
```

The comparator requires all three platform identities, matching supported
schema versions, valid canonical records, fixed contractual digests, and equal
deterministic evidence. Missing platforms, duplicate or extra artifacts,
corruption, unsupported records, mismatched platform identities, and contractual
divergence fail the comparison. Environment differences are validated
separately and are not compared as engine results. Relabeling copies of one
local record is only a comparator test fixture; it is never native platform
execution evidence. Native provenance comes from the three workflow jobs and
their uploaded artifacts.

Workflow permissions remain `contents: read`. All actions are pinned to full
commit SHAs. Artifacts expire after 30 days under this workflow configuration;
retain the relevant run and artifact evidence when accepting a published
change, or rerun the matrix if evidence is no longer available.

## Local validation and acceptance boundary

Run focused collector tests and the complete suite from the repository root:

```console
python -B -m unittest discover -s tests -p test_headless_engine_evidence.py -v
python -B -m unittest discover -s tests -v
```

Independent QA must also run temporary compilation, the complete materialized
corpus, two positive CLI smokes and raw-byte comparisons, negative CLI and
symlink rejection, two real collector invocations, privacy inspection, and
`git diff --check`. Verify that the production engine, harness, UI packages,
and existing fixtures did not change.

Local success is a local checkpoint. Issue #59 can close only after the
collector, tests, documentation, native artifacts, and cross-platform
comparison are published, integrated, and green with no reproducible open bug
within its scope. A passing local suite or an older matrix run is insufficient.
