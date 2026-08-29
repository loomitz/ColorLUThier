# 3D LUT Creator benchmark and capability inventory

- Status: research decision for ColorLUThier reference coverage
- Evidence cut-off: 2026-08-29
- Subject: 3D LUT Creator desktop application, not its mobile application or separately distributed host plug-ins

## Decision

ColorLUThier should use **3D LUT Creator Professional 1.52** as its named reference-coverage benchmark.

This means that every capability in the inventory below must eventually be classified as one of:

1. matched directly by ColorLUThier;
2. replaced by an explicitly better workflow with the same professional outcome; or
3. deliberately excluded with a recorded rationale.

It does **not** mean copying 3D LUT Creator's interface, terminology, assets, implementation, or undocumented internals.

### Why this is the authoritative benchmark

- The current official product page identifies the desktop product as **version 1.52**. No official page or distribution evidence found in this investigation names a later desktop version. [S1]
- Professional is the most capable official edition. The official comparison and FAQ reserve the 96-point maximum LUT size, color-target support, and batch processing for Professional; the FAQ also says Grading Edition has only the A/B and Curves tabs. [S1] [S2]
- A benchmark must include the full documented capability surface rather than the maintainer's most-used subset. Professional is therefore the only defensible edition boundary.
- The official manuals are older than the selected version: the English manual identifies 1.02 (dated 2015-05-01) and the newer Russian manual identifies 1.11 (revision 2016-03-17). The official tutorials describe later additions, including A/B targeted tools introduced in 1.4. Consequently, the inventory uses the **union of current official product claims, FAQ, tutorials, and versioned manuals**, while marking behavior that still needs observation in the licensed 1.52 build. [S3] [S4] [S5]

### Benchmark amendment rule

Version 1.52 remains the benchmark until stronger primary evidence is captured. If the maintainer's licensed account or installed application's About dialog shows a later build, do not silently replace this decision. Record the build number, platform, download provenance, date, and a capability delta first; then amend this report through a new decision.

## What the evidence does and does not establish

The labels in the inventory have precise meanings:

| Label | Meaning |
| --- | --- |
| `current-official` | A currently reachable first-party page makes the claim. This verifies the publisher's public position, not the runtime semantics. |
| `manual-1.02` | The behavior is documented in the official English 1.02 manual. |
| `manual-1.11` | The behavior is documented in the official Russian 1.11 manual. English descriptions here are paraphrased translations. |
| `official-tutorial` | A first-party tutorial page or its embedded first-party video describes or demonstrates the behavior. |
| `artifact-metadata` | A property was established from an official downloadable artifact without running its color pipeline. |
| `needs-1.52-observation` | The exact current behavior is not established. A controlled observation of the maintainer's licensed 1.52 installation is required. |

No color-transform behavior in this report is labeled runtime-verified. The research did not operate the maintainer's licensed installation, capture its menus, or compare numerical outputs. Official descriptions are evidence of intended capability, not a golden implementation specification.

## Primary-source corpus

- **S1 — Current product page and edition comparison:** [3D LUT Creator official site](https://3dlutcreator.com/). It names version 1.52, lists the edition-level capability families, names output/host workflows, and states the Professional maximum LUT size.
- **S2 — Current first-party FAQ:** [FAQ and Support](https://3dlutcreator.com/3d-lut-creator---faq-and-support.html). It explains edition differences, platforms, host compatibility, reference-frame video workflow, Log families, target families, and integration constraints.
- **S3 — First-party tutorials:** [Tutorials](https://3dlutcreator.com/3d-lut-creator---tutorials.html). The page embeds official videos and provides first-party descriptions of application workflows and later tools not covered by the manuals.
- **S4 — Official English manual:** [3D LUT Creator User Manual, version 1.02](https://3dlutcreator.com/downloads/manual/3dlut_manual_english.pdf), dated 2015-05-01 in the document.
- **S5 — Official Russian manual:** [3D LUT Creator User Manual, version 1.11](https://3dlutcreator.com/downloads/manual/3dlut_manual.pdf), revised 2016-03-17 in the document.
- **S6 — First-party test materials and Hald resources:** [Materials and LUTs](https://3dlutcreator.com/3d-lut-creator---materials-and-luts.html).
- **S7 — First-party companion plug-in page:** [Free Plugins](https://3dlutcreator.com/3d-lut-creator---free-plugins.html). This is ecosystem context, not part of the Professional desktop benchmark.
- **S8 — Official public demo artifacts:** [macOS demo DMG](https://3dlutcreator.com/downloads/3dlutcreator_demo/3DLUTCreatorMacDemo.dmg) and [Windows demo ZIP](https://3dlutcreator.com/downloads/3dlutcreator_demo/3DLUTCreatorDemo.zip). Artifact findings are recorded separately below and are not assumed to equal the licensed 1.52 build.

### Source reconciliation

The source set is internally inconsistent in places:

- S1 names version 1.52, while S4 and S5 document older versions.
- S1's marketing text names `.3dl`, `.cube`, and `.csv`; S4/S5 instead document `.3dl`, `.cube`, `.csp`, and several PNG encodings.
- S2 describes a frame-export workflow for video and says direct host automation was under development, while S7 now distributes separate host plug-ins.
- S5 exposes an “Open EXR in sRGB” preference but its supported-format list does not list OpenEXR.

These conflicts are not resolved by choosing the newest-looking statement. They are explicit verification tasks for the licensed 1.52 build.

### Public distribution metadata

Read-only inspection of the official public macOS demo in S8 independently corroborates the selected version:

- its app bundle reports `CFBundleShortVersionString` **1.52** and bundle build `1`;
- its main executable is a 64-bit **x86_64-only** Mach-O, with no `arm64` slice;
- the app bundle is unsigned;
- the server reported a 53,043,665-byte DMG last modified 2019-02-08;
- the application was not launched, so these are `artifact-metadata` facts, not behavioral observations.

The official Windows demo URL reported a 50,459,194-byte ZIP last modified 2019-12-06, but its contents were not needed to select the benchmark. These public-demo timestamps establish artifact age, not the date of the licensed build and not proof that development formally ended.

## Reference capability inventory

The stable identifiers below are seeds for the future reference-coverage matrix. Splitting or combining them later is acceptable if traceability back to these identifiers is preserved.

### A. Product shell, documents, and state

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| SHELL-01 | Standalone desktop application that authors a color transformation against a still reference image and exports a LUT for another application. It is not a video editor. | `current-official`, `manual-1.02`, S1/S2/S4 |
| SHELL-02 | Open a working image from disk, paste one from the clipboard, and navigate to previous/next images in the source folder. Version 1.11 also documents recent-image access. | `manual-1.02`, `manual-1.11`, S4 pp. 6–8; S5 pp. 5–6 |
| SHELL-03 | Load or paste a separate reference image used for visual comparison, curve extraction, or color matching. | `manual-1.02`, `manual-1.11`, S3 “Working with the Image window”; S4 pp. 6–8 |
| SHELL-04 | Save the processed image in place or under a new name, optionally retaining a backup of the source. | `manual-1.02`, `manual-1.11`, S4 pp. 6–7; S5 pp. 5, 10 |
| SHELL-05 | Reset all tool state, load/save a program preset, and reopen recent presets. `.luc` is the documented preset container. | `current-official`, `manual-1.02`, `manual-1.11`, S1; S4 pp. 6, 12; S5 pp. 5, 51 |
| SHELL-06 | Maintain two independent transform versions, copy settings between them, and switch quickly between them. | `manual-1.11`, `needs-1.52-observation`, S5 p. 6 |
| SHELL-07 | Multi-step undo/redo, named history, and a history window. | `manual-1.02`, `manual-1.11`, S4 pp. 7, 9; S5 pp. 6, 9 |
| SHELL-08 | Show loaded-file information, including EXIF metadata. | `manual-1.11`, `needs-1.52-observation`, S5 p. 5 |
| SHELL-09 | Rotate, flip, resize, zoom, and pan the working image for inspection or alignment. | `manual-1.02`, `manual-1.11`, S4 pp. 8, 36; S5 pp. 7, 12 |
| SHELL-10 | Make the processed result the new reference, swap work/reference images, bake the current transform into the image and reset the tools, and crop/split matching regions. | `manual-1.11`, `needs-1.52-observation`, S5 p. 7 |
| SHELL-11 | Drag-and-drop image/preset loading where supported, with documented platform differences for some drag operations. | `manual-1.02`, `manual-1.11`, S4 pp. 10, 30; S5 p. 12 |
| SHELL-12 | Separate image window for a two-display workspace plus tab/window navigation. | `manual-1.02`, `official-tutorial`, S3 “Working with the Image window”; S4 p. 9 |
| SHELL-13 | Extensive keyboard operation for file actions, grid selection, curve selection, view changes, analyzers, and external-LUT swapping. | `manual-1.02`, `manual-1.11`, S4 pp. 44–45; S5 pp. 55–57 |
| SHELL-14 | User preferences for output folders, JPEG quality, picker radius, default grid/model/save type/LUT size, background, close confirmation, and backup policy. | `manual-1.02`, `manual-1.11`, S4 pp. 6–7; S5 pp. 9–11 |

### B. Viewer, comparison, picking, and analysis

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| VIEW-01 | Before/after viewing as side-by-side or stacked images, movable split comparison, original-only view, and before/after swap. | `manual-1.02`, `manual-1.11`, S4 pp. 8, 36; S5 p. 8 |
| VIEW-02 | Toggle the separate reference image and compare work/reference during matching. | `manual-1.02`, `manual-1.11`, S3 “Working with the Image window”; S5 pp. 8, 46 |
| VIEW-03 | Display highlight/shadow clipping warnings and inspect RGB composite, individual RGB channels, grayscale, alpha, and black/white detail views. | `manual-1.02`, `manual-1.11`, S4 pp. 8–9, 36; S5 p. 8 |
| VIEW-04 | On-grid overlays for source color distribution, original node positions/tails, color planes, target/watch points, and the image color under the pointer. | `manual-1.02`, `manual-1.11`, S4 pp. 8, 16–18; S5 p. 8 |
| VIEW-05 | Mask preview and alpha-channel selection preview. | `manual-1.02`, `manual-1.11`, S4 pp. 8, 17–18, 34; S5 pp. 8, 12 |
| VIEW-06 | Color picker shows source and transformed values and cycles among RGB, RGB percent, linear RGB, HSV, HSP, Lab, MAB, and MXY representations. | `manual-1.02`, `manual-1.11`, S4 p. 37; S5 pp. 12–13 |
| VIEW-07 | Histogram modes for RGB channels and, in 1.11, saturation and hue. | `manual-1.02`, `manual-1.11`, S4 p. 38; S5 p. 43 |
| VIEW-08 | Waveform plus combined/separate RGB parade modes; the official product page positions Waveform/Parade as a Professional capability. | `current-official`, `manual-1.11`, S1; S5 pp. 43–44 |
| VIEW-09 | Vectorscope in YUV, with top/side views, rotation, and magnification. | `manual-1.02`, `manual-1.11`, S4 p. 38; S5 p. 44 |
| VIEW-10 | Dark/mid/light average swatches with numerical comparison against reference black/gray/white. | `manual-1.02`, `manual-1.11`, S4 pp. 38–39; S5 p. 44 |
| VIEW-11 | User color watches that retain source/result values, can target grids, and can be paired between work and reference images. | `manual-1.02`, `manual-1.11`, S4 p. 39; S5 pp. 44–45 |
| VIEW-12 | Color Sort visualization that orders pixels by brightness. | `manual-1.02`, `manual-1.11`, S4 p. 39; S5 p. 45 |
| VIEW-13 | Color-wheel test visualization after the current transformation. | `manual-1.02`, `manual-1.11`, S4 p. 39; S5 p. 45 |
| VIEW-14 | Analyzer source selection for full image, inside/outside an alpha selection, and work/reference image. | `manual-1.02`, `manual-1.11`, S4 p. 38; S5 p. 43 |
| VIEW-15 | Refresh the distributions/histograms after upstream edits. | `manual-1.02`, `manual-1.11`, S4 p. 9; S5 p. 8 |

### C. Color-management and material context

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| COLOR-01 | Use an embedded image ICC profile and provide automatic, explicit-load, discard-as-sRGB, or disabled monitor-profile modes. | `manual-1.02`, `manual-1.11`, S4 p. 6; S5 p. 5 |
| COLOR-02 | Assign an ICC profile without changing samples and convert an image to another ICC profile while preserving appearance. | `manual-1.02`, `manual-1.11`, S4 p. 8; S5 p. 7 |
| COLOR-03 | Select the ICC rendering intent used for out-of-gamut conversion. | `manual-1.02`, `manual-1.11`, S4 p. 7; S5 p. 10 |
| COLOR-04 | Load an output-device proof profile, enable soft proofing, and show a gamut warning. | `manual-1.02`, `manual-1.11`, S4 p. 9; S5 pp. 8–9 |
| COLOR-05 | Configure a working color model that changes the semantics of grids, brightness/saturation controls, and special curves. | `official-tutorial`, S3 “HSP and LAB color models” and “LXY, MXY, MABe, MXYe, SXY, YUV, CMYK and RGBW color models” |
| COLOR-06 | No official evidence was found for OCIO configuration, ACES transforms, explicit scene/display/view transforms, HDR display management, or floating-point image pipelines. | `needs-1.52-observation` |

### D. Composition model and global controls

The 1.11 manual documents a mostly fixed pipeline: white balance → Channels → Volume → A/B plus brightness/contrast → saturation → C/L → Curves → 2D Curves → Master. Curves may move before the grids, masks may be inserted at selected destinations, and an external LUT may be placed at input or output. This order is itself a reference capability because upstream changes alter downstream tool meaning. [S5 pp. 48–49]

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| PIPE-01 | Visible, deterministic transform order, including the ability to place Curves before or after the grids. | `manual-1.02`, `manual-1.11`, S4 p. 40; S5 pp. 48–49 |
| PIPE-02 | Enable/disable individual tool families and reset their state independently. | `manual-1.02`, `manual-1.11`, S4 throughout; S5 p. 3 and tool chapters |
| PIPE-03 | Temperature and tint controls, automatic/eyedropper white balance, and optional protection against white clipping. | `manual-1.02`, `manual-1.11`, S4 pp. 7, 21; S5 pp. 10, 14–15 |
| PIPE-04 | Global saturation, brightness, contrast, and contrast pivot controls. | `manual-1.02`, `manual-1.11`, S4 p. 21; S5 pp. 14–15 |
| PIPE-05 | Apply the current transformation to the working image, reset tools, and continue authoring a subsequent stage. | `manual-1.02`, `manual-1.11`, S4 p. 8; S5 p. 7 |

### E. Channels and Volume

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| CHAN-01 | Three-node visual RGB channel mixer with normalized mixtures, ordinary positive mixing inside the triangle, two-channel edges, and negative/hard mixing outside it. | `manual-1.02`, `manual-1.11`, S4 pp. 12–13; S5 pp. 16–17 |
| CHAN-02 | Direct numerical/node editing, grouped nodes, node brightness, reset, randomize, inverse, and whole-image hue/saturation operations. | `manual-1.02`, `manual-1.11`, S4 p. 13; S5 pp. 16–17 |
| CHAN-03 | Load/build a camera or color-calibration matrix and reset exposure compensation introduced by matrix fitting. | `current-official`, `manual-1.02`, S1 feature detail; S4 pp. 7, 13 |
| CHAN-04 | Match paired watch colors through the channel mixer. | `manual-1.11`, `needs-1.52-observation`, S5 p. 6 |
| VOL-01 | Build image luminance from a weighted mixture of RGB-channel luminances to recover or alter perceived detail/volume. | `current-official`, `manual-1.02`, S1 feature detail; S4 pp. 13–15 |
| VOL-02 | Lighten/darken amount, effect gamma, and node-level editing/reset. | `manual-1.02`, `manual-1.11`, S4 pp. 14–15; S5 pp. 18–19 |
| VOL-03 | Parallel/additive, multiplicative (“Star”), and arc/gamma-like luma modes, plus generation of a compensating luminance curve. | `manual-1.02`, `manual-1.11`, S4 p. 15; S5 pp. 18–19 |

### F. A/B color grid

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| AB-01 | Edit a 2D color plane whose node displacement changes hue/saturation and whose node depth/lightness changes luminance. Neutral colors occupy the center. | `current-official`, `manual-1.02`, `official-tutorial`, S1; S3 “Working principle of A/B and C/L color grids”; S4 pp. 16–18 |
| AB-02 | Work in documented Lab/Labn, LXY, MXY, MABe, MXYe, SXY/SXYe, HSP-family, YUV, CMYK, and RGBW-family models. Exact 1.52 dropdown contents remain to be captured. | `manual-1.02`, `manual-1.11`, `official-tutorial`, `needs-1.52-observation`, S3 model tutorials; S4 pp. 19–20; S5 pp. 21–23 |
| AB-03 | Circular/square regular grids and “Web” grids, with adjustable density. Manuals document regular sizes from 4 to 32 and Web variants from 6C to 24C. | `manual-1.02`, `manual-1.11`, S4 pp. 18–20; S5 pp. 25–26 |
| AB-04 | Pinned and interpolated/free nodes; select one, marquee-select, additive-select, invert selection, select/deselect all, and pin all. | `manual-1.02`, `manual-1.11`, S4 pp. 16–18; S5 pp. 20, 25 |
| AB-05 | Move one or four nodes on the grid or directly by dragging colors in the image; alter selected-color lightness from the image. | `manual-1.02`, `manual-1.11`, S4 pp. 17–18; S5 pp. 24–25 |
| AB-06 | Show the affected image region for a node or selected nodes and map the pointer's source/target color back to the grid. | `manual-1.02`, `manual-1.11`, S4 pp. 17–18; S5 pp. 24–25 |
| AB-07 | Contract or repel neighboring pinned nodes to compress/expand a color region, and smooth the grid. | `manual-1.02`, `manual-1.11`, S4 pp. 17–18; S5 pp. 24–25 |
| AB-08 | Reset all, selected nodes, only saturation, only hue, only position, or only node lightness. | `manual-1.02`, `manual-1.11`, S4 pp. 17–18; S5 pp. 24–25 |
| AB-09 | Choose additive, multiplicative, or gamma-style methods for node lightness changes. | `manual-1.02`, `manual-1.11`, S4 p. 19; S5 p. 25 |
| AB-10 | Edit target hue/saturation numerically through source/target indicators. | `manual-1.02`, `manual-1.11`, S4 p. 18; S5 p. 25 |
| AB-11 | Restrict the grid to shadows, highlights, or both with a gradual range control. | `manual-1.02`, `manual-1.11`, S4 pp. 22–23; S5 pp. 26–27 |
| AB-12 | Use independent highlight and shadow grids, including copy-up, copy-down, and swap operations. | `manual-1.02`, `manual-1.11`, S4 p. 23; S5 p. 27 |
| AB-13 | Targeted A/B tools introduced in 1.4 derive a desired characteristic from a chosen color or a color sampled from the work/reference image and bend the grid toward it. Exact modes and tolerances need licensed capture. | `official-tutorial`, `needs-1.52-observation`, S3 “Tools for working with the A/B color grid” / [official video](https://www.youtube.com/watch?v=etIX_e8-_lk) |
| AB-14 | Documented outcomes include selective recoloring, cast/reflection removal, separate shadow/highlight toning, hue-specific luminance, neutral tinting, saturation-dependent edits, harmonies, gamut cleanup, and target calibration. These are workflows over the grid, not necessarily separate tools. | `official-tutorial`, S3 “Practice with A/B color grid, part 1” |

### G. C/L color grid

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| CL-01 | Two orthogonal slices through the working color volume, with lightness vertical, saturation/hue horizontal, and the neutral axis centered. | `current-official`, `manual-1.02`, S1 feature detail; S4 pp. 24–25 |
| CL-02 | Rotate the slice axis numerically or by sampling a color; keep the two planes perpendicular. | `manual-1.02`, `manual-1.11`, S4 pp. 24–25; S5 pp. 29–30 |
| CL-03 | Move/select nodes on the grids or from the image and alter node lightness. | `manual-1.02`, `manual-1.11`, S4 p. 25; S5 p. 30 |
| CL-04 | Independently reset/smooth each color plane, reset/smooth luma, smooth both planes, pin all nodes, and pin neutrals. | `manual-1.02`, `manual-1.11`, S4 p. 25; S5 p. 30 |
| CL-05 | Select grid density while preserving the chosen axis orientation. | `manual-1.02`, `manual-1.11`, S4 p. 25; S5 p. 30 |

### H. Curves and curve extraction

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| CURVE-01 | Standard Master plus separate R/G/B curves. | `current-official`, `manual-1.02`, S1; S4 pp. 25–27 |
| CURVE-02 | Special Luminance, Saturation-by-Luminance, Saturation-by-Saturation, and Luminance-by-Saturation curves, interpreted in the current color model. The last is present on the current product page/tutorials but not clearly in the old English manual. | `current-official`, `official-tutorial`, `needs-1.52-observation`, S1 feature detail; S3 “Saturation curves” |
| CURVE-03 | Master modes documented as Normal, brightness-preserving Uniform, color-only, CMYK/CMYK2, and RGBW/RGBW2 separations. | `manual-1.02`, `manual-1.11`, S4 pp. 25–27; S5 pp. 30–33 |
| CURVE-04 | Per-curve enable/reset and strength, exact point entry, keyboard movement, point deletion, elastic editing, segment straightening, smoothing, and on-image point placement. | `manual-1.02`, `manual-1.11`, S4 pp. 27–29; S5 pp. 33–36 |
| CURVE-05 | Curve-local histograms/distributions and pointer-to-curve color location. | `manual-1.02`, `manual-1.11`, S4 p. 27; S5 pp. 33–34 |
| CURVE-06 | Targeted adjustment modes for neutralize, exact color, color with luminance preserved, hue only, saturation only, and luminance only. | `manual-1.02`, `manual-1.11`, S4 p. 28; S5 pp. 34–35 |
| CURVE-07 | Invert a curve, smooth RGB curves, extract Master from RGB, randomize, set automatic black/white, and show channel clipping. Version 1.11 also documents extracting RGB curves from an external LUT. | `manual-1.02`, `manual-1.11`, S4 pp. 27–29; S5 pp. 6, 35–36 |
| CURVE-08 | Import Photoshop `.acv` curves. | `current-official`, `manual-1.02`, S1; S4 p. 30 |
| CURVE-09 | Extract/apply split-toning curves from a reference image with De-grade/Grade, optional masked analysis, inverted import, and several statistical/channel methods. | `current-official`, `manual-1.02`, S1 feature detail; S4 pp. 29–30 |

### I. 2D Curves

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| 2DC-01 | Three side projections of the RGB cube with the neutral axis vertical, providing direct edits to the 3D structure of a LUT. | `current-official`, `manual-1.02`, S1 feature detail; S4 pp. 31–32 |
| 2DC-02 | Move nodes on a projection or from the image and alter node lightness. | `manual-1.02`, `manual-1.11`, S4 p. 31; S5 pp. 37–38 |
| 2DC-03 | Strength, updated color distribution, pin all/neutrals, proportional hue/lightness separation, luma reset, and smoothing. | `manual-1.02`, `manual-1.11`, S4 pp. 31–32; S5 pp. 37–38 |

### J. Masks, Master blend, and external LUT composition

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| MASK-01 | Build a color-domain mask from properties of the original image rather than a spatial painted mask. | `current-official`, `manual-1.02`, S1 feature detail; S4 pp. 33–35 |
| MASK-02 | Documented mask sources include original RGB/CMYK channels, luminance, hue, saturation, warmth, Lab/HSP color distances, HSP channels/phase, RGB distance, and transform-vs-source difference. | `manual-1.02`, `manual-1.11`, S4 pp. 34–35; S5 pp. 38–40 |
| MASK-03 | Curve-based mask shaping with preview, invert, randomize, exact point editing, and on-image placement. | `manual-1.02`, `manual-1.11`, S4 p. 34; S5 pp. 38–39 |
| MASK-04 | Fade, Limit, and Fit mask semantics. Version 1.11 additionally documents applying sources as input/output filters. Exact 1.52 method list needs capture. | `manual-1.02`, `manual-1.11`, `needs-1.52-observation`, S4 p. 34; S5 pp. 38–42 |
| MASK-05 | Select mask destination: entire transform or documented intermediate tool groups; 1.11 also documents “all except external LUT.” | `manual-1.02`, `manual-1.11`, `needs-1.52-observation`, S4 p. 34; S5 pp. 39–40 |
| EXT-01 | Load an external LUT, browse previous/next files in its folder, and control its blend. | `current-official`, `manual-1.02`, S1; S4 p. 35 |
| EXT-02 | Place an external LUT before or after application tools, use it as a monochrome mask, or alternate between it and the authored transform through a mask. | `manual-1.02`, `manual-1.11`, S4 p. 35; S5 p. 41 |
| EXT-03 | Compile the current transform as an in-memory external LUT, swap current/external transformations, and extract curves from an external LUT. | `manual-1.02`, `manual-1.11`, S4 pp. 7–8; S5 p. 6 |
| EXT-04 | Decompose a third-party LUT into contrast/Master, RGB split-toning, and HSL-like components for separate editing. A LUT created by 3D LUT Creator can be reopened as editable program settings. Exact supported input formats and decomposition fidelity need observation. | `current-official`, `official-tutorial`, `needs-1.52-observation`, S1 feature detail; S3 “How to change third party LUTs” |
| MASTER-01 | Final-stage controls for total blend and separate luminance, hue, and saturation contribution. | `manual-1.02`, `manual-1.11`, S4 p. 35; S5 pp. 41–42 |
| MASTER-02 | Blend modes documented in 1.11: Normal, Lighten, Darken, Less Saturated, More Saturated, Multiply, Screen, Soft Light, Overlay, and Linear Light. | `manual-1.11`, `official-tutorial`, S3 “Blend Modes”; S5 pp. 41–42 |

### K. Reference matching, Hald capture, and color targets

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| MATCH-01 | Transfer a reference image's tonal/color scheme to the work image through automatic Color Match. | `current-official`, `official-tutorial`, S1; S3 “Color Match with the Reference image” |
| MATCH-02 | Version 1.11 documents Color Match output through the A/B grid, white-balance controls, Luminance curve, and RGB curves, with selectable working model and optional dual grid. | `manual-1.11`, `needs-1.52-observation`, S5 pp. 46–48 |
| MATCH-03 | Reference analysis controls documented in 1.11 include de-grading method/amount, luminance range, color-area weighting, and previous/next reference browsing. | `manual-1.11`, `needs-1.52-observation`, S5 pp. 46–48 |
| MATCH-04 | Match controls documented in 1.11 include white-balance transfer, hue mapping method, protected hue/range, and independent hue/saturation/luminance/RGB-grading strengths. | `manual-1.11`, `needs-1.52-observation`, S5 pp. 47–48 |
| MATCH-05 | Convert a Lightroom preset, Photoshop plug-in/filter, or other externally applied image process into a LUT by applying it to an official Hald image and importing the result. Official Hald 5/8/16 materials represent 25³, 64³, and 256³ samples. | `current-official`, `official-tutorial`, S3 “How to create 3D LUT files from Lightroom presets or Photoshop Plugins”; S6 |
| TARGET-01 | Detect/align a photographed color target, optionally search offsets, apply a match, and report average, maximum, and selected-patch color error plus exposure/illumination deviation. | `manual-1.11`, `needs-1.52-observation`, S5 pp. 45–46 |
| TARGET-02 | Add target colors as paired watches, linearize neutral patches with curves, and adjust reference exposure. | `manual-1.11`, `needs-1.52-observation`, S5 pp. 45–46 |
| TARGET-03 | Current official list: X-Rite ColorChecker Classic, Passport Photo, Digital SG, Video, Passport Video; DSC Labs OneShot, CGH, ChromaDuMonde 24/28; Datacolor SpyderCheckr 24/SpyderCheckr; QPCard 202/203; IT8.7 and IT8.7 checkerboard. | `current-official`, S2 question 21 |
| TARGET-04 | Import custom measured target data in `.cie` or `.txt` form when the physical target is not built in. Schema, units, illuminant assumptions, and validation need observation. | `current-official`, `needs-1.52-observation`, S2 question 21 |
| TARGET-05 | Use targets to fit calibration through white balance/channel matrix and, where requested, curve linearization. Exact fitting objective and numerical color-difference formula are undocumented. | `current-official`, `manual-1.11`, `needs-1.52-observation`, S1; S5 pp. 45–46 |

### L. RAW, Log, and input-image handling

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| RAW-01 | Open camera RAW through LibRaw, choose decode color space, demosaic, and highlight-recovery algorithms. | `current-official`, `manual-1.02`, `manual-1.11`, S1; S4 pp. 7, 12; S5 pp. 10–11 |
| RAW-02 | Load or suppress RAW white balance and camera matrix, and optionally decode with UniWB. | `manual-1.11`, `needs-1.52-observation`, S5 p. 11 |
| RAW-03 | RAW development controls documented as Log profile, Blacks, Whites, and highlight/color recovery with manual/automatic overbright selection. | `manual-1.02`, `manual-1.11`, S4 pp. 21–22; S5 pp. 15–16 |
| RAW-04 | Current official Log/video-profile list: LogC, BMD Film, BMD Film 4K, BMD Film 4.6K, VisionLOG, Cinestyle, S-Log/S-Log2/S-Log3, RedLog, RedLogFilm, RED Log3G10, DJI Inspire Log, DJI D-Log variants, Cineon, V-Log, and Canon Log. | `current-official`, S1 feature detail; S2 question 20 |
| RAW-05 | Convert Log material to display-oriented spaces such as Rec.709/sRGB and author creative transforms against exported frames. Exact transfer functions, gamut assumptions, ranges, and versioned camera curves are not published. | `official-tutorial`, `needs-1.52-observation`, S3 “Working with LOG video footage” |
| IMG-01 | Documented still inputs: PNG, BMP, JPEG, TIFF (8/16-bit; RGB, CMYK, monochrome), Targa family (`.tga`, `.vda`, `.icb`, `.vst`), and camera RAW. Lab images are explicitly unsupported. | `manual-1.02`, `manual-1.11`, S4 p. 12; S5 p. 51 |
| IMG-02 | A version 1.11 preference refers to opening EXR in sRGB, but EXR is absent from the manual's format list. OpenEXR/HDR support is therefore unresolved. | `manual-1.11`, `needs-1.52-observation`, S5 pp. 10, 51 |
| IMG-03 | Save JPEG with configurable quality, RGB 16-bit TIFF, and PNG. Exact PNG depth/profile/alpha behavior needs observation. | `current-official`, `manual-1.02`, S1 feature detail; S4 p. 12 |
| IMG-04 | Import a Photoshop composite in 8- or 16-bit RGB, CMYK, or grayscale; Lab is unsupported. With a modified import action, a selection/layer mask can arrive in alpha. | `manual-1.02`, `manual-1.11`, S4 p. 10; S5 pp. 11–12 |

### M. LUT, preset, and auxiliary formats

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| FMT-01 | Export `.3dl` and `.cube`. The old manuals also document `.csp` with spline interpolation. | `current-official`, `manual-1.02`, `manual-1.11`, S1; S4 p. 12; S5 p. 51 |
| FMT-02 | Current marketing text names `.csv`, but the manuals do not. Exact CSV dialect and availability in Professional 1.52 require capture. | `current-official`, `needs-1.52-observation`, S1 “Videographers and Colorists” |
| FMT-03 | Export flattened PNG LUTs for GPUImage, Unity 3D (sizes 16 and 32), and Amplify Color (size 32). | `manual-1.02`, `manual-1.11`, S4 p. 12; S5 p. 51 |
| FMT-04 | Professional maximum LUT dimension is 96; Standard and Grading Edition are limited to 33. Preferences can force size 64 for Photoshop/export in the older manuals. The actual allowed size sequence needs capture. | `current-official`, `manual-1.02`, S1/S2; S4 p. 7 |
| FMT-05 | `.luc` program preset stores tool state; `.lub` stores batch settings; `.acv` imports curves; `.cie`/`.txt` import target measurements. | `current-official`, `manual-1.02`, `manual-1.11`, S2; S4 pp. 12, 30 |
| FMT-06 | Read and edit external LUTs, but the official public sources do not give an exhaustive accepted-input-format/dialect matrix. | `current-official`, `needs-1.52-observation`, S1 feature detail |
| FMT-07 | No official public specification was found for cube traversal order, interpolation method (except the `.csp` note), input/output domains, shaper LUTs, legal-range handling, values outside `[0,1]`, NaN/Inf policy, metadata preservation, or numerical precision. | `needs-1.52-observation` |

### N. Host and ecosystem interoperability

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| HOST-01 | Configure a known or custom Photoshop executable, diagnose Photoshop availability, import the active composite, and send the authored LUT back as a Color Lookup adjustment layer. | `current-official`, `manual-1.02`, `official-tutorial`, S2 questions 14–15; S3 “Working with LUTs in Photoshop”; S4 pp. 6–7, 10 |
| HOST-02 | Re-sending a LUT can replace the active, unrenamed Color Lookup layer while preserving its mask/properties; otherwise it creates a layer. This old behavior needs confirmation against current Photoshop. | `manual-1.02`, `needs-1.52-observation`, S4 p. 10 |
| HOST-03 | Use Color Lookup through Photoshop image adjustment, Layers, or Adjustments, and optionally embed LUT data in a PSD/action according to the old manual. | `manual-1.02`, `needs-1.52-observation`, S4 pp. 42–43 |
| HOST-04 | Configure ColorLUThier-like external-editor round trip in Lightroom: Lightroom exports a still copy, the desktop app edits/saves it, and Lightroom observes the saved image. Lightroom is not documented as consuming the LUT directly. | `manual-1.02`, `official-tutorial`, S3 “Working with Lightroom”; S4 pp. 40–42 |
| HOST-05 | Video workflow is explicitly frame-based: export/grab a representative frame, author against it, export a LUT, and apply that LUT to the clip in the host. Direct video-file editing is unsupported. | `current-official`, `manual-1.02`, `official-tutorial`, S2 question 19; S3 video tutorials; S4 pp. 41–44 |
| HOST-06 | Officially named LUT consumers include Photoshop, After Effects, Premiere, SpeedGrade, DaVinci Resolve, Final Cut Pro X, Hiero, Nuke, Sony Vegas, and Unity 3D components. Compatibility is a publisher claim, not a current conformance result. | `current-official`, S2 question 8 |
| HOST-07 | Current product detail claims one-click still/frame import from Photoshop, After Effects, and MLVProducer and one-click LUT export to Photoshop and MLVProducer. Exact mechanisms and platform coverage need capture. | `current-official`, `needs-1.52-observation`, S1 feature detail |
| HOST-08 | Resolve workflow demonstrated by the publisher exports a still (for example TIFF), opens it in 3D LUT Creator, exports a LUT, and applies it in Resolve. | `official-tutorial`, S3 “Using 3D LUT Creator with Davinci Resolve & Red Camera Footage” |
| HOST-09 | Premiere/Final Cut/other video hosts consume an exported LUT; camera-development and creative LUTs may occupy different stages in the host pipeline. | `official-tutorial`, S3 “Working with V-Log footage in 3D LUT Creator and Adobe Premiere” |
| HOST-10 | Separate free plug-ins currently exist for OFX (Resolve/Vegas), Premiere, and Final Cut Pro. They are associated ecosystem products and **not** part of the selected desktop benchmark; the Wayfinder map already places continuous live-link/full host-plug-in operation outside the first professional release. | `current-official`, S7 |

### O. Look management and batch processing

| ID | Capability to account for | Evidence |
| --- | --- | --- |
| LOOK-01 | Scan LUT libraries and create a thumbnail gallery showing each look on the active image. | `current-official`, `official-tutorial`, S1 feature detail; S3 “Look manager” |
| LOOK-02 | Browse/select a look without sequential file-by-file loading. | `official-tutorial`, S3 “Look manager” |
| LOOK-03 | Ship a library of ready-to-use LUTs and allow compatible library LUTs to open as editable presets. Bundled-content licensing is not a ColorLUThier parity requirement; the workflow is. | `current-official`, `official-tutorial`, S1; S3 “Look manager” |
| BATCH-01 | Professional-only processing of multiple still images with the current LUT. | `current-official`, `official-tutorial`, S2 question 2; S3 “Batch processing” |
| BATCH-02 | Add files or a folder, optionally recurse into subfolders, remove/clear list items, and choose the output format. | `manual-1.02`, `manual-1.11`, S4 p. 11; S5 p. 50 |
| BATCH-03 | Save beside sources, in a subfolder, or in a specified folder; add prefix/postfix; skip existing outputs. | `manual-1.02`, `manual-1.11`, S4 p. 11; S5 p. 50 |
| BATCH-04 | Load/save `.lub` batch presets and run/close the batch dialog. | `manual-1.02`, `manual-1.11`, S4 pp. 11–12; S5 pp. 50–51 |

## Material and platform constraints that reference coverage must acknowledge

These constraints are not necessarily desirable ColorLUThier behaviors. They are part of understanding the benchmark and identifying where ColorLUThier should deliberately improve it.

1. **Still-frame application model.** The desktop app does not edit video files; hosts provide a frame and later consume the LUT. [S2 question 19; S4 pp. 41–44]
2. **Professional maximum LUT size of 96.** Other desktop editions are documented as limited to 33. [S1; S2 question 2]
3. **Legacy documented platforms and Intel-only public Mac build.** The FAQ says Windows XP or newer and OS X 10.6 or newer, with separate Windows/macOS licenses; Linux is not offered. The official macOS demo's executable is x86_64-only and therefore not a native Apple Silicon build. This does not establish whether it runs correctly under Rosetta or whether a different licensed artifact exists. [S2 questions 1, 11–12; S8]
4. **No documented Lab image input.** Lab is explicitly excluded even though Lab and Lab-derived models are authoring spaces. [S4 p. 12]
5. **Fixed/partially movable pipeline.** Tool order affects semantics; it is not a free node graph. [S5 pp. 48–49]
6. **ICC-era public color contract.** The manuals describe ICC monitor/image/proofing behavior, but the public sources do not document OCIO, ACES, HDR display transforms, or scene-linear policy.
7. **Ambiguous modern file contract.** `.csv` versus `.csp`, OpenEXR, accepted external-LUT dialects, PNG depth, and domain/range behavior require licensed-build evidence.
8. **No public numerical conformance contract.** Interpolation, precision, clamping, gamut behavior, transform round-trip error, and target-matching objective are not specified.
9. **Old public documentation.** The newest public manual found is 1.11; the selected product version is 1.52. Tutorials bridge part, not all, of that gap.
10. **Companion plug-ins are a separate surface.** Current OFX/Premiere/FCP plug-ins exist, but they do not change the selected standalone Professional benchmark boundary. [S7]

## Licensed 1.52 evidence capture still required

This is a bounded verification protocol for the maintainer's lawful installation. It should be performed before the coverage matrix is treated as exhaustive at control-level fidelity.

### Provenance capture

- Capture About dialog, edition, exact version/build, platform, and architecture.
- Record the official-account download filename, byte size, SHA-256, code-signing/notarization metadata, and download date without redistributing the installer.
- Record OS and host-application versions used for observations.

### Surface capture

- Capture every menu, preference pane, tab, context menu, toolbar, model list, grid size, curve mode, mask source/method/destination, blend mode, target type, Log profile, input/output file picker, and shortcut list.
- Diff the capture against every inventory ID above. Add genuinely new capabilities; do not erase older documented ones until their removal is observed.

### Behavioral capture

- Save minimal fixtures for every tool using synthetic ramps, RGB cubes, color wheels, alpha masks, embedded ICC profiles, and values near black/white/gamut boundaries.
- For each tool, record default state, parameter range, neutral/no-op state, reset semantics, upstream/downstream order, and whether output depends on working model.
- Export identity and nontrivial LUTs at every offered size/format; parse headers/order/domains and compare sampled results with the application preview.
- Test external-LUT imports for every offered dialect, interpolation behavior, input/output placement, decomposition, re-export, and out-of-range values.
- Test Photoshop import/send/replace behavior and the explicit Resolve still→author→LUT→clip round trip on current host versions.
- Test target matching with a known spectral/measurement dataset and record the actual error metric, illuminant/observer assumptions, adaptation, and fitting stages.

### Numerical acceptance evidence to retain

- Source fixture and its ICC/transfer/gamut metadata.
- All application settings or `.luc` preset.
- Exported LUT and parsed metadata.
- Independent reference evaluation over both lattice points and dense off-lattice samples.
- Maximum, percentile, and visualized error, including near boundaries.
- Screenshots only where they prove interaction semantics; never copy proprietary assets into ColorLUThier.

## Implications for later Wayfinder decisions

The inventory clears enough fog to phrase these decisions precisely:

1. **Authoring transform model:** which grid/model families ColorLUThier will implement literally, which will be generalized, and how a modern composable pipeline replaces the benchmark's fixed order without losing outcomes.
2. **Reference and target matching contract:** algorithms, fit objectives, protected regions, error metrics, and reproducibility for automated image and chart matching.
3. **External-LUT editing contract:** supported formats/domains, decomposition guarantees, interpolation, placement, blending, masking, and numerical round-trip requirements.
4. **Analyzer contract:** scopes, histograms, waveform/parade, vectorscope, watches, color wheel, clipping, proofing, and reference comparison under explicit color contexts.
5. **Project/preset and look-library contract:** durable editable state, version comparison, thumbnails, search/organization, portability, and migration.
6. **RAW/Log boundary:** whether ColorLUThier decodes camera RAW/Log directly or requires normalized stills from host applications while preserving exhaustive reference coverage through a better workflow.

The licensed-build capture itself should remain a task that gates final control-level coverage, not a reason to defer the product-level decisions above.

## Resolution summary

Adopt **3D LUT Creator Professional 1.52** as the authoritative named benchmark and use this inventory as the initial reference-coverage ledger. The benchmark is exhaustive at publicly documented capability-family level, while exact 1.52 controls, file dialects, numerical semantics, and current host behavior remain explicitly gated on lawful observation of the maintainer's licensed installation.
