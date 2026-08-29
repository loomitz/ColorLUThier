# Independent affine cross-channel oracle

This fixture samples the following affine transformation on the lattice
coordinates `{0, 1/2, 1}` in each input channel:

```text
R' = (((0.0625 + 0.5 * R)   + 0.25 * G)  + 0.125 * B)
G' = (((0.125  + 0.125 * R) + 0.375 * G) + 0.25 * B)
B' = (((0.1875 + 0.25 * R)  + 0.125 * G) + 0.375 * B)
```

Every coefficient, bias, lattice coordinate, and stored output is dyadic and
therefore exactly representable as IEEE 754 binary32. Every output depends on
all three input channels. Over the implicit input domain, the three output
ranges are `[1/16, 15/16]`, `[1/8, 7/8]`, and `[3/16, 15/16]`.

## Binary32 samples and binary64 oracle

The independent oracle starts from the binary32 table samples promoted exactly
to binary64. Let the origin sample be:

```text
S000 = (0.0625, 0.125, 0.1875)
```

The three affine matrix columns are reconstructed only from stored half-axis
samples:

```text
2 * (S(1/2, 0,   0)   - S000) = (0.5,   0.125, 0.25)
2 * (S(0,   1/2, 0)   - S000) = (0.25,  0.375, 0.125)
2 * (S(0,   0,   1/2) - S000) = (0.125, 0.25,  0.375)
```

Each explicit expected value is calculated in binary64, channel by channel,
with the left-associated expression shown above. No ColorLUThier harness
evaluator code participates in producing the expected values.

Within any lattice cell, trilinear weights and tetrahedral barycentric weights
each sum to one and reproduce the input coordinate. Applying either weight
system to samples of an affine function therefore reconstructs the same
closed-form transformation. At stored nodes, the expected output is the exact
promoted binary32 sample.

## Evaluation geometry

Both descriptors contain the same 67 inputs and expected outputs:

- all 27 stored nodes, partitioned into 8 corners, 12 non-corner edge nodes,
  6 face centers, and 1 global center;
- 12 off-node probes, one on every global cube edge;
- 6 off-node probes, one on every outer cube face;
- all 8 cell centers; and
- 11 additional dyadic interior probes; and
- 3 non-dyadic interior probes.

The additional dyadic probes are exact under both interpolation paths. Together
with the non-dyadic probes, they produce 201 component errors and distinguish
the nearest-rank p99 statistic from the maximum:

- trilinear has two errors of `2^-54` and 199 zero errors, so maximum is
  `2^-54`, mean is `2^-53 / 201`, and p99 is zero;
- tetrahedral has two errors of `2^-53`, two of `2^-54`, one of `2^-55`, and
  196 zero errors, so maximum is `2^-53`, mean is `(13 * 2^-55) / 201`, and p99
  is `2^-54`.

The maximum CLF-style normalized errors are independently obtained by dividing
the trilinear maximum by `0.24583333333333335` and the tetrahedral maximum by
`0.36250000000000004`, the expected values attached to the governing errors.

The non-dyadic probes make binary64 roundoff observable. Off-node conformance
uses the explicit `2^-20` maximum absolute error gate; only stored-node and
serialization checks require binary32 bit identity. The tetrahedral reference
path uses four binary64 products accumulated explicitly from left to right in
region-vertex order, without compensated summation, extended-precision
summation, or fused multiply-add semantics.
