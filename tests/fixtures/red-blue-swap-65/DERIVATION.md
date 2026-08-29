# Independent 65-point red/blue permutation oracle

This fixture samples a red/blue channel permutation on a 65-point lattice. For
integer indices `r`, `g`, and `b` in `0...64`, define:

```text
q(i) = i / 64
T(r, g, b) = (q(b), q(g), q(r))
```

The Cube rows are emitted in blue, green, red loop order, with red varying
fastest. The denominator is a power of two, so every lattice coordinate is
exactly representable as both binary32 and binary64. Formatting those values
with `.9g` therefore produces canonical decimal tokens that recover the exact
stored binary32 samples.

## Recorded evaluations

The descriptor contains 14 literal input/expected pairs:

- all eight global corners;
- the center node `(32, 32, 32)`;
- the edge node `(0, 64, 27)`;
- the face node `(64, 13, 47)`;
- the asymmetric interior nodes `(1, 7, 61)` and `(63, 37, 3)`; and
- the off-node probe `(39/256, 63/128, 213/256)`, whose local cell coordinates
  are `(3/4, 1/2, 1/4)`.

For every evaluation, expected RGB is the input blue, green, and red value in
that order. The asymmetric nodes make a red-fastest addressing or channel-order
mistake observable. The representative stored-node evaluations expose selected
outputs explicitly, while the binary32 node gate separately checks every
stored node.

## Generation and independence

The standalone `tests/materialize_portable_cube_corpus.py` tool emits only Cube
input bytes. It does not import the conformance harness and does not generate
the descriptor, expected values, reports, or expected canonical output. The
literal expectations above are independently reviewable from the channel
permutation formula.

The generated file has these fixed properties:

```text
sample count = 274,625
byte count   = 6,514,965
SHA-256      = 4664568c299ffcf31164a4d504524c322594fd5f7fe66da26874e81b96e08d30
```

The materializer verifies the byte count and digest before publishing the
file. The digest is also pinned in the static descriptor so the public harness
cannot silently accept generator drift.

The 33- and 65-point plaintext inputs total 7,253,322 bytes, compared with a
tracked fixture corpus of roughly 100 KiB when this case was introduced. They
are therefore materialized into a disposable build or temporary directory
rather than committed to the repository.
