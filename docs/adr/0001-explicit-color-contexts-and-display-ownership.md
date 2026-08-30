---
status: accepted
---

# Keep color contexts explicit and display adaptation layered

ColorLUThier uses one explicitly selected ICC or OCIO/ACES Color-management lane and one Working color context per authoring scope. Unknown identities permit inspection only and block color-dependent authoring, validation, and export. Crossing lanes is an explicit, directional, provenance-bearing conversion that preserves the original representation and creates a derived representation; no conversion is inferred from names, paths, roles, or defaults.

ColorLUThier owns color interpretation from the Source color context through the authored Color transformation and the declared Proof and Display color contexts. The platform owns exactly once the final adaptation from a correctly identified display-referred surface to the active physical display. Display moves, active physical-display profile changes, and SDR, HDR, or EDR capability changes invalidate and require revalidation of only that viewing leg; they never mutate authored or export state. An unavailable display context may use a clearly labeled non-reference fallback, but never a silent context switch or tone map.

Proof, Display/view, and physical-display transforms are excluded from ordinary exports. Every export declares its input and output semantics separately and fails closed when required identities are unknown or the Color transformation is not representable. This boundary prevents assumptions, double transforms, and accidental display baking without selecting a CMM, GPU API, project schema, interchange-manifest schema, or Host-support matrix.

This boundary resolves [#5](https://github.com/loomitz/ColorLUThier/issues/5) from the interchange evidence established in [#3](https://github.com/loomitz/ColorLUThier/issues/3).
