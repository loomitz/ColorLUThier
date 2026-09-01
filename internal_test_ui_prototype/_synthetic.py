# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wholly synthetic, redistributable inputs for the disposable prototype."""

from __future__ import annotations

from colorluthier_engine import (
    ColorContextDeclaration,
    ColorManagementLane,
    ContentIdentity,
    DisplayColorContext,
    EncodingIdentity,
    ExportColorContext,
    HostFormatProfileIdentity,
    IccColorContextIdentity,
    Interpolation,
    KnownColorContext,
    ProofColorContext,
    RgbBounds,
    WorkingColorContext,
)


SYNTHETIC_REFERENCE_PPM = (
    b"P6\n2 2\n255\n"
    b"\x00\x00\x00"
    b"\xff\x00\x00"
    b"\x00\xff\x00"
    b"\x00\x00\xff"
)

SYNTHETIC_IDENTITY_CUBE = (
    b"LUT_3D_SIZE 2\n"
    b"0 0 0\n"
    b"1 0 0\n"
    b"0 1 0\n"
    b"1 1 0\n"
    b"0 0 1\n"
    b"1 0 1\n"
    b"0 1 1\n"
    b"1 1 1\n"
)


def _content_identity(digit: str) -> ContentIdentity:
    return ContentIdentity(digit * 64)


def _known_context(identity_digit: str, encoding_digit: str) -> KnownColorContext:
    return KnownColorContext(
        lane=ColorManagementLane.ICC,
        identity=IccColorContextIdentity(_content_identity(identity_digit)),
        encoding=EncodingIdentity(
            identifier="rgb-values-v1",
            specification=_content_identity(encoding_digit),
        ),
    )


def synthetic_color_context_declaration() -> ColorContextDeclaration:
    """Return one complete visible ICC declaration including Export."""

    bounds = RgbBounds(
        minimum=(0.0, 0.0, 0.0),
        maximum=(1.0, 1.0, 1.0),
    )
    return ColorContextDeclaration(
        selected_lane=ColorManagementLane.ICC,
        working=WorkingColorContext(_known_context("1", "2")),
        proof=ProofColorContext(_known_context("3", "4")),
        display=DisplayColorContext(
            _known_context("5", "6"),
            viewing_interpretation=_content_identity("b"),
        ),
        export_context=ExportColorContext(
            input_context=_known_context("7", "8"),
            output_context=_known_context("9", "a"),
            numeric_domain=bounds,
            numeric_range=bounds,
            interpolation=Interpolation.TETRAHEDRAL,
            profile=HostFormatProfileIdentity(
                identifier="portable-cube",
                version="1",
                specification=_content_identity("c"),
            ),
        ),
    )
