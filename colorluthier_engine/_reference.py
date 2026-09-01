"""Provisional, bounded reference-image decoding for the headless engine.

This module intentionally decodes only the synthetic RGB8 formats accepted by
the first functional vertical.  It does not infer a color context from image
metadata and is not a general-purpose image loading API.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass

from ._limits import (
    REFERENCE_ENCODED_BYTES,
    REFERENCE_MAX_DIMENSION,
    REFERENCE_MAX_PIXELS,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_DECOMPRESS_CHUNK_BYTES = 64 * 1024
_PPM_WHITESPACE = frozenset(b" \t\r\n\v\f")

_REFERENCE_FORMAT_UNSUPPORTED = "REFERENCE_FORMAT_UNSUPPORTED"
_REFERENCE_STRUCTURE_INVALID = "REFERENCE_STRUCTURE_INVALID"
_REFERENCE_RESOURCE_LIMIT = "REFERENCE_RESOURCE_LIMIT"

DiagnosticValue = int | str
DiagnosticContext = tuple[tuple[str, DiagnosticValue], ...]


@dataclass(frozen=True, slots=True)
class DecodedReference:
    """A fully validated reference image with an immutable RGB8 payload."""

    width: int
    height: int
    pixels_rgb8: bytes
    encoded: bytes
    format_name: str
    sha256: str


class ReferenceImageError(ValueError):
    """A bounded and stable diagnostic for rejected reference-image bytes."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        reason: str,
        context: DiagnosticContext = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.context = context


def _invalid(
    reason: str,
    *,
    context: DiagnosticContext = (),
    message: str = "The reference image structure is invalid.",
) -> ReferenceImageError:
    return ReferenceImageError(
        message,
        code=_REFERENCE_STRUCTURE_INVALID,
        reason=reason,
        context=context,
    )


def _resource_limit(
    reason: str,
    *,
    context: DiagnosticContext,
) -> ReferenceImageError:
    return ReferenceImageError(
        "The reference image exceeds a provisional resource limit.",
        code=_REFERENCE_RESOURCE_LIMIT,
        reason=reason,
        context=context,
    )


def _validate_dimensions(width: int, height: int) -> int:
    for axis, value in (("width", width), ("height", height)):
        if value < 1:
            raise _invalid(
                "dimension_not_positive",
                context=(("axis", axis), ("value", value)),
            )
        if value > REFERENCE_MAX_DIMENSION:
            raise _resource_limit(
                "dimension_limit_exceeded",
                context=(
                    ("axis", axis),
                    ("maximum", REFERENCE_MAX_DIMENSION),
                    ("value", value),
                ),
            )

    pixel_count = width * height
    if pixel_count > REFERENCE_MAX_PIXELS:
        raise _resource_limit(
            "pixel_count_limit_exceeded",
            context=(
                ("maximum", REFERENCE_MAX_PIXELS),
                ("value", pixel_count),
            ),
        )
    return pixel_count


def _skip_ppm_header_separators(encoded: bytes, offset: int) -> tuple[int, bool]:
    skipped = False
    while offset < len(encoded):
        value = encoded[offset]
        if value in _PPM_WHITESPACE:
            skipped = True
            offset += 1
            continue
        if value != ord("#"):
            break

        skipped = True
        offset += 1
        while offset < len(encoded) and encoded[offset] not in (ord("\r"), ord("\n")):
            offset += 1
    return offset, skipped


def _read_ppm_header_token(
    encoded: bytes,
    offset: int,
    *,
    field: str,
) -> tuple[bytes, int]:
    offset, had_separator = _skip_ppm_header_separators(encoded, offset)
    if not had_separator or offset >= len(encoded):
        raise _invalid(
            "ppm_header_token_missing",
            context=(("field", field),),
        )

    start = offset
    while (
        offset < len(encoded)
        and encoded[offset] not in _PPM_WHITESPACE
        and encoded[offset] != ord("#")
    ):
        offset += 1

    token_length = offset - start
    if token_length == 0 or token_length > 32:
        raise _invalid(
            "ppm_header_token_invalid",
            context=(("field", field), ("token_length", token_length)),
        )
    return encoded[start:offset], offset


def _parse_ppm_decimal(token: bytes, *, field: str) -> int:
    if not token or any(value < ord("0") or value > ord("9") for value in token):
        raise _invalid(
            "ppm_decimal_invalid",
            context=(("field", field),),
        )

    value = 0
    for digit in token:
        value = value * 10 + digit - ord("0")
    return value


def _decode_ppm(encoded: bytes) -> tuple[int, int, bytes]:
    if not encoded.startswith(b"P6"):
        raise _invalid("ppm_magic_invalid")

    width_token, offset = _read_ppm_header_token(
        encoded,
        2,
        field="width",
    )
    height_token, offset = _read_ppm_header_token(
        encoded,
        offset,
        field="height",
    )
    maxval_token, offset = _read_ppm_header_token(
        encoded,
        offset,
        field="maxval",
    )

    width = _parse_ppm_decimal(width_token, field="width")
    height = _parse_ppm_decimal(height_token, field="height")
    maxval = _parse_ppm_decimal(maxval_token, field="maxval")
    pixel_count = _validate_dimensions(width, height)

    if maxval != 255:
        raise _invalid(
            "ppm_maxval_unsupported",
            context=(("required", 255), ("value", maxval)),
        )
    if offset >= len(encoded) or encoded[offset] not in _PPM_WHITESPACE:
        raise _invalid("ppm_raster_separator_missing")

    # The PPM raster begins after exactly one header whitespace character.
    # Treat CRLF as one logical line ending so Windows-authored fixtures remain
    # deterministic without consuming arbitrary leading raster bytes.
    if encoded[offset] == ord("\r") and encoded[offset : offset + 2] == b"\r\n":
        raster_offset = offset + 2
    else:
        raster_offset = offset + 1

    expected_payload_bytes = pixel_count * 3
    actual_payload_bytes = len(encoded) - raster_offset
    if actual_payload_bytes != expected_payload_bytes:
        reason = (
            "ppm_pixel_payload_truncated"
            if actual_payload_bytes < expected_payload_bytes
            else "ppm_trailing_data"
        )
        raise _invalid(
            reason,
            context=(
                ("actual_bytes", actual_payload_bytes),
                ("expected_bytes", expected_payload_bytes),
            ),
        )

    return width, height, encoded[raster_offset:]


def _valid_png_chunk_type(chunk_type: bytes) -> bool:
    return len(chunk_type) == 4 and all(
        ord("A") <= value <= ord("Z") or ord("a") <= value <= ord("z")
        for value in chunk_type
    )


def _decode_png_chunks(encoded: bytes) -> tuple[int, int, int, bytes]:
    if not encoded.startswith(_PNG_SIGNATURE):
        raise _invalid("png_signature_invalid")

    offset = len(_PNG_SIGNATURE)
    width: int | None = None
    height: int | None = None
    channels: int | None = None
    saw_idat = False
    idat_ended = False
    saw_iend = False
    saw_plte = False
    idat_payload = bytearray()

    while offset < len(encoded):
        chunk_offset = offset
        if len(encoded) - offset < 12:
            raise _invalid(
                "png_chunk_truncated",
                context=(("chunk_offset", chunk_offset),),
            )

        chunk_length = struct.unpack_from(">I", encoded, offset)[0]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(encoded):
            raise _invalid(
                "png_chunk_truncated",
                context=(
                    ("chunk_offset", chunk_offset),
                    ("declared_length", chunk_length),
                ),
            )

        chunk_type = encoded[offset + 4 : offset + 8]
        chunk_data = encoded[offset + 8 : offset + 8 + chunk_length]
        expected_crc = struct.unpack_from(">I", encoded, offset + 8 + chunk_length)[0]
        actual_crc = zlib.crc32(chunk_type)
        actual_crc = zlib.crc32(chunk_data, actual_crc) & 0xFFFFFFFF
        offset = chunk_end

        if not _valid_png_chunk_type(chunk_type) or not (
            ord("A") <= chunk_type[2] <= ord("Z")
        ):
            raise _invalid(
                "png_chunk_type_invalid",
                context=(("chunk_offset", chunk_offset),),
            )
        if actual_crc != expected_crc:
            raise _invalid(
                "png_chunk_crc_mismatch",
                context=(("chunk_offset", chunk_offset),),
            )

        if width is None and chunk_type != b"IHDR":
            raise _invalid("png_ihdr_not_first")

        if chunk_type == b"IHDR":
            if width is not None:
                raise _invalid("png_ihdr_duplicate")
            if chunk_length != 13:
                raise _invalid(
                    "png_ihdr_length_invalid",
                    context=(("actual_bytes", chunk_length), ("expected_bytes", 13)),
                )

            (
                parsed_width,
                parsed_height,
                bit_depth,
                color_type,
                compression_method,
                filter_method,
                interlace_method,
            ) = struct.unpack(">IIBBBBB", chunk_data)
            _validate_dimensions(parsed_width, parsed_height)
            if bit_depth != 8:
                raise _invalid(
                    "png_bit_depth_unsupported",
                    context=(("required", 8), ("value", bit_depth)),
                )
            if color_type not in (2, 6):
                raise _invalid(
                    "png_color_type_unsupported",
                    context=(("value", color_type),),
                )
            if compression_method != 0:
                raise _invalid(
                    "png_compression_method_unsupported",
                    context=(("value", compression_method),),
                )
            if filter_method != 0:
                raise _invalid(
                    "png_filter_method_unsupported",
                    context=(("value", filter_method),),
                )
            if interlace_method != 0:
                raise _invalid(
                    "png_interlace_unsupported",
                    context=(("value", interlace_method),),
                )

            width = parsed_width
            height = parsed_height
            channels = 3 if color_type == 2 else 4
            continue

        if chunk_type == b"IDAT":
            if idat_ended:
                raise _invalid("png_idat_not_consecutive")
            saw_idat = True
            idat_payload.extend(chunk_data)
            continue

        if saw_idat:
            idat_ended = True

        if chunk_type == b"PLTE":
            if saw_plte:
                raise _invalid("png_plte_duplicate")
            if saw_idat:
                raise _invalid("png_plte_after_idat")
            if chunk_length == 0 or chunk_length > 768 or chunk_length % 3 != 0:
                raise _invalid(
                    "png_plte_length_invalid",
                    context=(("actual_bytes", chunk_length),),
                )
            saw_plte = True
            continue

        if chunk_type == b"IEND":
            if chunk_length != 0:
                raise _invalid(
                    "png_iend_length_invalid",
                    context=(("actual_bytes", chunk_length),),
                )
            if not saw_idat:
                raise _invalid("png_idat_missing")
            if offset != len(encoded):
                raise _invalid(
                    "png_trailing_data",
                    context=(("trailing_bytes", len(encoded) - offset),),
                )
            saw_iend = True
            break

        # Unknown critical chunks cannot be decoded safely.  Ancillary chunks
        # remain preserved in ``encoded`` but intentionally do not establish a
        # color context in this provisional adapter.
        if ord("A") <= chunk_type[0] <= ord("Z"):
            raise _invalid("png_critical_chunk_unsupported")

    if width is None or height is None or channels is None:
        raise _invalid("png_ihdr_missing")
    if not saw_idat:
        raise _invalid("png_idat_missing")
    if not saw_iend:
        raise _invalid("png_iend_missing")

    return width, height, channels, bytes(idat_payload)


def _decompress_png_scanlines(compressed: bytes, expected_bytes: int) -> bytes:
    decompressor = zlib.decompressobj()
    output = bytearray()
    input_offset = 0

    try:
        while input_offset < len(compressed):
            compressed_chunk = compressed[
                input_offset : input_offset + _PNG_DECOMPRESS_CHUNK_BYTES
            ]
            input_offset += len(compressed_chunk)

            while compressed_chunk:
                remaining = expected_bytes + 1 - len(output)
                if remaining <= 0:
                    raise _invalid(
                        "png_scanline_data_too_long",
                        context=(("expected_bytes", expected_bytes),),
                    )
                output.extend(decompressor.decompress(compressed_chunk, remaining))
                compressed_chunk = decompressor.unconsumed_tail

            if decompressor.eof:
                if decompressor.unused_data or input_offset != len(compressed):
                    raise _invalid("png_compressed_trailing_data")
                break
    except zlib.error as error:
        raise _invalid("png_zlib_stream_invalid") from error

    if len(output) > expected_bytes:
        raise _invalid(
            "png_scanline_data_too_long",
            context=(("expected_bytes", expected_bytes),),
        )
    if not decompressor.eof:
        raise _invalid("png_zlib_stream_truncated")
    if len(output) != expected_bytes:
        raise _invalid(
            "png_scanline_data_length_invalid",
            context=(
                ("actual_bytes", len(output)),
                ("expected_bytes", expected_bytes),
            ),
        )
    return bytes(output)


def _paeth_predictor(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    distance_left = abs(prediction - left)
    distance_above = abs(prediction - above)
    distance_upper_left = abs(prediction - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def _unfilter_png_scanlines(
    filtered: bytes,
    *,
    width: int,
    height: int,
    channels: int,
) -> bytes:
    row_bytes = width * channels
    rgb = bytearray(width * height * 3)
    previous = bytearray(row_bytes)
    source_offset = 0
    destination_offset = 0

    for row_index in range(height):
        filter_type = filtered[source_offset]
        source_offset += 1
        raw = filtered[source_offset : source_offset + row_bytes]
        source_offset += row_bytes
        reconstructed = bytearray(row_bytes)

        if filter_type == 0:
            reconstructed[:] = raw
        elif filter_type == 1:
            for index, value in enumerate(raw):
                left = reconstructed[index - channels] if index >= channels else 0
                reconstructed[index] = (value + left) & 0xFF
        elif filter_type == 2:
            for index, value in enumerate(raw):
                reconstructed[index] = (value + previous[index]) & 0xFF
        elif filter_type == 3:
            for index, value in enumerate(raw):
                left = reconstructed[index - channels] if index >= channels else 0
                reconstructed[index] = (value + ((left + previous[index]) // 2)) & 0xFF
        elif filter_type == 4:
            for index, value in enumerate(raw):
                left = reconstructed[index - channels] if index >= channels else 0
                above = previous[index]
                upper_left = previous[index - channels] if index >= channels else 0
                reconstructed[index] = (
                    value + _paeth_predictor(left, above, upper_left)
                ) & 0xFF
        else:
            raise _invalid(
                "png_scanline_filter_invalid",
                context=(("filter", filter_type), ("row", row_index)),
            )

        if channels == 3:
            rgb[destination_offset : destination_offset + width * 3] = reconstructed
            destination_offset += width * 3
        else:
            for source_pixel_offset in range(0, row_bytes, 4):
                rgb[destination_offset : destination_offset + 3] = reconstructed[
                    source_pixel_offset : source_pixel_offset + 3
                ]
                destination_offset += 3
        previous = reconstructed

    return bytes(rgb)


def _decode_png(encoded: bytes) -> tuple[int, int, bytes]:
    width, height, channels, compressed = _decode_png_chunks(encoded)
    expected_scanline_bytes = height * (1 + width * channels)
    filtered = _decompress_png_scanlines(compressed, expected_scanline_bytes)
    pixels_rgb8 = _unfilter_png_scanlines(
        filtered,
        width=width,
        height=height,
        channels=channels,
    )
    return width, height, pixels_rgb8


def decode_reference_image(encoded: bytes, declared_format: str) -> DecodedReference:
    """Decode one explicitly declared, bounded synthetic reference image.

    ``declared_format`` is intentionally authoritative.  The adapter never
    sniffs a format or interprets embedded color metadata.
    """

    if declared_format not in ("ppm-p6-rgb8", "png-rgb8"):
        format_length = len(declared_format) if isinstance(declared_format, str) else 0
        raise ReferenceImageError(
            "The declared reference image format is not supported.",
            code=_REFERENCE_FORMAT_UNSUPPORTED,
            reason="declared_format_unsupported",
            context=(("declared_format_length", min(format_length, 1_000_000)),),
        )
    if not isinstance(encoded, bytes):
        raise _invalid("encoded_bytes_required")
    if len(encoded) > REFERENCE_ENCODED_BYTES:
        raise _resource_limit(
            "encoded_size_limit_exceeded",
            context=(
                ("maximum_bytes", REFERENCE_ENCODED_BYTES),
                ("value_bytes", len(encoded)),
            ),
        )

    if declared_format == "ppm-p6-rgb8":
        width, height, pixels_rgb8 = _decode_ppm(encoded)
    else:
        width, height, pixels_rgb8 = _decode_png(encoded)

    return DecodedReference(
        width=width,
        height=height,
        pixels_rgb8=pixels_rgb8,
        encoded=encoded,
        format_name=declared_format,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )
