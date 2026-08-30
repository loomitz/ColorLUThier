# Contributing to ColorLUThier

Thank you for helping build ColorLUThier. Contributions are accepted under a
copyright-retained, inbound-equals-outbound model: you retain copyright in your
work and license it to recipients under the license assigned to that material
category.

ColorLUThier does not require a contributor license agreement or copyright
assignment, and contributors do not grant the project special rights to publish
their work in a proprietary edition.

## Developer Certificate of Origin

Every commit that contributes code after adoption of this policy must certify
the unmodified [Developer Certificate of Origin 1.1](https://developercertificate.org/)
with a `Signed-off-by` trailer. The sign-off certifies that you have the right to
submit the work under the project's terms; it is not a separate copyright or
patent license.

Create a signed-off commit with:

```console
git commit -s
```

The resulting commit message must contain a trailer in this form:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use a name and email address that you are authorized to use for this
certification. Add the trailer to each commit that contributes code. Do not add
a sign-off on another contributor's behalf, and do not add retroactive sign-offs
to historical commits whose authors have not provided them.

## License categories

The governing license must remain explicit for every contributed file:

- Source code, build and maintenance scripts, workflows, shaders, and executable
  code examples use `GPL-3.0-or-later`.
- Original documentation, diagrams, non-brand educational material, and
  original creative test images with verified rights use `CC-BY-4.0`.
- Wholly project-generated synthetic numerical fixtures, reference tables, and
  conformance corpus data use `CC0-1.0`.
- The ColorLUThier name, official logo, and brand identity are not licensed by
  those software or content licenses.
- Third-party material remains exclusively under its original terms and must
  never be represented as project-created material.

See [`LICENSING.md`](LICENSING.md) for the licensing overview and
[`REUSE.toml`](REUSE.toml) for the current path-based SPDX declarations. New or
exceptional files must add an SPDX header, sidecar, or appropriately narrow
central annotation. A broad path rule is not permission to relicense
third-party work.

## Rights and third-party provenance

By signing off a contribution, you certify the statements in DCO 1.1, including
that you have the right to submit it. Confirm any employer, co-author, patent,
privacy, publicity, and third-party permissions before submission.

Do not commit a dependency, configuration, profile, LUT, image, font, codec,
fixture, generated resource, or other third-party artifact unless its exact
redistribution review has been approved. That review must identify at least:

- the official source, rights holder, exact version or revision, and content
  hash;
- the license or permission for that exact artifact and all required notices;
- transitive contents, generation inputs, enabled features, codecs, plugins,
  and static or dynamic linkage;
- permitted use, modification, embedding, and redistribution destinations; and
- any corresponding-source, patch, build-recipe, installation-information,
  replacement, or relinking obligations.

Material merely discovered on a contributor's or user's system stays local
unless its exact redistribution rights are documented and approved.

## Scope of review

A maintainer may ask for provenance evidence, a narrower license declaration,
or removal of material whose rights are unclear. License compatibility for a
particular plugin boundary, distribution channel, codec, standard, profile, or
other artifact can be fact-specific and may require qualified legal advice.
