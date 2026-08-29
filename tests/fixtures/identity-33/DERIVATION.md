# Independent 33-point identity oracle

This fixture samples the identity transformation on a 33-point lattice. For
integer indices `r`, `g`, and `b` in `0...32`, define:

```text
q(i) = i / 32
T(r, g, b) = (q(r), q(g), q(b))
```

The Cube rows are emitted in blue, green, red loop order, with red varying
fastest. The denominator is a power of two, so every lattice coordinate is
exactly representable as both binary32 and binary64. Formatting those values
with `.9g` therefore produces canonical decimal tokens that recover the exact
stored binary32 samples.

## Recorded evaluations

The descriptor contains 14 literal input/expected pairs:

- all eight global corners;
- the center node `(16, 16, 16)`;
- the edge node `(0, 32, 11)`;
- the face node `(32, 7, 25)`;
- the asymmetric interior nodes `(1, 7, 29)` and `(31, 19, 5)`; and
- the off-node probe `(21/128, 27/64, 111/128)`, whose local cell coordinates
  are `(1/4, 1/2, 3/4)`.

For every evaluation, the expected output is the input RGB value. The
representative stored-node evaluations make lattice addressing observable,
while the binary32 node gate separately checks every stored node.

## Generation and independence

The standalone `tests/materialize_portable_cube_corpus.py` tool emits only Cube
input bytes. It does not import the conformance harness and does not generate
the descriptor, expected values, reports, or expected canonical output. The
literal expectations above are independently reviewable from the identity
formula.

The generated file has these fixed properties:

```text
sample count = 35,937
byte count   = 738,357
SHA-256      = ed09443c84100f8d9620bb4fc22325e56b2777577b37323cc1ba940d0472ba60
```

The materializer verifies the byte count and digest before publishing the
file. The digest is also pinned in the static descriptor so the public harness
cannot silently accept generator drift.

The 33- and 65-point plaintext inputs total 7,253,322 bytes, compared with a
tracked fixture corpus of roughly 100 KiB when this case was introduced. They
are therefore materialized into a disposable build or temporary directory
rather than committed to the repository.
