# Provisional Portable Cube conformance harness

This repository-local harness is a test-only oracle for executable Portable Cube
evidence. It is not the ColorLUThier production color engine, a public library, a
stable interface for product integrations, or a Host application compatibility
claim.

The harness requires Python 3.12 and uses only the Python standard library.

## Run the identity case

From the repository root, select a Python 3.12 interpreter and run:

```console
python -m portable_cube_harness --descriptor tests/fixtures/identity-2/case.json --cube tests/fixtures/identity-2/input.cube --output-dir build/identity-2
```

The descriptor is versioned internal test metadata. It is not a ColorLUThier
interchange manifest. The command writes `canonical.cube` and `report.json` in
the requested output directory. On a completed conformance run, stdout is
byte-identical to `report.json`.

The canonical Cube uses Basic Latin text, LF line endings, red-fastest sample
ordering, and `.9g` decimal formatting over binary32 table samples. `.9g` means
up to nine significant decimal digits without insignificant trailing zeroes; it
is sufficient to recover every finite binary32 value with correct rounding.

Successful evidence is labeled `provisional`, records Host validation as
`not_performed`, and carries no compatibility claims.

## Exit statuses

- `0`: the requested case passed its numerical and round-trip gates.
- `1`: the case was valid but failed at least one conformance gate.
- `2`: invocation, descriptor, Cube, checksum, or output validation failed.
- `3`: the harness encountered an unexpected internal error.

Success leaves stderr empty. Validation and internal failures emit a
machine-readable, provisional error record to stderr.

The umbrella `INPUT_INVALID` code in this first slice is provisional. Stable
diagnostic codes and acceptance corpora for individual Cube and descriptor
validation classes remain outside issue #26.

## Run the acceptance test

```console
python -m unittest discover -s tests -v
```

The acceptance test invokes only the public command as a subprocess. It observes
the generated files, stdout, stderr, and exit status without importing harness
implementation modules.
