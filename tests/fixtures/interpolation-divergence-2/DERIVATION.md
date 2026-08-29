# Independent interpolation-divergence oracle

This fixture defines each output channel as one Boolean pair-product at the
eight vertices of a 2x2x2 lattice:

```text
Y(R, G, B) = (R * G, R * B, G * B), where R, G, B are each 0 or 1.
```

The Cube rows are listed in red-fastest order as `C000`, `C100`, `C010`,
`C110`, `C001`, `C101`, `C011`, and `C111`.

The expected values were derived from this definition without invoking the
ColorLUThier harness evaluator:

- The unique trilinear extension of the vertex samples is
  `(r * g, r * b, g * b)`.
- In the CLF six-tetrahedron partition, linear interpolation of each Boolean
  pair-product is the smaller of its two coordinates. The tetrahedral result is
  therefore `(min(r, g), min(r, b), min(g, b))`.

All evaluation coordinates are exact multiples of `1/64`. Each pair-equality
facet is evaluated on the boundary and one exact dyadic step on both sides.
The center point also exercises the all-equal tie. The strict ordering regions
are covered as follows:

| Region | Evaluation identifiers |
| --- | --- |
| `R > G > B` | `rg-high-r-side`, `gb-low-g-side` |
| `R > B > G` | `rb-high-r-side`, `gb-low-b-side` |
| `B > R > G` | `rb-high-b-side`, `rg-low-r-side` |
| `B > G > R` | `gb-high-b-side`, `rg-low-g-side` |
| `G > B > R` | `gb-high-g-side`, `rb-low-b-side` |
| `G > R > B` | `rg-high-g-side`, `rb-low-r-side` |

The two descriptors contain the same input coordinates. They differ only in
the mandatory interpolation selection and independently derived expected
outputs. Both cases use the same Cube bytes and serialization golden.
