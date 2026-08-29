# Independent separable nonlinear oracle

This fixture samples the same endpoint-preserving quadratic in each channel:

```text
F(x) = x + 2^-15 * x * (1 - x)
T(R, G, B) = (F(R), F(G), F(B))
```

The curve is monotonic on `[0,1]`, stays inside that interval, and is
nonlinear while preserving both endpoints.

## Binary32 table samples

The lattice coordinates are `{0, 1/4, 1/2, 3/4, 1}`. Their sampled outputs
are:

```text
F(0)   = 0
F(1/4) = 0.2500057220458984375
F(1/2) = 0.50000762939453125
F(3/4) = 0.7500057220458984375
F(1)   = 1
```

Every coordinate and stored value is dyadic and exactly representable as IEEE
754 binary32. The Cube contains the Cartesian product of these channel values
in red-fastest order.

For an input component represented by a binary64 value, the independent
analytic oracle treats that value as an exact rational and rounds the following
result once to binary64:

```text
x + x * (1 - x) / 32768
```

The explicit expected values in both descriptors were produced from that
closed-form expression. No ColorLUThier harness evaluator participated.

## Interpolation error

Within one lattice interval `[a,b]`, the difference between the analytic curve
and its sampled linear chord is exactly:

```text
F(x) - L(x) = 2^-15 * (x - a) * (b - x)
```

Each interval has width `1/4`, so the global maximum occurs at its center and
is exactly `2^-21`. A separable table reduces both trilinear and tetrahedral
interpolation to the same per-channel chord; #28 independently proves that the
two methods diverge on non-separable data.

## Recorded evaluation corpus

The corpus contains 95 evaluations:

- seven complete nine-stop ramps at `t = i/8` for `i = 0...8`: neutral,
  primary red, primary green, primary blue, secondary cyan, secondary magenta,
  and secondary yellow;
- 32 deterministic interior RGB triples from the recorded LCG32 seed below.

Repeated black inputs are intentional: each named family remains a complete,
independently inspectable ramp.

The pseudo-random generator is specified without relying on a language runtime:

```text
initial state = 0x434C5554
state = (1664525 * state + 1013904223) mod 2^32
u = state >> 16
coordinate = (u + 0.5) / 2^16
```

The generator advances once per component in red, green, blue order. Thirty-two
triples consume 96 advances and finish at state `0x13261934`. All coordinates
are exact binary64 dyadics strictly inside `(0,1)`; the triples are unique,
avoid stored nodes, and cover all eight half-cube octants.

## Metrics and gates

The 95 evaluations produce 285 component errors. Independent rational
aggregation gives the same metric values for both interpolation methods:

```text
maximum_absolute_error        = 2^-21
mean_absolute_error           = 710218667 / 4011018418126848
                              = 1.7706691741686724e-7
p99_absolute_error            = 2^-21
maximum_clf_normalized_error  = 4.169651174994186e-6
```

The passing descriptors use the explicit `2^-20` maximum absolute error gate.
The acceptance test gives a descriptor clone a distinct case identifier and
changes its gate to `2^-22`. The Cube metadata, interpolation, evaluation
inputs, expected values, and remaining gates stay unchanged.
