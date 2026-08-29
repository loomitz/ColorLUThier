# Professional interchange and color-fidelity evidence base

- **Status:** Research resolution for *Define the professional interchange and color-fidelity evidence base*
- **Evidence cutoff:** 2026-08-29
- **Scope:** File-based interchange of a ColorLUThier color transformation and its reference image with Adobe Photoshop, DaVinci Resolve, and standards-compatible ICC or OCIO/ACES applications. This report defines a product contract and a validation plan; it does not claim that current ColorLUThier code or either host has already passed the proposed tests.

## Resolution

ColorLUThier should implement two explicit, non-interchangeable color-management lanes over one floating-point color engine:

1. **ICC still-image lane:** flattened 16-bit RGB TIFF with an embedded source ICC profile is the default Photoshop-oriented reference image. PNG is a compact secondary option. The portable LUT deliverable is a host-profiled 33- or 65-point 3D `.cube`; ICC v4 abstract and RGB DeviceLink profiles are additional Photoshop deliverables, not substitutes for declaring the LUT's source and destination encodings.
2. **OCIO/ACES lane:** lossless RGB OpenEXR (half or float, depending on the test or project requirement) plus an explicit, pinned OCIO configuration, source color space, working color space, and display/view choice is the scene-linear reference path. CLF v3 is the preferred rich transformation interchange. An ACES Metadata File (AMF) should accompany an ACES viewing-pipeline exchange when a recipe or receipt must survive outside the ColorLUThier project.

The extension `.cube` alone is insufficient evidence of compatibility. Adobe/IRIDAS Cube and Resolve Cube have different domain-header dialects, and Cube does not carry a normative color-space identifier or interpolation selection. ColorLUThier therefore needs:

- a deliberately small **portable Cube subset** for Photoshop and Resolve;
- separate **Adobe/IRIDAS Cube** and **Resolve Cube** export profiles when non-default domains or a 1D shaper are required;
- explicit source/output encoding and interpolation in a ColorLUThier manifest;
- per-host black-box round-trip evidence tied to an application version, OS, project/document settings, and interpolation mode.

No imported LUT may be applied on the assumption that it is sRGB, Rec.709, full range, or scene-linear. Unknown semantics are an error that the user must resolve, not a default.

## 1. Evidence-backed format contract

### 1.1 Reference images

| Format | Required role | Color and metadata requirements | Boundary and evidence |
| --- | --- | --- | --- |
| **TIFF (`.tif`, `.tiff`)** | Default ICC-lane interchange | Flattened RGB; 16 bits/channel; lossless compression only; embed the complete source ICC profile; preserve dimensions, orientation, alpha policy, and pixel aspect explicitly | Photoshop supports profile embedding in TIFF, and Resolve 20 decodes TIFF and writes RGB/RGBA 16-bit TIFF. ICC defines TIFF profile embedding. [Adobe profile embedding](https://helpx.adobe.com/photoshop/desktop/adjust-color/color-profiles/embed-color-profiles.html), [ICC embedding guidance](https://www.color.org/profile_embedding/), [Resolve 20 formats, pp. 5-6](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_Supported_Codec_List.pdf) |
| **PNG (`.png`)** | Secondary lossless ICC-lane interchange and deterministic integer test fixture | RGB, 8- or 16-bit; `iCCP` profile chunk when color-managed; reject contradictory `iCCP`/`sRGB`/chromaticity declarations rather than guessing; no palette conversion in fidelity tests | Resolve 20 decodes PNG and writes RGB 8/16-bit. ICC points to the W3C PNG embedding mechanism. PNG is bounded integer data, so it is not the scene-linear HDR master. [ICC embedding guidance](https://www.color.org/profile_embedding/), [PNG specification](https://www.w3.org/TR/png-3/), [Resolve 20 formats, pp. 5-6](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_Supported_Codec_List.pdf) |
| **OpenEXR (`.exr`)** | Default OCIO/ACES scene-linear interchange and floating-point test fixture | RGB channels; HALF for normal production interchange or FLOAT when the source/test demands it; use uncompressed, ZIP, PIZ, or RLE for the documented Resolve-compatible lossless profile; write and validate `chromaticities`; also record the exact OCIO color-space/config identity outside the optional EXR attributes | OpenEXR does not apply a display transform and `chromaticities` is optional, so chromaticities alone do not identify transfer function or OCIO role. DWAA/DWAB, B44/B44A, and PXR24 are lossy and must not be used for fidelity evidence. Strict ST 2065-4 ACES container output has additional requirements, including no compression, ACES chromaticities, and `acesImageContainerFlag=1`. [OpenEXR technical introduction](https://openexr.com/en/latest/TechnicalIntroduction.html), [OpenEXR standard attributes](https://openexr.com/en/latest/StandardAttributes.html), [`exr2aces` conformance notes](https://openexr.com/en/latest/bin/exr2aces.html), [Resolve 20 formats, pp. 5-6](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_Supported_Codec_List.pdf) |
| **PSD/PSB** | Photoshop convenience import, not canonical interchange | Preserve and inspect embedded ICC/OCIO document information, but use the flattened composite as the reference image unless a later feature explicitly models Photoshop layers | Photoshop documents carry host-specific layer and color-management behavior. Resolve lists PSD decode support but does not promise equivalent layer compositing. Adobe's native OCIO documents may be PSD/PSB, yet a placed layer still requires an input-space decision. [Adobe OCIO workflow](https://helpx.adobe.com/photoshop/using/opencolorio-transform.html), [Resolve 20 formats](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_Supported_Codec_List.pdf) |
| **JPEG** | Preview or user convenience only | Read embedded ICC when present; mark the image as lossy/8-bit; never use it as a numerical oracle or round-trip fixture | JPEG quantization and chroma subsampling make it unsuitable for evidence, even though Photoshop can embed ICC and Resolve decodes it. [Adobe profile embedding](https://helpx.adobe.com/photoshop/desktop/adjust-color/color-profiles/embed-color-profiles.html), [Resolve 20 formats](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_Supported_Codec_List.pdf) |

DPX/Cineon remain useful compatibility inputs for log and integer cinema pipelines, but are not required to establish the first Photoshop-to-ColorLUThier still-image workflow. Their exact packing, range, and color-space metadata must be a separate host-profile decision before they become canonical interchange formats.

### 1.2 Color-transformation deliverables

| Deliverable | Required support | Contract |
| --- | --- | --- |
| **Portable 3D Cube (`.cube`)** | Read and write; default host deliverable | ASCII/BASIC LATIN; LF line endings; comments only before header; exactly one `LUT_3D_SIZE`; no `TITLE`, `DOMAIN_*`, or `LUT_*D_INPUT_RANGE` in the portable profile; red index changes fastest; default domain `[0,1]` on all channels; finite decimal samples written with enough significant digits to round-trip a float32; 33 points default, 65 points high quality. This is the syntactic intersection to verify in both hosts, not a claim that the file is self-describing. |
| **Adobe/IRIDAS Cube** | Read and write | Follow Adobe Cube 1.0: either a 3x1D table or one 3D table; optional `TITLE`, per-channel `DOMAIN_MIN`/`DOMAIN_MAX`; 3D size 2-256; red index fastest; linear interpolation for 1D and tetrahedral recommended for 3D. The original Adobe URL is offline, so the cited primary specification is an archived copy. [Adobe Cube LUT Specification 1.0 (archived original)](https://web.archive.org/web/20201027210601if_/https://wwwimages2.adobe.com/content/dam/acom/en/products/speedgrade/cc/pdfs/cube-lut-specification-1.0.pdf) |
| **Resolve Cube** | Read and write | Support 1D-only, 3D-only, and a 1D shaper followed by 3D; `LUT_1D_SIZE`, `LUT_1D_INPUT_RANGE`, `LUT_3D_SIZE`, `LUT_3D_INPUT_RANGE`; scalar rather than per-channel input range; red index fastest. Resolve-generated 3D exports are 17, 33, or 65 points; 17 is explicitly not recommended for grading. [Resolve 20 manual, pp. 3407 and 3413](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf), [OCIO Resolve Cube reader/writer](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.5.2/src/OpenColorIO/fileformats/FileFormatResolveCube.cpp) |
| **CLF v3 (`.clf`)** | Read and write; preferred rich interchange and ACES look deliverable | Preserve the ordered process list rather than baking when supported. Validate XML/schema and all nodes. Preserve `id`, `name`, descriptions, `InputDescriptor`, `OutputDescriptor`, `Info`, bit-depth scaling, explicit `Range` clamp behavior, and explicit `LUT3D` interpolation. CLF requires 32-bit floating-point processing semantics; 1D interpolation is linear; 3D interpolation is trilinear or tetrahedral and defaults to trilinear when omitted. [CLF v3 specification](https://docs.acescentral.com/clf/specification/), [CLF implementation guide](https://docs.acescentral.com/clf/guides/) |
| **ICC (`.icc`, `.icm`)** | Read/validate embedded v2 and v4 profiles; write ICC v4 abstract and RGB DeviceLink deliverables when the authored transformation fits those classes | An abstract profile is PCS-to-PCS; a DeviceLink directly joins a defined source data color space to a defined destination and is specific to that link. Record profile class, profile version, profile ID/hash, data color space, PCS, rendering intent, CMM, black-point-compensation choice, and source/destination profile identities in the project evidence. Never label an arbitrary RGB Cube as equivalent to an ICC transform. [ICC.1:2022](https://www.color.org/specification/ICC.1-2022-05.pdf), [ICC profile FAQ](https://www.color.org/faqs/) |
| **OCIO configuration (`config.ocio`)** | Load, validate, pin, and package by content hash; not marketed as a LUT | Persist config content/hash and OCIO profile version, source space, working/process space, target space or display/view, looks and directions, context variables, file rules used, and OCIO library version. A color-space transform and a display/view transform are different operations. Validate with the OCIO API and `ociocheck`. [OCIO config authoring](https://opencolorio.readthedocs.io/en/latest/guides/authoring/authoring.html), [OCIO displays and views](https://opencolorio.readthedocs.io/en/latest/guides/authoring/displays_views.html) |
| **ACES Metadata File (`.amf`)** | Read/write or package when exchanging an ACES viewing-pipeline recipe/receipt | Use AMF v2 to associate input, ordered look transforms, output transform, ACES system version, identifiers/hashes, and whether a transform was already applied. AMF is a sidecar description of the viewing pipeline, not the pixel transform itself. [AMF specification](https://docs.acescentral.com/amf/specification/), [AMF implementation guide](https://docs.acescentral.com/amf/guides/implementation/) |

Photoshop's 3DL and CSP exports should be compatibility formats after a dedicated conformance corpus exists. They should not be ColorLUThier masters: OCIO documents that some legacy formats resample or approximate shapers and recommends CLF/CTF where exact operator representation is available. CTF may be useful as a lossless OCIO/project serialization, but neither Photoshop Color Lookup nor Resolve's documented normal LUT browser establishes CTF as a common user deliverable. [OCIO supported LUT formats](https://opencolorio.readthedocs.io/en/stable/guides/using_ocio/using_ocio.html#supported-lut-formats)

Resolve-specific DCTL is executable transform code rather than portable sampled interchange. It may become an optional Resolve exporter, but it is not evidence that a transformation exchanges with Photoshop or standards-compatible LUT consumers.

## 2. Why `.cube` requires named host profiles

Adobe Cube 1.0 and Resolve Cube share the extension, RGB samples, `LUT_1D_SIZE`/`LUT_3D_SIZE`, and red-fastest 3D ordering, but differ materially:

| Semantic | Adobe/IRIDAS Cube | Resolve Cube |
| --- | --- | --- |
| Domain syntax | Per-channel `DOMAIN_MIN r g b` / `DOMAIN_MAX r g b` | Scalar `LUT_1D_INPUT_RANGE min max` / `LUT_3D_INPUT_RANGE min max` |
| Combined shaper + 3D | Adobe 1.0 specifies either 3x1D or 3D | Resolve specifies a 1D shaper followed by 3D in one file |
| Interpolation in file | Not encoded; Adobe spec recommends tetrahedral for 3D | Not encoded; Resolve project setting chooses trilinear or tetrahedral |
| Metadata | Title and comments, neither a normative color-space declaration | Comments; host metadata such as video/full range is documented separately by Resolve, but the public manual does not publish the syntax |
| Wide-domain behavior | Per-channel domains and unconstrained float output are syntactically allowed | Shaper and scalar ranges are supported; Resolve warns that 3D LUTs clip out-of-range input without shaping |

The Resolve 20 manual explicitly says its `.cube` is a DaVinci-developed format with no relation to Adobe SpeedGrade `.cube` (p. 319), while OCIO maintains separate Resolve Cube and Iridas Cube readers. The safe conclusion is not that interchange is impossible; it is that interoperability must be demonstrated per generated file profile. [Resolve 20 manual](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf), [OCIO Iridas Cube reader/writer](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.5.2/src/OpenColorIO/fileformats/FileFormatIridasCube.cpp), [OCIO Resolve Cube reader/writer](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.5.2/src/OpenColorIO/fileformats/FileFormatResolveCube.cpp)

### Required Cube semantics

For every Cube import or export, ColorLUThier must materialize the following semantics in the project and companion manifest:

- dialect and dialect version;
- source color space and transfer/encoding;
- destination color space and transfer/encoding;
- whether the transform is scene-referred, display-referred, or a display/view rendering;
- input domain for every channel and behavior outside it;
- output range expected by the consumer;
- full/data range versus video/legal range;
- 1D shaper identity, domain, size, and interpolation, when present;
- 3D size, sample ordering, and intended interpolation;
- forward/inverse direction and whether a reliable inverse exists;
- creator, transform version/UUID, creation time, license/copyright, file SHA-256, and validation-host matrix.

Cube comments may duplicate human-readable parts of that data but are not authoritative. Host applications may ignore or rewrite comments. The companion manifest is ColorLUThier metadata, not an industry standard, and must be identified as such.

### Domain and interpolation policy

For a channel with declared domain `[d_min, d_max]`, the table coordinate is proportional to `(x - d_min) / (d_max - d_min)`. Samples are uniformly spaced. The Adobe spec does not define behavior outside the declared domain; ColorLUThier must therefore test each host and must not rely on extrapolation. An export that receives expected values outside its representable domain must either:

1. add a compatible shaper and prove the round trip;
2. use CLF/another rich transform that preserves the domain;
3. expand/rebake the domain and prove the new error; or
4. stop with a clipping warning.

Silent clipping is not acceptable.

The engine and preview must implement linear 1D, trilinear 3D, and tetrahedral 3D evaluation. The export panel must show the intended method and host behavior. Resolve 20 defaults to trilinear for backward compatibility and recommends tetrahedral for higher quality/reduced banding; Adobe Cube recommends tetrahedral but current Photoshop documentation does not state the Color Lookup implementation. Consequently, “Photoshop match” remains an empirical host profile until measured. [Resolve 20 manual, pp. 151-152](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf), [Adobe Cube 1.0, §§7-8](https://web.archive.org/web/20201027210601if_/https://wwwimages2.adobe.com/content/dam/acom/en/products/speedgrade/cc/pdfs/cube-lut-specification-1.0.pdf), [CLF interpolation definitions](https://docs.acescentral.com/clf/specification/#appendix-a-interpolation)

## 3. Photoshop host contract

### Document and image boundary

- A Photoshop 3D Color Lookup adjustment requires RGB mode; Adobe's current tutorial says the 3DLUT control is disabled otherwise. [Adobe Color Lookup adjustment](https://helpx.adobe.com/photoshop/how-to/edit-photo-color-lookup-adjustment.html)
- Photoshop's current format documentation describes OpenEXR as a 32-bits/channel document format. A HALF source may therefore be promoted on import; bit-exact HALF round trips must be tested through exported pixels, not inferred from the Photoshop document bit-depth label. [Adobe supported image formats](https://helpx.adobe.com/photoshop/desktop/save-and-export/export-files-to-different-formats/image-file-formats-supported-in-photoshop.html)
- Photoshop distinguishes **assigning** a profile (changes interpretation, not code values) from **converting** to a profile (changes code values). A round-trip recipe must say which occurred, including CMM, intent, black-point compensation, and dithering. [Adobe profile assignment and conversion](https://helpx.adobe.com/photoshop/desktop/adjust-color/color-profiles/change-color-profile-for-documents.html)
- TIFF/PSD/PSB/JPEG support embedded ICC profiles according to Adobe. ColorLUThier must inspect the embedded profile rather than silently use the current working RGB. [Adobe profile embedding](https://helpx.adobe.com/photoshop/desktop/adjust-color/color-profiles/embed-color-profiles.html)
- Photoshop's own LUT exporter requires a background layer plus color-modifying layers, accepts grid points from 0 through 256, and writes 3DL, CUBE, CSP, or ICC. Lab documents may produce ICC abstract profiles, CMYK documents CMYK DeviceLinks, and RGB documents 3D LUT formats or RGB DeviceLinks. Those are useful reference fixtures for reverse interoperability tests. [Adobe LUT export](https://helpx.adobe.com/photoshop/using/export-color-lookup-tables.html)

### ICC/OCIO boundary inside Photoshop

Photoshop now has native OCIO documents and built-in ACES configuration support. `Open as OpenColorIO` creates an OCIO document and places the input as a Smart Object with a selected input transform. Placed layers may use OCIO file rules, an embedded profile, explicit pass-through, or an explicitly chosen OCIO source space. `Convert to OpenColorIO` and `Duplicate to Profile` are explicit boundary operations; the latter flattens the result and requires a display/view, output bit depth, and ICC profile decision. [Adobe OCIO workflow](https://helpx.adobe.com/photoshop/using/opencolorio-transform.html)

Therefore ColorLUThier must expose two separate Photoshop recipes:

1. **ICC document recipe:** export a profiled TIFF, author the color transformation in that exact RGB encoding, export the corresponding Cube or ICC transform, and load it into an RGB Color Lookup adjustment.
2. **OCIO document recipe:** export EXR (or another explicitly assigned source), pin the same OCIO config and working space in both applications, keep the creative transform separate from the display/view, and exchange CLF or a Cube baked for a named process space. A display transform is baked only when the user explicitly requests a display-referred deliverable.

### Photoshop uncertainties requiring runtime characterization

Adobe's current public documentation does **not** specify:

- whether current Photoshop Color Lookup uses tetrahedral, trilinear, or another 3D interpolation path;
- its exact treatment of values below 0 or above 1 in 16/32-bit documents;
- which Resolve Cube headers it accepts, ignores, or rejects;
- whether Color Lookup behavior differs between normal ICC and native OCIO documents;
- how imported Cube comments, title, or non-default domains survive a save/reload.

These are test requirements, not assumptions to settle from secondary sources.

## 4. DaVinci Resolve host contract

- Resolve 20 reads 1D and 3D Cube, Resolve shaper Cube, CLF, Panasonic VLUT, and DCTL. It generates 17-, 33-, and 65-point Resolve Cube; 17-point is not recommended for grading. CLF is the documented preferred LMT format for ACES due to precision and flexibility. [Resolve 20 manual, pp. 3407-3408](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf)
- Resolve's project-wide 3D LUT interpolation can be trilinear (default/backward-compatible) or tetrahedral (higher quality/reduced banding). Every host comparison must record this setting. [Resolve 20 manual, pp. 151-152](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf)
- Pipeline placement is semantic. Input LUTs run before Color-page processing; output LUTs after it; monitor/viewer LUTs are viewing-only and are not rendered; 1D runs before 3D at a shared placement; and a node LUT is the last operation in that node. A screenshot that “looks right” with a monitor LUT is not export evidence. [Resolve 20 manual, pp. 151 and 3412](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf)
- A generated LUT ignores unsupported spatial and contextual operations such as qualifiers, windows, sharpening/blur, and incompatible effects. A ColorLUThier color transformation is likewise spatially invariant; any unsupported operation must be reported rather than omitted silently. [Resolve 20 manual, pp. 319 and 3413](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf)
- Resolve's own color-management chapter warns that LUTs may clip out-of-bounds data and that differing interpolation can cause cross-application inconsistencies. Color Space Transform/RCM uses explicit source and destination spaces and preserves wide-latitude data more reliably than an unshaped bounded LUT. [Resolve 20 manual, pp. 226-227](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf)
- In ACES projects, Resolve documents different processing spaces for node CLFs/LUTs and warns that ordinary LUTs require an explicit conversion from ACES to the LUT's intended space and back. [Resolve 20 manual, pp. 253-254 and 3408](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf)

The default Resolve exchange recipe is therefore: import the reference image, explicitly set its input color space/range, use a node in a recorded timeline working space, apply the LUT with the recorded interpolation, bypass unrelated output/monitor LUTs during comparison, and render a lossless 16-bit TIFF or lossless float/half OpenEXR in a recorded output space.

The current Resolve manual documents metadata that distinguishes Video Range LUTs but delegates exact syntax to Developer Documentation installed with Resolve. That syntax was not available in the public primary-source set used here. ColorLUThier must not invent it. A host-characterization ticket must extract the installed current developer specification and add legal/full-range fixtures before the exporter claims this capability.

Resolve 20 documentation also does not promise that an embedded ICC profile in an imported TIFF/PNG determines the clip's input color space. The safe contract is explicit input-space assignment in Resolve and an automated warning when the Resolve recipe and embedded ICC/manifest disagree.

## 5. ICC versus OCIO/ACES: hard boundary

### ICC lane

ICC v4 defines input, display, output, DeviceLink, ColorSpace, Abstract, and NamedColor profile classes. Except for DeviceLink, the Profile Connection Space is PCSXYZ or PCSLAB; DeviceLink uses the data color space of the linked destination on its B side. Abstract profiles encode a color effect in PCS-to-PCS form, whereas DeviceLinks bind a particular sequence/source-destination relationship. [ICC.1:2022, §§6-8](https://www.color.org/specification/ICC.1-2022-05.pdf)

ColorLUThier must preserve:

- embedded profile bytes and profile ID/hash;
- profile class and version;
- source data color space, PCS, and destination data color space where applicable;
- selected rendering intent and any black-point compensation outside the profile;
- CMM/version used for evidence;
- assign-versus-convert history.

ICC is the right lane for document/device interpretation and Photoshop's conventional profiled workflow. It is not an OCIO configuration, does not identify an OCIO working/process space or display/view, and does not replace an ACES AMF.

### OCIO/ACES lane

OCIO v2 configurations separately define scene-referred and display-referred reference spaces, colorspaces, display colorspaces, looks with process spaces, file rules, roles, context variables, and displays/views. Configuration names alone are not durable identity; ColorLUThier must package or hash the actual config and record the OCIO version. [OCIO config authoring](https://opencolorio.readthedocs.io/en/latest/guides/authoring/authoring.html)

For ACES interchange:

- preserve the ACES system/config version and transform identifiers;
- distinguish ACES2065-1/AP0 linear, ACEScg/AP1 linear, and ACEScct/ACEScc log encodings;
- keep the creative look separate from input and output transforms unless the deliverable explicitly bakes them;
- use CLF for a robust ACES look when supported;
- use AMF v2 to describe the ordered viewing-pipeline recipe/receipt, including `applied` state;
- use a conforming ACES OpenEXR container only when its stricter ST 2065-4 restrictions are actually satisfied.

### Crossing lanes

Crossing ICC and OCIO is a color conversion, never a relabeling operation. The boundary dialog and manifest must name:

1. source encoding/profile;
2. conversion engine and version;
3. rendering intent/adaptation assumptions;
4. OCIO source/target space or ICC destination profile;
5. whether the selected OCIO display/view was baked;
6. output bit depth and clipping/quantization policy.

If any element is unknown, ColorLUThier may import pixels for inspection but must mark the color transformation as unresolved and prevent a “verified” LUT export.

## 6. Numerical acceptance contract

The tolerances below separate engine correctness, serialization correctness, baking approximation, and perceptual diagnostics. Passing one does not imply the others.

### 6.1 Normative baseline from CLF

The ACES CLF implementation guide supplies the strongest public cross-implementation metric found in the primary sources:

```text
error = abs(actual - aim) / max(abs(aim), 0.1)
max(error) <= 0.002
no Infinity or NaN values
```

This is an absolute tolerance of 0.0002 below magnitude 0.1 and a 0.2% relative tolerance above it. CLF's Preview Tier uses normalized absolute error `<= 0.002`, approximately two 10-bit code values, for its integer tetrahedral LUT3D test. These gates should be adopted unchanged for claiming CLF Finishing Tier and Preview Tier compatibility. [CLF implementation guide, Applying CLFs](https://docs.acescentral.com/clf/guides/#applying-clfs)

### 6.2 Proposed ColorLUThier gates

These are product proposals, not thresholds mandated by Adobe, Blackmagic, ICC, or OCIO. They must be revised from measured host evidence rather than weakened merely to make a failing test pass.

| Layer | Proposed release gate |
| --- | --- |
| Core analytic transform, CPU reference | Float32 implementation versus float64 oracle: `max(abs(error)) <= 2^-20` for normalized `[0,1]` test data; no unexpected clamp; no NaN/Infinity. Operations with a published stronger reference use that reference. |
| GPU versus CPU | Same relative metric as CLF Finishing Tier with max `<= 0.002`, plus a stricter tracked target of max normalized absolute error `<= 2^-16` for ordinary finite `[0,1]` paths. Both values are reported. |
| Lossless image no-op | Decoder-to-encoder with identical encoding and metadata: integer code values bit-exact when no conversion is requested; float32 bit-exact where the format preserves float32; HALF bit-exact for HALF. A host-rendered integer no-op may differ by at most one destination code value after a documented conversion/rounding step. |
| LUT sample nodes and serialization | Applying an exported/reparsed LUT at every stored node must reproduce the stored float32 samples bit-exactly. Parse-write-parse must preserve semantic metadata and all sample float32 values; unknown metadata is preserved or reported. |
| 33-point standard bake | Against the unbaked float64 color transformation, declared interpolation, and declared domain: CLF-style max relative error `<= 0.002`, p99 `<= 0.001`. Failure triggers a quality warning and recommendation for a shaper, 65-point output, or CLF. |
| 65-point high-quality bake | CLF-style max relative error `<= 0.001`, p99 `<= 0.0005`. A transformation that fails is not labeled high quality, regardless of grid size. |
| Host LUT rendering | Compared in the same input/output encoding and interpolation: meet the CLF Finishing metric for float output or Preview absolute `<= 0.002` for normalized integer output. Also report max/mean error in destination code values. |
| ICC profile and cross-CMM | First pass ICC's structural validation using a pinned ICC `iccDEV` release. Against the same profile sequence evaluated by the pinned oracle, require the CLF-style numeric metric `<= 0.002`, no invalid values, and provisional display-referred diagnostics of mean ΔE00 `<= 0.1`, p99 `<= 0.5`, max `<= 1.0`. Report Adobe CMM, ColorSync, and open-source CMM results separately; the thresholds are a ColorLUThier proposal, not an ICC guarantee. [ICC iccDEV](https://github.com/InternationalColorConsortium/iccDEV), [ICC profile compliance notes](https://www.color.org/whitepapers/ICC_White_Paper_21_Profile_Compliance_Testing_with_iccDEV.pdf) |
| Perceptual diagnostic | For SDR display-referred comparisons, track mean ΔE00 `<= 0.1`, p99 `<= 0.5`, and max `<= 1.0` as provisional warning thresholds. For scene-linear/HDR, compute ΔE00 only after the named target view and also retain scene-linear numeric error. These are diagnostics, not a substitute for numeric conformance. |

“Round trip” must always name the quantization points. A float transform rendered to 8-bit JPEG cannot be expected to meet the same gate as lossless 16-bit TIFF or float EXR.

## 7. Required test evidence

### 7.1 Deterministic corpus

Create version-controlled source values and expected results for:

- identity and channel-swap transforms;
- primary, secondary, neutral, and near-neutral ramps;
- all LUT grid nodes, cell centers, face/edge points, and values on both sides of tetrahedron branch boundaries;
- values exactly at, just inside, and just outside every declared domain boundary;
- negative, super-white, subnormal HALF, largest finite HALF, Infinity, and NaN rejection/handling cases where the format permits them;
- separable tone curves, matrices with cross-channel terms, hue rotations, gamut compression, and deliberately non-monotonic creative transforms;
- 1D shaper + 3D combinations;
- legal/video-range and full/data-range code ramps;
- ICC v2/v4 matrix/TRC, LUT-based, abstract, and RGB DeviceLink fixtures with all supported intents, including ICC `iccDEV` structural validation;
- OCIO scene-to-scene, scene-to-display, look/process-space, and inverse/no-inverse cases;
- CLF's official legal and illegal files, Finishing frames, and Preview tetrahedral LUT3D frame.

Every fixture must carry a machine-readable manifest containing source generator/version, expected encoding, dimensions, channel order, domain, interpolation, checksum, and oracle command/commit.

### 7.2 Photoshop black-box matrix

For the current macOS Photoshop release and at least the previous supported major release:

1. Open ICC-tagged 16-bit TIFF and 16-bit PNG; prove assign/convert behavior with identity patches.
2. Open lossless FLOAT/HALF EXR through native OCIO using a pinned built-in and external ACES config.
3. Apply portable, Adobe-domain, and Resolve-domain Cube fixtures through a Color Lookup adjustment in 8-, 16-, and 32-bit RGB where the host allows it.
4. Render to profiled 16-bit TIFF and lossless EXR; compare pixel values to ColorLUThier's evaluator.
5. Characterize interpolation with a LUT whose trilinear and tetrahedral results deliberately diverge.
6. Characterize below-zero, above-one, and non-default-domain behavior without a display transform hiding clipping.
7. Export known Photoshop adjustment stacks at several grid sizes to CUBE, 3DL, CSP, ICC abstract, and RGB DeviceLink; parse and reapply them in ColorLUThier.
8. Repeat the OCIO/ICC boundary using `Duplicate to Profile` and record flattening, display/view, profile, and bit-depth choices.

The evidence record must include Photoshop build, macOS build, architecture, document mode/bit depth/profile, color settings, GPU setting, OCIO config hash, exact clicks/API path, output checksum, error tables, and screenshots only as supporting—not numerical—evidence.

### 7.3 Resolve black-box matrix

For current Resolve 20 Free and Studio on macOS Apple silicon where behavior may differ:

1. Import the same TIFF, PNG, and EXR fixtures and explicitly assign the intended input color space and data level.
2. In DaVinci YRGB, RCM, ACEScct, and ACES AP0 test projects, document timeline/output spaces and all automatic transforms.
3. Apply each Cube/CLF in a node, then repeat at input, output, viewer, and monitor positions to prove pipeline placement and whether it is rendered.
4. Render once with trilinear and once with tetrahedral interpolation; compare to matching local evaluators.
5. Import and export 17-, 33-, and 65-point Resolve Cube, shaper Cube, CLF, and legal/video-range fixtures.
6. Characterize non-default domains, negative/super-white input, output outside `[0,1]`, and malformed/unknown headers.
7. Verify that unsupported spatial grade operations are excluded with an explicit user-visible warning in the equivalent ColorLUThier workflow.

Record Resolve build/edition, macOS build, architecture/GPU, project archive/settings, node graph, LUT path and checksum, input/output range, rendered format, and full numeric comparison.

### 7.4 Cross-host round trip

A release candidate is not “Photoshop/Resolve compatible” until all of these pass for at least identity, smooth nonlinear, cross-channel, and adversarial-domain transforms:

```text
ColorLUThier graph
  -> exported host profile
  -> host render
  -> lossless reference output
  -> ColorLUThier decode and numerical comparison

Host-generated transform
  -> ColorLUThier import
  -> ColorLUThier render
  -> host re-import/re-render
  -> numerical comparison
```

Compatibility claims must be scoped, for example: “Photoshop 2026 on macOS, 16-bit RGB ICC document, portable 33 Cube” or “Resolve 20.1, node LUT, tetrahedral, ACEScct process space.” A bare “Photoshop compatible” badge is not evidence.

## 8. Product requirements derived from the evidence

ColorLUThier **must**:

- use a floating-point internal color engine and keep display rendering separate from the authored color transformation;
- require explicit input, working/process, and output encodings;
- preserve ICC profile bytes/IDs and pin OCIO config content/hash;
- implement Adobe/IRIDAS and Resolve Cube as separate parsers/export profiles plus the tested portable subset;
- support linear, trilinear, and tetrahedral evaluation and expose host-specific preview modes;
- make 33 and 65 the normal Cube export choices, with 17 visibly labeled for constrained/monitor compatibility rather than professional grading;
- read/write CLF v3 and run the official legal/illegal and apply suites before claiming CLF compatibility;
- never silently omit a spatial, temporal, content-dependent, or otherwise non-LUT-representable operation;
- generate a transformation manifest and reproducible evidence bundle for every verified export;
- make clipping, gamut compression, quantization, and display-transform baking visible decisions;
- qualify compatibility by host version, mode, encoding, placement, and interpolation.

ColorLUThier **should**:

- use 16-bit profiled TIFF for the first Photoshop exchange workflow and lossless OpenEXR for OCIO/ACES;
- provide ICC abstract/RGB DeviceLink and AMF outputs after their conformance harnesses exist;
- offer automatic host recipes/checklists and import-time mismatch diagnostics;
- preserve imported unknown metadata and refuse unverifiable semantics rather than normalize files destructively.

## 9. Explicit uncertainty and newly surfaced decisions

The primary sources settle the architecture and minimum evidence, but not the following host behavior:

1. **Photoshop Cube conformance characterization:** exact Cube dialect tolerance, interpolation, out-of-domain behavior, 32-bit Color Lookup behavior, and behavior inside native OCIO documents.
2. **Resolve developer-metadata characterization:** exact current syntax and semantics for full/video-range LUT metadata and any additional installed Resolve Cube extensions.
3. **Resolve still-image metadata characterization:** whether/how current Resolve uses embedded ICC, PNG color chunks, EXR chromaticities, and ancillary color metadata during import under YRGB, RCM, and ACES.
4. **ICC deliverable profile:** which v2/v4 profile elements, CMMs, rendering intents, and precision gates are required for Photoshop parity across macOS and later Windows.
5. **ColorLUThier interchange-manifest schema:** stable identifiers, hashes, host profiles, sidecar naming, signing/security limits, and migration policy.
6. **Platform qualification matrix:** the minimum Photoshop/Resolve versions and Windows/Linux applications against which community-visible compatibility may be claimed.

These are now sharp enough to become decision or prototype tickets. None should be hidden inside implementation tasks.

## Primary sources

- Adobe, [Export color lookup tables from Photoshop](https://helpx.adobe.com/photoshop/using/export-color-lookup-tables.html).
- Adobe, [Color Lookup adjustment](https://helpx.adobe.com/photoshop/how-to/edit-photo-color-lookup-adjustment.html).
- Adobe, [OpenColorIO workflow in Photoshop](https://helpx.adobe.com/photoshop/using/opencolorio-transform.html).
- Adobe, [Assign and convert document profiles](https://helpx.adobe.com/photoshop/desktop/adjust-color/color-profiles/change-color-profile-for-documents.html) and [embed profiles](https://helpx.adobe.com/photoshop/desktop/adjust-color/color-profiles/embed-color-profiles.html).
- Adobe, [Cube LUT Specification 1.0 (archived original publication)](https://web.archive.org/web/20201027210601if_/https://wwwimages2.adobe.com/content/dam/acom/en/products/speedgrade/cc/pdfs/cube-lut-specification-1.0.pdf), September 2013.
- Blackmagic Design, [DaVinci Resolve 20 Reference Manual](https://documents.blackmagicdesign.com/UserManuals/DaVinci_Resolve_20_Reference_Manual.pdf), especially pp. 151-152, 226-227, 253-254, 319, and 3405-3414.
- Blackmagic Design, [DaVinci Resolve 20 Supported Formats and Codecs](https://documents.blackmagicdesign.com/SupportNotes/DaVinci_Resolve_20_Supported_Codec_List.pdf), pp. 5-6.
- International Color Consortium, [ICC.1:2022 profile specification](https://www.color.org/specification/ICC.1-2022-05.pdf) and [profile embedding guidance](https://www.color.org/profile_embedding/).
- International Color Consortium, [`iccDEV` reference implementation and tools](https://github.com/InternationalColorConsortium/iccDEV) and [profile-compliance implementation notes](https://www.color.org/whitepapers/ICC_White_Paper_21_Profile_Compliance_Testing_with_iccDEV.pdf).
- Academy Software Foundation, OpenColorIO [configuration documentation](https://opencolorio.readthedocs.io/en/latest/guides/authoring/authoring.html), [supported LUT formats](https://opencolorio.readthedocs.io/en/stable/guides/using_ocio/using_ocio.html#supported-lut-formats), and v2.5.2 [Iridas Cube](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.5.2/src/OpenColorIO/fileformats/FileFormatIridasCube.cpp) / [Resolve Cube](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/v2.5.2/src/OpenColorIO/fileformats/FileFormatResolveCube.cpp) implementations.
- Academy/ASC, [Common LUT Format v3 specification](https://docs.acescentral.com/clf/specification/) and [implementation guide/test requirements](https://docs.acescentral.com/clf/guides/).
- Academy, [ACES Metadata File specification](https://docs.acescentral.com/amf/specification/).
- Academy Software Foundation, [OpenEXR technical introduction](https://openexr.com/en/latest/TechnicalIntroduction.html), [standard attributes](https://openexr.com/en/latest/StandardAttributes.html), and [`exr2aces`](https://openexr.com/en/latest/bin/exr2aces.html).
