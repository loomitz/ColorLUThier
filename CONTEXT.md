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

**Color transformation**:
The intended mapping from source colors to output colors that a user authors and evaluates in ColorLUThier.
_Avoid_: filter, effect, LUT

**LUT**:
A portable sampled representation of a color transformation, exported for use in compatible host applications.
_Avoid_: filter, project

**Reference coverage**:
The requirement that every user-facing capability in the selected 3D LUT Creator benchmark be accounted for, whether matched directly, replaced by a better ColorLUThier workflow, or deliberately excluded with rationale.
_Avoid_: clone, identical UI parity
