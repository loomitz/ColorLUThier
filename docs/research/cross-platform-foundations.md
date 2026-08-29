# Cross-platform application foundations survey

**Status:** Research resolution; no architecture selected  
**Snapshot:** 2026-08-29  
**Question:** Which maintained open-source foundations could support a macOS-first ColorLUThier application with a shared Windows/Linux core, ICC and OCIO/ACES color management, an interactive GPU viewport, international contributors, automated tests, and distributable desktop packages?

## Answer in brief

There is no single framework that supplies a trustworthy color-managed desktop application end to end. The viable foundations separate into three layers:

1. a native color and image kernel built around **OpenColorIO + ACES configuration data**, **Little CMS**, and either **OpenImageIO** or **libvips**;
2. an application shell and viewport chosen from several credible cross-platform shapes; and
3. small platform adapters for display profiles, HDR/EDR behavior, signing, and packaging.

Five integrated shapes remain plausible enough to prototype rather than eliminate on paper:

- C++20 + Qt Quick + a native C++ color kernel;
- Rust + egui/wgpu + a C++ color bridge;
- Rust/Tauri + a web UI around a native worker and native viewport;
- .NET/Avalonia + a native color kernel; and
- a shared C++ kernel behind platform-native shells, beginning with SwiftUI/AppKit/Metal on macOS.

They trade off FFI complexity, desktop polish, GPU ownership, contributor accessibility, packaging maturity, and license obligations. None has yet proved ColorLUThier's required pixel fidelity or interaction latency. In particular, OCIO can generate GPU shader code, but the application still owns texture formats, resource binding, display transformation, CPU/GPU parity, and per-platform presentation. The next architecture decision therefore needs measured prototypes and an explicit display contract, not a framework popularity vote.

## Scope and evaluation method

This survey uses official project documentation, repositories, release records, and license texts. "Maintained" means that the project shows a current supported release or recent upstream activity as of the snapshot date; it does not guarantee future stewardship. License notes are engineering inputs, not legal advice.

The comparison uses three confidence terms:

- **Direct:** upstream exposes the relevant capability without a new cross-language boundary.
- **Integrate:** there is a documented path, but ColorLUThier must own meaningful glue.
- **Prove:** fidelity, performance, or distribution behavior is still uncertain enough to require a prototype on target hardware.

The survey does not choose the product architecture, license, supported image formats, HDR scope, or minimum operating-system versions.

## Common color and image foundation

### OpenColorIO and ACES configuration data

[OpenColorIO (OCIO)](https://opencolorio.readthedocs.io/en/latest/) is the strongest common foundation for scene-referred transforms, display/view transforms, and LUT processing. Its processor API exposes both [optimized CPU processors and GPU processors](https://opencolorio.readthedocs.io/en/latest/api/processors.html). The GPU path can emit shader descriptions for GLSL, HLSL/D3D, Metal Shading Language, and Vulkan-oriented GLSL, but application code must still create textures, uniforms, samplers, command buffers, and the presentation surface.

OCIO's [supported formats and utilities](https://opencolorio.readthedocs.io/en/latest/guides/using_ocio/using_ocio.html) cover common LUT interchange, including reading `.cube` and baking output formats. CLF/CTF support gives a more expressive interchange path than a 3D LUT alone. OCIO 2.5 also ships built-in [ACES 2.0 CG and Studio configurations](https://opencolorio.readthedocs.io/en/latest/releases/ocio_2_5.html), while the separately maintained [OpenColorIO ACES configuration repository](https://opencolorio.readthedocs.io/projects/config-aces/en/latest/) records its own versioning and BSD-3-Clause license.

OCIO is not a complete ICC solution. Its user guide describes only basic monitor-ICC support. That is adequate as a convenience path, not as the sole foundation for arbitrary input, output, proofing, device-link, and display profiles. The core is [BSD-3-Clause licensed](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/main/LICENSE). The current [2.5.2 release](https://github.com/AcademySoftwareFoundation/OpenColorIO/releases/tag/v2.5.2) also fixed security-sensitive LUT parser issues, evidence that untrusted LUT input needs fuzzing and prompt dependency updates.

### Little CMS for ICC

[Little CMS](https://github.com/mm2/Little-CMS) implements ICC v2/v4 and the current ICC specification family, including device-link, abstract, and named-color profiles. Its C API makes it usable from every candidate stack, and the core [MIT license](https://github.com/mm2/Little-CMS/blob/master/LICENSE) is compatible with permissive or copyleft application licenses. The current maintenance baseline is [2.19.1](https://github.com/mm2/Little-CMS/releases/tag/lcms2.19.1).

One dependency trap must be explicit: the repository's optional [`threaded`](https://github.com/mm2/Little-CMS/blob/master/plugins/threaded/include/lcms2_threaded.h) and [`fast_float`](https://github.com/mm2/Little-CMS/blob/master/plugins/fast_float/include/lcms2_fast_float.h) plug-ins are GPLv3-or-later even though the Little CMS core is MIT. A permissively licensed ColorLUThier distribution should exclude them unless a later license decision and review says otherwise. Performance tests must therefore use the exact dependency build intended for distribution.

### OpenImageIO versus libvips

Both imaging libraries are maintained and cross-platform; they optimize for different workloads.

| Input | OpenImageIO | libvips |
|---|---|---|
| Primary model | VFX-oriented image I/O, metadata, `ImageBuf`, and cached/tiled access | Demand-driven image graph with horizontal threading and low-memory streaming |
| Color integration | Direct C++ integration with OCIO and broad high-dynamic-range workflows | Built-in ICC operations through Little CMS; OCIO would be application glue |
| Formats | Broad plug-in set; exact availability depends on build dependencies | Broad photo/web formats; exact availability also depends on loaders present |
| Shared-kernel fit | Best fit for a C++ kernel and EXR/VFX-grade metadata | Attractive for very large Reference images and Rust/C#/web worker boundaries |
| License | Apache-2.0 for nearly all current code, with small historical BSD portions | LGPL-2.1-or-later |
| Open question | Memory behavior and dependency footprint for the selected Reference image set | Precision, metadata round trips, and OCIO-centered workflow coverage |

[OpenImageIO's documentation](https://openimageio.readthedocs.io/en/stable/) describes the supported image formats and processing APIs. `ImageBuf` supports local image manipulation, while [ImageCache](https://openimageio.readthedocs.io/en/v3.0.16.0/imagecache.html) provides lazy, tiled, shared caching for large data. Its [installation guide](https://github.com/AcademySoftwareFoundation/OpenImageIO/blob/main/INSTALL.md) documents C++17, CMake, and Windows/macOS/Linux builds. The current maintenance point is [3.1.16.0](https://github.com/AcademySoftwareFoundation/OpenImageIO/releases/tag/v3.1.16.0), and its [license statement](https://openimageio.readthedocs.io/en/v3.0.13.0/copyr.html) is permissive.

[libvips](https://github.com/libvips/libvips/blob/master/README.md) explicitly documents demand-driven evaluation, threading, and low memory use, and its [color operations](https://github.com/libvips/libvips/blob/master/doc/libvips-colour.md) use Little CMS for ICC transforms. Its current [8.18.6 release](https://github.com/libvips/libvips/releases/tag/v8.18.6) and LGPL-2.1-or-later license make it viable, but distribution and relinking obligations need to be incorporated into packaging.

The image library cannot be chosen until the project states which RAW, PSD, TIFF, EXR, JPEG/HEIF/AVIF, alpha, bit depth, orientation, and metadata behaviors are required. Format names alone are insufficient: build-time codecs and read/write asymmetries must be tested from packaged binaries.

## GPU and display-color boundary

### GPU execution

[wgpu](https://github.com/gfx-rs/wgpu) is a maintained MIT/Apache-2.0 implementation of the WebGPU model with native Metal, Direct3D 12, Vulkan, and OpenGL/GLES backends. Its native Rust API accepts [WGSL, SPIR-V, and GLSL shader sources](https://docs.rs/wgpu/latest/wgpu/enum.ShaderSource.html). That makes an OCIO-generated GLSL-to-wgpu experiment plausible, but not automatic: ColorLUThier must prove shader translation, 1D/3D LUT resource layouts, half/float texture choices, dynamic properties, and numeric parity across Metal, Direct3D, and Vulkan.

Qt Quick uses the [Rendering Hardware Interface](https://doc.qt.io/qt-6/qrhi.html) over Metal, Direct3D, Vulkan, and OpenGL. [`QQuickRhiItem`](https://doc.qt.io/qt-6/qquickrhiitem.html) is a public route for integrating custom rendering into a Qt Quick scene, but the underlying `QRhi` API is in Qt Gui's private module and explicitly has limited source and binary compatibility guarantees. A direct QRhi viewport is therefore a maintenance risk that needs a version-upgrade prototype. A Qt shell could alternatively host wgpu or another native renderer, at the cost of native-window and synchronization glue.

### Display profiles and HDR

Display color cannot be delegated blindly to any cross-platform UI toolkit:

- On macOS, [ColorSync](https://developer.apple.com/documentation/colorsync) and [`NSScreen.colorSpace`](https://developer.apple.com/documentation/appkit/nsscreen/colorspace) expose system color information, but the application must define whether ColorSync or its own OCIO/ICC pipeline owns the final transform.
- On Windows, the legacy [`WcsGetDefaultColorProfile`](https://learn.microsoft.com/en-us/windows/win32/api/icm/nf-icm-wcsgetdefaultcolorprofile) documentation says it does not return the advanced color profile used for HDR/Advanced Color displays. A modern Windows adapter and OS-version matrix are required.
- On Linux, [colord](https://github.com/hughsie/colord) provides a D-Bus service for device/profile association. Window-system and compositor behavior still differs across X11 and Wayland.
- Qt's [`QColorSpace`](https://doc.qt.io/qt-6/qcolorspace.html) can parse RGB and gray ICC profiles and represent common transfer functions, but it is not a complete arbitrary-profile or monitor-HDR contract.
- A web viewport is the least deterministic option. The WebGPU specification states that [WebGPU itself performs no color management](https://www.w3.org/TR/2026/CRD-webgpu-20260109/); web canvas color spaces are generally bounded to sRGB or Display-P3, as illustrated by WebKit's [wide-gamut canvas implementation](https://webkit.org/blog/12058/wide-gamut-2d-graphics-using-html-canvas/). That does not prove arbitrary ICC/OCIO output or HDR fidelity.

Every candidate needs a written rule for transform order and ownership. Otherwise a Reference image can be transformed twice—once by ColorLUThier and once by a framework, webview, or operating system—or not transformed at all after a window moves to another display.

## Integrated stack shapes

### A. C++20 + Qt 6 Quick/QML

**Shape:** C++ application and color kernel; Qt Quick/QML shell; OCIO + Little CMS + OpenImageIO/libvips; custom Qt RHI or embedded wgpu viewport; CMake/CTest; Qt deployment tools.

**Strengths.** OCIO and OpenImageIO are native C++ libraries, so this shape has the smallest FFI surface. Qt supports current [desktop platforms](https://doc.qt.io/qt-6/supported-platforms.html), including Apple Silicon and Intel macOS as well as Windows and Linux. Qt recommends Qt Quick for new accelerated interfaces in its [graphics overview](https://doc.qt.io/qt-6/topics-graphics.html). Qt Test, [Qt Quick Test](https://doc.qt.io/qt-6/qtquicktest-index.html), and CTest cover unit and UI-component tests. `macdeployqt`, `windeployqt`, and CMake deployment support provide documented starting points for [macOS](https://doc.qt.io/qt-6/macos-deployment.html), [Windows](https://doc.qt.io/qt-6/windows-deployment.html), and [Linux](https://doc.qt.io/qt-6/linux-deployment.html).

**Costs and proof points.** Modern C++ and QML are a narrower contributor funnel than TypeScript or C#. A color viewport using private QRhi types creates upgrade risk; embedding a separate GPU layer creates window/surface complexity. Qt's [open-source licensing](https://doc.qt.io/qt-6/licensing.html) is LGPLv3/GPL, with some modules available only under GPL or commercial terms. A distribution needs an approved module list, license notices, corresponding library source or offer where required, and a relinking/replacement strategy. Static linkage is possible under LGPL only with additional compliance work; dynamic linkage is the simpler engineering lane. Qt's [release policy](https://doc.qt.io/qt-6/qt-releases.html) also distinguishes commercial LTS access, which should be considered in a long-lived open-source maintenance plan.

### B. Rust + egui/eframe + wgpu

**Shape:** Rust application and GPU viewport; egui/eframe shell; wgpu renderer; Little CMS through C FFI; OCIO/OpenImageIO through a narrow C or C++ bridge; Cargo tests and packaging.

**Strengths.** Rust has supported Apple, Windows, and Linux targets in its [platform support policy](https://doc.rust-lang.org/rustc/platform-support.html). [egui](https://github.com/emilk/egui) is a portable immediate-mode GUI with eframe integration, a wgpu renderer, custom GPU callbacks, and AccessKit accessibility integration. Rust and wgpu are memory-safe foundations for new application and renderer code, and [`cargo test`](https://doc.rust-lang.org/cargo/commands/cargo-test.html) gives consistent workspace-level test orchestration. [`cargo-packager`](https://github.com/crabnebula-dev/cargo-packager) supports macOS application/DMG, Linux package formats, and Windows NSIS/MSI output.

**Costs and proof points.** egui's own README says it does not aim to look native and that API stability is still evolving; a professional desktop editor must validate text input, menus, accessibility, drag/drop, high-DPI behavior, and long sessions. OCIO and OpenImageIO are C++, so a bridge such as [CXX](https://github.com/dtolnay/cxx) can statically check the declared Rust/C++ boundary but does not remove C++ build, exception, lifetime, or ABI work. GPU shader translation and display management remain application-owned. `cargo-packager` does not by itself solve native C++ dynamic libraries, rpaths, universal macOS binaries, signing, or notarization.

### C. Rust/Tauri 2 + web UI + native worker

**Shape:** HTML/CSS/TypeScript application shell in Tauri; Rust command layer; C/C++ color worker; image pixels remain in a native GPU surface or worker rather than crossing IPC for every frame.

**Strengths.** [Tauri](https://github.com/tauri-apps/tauri) is MIT/Apache-2.0 and uses the platform webview rather than shipping a full browser engine. It offers a large TypeScript contributor surface and documented bundling for [macOS, Windows, and Linux](https://v2.tauri.app/distribute/). Its [testing guidance](https://v2.tauri.app/develop/tests/) covers Rust unit/integration tests, mocked frontend APIs, and WebDriver-based application tests.

**Costs and proof points.** WKWebView, WebView2, and WebKitGTK do not produce one identical rendering/color environment. Full-resolution or interactive frames cannot be copied through JSON/IPC on each update; the native viewport integration has to be designed and measured. WebGPU and canvas do not establish an arbitrary ICC/OCIO/HDR presentation contract, so a pure canvas viewport is a **Prove**, not a direct fit. Linux inherits the distribution's WebKitGTK variability. Tauri packages the shell but the project still owns native dependency bundling and platform signing.

### D. .NET 10/C# + Avalonia 12

**Shape:** C#/Avalonia application shell and state model; Skia/custom rendering or an imported native GPU surface; C ABI around the native color kernel; `dotnet test` and `dotnet publish`.

**Strengths.** [.NET](https://github.com/dotnet/runtime) and [Avalonia](https://github.com/AvaloniaUI/Avalonia/blob/main/licence.md) are MIT licensed. Avalonia documents [Windows, macOS, and Linux support](https://docs.avaloniaui.net/docs/supported-platforms), provides a single XAML/C# UI model, and has [headless testing facilities](https://docs.avaloniaui.net/docs/concepts/headless/). Its [custom rendering APIs](https://docs.avaloniaui.net/docs/graphics-animation/custom-rendering) allow Skia drawing and imported external GPU objects. C# is approachable to a broad contributor pool, and application logic can be strongly tested without a display server.

**Costs and proof points.** Avalonia's current support table marks Linux X11 as the default and Wayland support as experimental, so Linux expectations need a versioned target. The renderer does not natively consume an OCIO GPU processor; a custom Skia effect or separate native surface is still needed. P/Invoke should target a stable C ABI rather than exporting a C++ ABI. [.NET single-file deployment](https://learn.microsoft.com/en-us/dotnet/core/deploying/single-file/overview) simplifies runtime distribution, but native dependencies still require per-RID packaging. Avalonia's [macOS deployment guide](https://docs.avaloniaui.net/docs/deployment/macos) notes that universal binaries require separate architecture publications and combination; signing/notarization remain build-pipeline responsibilities. Avalonia Parcel can automate distribution but requires a paid Plus license, so it is not counted as an open-source foundation.

### E. Shared C++ kernel + platform-native shells

**Shape:** a stable C/C++ color and document kernel; SwiftUI/AppKit/Metal shell first on macOS; later Windows and Linux shells over the same kernel.

**Strengths.** This gives the macOS product the most direct access to ColorSync, Metal, EDR, AppKit documents, drag/drop, accessibility, and signing conventions. OCIO/OpenImageIO remain direct C++ dependencies. It also provides a control case against which cross-platform toolkit compromises can be measured.

**Costs and proof points.** AppKit and SwiftUI are platform SDKs, not open-source cross-platform foundations. The shared color and project core can be open source, but UI behavior, viewport hosting, accessibility, and UI tests must be implemented again for Windows and Linux. It front-loads macOS quality while postponing proof of the Windows/Linux product. Contributor skills fragment by shell, and feature parity becomes a governance concern.

## Comparison matrix

| Stack shape | Shared core/UI | ICC + OCIO/ACES | GPU viewport | Desktop/platform maturity | Testability | Packaging | License posture | Largest unknown |
|---|---|---|---|---|---|---|---|---|
| C++/Qt Quick | Direct core; shared UI | **Direct** C++ integration | **Integrate/Prove** through QQuickRhiItem, private QRhi, or embedded renderer | Mature desktop coverage | Strong C++/Qt/CTest layers; real-GPU CI still needed | Documented deploy tools; Linux and native codec closure still app-owned | LGPLv3/GPL/module audit; permissive color kernel | Can a maintainable public-API viewport meet fidelity and latency without private-API lock-in? |
| Rust/egui/wgpu | Shared Rust UI; C++ bridge | **Integrate** through C/C++ FFI | **Integrate/Prove**; renderer ownership is clear | Cross-platform, but less native desktop convention | Strong unit/property tests; GUI and GPU hardware matrix needed | Cross-platform packager; native libraries/signing manual | Mostly MIT/Apache; bridged dependencies retain their licenses | Is the FFI/build burden and egui desktop polish acceptable for international contributors? |
| Tauri/native worker | Shared web UI and Rust command layer | **Integrate** in native worker | **Prove**; native surface preferred over canvas/IPC frames | Strong shell reach, variable system webviews | Strong web/Rust tests; native viewport E2E harder | Broad built-in bundle targets | MIT/Apache plus web/native dependencies | Can a native color-managed viewport coexist cleanly with the webview on every platform? |
| .NET/Avalonia | Shared C# UI; native kernel bridge | **Integrate** through C ABI/P/Invoke | **Prove** through Skia effect or imported surface | Strong Windows/macOS; Linux Wayland still experimental | Strong headless/unit testing; GPU matrix needed | `dotnet publish`; universal Mac/signing/native libs require pipeline work | MIT framework/runtime; dependency audit remains | Can imported GPU rendering preserve color fidelity, portability, and acceptable deployment size? |
| Native shells/shared C++ | Shared kernel, separate UIs | **Direct** kernel integration | **Direct on macOS**, later platforms separate | Best macOS integration; other shells unproved | Strong kernel tests; duplicate shell/UI tests | Best native Mac path, three separate packaging systems | Kernel can be permissive; Apple UI SDK is proprietary platform infrastructure | Does macOS-first velocity justify later UI duplication and parity governance? |

This matrix intentionally does not rank the candidates. "Direct" describes API proximity, not guaranteed correctness.

## Maintenance snapshot

The following versions demonstrate current activity at the snapshot date; they are not dependency pins:

| Foundation | Current evidence at 2026-08-29 | License posture |
|---|---|---|
| OpenColorIO | [2.5.2, 2026-05-13](https://github.com/AcademySoftwareFoundation/OpenColorIO/releases/tag/v2.5.2) | BSD-3-Clause |
| OCIO ACES configs | [current documentation/release stream](https://opencolorio.readthedocs.io/projects/config-aces/en/latest/) | BSD-3-Clause |
| Little CMS | [2.19.1, 2026-05-06](https://github.com/mm2/Little-CMS/releases/tag/lcms2.19.1) | MIT core; selected optional plug-ins GPLv3-or-later |
| OpenImageIO | [3.1.16.0, 2026-08-01](https://github.com/AcademySoftwareFoundation/OpenImageIO/releases/tag/v3.1.16.0) | Apache-2.0, small historical BSD portions |
| libvips | [8.18.6, 2026-08-25](https://github.com/libvips/libvips/releases/tag/v8.18.6) | LGPL-2.1-or-later |
| Qt | [6.11 release series](https://wiki.qt.io/Qt_6.11_Release) | LGPLv3/GPL/commercial; module-specific |
| Rust | [1.98.0, 2026-08-20](https://blog.rust-lang.org/2026/08/20/Rust-1.98.0/) | MIT/Apache-2.0 toolchain components |
| wgpu | [release history](https://github.com/gfx-rs/wgpu/releases) | MIT/Apache-2.0 |
| egui | [release history](https://github.com/emilk/egui/releases) | MIT/Apache-2.0 |
| Tauri | [release history](https://github.com/tauri-apps/tauri/releases) | MIT/Apache-2.0 |
| Avalonia | [12.1.1, 2026-07-29](https://github.com/AvaloniaUI/Avalonia/releases/tag/12.1.1) | MIT |
| .NET runtime | [release history](https://github.com/dotnet/runtime/releases) | MIT |
| cargo-packager | [release history](https://github.com/crabnebula-dev/cargo-packager/releases) | MIT/Apache-2.0 |

Release recency is only one signal. Bus factor, security response, compatibility policy, CI coverage, and the cost of carrying a fork need separate evaluation before dependency commitment.

## License and distribution inputs

The product license is unresolved, so two lanes must remain visible:

- A **permissive application** is straightforward with OCIO, the ACES configs, Little CMS core, OpenImageIO, Rust/wgpu/egui/Tauri/CXX, Avalonia/.NET, and permissive packaging tools. It requires excluding GPL-only Little CMS plug-ins and auditing every optional codec, Qt module, and bundled profile.
- An **LGPL/GPL-compatible application** can more easily consume Qt and libvips, but still needs source/notices/relinking processes and cannot assume that all ICC profiles or codec data are redistributable.

Qt under LGPL is not the same as a permissive dependency; libvips under LGPL-2.1-or-later has its own compliance requirements. A GPL application could simplify some choices but would be a product/governance decision, not a technical default. Commercial packaging helpers such as Avalonia Parcel should not silently become required for a supposedly open-source build.

Third-party configuration and data assets need an inventory separate from code. ACES config data is BSD-3-Clause, but display/camera profiles and vendor LUTs can have independent redistribution terms. ColorLUThier should never treat a profile found on a user's system as redistributable project data by default.

## Validation architecture required for every candidate

A serious foundation decision should require the same evidence from each finalist:

1. **Canonical CPU reference.** Define a float CPU transform using pinned OCIO configuration data and Little CMS behavior, including alpha and out-of-range values.
2. **CPU/GPU parity.** Compare the same Color transformation on Apple Silicon/Metal, Windows/Direct3D, and Linux/Vulkan with explicit tolerances and adversarial colors, not only a visually pleasant image.
3. **Image round trips.** Test representative bit depths, transfer functions, embedded ICC profiles, orientation, alpha semantics, metadata, and malformed input from the packaged application.
4. **Display transitions.** Test profile changes, window moves between unlike monitors, SDR/HDR/EDR switching, sleep/wake, and screen hot-plug while detecting both missing and double transforms.
5. **Interactive budgets.** Measure cold load, first preview, slider-to-photon latency, sustained 4K/8K updates, peak resident memory, cache eviction, and export time on declared minimum hardware. Numeric gates belong in the architecture/prototype ticket.
6. **Parser security.** Fuzz LUT, ICC, project, and image inputs; cap dimensions and allocations; run sanitizers on the native kernel. OCIO 2.5.2's parser security fix makes this an operational requirement, not an optional hardening pass.
7. **Clean-machine distribution.** Build and test signed/notarized universal macOS packages first, then Windows and representative Linux packages, with no developer-installed codecs or runtimes assumed.
8. **UI-independent project state.** Serialize Color transformations and LUT/export settings independently of QML, egui, the DOM, XAML, or SwiftUI so candidate shells and headless tests exercise the same semantics.

## Risks that remain across all stacks

- **Display ownership is undefined.** The current requirements do not state whether ColorLUThier, the OS, or the framework owns the last display conversion, especially for HDR/EDR.
- **LUT export is narrower than the working transform.** ICC and OCIO operations can exceed what a fixed 3D LUT represents. Domain/range, shaper curves, grid size, clipping, interpolation, alpha, and metadata policy must be explicit for Photoshop, Resolve, and other Host applications.
- **Image-format scope drives architecture.** RAW demosaic, layered PSD, EXR, HEIF/AVIF, camera metadata, and very large Reference images imply different dependencies and cache designs.
- **GPU correctness is not portable by declaration.** Shader generation is only one stage; texture formats, interpolation, driver behavior, swapchain color spaces, and OS presentation differ.
- **Native dependency packaging is the common bottleneck.** Every shell must close over OCIO, Little CMS, codecs, C++ runtimes, configurations, profiles, and notices, then sign the exact bits tested.
- **Framework release cadence can transfer maintenance risk.** Private Qt APIs, evolving egui APIs, system webview drift, experimental Avalonia Wayland support, or multiple native shells can each create a different kind of downstream burden.
- **Accessibility and localization need real workflows.** International contributors benefit from familiar languages, but users also need keyboard navigation, screen-reader semantics, IME input, RTL-safe layout, and translatable resources in the chosen shell.

## Decision inputs and follow-up investigations

Architecture selection should wait for these bounded inputs:

1. **Define the color-managed viewport contract.** Specify SDR versus HDR/EDR, OCIO/ICC transform order, display-profile discovery and change events, multi-monitor behavior, OS-compositor ownership, and acceptable precision.
2. **Prototype OCIO CPU/GPU parity on Apple Silicon.** Exercise one representative Reference image, 1D/3D LUT resources, a dynamic adjustment, display transform, and CPU comparison through both a Qt RHI route and wgpu. Record correctness, frame latency, memory, and implementation friction.
3. **Choose the image-I/O baseline and dependency envelope.** Turn required formats, bit depths, metadata, RAW/PSD/EXR behavior, and maximum Reference image size into fixtures; compare packaged OpenImageIO and libvips builds.
4. **Choose the project license and third-party distribution policy.** Decide permissive versus copyleft goals, then audit Qt modules, libvips, Little CMS plug-ins, codecs, profiles, ACES configs, notices, and source/relinking delivery.
5. **Measure contributor and release ergonomics for finalists.** On a clean Apple Silicon Mac, time checkout-to-build, native dependency compilation, unit tests, UI tests, universal packaging, signing/notarization preparation, and one dependency upgrade. Repeat the winning flow on Windows and Linux before claiming cross-platform readiness.
6. **Then make the architecture decision.** Use the measured fidelity, latency, package closure, license outcome, contributor workflow, and UI-quality evidence; do not infer them from framework feature lists.

Secondary options such as wxWidgets, Slint, Flutter, or GTK may be revisited if a finalist fails a gate. They were not promoted here because each still needs a separate high-fidelity GPU viewport and either has weaker macOS/Windows parity, a less settled desktop ecosystem, or additional licensing/runtime questions. They are not disproved by this survey.

## Resolution

Maintained open-source foundations do exist for ColorLUThier's shared color core and for several credible desktop shells. The durable common denominator is OCIO/ACES + Little CMS, with OpenImageIO or libvips chosen from explicit image requirements. The UI/GPU choice remains legitimately open between Qt/C++, Rust/wgpu, Tauri with a native viewport, Avalonia/.NET, and native platform shells. The decisive evidence is missing at the display/GPU/package boundaries, so those boundaries should be specified and prototyped before an architecture is selected.
