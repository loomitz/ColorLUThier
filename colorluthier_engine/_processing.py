"""Deterministic, cooperative CPU plans used by ColorDocument jobs."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Generator
from dataclasses import dataclass

from ._portable_cube import (
    PortableCube,
    evaluate_portable_cube,
    parse_portable_cube,
    serialize_portable_cube,
)
from ._image_source import DecodedImage


@dataclass(frozen=True, slots=True)
class PreviewCandidate:
    width: int
    height: int
    row_stride: int
    original_pixels: bytes
    processed_pixels: bytes


@dataclass(frozen=True, slots=True)
class ExportCandidate:
    encoded: bytes
    sha256: str


class ProcessingError(ValueError):
    """A bounded expected processing failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        context: tuple[tuple[str, int | str], ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = context


def preview_total_units(reference: DecodedImage) -> int:
    return reference.height + 1


def preview_plan(
    *,
    reference: DecodedImage,
    cube: PortableCube,
    interpolation: str,
    bypass: bool,
    mix: float,
) -> Generator[int, None, PreviewCandidate]:
    """Yield one deterministic work unit per scanline, then return a pair."""

    original = bytearray()
    processed = bytearray()
    row_byte_count = reference.width * 3

    for row_index in range(reference.height):
        row_start = row_index * row_byte_count
        row = reference.pixels_rgb8[row_start : row_start + row_byte_count]
        for pixel_start in range(0, len(row), 3):
            input_rgb = (
                row[pixel_start] / 255.0,
                row[pixel_start + 1] / 255.0,
                row[pixel_start + 2] / 255.0,
            )
            original.extend(struct.pack(">fff", *input_rgb))
            if bypass:
                output_rgb = input_rgb
            else:
                evaluated = evaluate_portable_cube(
                    cube,
                    input_rgb,
                    interpolation,
                )
                output_rgb = tuple(
                    source + mix * (target - source)
                    for source, target in zip(input_rgb, evaluated, strict=True)
                )
            if not all(math.isfinite(component) for component in output_rgb):
                raise ProcessingError(
                    "Preview evaluation produced a non-finite component.",
                    code="PREVIEW_VALUE_UNREPRESENTABLE",
                    context=(("row", row_index + 1),),
                )
            try:
                processed.extend(struct.pack(">fff", *output_rgb))
            except (OverflowError, struct.error) as error:
                raise ProcessingError(
                    "Preview evaluation is outside the finite binary32 range.",
                    code="PREVIEW_VALUE_UNREPRESENTABLE",
                    context=(("row", row_index + 1),),
                ) from error
        yield row_index + 1

    return PreviewCandidate(
        width=reference.width,
        height=reference.height,
        row_stride=reference.width * 12,
        original_pixels=bytes(original),
        processed_pixels=bytes(processed),
    )


def export_total_units(_: PortableCube) -> int:
    # Serialization and completion validation are separate cancellable units.
    return 2


def export_plan(cube: PortableCube) -> Generator[int, None, ExportCandidate]:
    """Canonicalize an imported lattice without defining authored-state baking."""

    encoded = serialize_portable_cube(cube)
    yield 1
    reparsed = parse_portable_cube(encoded)
    if reparsed != cube:
        raise ProcessingError(
            "Canonical Portable Cube validation changed the imported lattice.",
            code="EXPORT_VALIDATION_FAILED",
        )
    return ExportCandidate(
        encoded=encoded,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )
