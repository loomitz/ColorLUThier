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

The independent red/blue channel-permutation case uses the same public seam:

```console
python -m portable_cube_harness --descriptor tests/fixtures/red-blue-swap-2/case.json --cube tests/fixtures/red-blue-swap-2/input.cube --output-dir build/red-blue-swap-2
```

The interpolation-divergence fixture supplies two complete cases over the same
Cube and evaluation coordinates:

```console
python -m portable_cube_harness --descriptor tests/fixtures/interpolation-divergence-2/trilinear.case.json --cube tests/fixtures/interpolation-divergence-2/input.cube --output-dir build/interpolation-divergence-trilinear
python -m portable_cube_harness --descriptor tests/fixtures/interpolation-divergence-2/tetrahedral.case.json --cube tests/fixtures/interpolation-divergence-2/input.cube --output-dir build/interpolation-divergence-tetrahedral
```

The descriptor must explicitly select either `trilinear` or `tetrahedral`
interpolation. The harness never chooses a default. The fixture's static
expected values and branch-boundary corpus are documented in
[`DERIVATION.md`](../tests/fixtures/interpolation-divergence-2/DERIVATION.md).

The affine cross-channel fixture also runs both interpolation methods over one
Cube and one independently derived evaluation corpus:

```console
python -m portable_cube_harness --descriptor tests/fixtures/affine-cross-channel-3/trilinear.case.json --cube tests/fixtures/affine-cross-channel-3/input.cube --output-dir build/affine-cross-channel-trilinear
python -m portable_cube_harness --descriptor tests/fixtures/affine-cross-channel-3/tetrahedral.case.json --cube tests/fixtures/affine-cross-channel-3/input.cube --output-dir build/affine-cross-channel-tetrahedral
```

Its closed-form oracle and 67-point geometry corpus are documented in
[`DERIVATION.md`](../tests/fixtures/affine-cross-channel-3/DERIVATION.md). The
corpus covers every stored node, the global corners, edges and faces, every cell
center, and additional dyadic and non-dyadic interior probes.

The canonical Cube uses Basic Latin text, LF line endings, red-fastest sample
ordering, and `.9g` decimal formatting over binary32 table samples. `.9g` means
up to nine significant decimal digits without insignificant trailing zeroes; it
is sufficient to recover every finite binary32 value with correct rounding.

Successful evidence is labeled `provisional`, records Host validation as
`not_performed`, and carries no compatibility claims.

## Provisional reference arithmetic

Cube table tokens are rounded to IEEE 754 binary32 when parsed, then promoted
exactly to binary64 for evaluation. Stored-node evaluation returns the promoted
sample directly, so the node and serialization gates compare binary32 bit
patterns without an off-node tolerance.

For current off-node evidence, trilinear interpolation applies binary64 lerps
in fixed red, then green, then blue axis order. Tetrahedral interpolation forms
four binary64 weighted products per channel and accumulates them explicitly
from left to right in the selected region's vertex order. These paths do not use
`sum`, `math.fsum`, fused multiply-add, or compensated summation. This operation
order belongs only to the provisional harness evidence; it is not a production
engine contract.

Each completed report includes maximum, mean, and p99 absolute error plus the
maximum CLF-style normalized error for both input and canonical Cube evaluation.
The affine fixture permits at most `2^-20` absolute error and separately requires
finite output, stored-node binary32 identity, and serialization binary32
identity.

## Exit statuses

- `0`: the requested case passed its numerical and round-trip gates.
- `1`: the case was valid but failed at least one conformance gate.
- `2`: invocation, descriptor, Cube, checksum, or output validation failed.
- `3`: the harness encountered an unexpected internal error.

Success leaves stderr empty. Validation and internal failures emit a
machine-readable, provisional error record to stderr.

Interpolation selection has two stable diagnostics:

- `INTERPOLATION_REQUIRED`: the descriptor omits `interpolation`.
- `INTERPOLATION_UNSUPPORTED`: the descriptor does not select `trilinear` or
  `tetrahedral`.

Both produce status `2`, empty stdout, a provisional JSON error record on
stderr, and no output artifacts. The umbrella `INPUT_INVALID` code remains
provisional for all other invocation, Cube, descriptor, checksum, and output
validation classes.

## Run the acceptance test

```console
python -m unittest discover -s tests -v
```

The acceptance test invokes only the public command as a subprocess. It observes
the generated files, stdout, stderr, and exit status without importing harness
implementation modules.
