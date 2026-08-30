# ColorLUThier licensing

ColorLUThier is a multi-licensed project. The license that applies to a file is
identified by its SPDX metadata. Existing files are mapped centrally in
[`REUSE.toml`](REUSE.toml); a more specific SPDX declaration on a file or in an
adjacent sidecar takes precedence.

This overview is a guide. The SPDX metadata and the unmodified license texts in
[`LICENSES/`](LICENSES/) are authoritative.

The root [`LICENSE`](LICENSE) is an exact copy of the
`GPL-3.0-or-later` text for conventional license discovery. It does not override
the per-file licenses recorded here and in `REUSE.toml`.

## Project-created material

| Material | SPDX identifier | License text |
| --- | --- | --- |
| Source code, build and maintenance scripts, workflows, shaders, and executable code examples | `GPL-3.0-or-later` | [GNU General Public License v3.0 or later](LICENSES/GPL-3.0-or-later.txt) |
| Original documentation, diagrams, and non-brand educational material | `CC-BY-4.0` | [Creative Commons Attribution 4.0 International](LICENSES/CC-BY-4.0.txt) |
| Wholly project-generated synthetic numerical fixtures, reference tables, and conformance corpus data | `CC0-1.0` | [CC0 1.0 Universal](LICENSES/CC0-1.0.txt) |
| Original creative test images with verified rights, when explicitly identified | `CC-BY-4.0` | [Creative Commons Attribution 4.0 International](LICENSES/CC-BY-4.0.txt) |

Creative Commons licenses are not used for executable software examples.

The project licenses permit commercial use. The GPL protects the freedom to
inspect, modify, and redistribute covered software; it does not require copies,
distribution, or services to be provided at no charge.

## Software boundaries

A distributed modified version of ColorLUThier, or another distributed combined
work covered by the GPL, must remain GPL-compatible and satisfy the GPL's source
and notice requirements. A distributed plugin or extension that is linked into
ColorLUThier, loaded into its process, or otherwise designed to form one combined
program is expected to be GPL-compatible. The legal classification of a specific
boundary is fact-dependent and may require qualified legal advice.

A genuinely independent program may use its own license when it communicates at
arm's length through documented LUT or image formats, files, a command-line
interface, or ordinary inter-process communication. Interoperability with a host
application does not make that independent application part of ColorLUThier.

Mere network interaction without conveying a copy does not trigger the GPL's
source-delivery obligations. ColorLUThier does not use the GNU Affero
General Public License for the desktop application.

## Patents and future relicensing

The project relies on GPLv3's contributor patent provisions and defensive
protections. The DCO sign-off is not a separate patent license, and patent risks
from codecs, standards, profiles, or third-party components require independent
review.

Contributors retain their copyrights. Any future relicensing would require the
permissions actually held at that time, which may include consent from affected
copyright holders or replacement of their contributions.

## User material and outputs

Using ColorLUThier does not grant the project any rights in a user's reference
images, authored color transformations, exported LUTs, or other outputs, and it
does not grant the user any additional rights in third-party material that may
be present in an input or output.

## Third-party material

Third-party software, profiles, LUTs, images, fonts, configurations, codecs,
fixtures, and other material remain under their original terms. They are not
relicensed as ColorLUThier material merely because the application can discover,
load, process, or interoperate with them.

Redistribution is default-deny until the exact artifact has an approved,
reproducible record covering its source, rights holder, version or revision,
content hash, license terms, transitive contents, build and linkage choices,
required notices, and any corresponding-source, installation, replacement, or
relinking obligations. Exact-artifact review for OpenColorIO Configs for ACES is
tracked in [issue #46](https://github.com/loomitz/ColorLUThier/issues/46).

## Name and branding

The software and content licenses do not grant permission to use the
ColorLUThier name, official logo, or brand identity to identify a modified or
unofficial distribution. Publicly distributed modified versions must use a
distinct name and branding. Truthful descriptive statements such as "based on
ColorLUThier" or "compatible with ColorLUThier" are intended to remain
permissible, provided they do not imply sponsorship or official status. That
intention remains subject to applicable law and third-party rights.

Trademark clearance, registration, custodianship, and rights in a future logo
remain under review in [issue #47](https://github.com/loomitz/ColorLUThier/issues/47).
This notice does not assert that any mark is registered.

## Contributions

Contributors retain copyright in their work and license each contribution under
the outbound license for its material category. See
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the Developer Certificate of Origin
requirement and submission rules.
