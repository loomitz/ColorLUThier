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

## Internal test descriptor

Descriptor schema version `1` is a closed, test-only metadata shape. It may
evolve with this provisional oracle and has no compatibility or migration
relationship with a future ColorLUThier interchange manifest. Its root object
contains exactly these fields:

- `test_case_schema_version`: the integer `1`;
- `case_id`: a lowercase, hyphen-separated stable identifier;
- `cube`: an object containing only the lowercase `sha256` digest;
- `interpolation`: `trilinear` or `tetrahedral`;
- `oracle`: an object whose `kind` is `explicit_expected_values` and whose
  non-empty `provenance` identifies the independent derivation;
- `evaluations`: a non-empty array of closed objects containing a unique stable
  `id`, a three-component `input`, and a three-component finite `expected`
  result; and
- `gates`: a closed object containing the finite, non-negative
  `maximum_absolute_error` plus boolean `require_finite_outputs`,
  `require_node_binary32_identity`, and
  `require_serialization_binary32_identity` fields.

Unknown members are rejected at every object level. In particular, the
descriptor cannot declare a custom domain, clamping, extrapolation, range, or
shaper policy. Every evaluation input component must be finite and inside the
closed implicit Portable Cube domain `[0,1]`. A request outside that domain is
invalid; it is never clamped or extrapolated.

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

The separable nonlinear fixture measures interpolation approximation against a
closed-form quadratic oracle:

```console
python -m portable_cube_harness --descriptor tests/fixtures/nonlinear-separable-5/trilinear.case.json --cube tests/fixtures/nonlinear-separable-5/input.cube --output-dir build/nonlinear-separable-trilinear
python -m portable_cube_harness --descriptor tests/fixtures/nonlinear-separable-5/tetrahedral.case.json --cube tests/fixtures/nonlinear-separable-5/input.cube --output-dir build/nonlinear-separable-tetrahedral
```

Its 95-point corpus contains complete neutral, primary, and secondary ramps plus
32 deterministic interior samples from a recorded LCG32 seed. The analytic
curve, generator, expected metrics, and gates are documented in
[`DERIVATION.md`](../tests/fixtures/nonlinear-separable-5/DERIVATION.md).

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
identity. The nonlinear fixture uses the same explicit `2^-20` gate and has a
closed-form maximum approximation error of `2^-21`.

## Exit statuses

- `0`: the requested case passed its numerical and round-trip gates.
- `1`: the case was valid but failed at least one conformance gate.
- `2`: invocation, descriptor, Cube, checksum, or output validation failed.
- `3`: the harness encountered an unexpected internal error.

A completed valid run, whether it passes with status `0` or misses a gate with
status `1`, leaves stderr empty, writes `canonical.cube` and `report.json`, and
copies the report bytes to stdout. A status `1` report has a successful input
validation result and an `overall_result` of `fail`. Validation and internal
failures emit a machine-readable, provisional error record to stderr.

The two successful artifacts are staged before publication. If output
publication fails, the command exits `2`, emits no successful report, removes
any newly published final artifact, and makes a best-effort rollback to preserve
pre-existing `canonical.cube` and `report.json` files.

Interpolation selection has two stable diagnostics:

- `INTERPOLATION_REQUIRED`: the descriptor omits `interpolation`.
- `INTERPOLATION_UNSUPPORTED`: the descriptor does not select `trilinear` or
  `tetrahedral`.

Both produce status `2`, empty stdout, a provisional JSON error record on
stderr, and no output artifacts.

Internal descriptor and evaluation validation has six additional stable
top-level diagnostics:

- `DESCRIPTOR_ENCODING_INVALID`: the descriptor is not valid UTF-8;
- `DESCRIPTOR_JSON_INVALID`: its JSON text is malformed, ambiguous, too deeply
  nested, or contains a numeric token that cannot be parsed safely;
- `DESCRIPTOR_SCHEMA_UNSUPPORTED`: its integer schema version is not supported;
- `DESCRIPTOR_SCHEMA_INVALID`: its closed shape, required fields, field types,
  identifiers, oracle metadata, expected values, or gates are invalid;
- `CUBE_CHECKSUM_MISMATCH`: the supplied Cube bytes do not match the descriptor
  SHA-256 digest; and
- `EVALUATION_INPUT_INVALID`: an evaluation input has the wrong shape, contains
  a non-finite value, or lies outside `[0,1]`.

These failures exit `2`, leave stdout empty, emit a deterministic provisional
JSON error record on stderr, and write no new `canonical.cube` or `report.json`
artifact. The stable `code` is the classifier. Deterministic `reason`,
`context`, and `message` fields provide bounded factual detail without absolute
paths, timestamps, or descriptor payloads; callers must not branch on them.

Cube artifact validation has four stable top-level diagnostics:

- `CUBE_ENCODING_INVALID`: the Cube artifact is not Basic Latin text.
- `CUBE_STRUCTURE_INVALID`: the strict Portable Cube structure is missing,
  duplicated, unsupported, or malformed.
- `CUBE_LATTICE_SIZE_INVALID`: `LUT_3D_SIZE` does not declare an integer from
  `2` through `65`, inclusive.
- `CUBE_SAMPLE_VALUE_INVALID`: a sample is not an accepted finite decimal
  value representable as binary32.

Every Cube artifact rejection exits `2`, leaves stdout empty, emits one
provisional JSON error record on stderr, and writes no new `canonical.cube` or
`report.json` artifact. The error object includes the stable `code` plus a
deterministic `reason`, structured `context`, and English `message`. The latter
three fields are informational rather than stable identifiers; callers must
branch only on `code`. When present, `context.line` and `context.component` are
one-based, while `context.byte_offset` is zero-based and `context.byte_value` is
an integer.

The strict subset accepts leading blank lines and comments before exactly one
`LUT_3D_SIZE` declaration. It rejects a missing or duplicate size declaration;
known non-portable directives such as `TITLE`, `LUT_1D_SIZE`, `DOMAIN_MIN`,
`DOMAIN_MAX`, `LUT_1D_INPUT_RANGE`, and `LUT_3D_INPUT_RANGE`; unknown headers;
and standalone or inline comments after the size declaration. The declaration
must be followed by exactly `N³` sample rows, each containing exactly three
tokens. Malformed decimals, hexadecimal numbers, locale-dependent numbers,
NaN, positive or negative Infinity, values outside the finite binary32 range,
and non-ASCII input are rejected rather than normalized.

The `2...65` lattice-size bound is checked before allocating or waiting for the
declared sample table. The umbrella `INPUT_INVALID` code remains provisional for
other invocation, file-access, and output validation classes. Descriptor
metadata, evaluation-domain validation, and unexpected internal failures are
outside the Cube diagnostic taxonomy.

An unexpected implementation failure exits `3`, leaves stdout empty, and emits
the stable top-level code `INTERNAL_ERROR` with a fixed message. It does not
expose exception text or other implementation details. This status is distinct
from every expected invocation, descriptor, Cube, checksum, and output
validation failure.

## Run the acceptance test

```console
python -m unittest discover -s tests -v
```

The acceptance test invokes only the public command as a subprocess. It observes
the generated files, stdout, stderr, and exit status without importing harness
implementation modules.
