# ColorLUThier

ColorLUThier is the domain of authoring, evaluating, and exchanging professional color transformations as reusable LUTs for external creative applications.

## Language

**ColorLUThier**:
The open-source standalone application for authoring, inspecting, and exporting professional color transformations. Its canonical spelling highlights “LUT” within “luthier.”
_Avoid_: ColorLUTier, Color Lutier, 3D LUT Creator clone

**Host application**:
An external color-capable application, such as Adobe Photoshop or DaVinci Resolve, that supplies a reference image or consumes a LUT exported by ColorLUThier.
_Avoid_: ColorLUThier client, editor

**Reference image**:
An image imported from a host workflow to author and evaluate a color transformation; it is not the exported deliverable.
_Avoid_: project, LUT

**Color context**:
The explicit, versioned identity and interpretation of color values at one pipeline boundary. A color-space name without its governing profile or configuration content and required parameters is incomplete.
_Avoid_: color-space label, assumed profile

**Color-management lane**:
One of two explicit semantic routes for an authoring scope: ICC still-image or OCIO/ACES configuration-managed. One authoring scope uses one lane, and their identities and conversions never mix implicitly.
_Avoid_: hybrid color mode, automatic bridge

**Source color context**:
The explicit color-space identity, encoding, and interpretation of a Reference image before ColorLUThier applies a Color transformation. Missing or ambiguous metadata constitutes an unknown source color context, not an assumed default.
_Avoid_: assumed sRGB, implicit input profile

**Working color context**:
The single explicit color space and encoding in which a Color transformation is authored and evaluated within one authoring scope. A Reference image enters it by identity when contexts match or through an identified conversion from its Source color context.
_Avoid_: per-image working space, implicit workspace

**Display color context**:
The declared display-referred encoding and viewing interpretation before final adaptation to the active physical display. It is distinct from the monitor profile and is never part of the authored Color transformation.
_Avoid_: monitor profile, baked display transform

**Proof color context**:
An explicitly selected, non-destructive simulation of a target output condition in the viewing path between the authored Color transformation and the Display color context. It is not part of the Working color context or a normal LUT export.
_Avoid_: baked proof, proof working space

**Export color context**:
The declared input and output color identities, encodings, numeric domain and range, interpolation convention, and Host or format profile governing one exported deliverable. It is declared separately from Working, Display, and Proof color contexts and remains incomplete while any required identity is unknown.
_Avoid_: active view, inherited export space

**OCIO configuration identity**:
The immutable content identity of an OCIO configuration and every resource and variable resolved for a color operation. A configuration name, role, default, or filesystem path is not sufficient identity.
_Avoid_: config name, current default

**Cross-lane conversion**:
An explicit, directional, provenance-bearing conversion that preserves the original representation and creates a derived representation in another Color-management lane. It is never relabeling or assumed to be invertible.
_Avoid_: automatic bridge, profile assignment

**Color transformation**:
The intended mapping from source colors to output colors that a user authors and evaluates in ColorLUThier.
_Avoid_: filter, effect, LUT

**LUT**:
A portable sampled representation of a color transformation, exported for use in compatible host applications.
_Avoid_: filter, project

**Reference coverage**:
The requirement that every user-facing capability in the selected 3D LUT Creator benchmark be accounted for, whether matched directly, replaced by a better ColorLUThier workflow, or deliberately excluded with rationale.
_Avoid_: clone, identical UI parity
