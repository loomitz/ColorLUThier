"""Strict Portable Cube parsing and deterministic CPU evaluation.

This module is the production-side implementation of the repository's accepted
Portable Cube subset.  The fixed interpolation operation order is deliberately
provisional: it preserves the current conformance evidence without claiming a
stable interchange format or Host-application compatibility.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import cast

from ._limits import PORTABLE_CUBE_ENCODED_BYTES

RGB = tuple[float, float, float]
Binary32RGB = tuple[int, int, int]
ErrorContextValue = bool | int | float | str
ErrorContext = tuple[tuple[str, ErrorContextValue], ...]

_MIN_LATTICE_SIZE = 2
_MAX_LATTICE_SIZE = 65
_MAX_CONTEXT_ITEMS = 8
_MAX_CONTEXT_KEY_LENGTH = 48
_MAX_CONTEXT_TEXT_LENGTH = 64

_DECIMAL_TOKEN = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
_HEADER_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UNSUPPORTED_CUBE_DIRECTIVES = frozenset(
    {
        "DOMAIN_MAX",
        "DOMAIN_MIN",
        "LUT_1D_INPUT_RANGE",
        "LUT_1D_SIZE",
        "LUT_3D_INPUT_RANGE",
        "TITLE",
    }
)


def _bounded_context(*items: tuple[str, ErrorContextValue]) -> ErrorContext:
    """Return a small immutable diagnostic context without artifact payloads."""

    bounded: list[tuple[str, ErrorContextValue]] = []
    for key, value in items[:_MAX_CONTEXT_ITEMS]:
        bounded_key = key[:_MAX_CONTEXT_KEY_LENGTH]
        bounded_value: ErrorContextValue
        if isinstance(value, str):
            bounded_value = value[:_MAX_CONTEXT_TEXT_LENGTH]
        else:
            bounded_value = value
        bounded.append((bounded_key, bounded_value))
    return tuple(bounded)


class PortableCubeError(ValueError):
    """A stable, payload-free Portable Cube validation failure."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        reason: str,
        context: ErrorContext = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.context = _bounded_context(*context)


@dataclass(frozen=True, slots=True)
class PortableCube:
    """An immutable red-fastest lattice containing finite binary32 samples."""

    size: int
    sample_bits: tuple[Binary32RGB, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.size, bool)
            or not isinstance(self.size, int)
            or self.size < _MIN_LATTICE_SIZE
            or self.size > _MAX_LATTICE_SIZE
        ):
            raise PortableCubeError(
                "The Portable Cube lattice size must be an integer from 2 through 65.",
                code="CUBE_LATTICE_SIZE_INVALID",
                reason="size_out_of_range",
                context=_bounded_context(
                    ("minimum", _MIN_LATTICE_SIZE),
                    ("maximum", _MAX_LATTICE_SIZE),
                ),
            )
        if not isinstance(self.sample_bits, tuple):
            raise PortableCubeError(
                "Portable Cube samples must be stored in an immutable tuple.",
                code="CUBE_STRUCTURE_INVALID",
                reason="immutable_sample_table_required",
            )

        expected_count = self.size**3
        if len(self.sample_bits) != expected_count:
            raise PortableCubeError(
                "The Portable Cube sample count does not match its lattice size.",
                code="CUBE_STRUCTURE_INVALID",
                reason="sample_count_mismatch",
                context=_bounded_context(
                    ("expected_rows", expected_count),
                    ("actual_rows", len(self.sample_bits)),
                    ("lattice_size", self.size),
                ),
            )

        for sample_row, sample in enumerate(self.sample_bits, start=1):
            if not isinstance(sample, tuple) or len(sample) != 3:
                raise PortableCubeError(
                    "Each Portable Cube sample must contain three binary32 components.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="sample_component_count",
                    context=_bounded_context(("sample_row", sample_row)),
                )
            for component, bits in enumerate(sample, start=1):
                if (
                    isinstance(bits, bool)
                    or not isinstance(bits, int)
                    or bits < 0
                    or bits > 0xFFFFFFFF
                ):
                    raise PortableCubeError(
                        "A Portable Cube component is not a binary32 bit pattern.",
                        code="CUBE_SAMPLE_VALUE_INVALID",
                        reason="invalid_binary32_bits",
                        context=_bounded_context(
                            ("sample_row", sample_row),
                            ("component", component),
                        ),
                    )
                if bits & 0x7F800000 == 0x7F800000:
                    raise PortableCubeError(
                        "Portable Cube components must be finite binary32 values.",
                        code="CUBE_SAMPLE_VALUE_INVALID",
                        reason="non_finite_binary32_bits",
                        context=_bounded_context(
                            ("sample_row", sample_row),
                            ("component", component),
                        ),
                    )

    @property
    def sample_count(self) -> int:
        return len(self.sample_bits)

    def sample(self, red: int, green: int, blue: int) -> RGB:
        for axis, index in (("red", red), ("green", green), ("blue", blue)):
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or index >= self.size
            ):
                raise PortableCubeError(
                    "A Portable Cube lattice index is outside its valid range.",
                    code="EVALUATION_INPUT_INVALID",
                    reason="lattice_index_out_of_range",
                    context=_bounded_context(
                        ("axis", axis),
                        ("minimum", 0),
                        ("maximum", self.size - 1),
                    ),
                )
        index = red + self.size * green + self.size * self.size * blue
        return cast(
            RGB,
            tuple(
                _binary32_bits_to_float(bits) for bits in self.sample_bits[index]
            ),
        )


@dataclass(frozen=True, slots=True)
class _LatticeAxisPosition:
    lower_index: int
    upper_index: int
    fraction: float


def _round_ratio_ties_to_even(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    twice_remainder = remainder * 2
    if twice_remainder > denominator or (
        twice_remainder == denominator and quotient % 2 == 1
    ):
        quotient += 1
    return quotient


def _floor_log2_ratio(numerator: int, denominator: int) -> int:
    exponent = numerator.bit_length() - denominator.bit_length()
    if exponent >= 0:
        if numerator < denominator << exponent:
            exponent -= 1
    elif numerator << -exponent < denominator:
        exponent -= 1
    return exponent


def _sample_value_error(
    *,
    line_number: int,
    sample_row: int,
    component: int,
    reason: str,
    message: str,
) -> PortableCubeError:
    return PortableCubeError(
        message,
        code="CUBE_SAMPLE_VALUE_INVALID",
        reason=reason,
        context=_bounded_context(
            ("line", line_number),
            ("sample_row", sample_row),
            ("component", component),
        ),
    )


def _outside_binary32_error(
    *, line_number: int, sample_row: int, component: int
) -> PortableCubeError:
    return _sample_value_error(
        line_number=line_number,
        sample_row=sample_row,
        component=component,
        reason="outside_binary32_range",
        message=(
            f"Cube line {line_number} component {component} is outside the finite "
            "binary32 range."
        ),
    )


def _is_non_finite_token(token: str) -> bool:
    return token.lower().lstrip("+-") in {"inf", "infinity", "nan"}


def _decimal_to_binary32_bits(
    token: str, *, line_number: int, sample_row: int, component: int
) -> int:
    if _DECIMAL_TOKEN.fullmatch(token) is None:
        normalized = token.lower().lstrip("+-")
        if _is_non_finite_token(token):
            reason = "non_finite_number"
            message = f"Cube line {line_number} component {component} must be finite."
        elif normalized.startswith("0x"):
            reason = "hexadecimal_number"
            message = (
                f"Cube line {line_number} component {component} does not accept "
                "hexadecimal numbers."
            )
        elif "," in token:
            reason = "locale_dependent_number"
            message = (
                f"Cube line {line_number} component {component} must use a period "
                "as the decimal separator."
            )
        else:
            reason = "malformed_decimal"
            message = (
                f"Cube line {line_number} component {component} must be a decimal "
                "number."
            )
        raise _sample_value_error(
            line_number=line_number,
            sample_row=sample_row,
            component=component,
            reason=reason,
            message=message,
        )

    try:
        value = Decimal(token)
    except InvalidOperation:
        raise _sample_value_error(
            line_number=line_number,
            sample_row=sample_row,
            component=component,
            reason="malformed_decimal",
            message=(
                f"Cube line {line_number} component {component} must be a decimal "
                "number."
            ),
        ) from None

    sign = 1 if value.is_signed() else 0
    if value.is_zero():
        return sign << 31

    # Decimal.__abs__ can apply the active context and round the source token.
    magnitude = value.copy_abs()
    adjusted_exponent = magnitude.adjusted()
    if adjusted_exponent > 38:
        raise _outside_binary32_error(
            line_number=line_number,
            sample_row=sample_row,
            component=component,
        )
    if adjusted_exponent < -46:
        return sign << 31

    numerator, denominator = magnitude.as_integer_ratio()
    exponent = _floor_log2_ratio(numerator, denominator)

    if exponent >= -126:
        shift = 23 - exponent
        if shift >= 0:
            significand = _round_ratio_ties_to_even(
                numerator << shift, denominator
            )
        else:
            significand = _round_ratio_ties_to_even(
                numerator, denominator << -shift
            )

        if significand == 1 << 24:
            significand = 1 << 23
            exponent += 1
        if exponent > 127:
            raise _outside_binary32_error(
                line_number=line_number,
                sample_row=sample_row,
                component=component,
            )

        exponent_bits = exponent + 127
        fraction_bits = significand - (1 << 23)
    else:
        significand = _round_ratio_ties_to_even(numerator << 149, denominator)
        if significand >= 1 << 23:
            exponent_bits = 1
            fraction_bits = 0
        else:
            exponent_bits = 0
            fraction_bits = significand

    return (sign << 31) | (exponent_bits << 23) | fraction_bits


def _binary32_bits_to_float(bits: int) -> float:
    return struct.unpack(">f", struct.pack(">I", bits))[0]


def _unsupported_directive_error(
    token: str, *, line_number: int, section: str
) -> PortableCubeError:
    return PortableCubeError(
        f"Cube line {line_number} uses unsupported directive {token}.",
        code="CUBE_STRUCTURE_INVALID",
        reason="unsupported_directive",
        context=_bounded_context(
            ("directive", token),
            ("line", line_number),
            ("section", section),
        ),
    )


def _unknown_header_error(
    *, line_number: int, section: str, header_length: int
) -> PortableCubeError:
    return PortableCubeError(
        f"Cube line {line_number} contains an unknown header.",
        code="CUBE_STRUCTURE_INVALID",
        reason="unknown_header",
        context=_bounded_context(
            ("line", line_number),
            ("section", section),
            ("header_length", header_length),
        ),
    )


def parse_portable_cube(encoded: bytes) -> PortableCube:
    """Parse bytes in the strict Portable Cube subset.

    Input is bounded before decoding or allocating the lattice table.  Decimal
    samples are rounded directly to IEEE 754 binary32 with ties to even.
    """

    if not isinstance(encoded, bytes):
        raise PortableCubeError(
            "A Portable Cube artifact must be supplied as bytes.",
            code="CUBE_ENCODING_INVALID",
            reason="bytes_required",
        )
    if len(encoded) > PORTABLE_CUBE_ENCODED_BYTES:
        raise PortableCubeError(
            "The Cube artifact exceeds the 16 MiB input limit.",
            code="CUBE_RESOURCE_LIMIT",
            reason="input_byte_limit_exceeded",
            context=_bounded_context(
                ("maximum_bytes", PORTABLE_CUBE_ENCODED_BYTES),
                ("actual_bytes", len(encoded)),
            ),
        )

    try:
        text = encoded.decode("ascii")
    except UnicodeDecodeError as error:
        raise PortableCubeError(
            "The Cube artifact must use Basic Latin text.",
            code="CUBE_ENCODING_INVALID",
            reason="non_ascii_text",
            context=_bounded_context(
                ("byte_offset", error.start),
                ("byte_value", encoded[error.start]),
            ),
        ) from None

    size: int | None = None
    samples: list[Binary32RGB] | None = None

    try:
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if size is None:
                if not stripped or stripped.startswith("#"):
                    continue
                tokens = stripped.split()
                first_token = tokens[0]
                if first_token in _UNSUPPORTED_CUBE_DIRECTIVES:
                    raise _unsupported_directive_error(
                        first_token,
                        line_number=line_number,
                        section="preamble",
                    )
                if first_token != "LUT_3D_SIZE":
                    if _HEADER_TOKEN.fullmatch(first_token) is not None:
                        raise _unknown_header_error(
                            line_number=line_number,
                            section="preamble",
                            header_length=len(first_token),
                        )
                    raise PortableCubeError(
                        f"Cube line {line_number} appears before LUT_3D_SIZE.",
                        code="CUBE_STRUCTURE_INVALID",
                        reason="missing_size_declaration",
                        context=_bounded_context(("declaration", "LUT_3D_SIZE")),
                    )
                if len(tokens) != 2:
                    raise PortableCubeError(
                        f"Cube line {line_number} must contain LUT_3D_SIZE and one "
                        "integer value.",
                        code="CUBE_STRUCTURE_INVALID",
                        reason="malformed_size_declaration",
                        context=_bounded_context(
                            ("actual_tokens", len(tokens)),
                            ("declaration", "LUT_3D_SIZE"),
                            ("expected_tokens", 2),
                            ("line", line_number),
                        ),
                    )

                size_token = tokens[1]
                if not size_token.isdigit():
                    raise PortableCubeError(
                        f"Cube line {line_number} lattice size must be an integer.",
                        code="CUBE_LATTICE_SIZE_INVALID",
                        reason="size_not_integer",
                        context=_bounded_context(
                            ("line", line_number),
                            ("minimum", _MIN_LATTICE_SIZE),
                            ("maximum", _MAX_LATTICE_SIZE),
                        ),
                    )

                normalized_size = size_token.lstrip("0") or "0"
                if len(normalized_size) > 2:
                    raise PortableCubeError(
                        f"Cube line {line_number} lattice size must be between 2 and 65.",
                        code="CUBE_LATTICE_SIZE_INVALID",
                        reason="size_out_of_range",
                        context=_bounded_context(
                            ("line", line_number),
                            ("minimum", _MIN_LATTICE_SIZE),
                            ("maximum", _MAX_LATTICE_SIZE),
                            ("value_digits", len(normalized_size)),
                        ),
                    )
                size = int(normalized_size)
                if size < _MIN_LATTICE_SIZE or size > _MAX_LATTICE_SIZE:
                    raise PortableCubeError(
                        f"Cube line {line_number} lattice size must be between 2 and 65.",
                        code="CUBE_LATTICE_SIZE_INVALID",
                        reason="size_out_of_range",
                        context=_bounded_context(
                            ("line", line_number),
                            ("minimum", _MIN_LATTICE_SIZE),
                            ("maximum", _MAX_LATTICE_SIZE),
                            ("value", size),
                        ),
                    )

                # Allocate the table only after the declared bound is accepted.
                samples = []
                continue

            if not stripped:
                raise PortableCubeError(
                    f"Cube line {line_number} is blank after LUT_3D_SIZE.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="blank_line_after_size",
                    context=_bounded_context(
                        ("line", line_number),
                        ("section", "sample_table"),
                    ),
                )
            if "#" in stripped:
                raise PortableCubeError(
                    f"Cube line {line_number} contains a comment after LUT_3D_SIZE.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="comment_after_size",
                    context=_bounded_context(
                        ("line", line_number),
                        ("section", "sample_table"),
                    ),
                )

            tokens = stripped.split()
            first_token = tokens[0]
            if first_token == "LUT_3D_SIZE":
                raise PortableCubeError(
                    f"Cube line {line_number} repeats LUT_3D_SIZE.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="duplicate_size_declaration",
                    context=_bounded_context(
                        ("declaration", "LUT_3D_SIZE"),
                        ("line", line_number),
                    ),
                )
            if first_token in _UNSUPPORTED_CUBE_DIRECTIVES:
                raise _unsupported_directive_error(
                    first_token,
                    line_number=line_number,
                    section="sample_table",
                )
            if (
                _HEADER_TOKEN.fullmatch(first_token) is not None
                and not _is_non_finite_token(first_token)
            ):
                raise _unknown_header_error(
                    line_number=line_number,
                    section="sample_table",
                    header_length=len(first_token),
                )

            assert samples is not None
            expected_count = size**3
            sample_row = len(samples) + 1
            if sample_row > expected_count:
                raise PortableCubeError(
                    f"Cube lattice size {size} requires {expected_count} sample rows; "
                    f"line {line_number} starts row {sample_row}.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="too_many_sample_rows",
                    context=_bounded_context(
                        ("actual_rows", sample_row),
                        ("expected_rows", expected_count),
                        ("lattice_size", size),
                        ("line", line_number),
                    ),
                )
            if len(tokens) != 3:
                raise PortableCubeError(
                    f"Cube line {line_number} must contain exactly three sample values.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="sample_token_count",
                    context=_bounded_context(
                        ("actual_tokens", len(tokens)),
                        ("expected_tokens", 3),
                        ("line", line_number),
                        ("sample_row", sample_row),
                    ),
                )

            samples.append(
                cast(
                    Binary32RGB,
                    tuple(
                        _decimal_to_binary32_bits(
                            token,
                            line_number=line_number,
                            sample_row=sample_row,
                            component=component,
                        )
                        for component, token in enumerate(tokens, start=1)
                    ),
                )
            )
    except MemoryError:
        raise PortableCubeError(
            "The Cube artifact could not be processed within resource limits.",
            code="CUBE_RESOURCE_LIMIT",
            reason="processing_resource_exhausted",
        ) from None

    if size is None or samples is None:
        raise PortableCubeError(
            "The Cube artifact is missing LUT_3D_SIZE.",
            code="CUBE_STRUCTURE_INVALID",
            reason="missing_size_declaration",
            context=_bounded_context(("declaration", "LUT_3D_SIZE")),
        )

    expected_count = size**3
    if len(samples) != expected_count:
        raise PortableCubeError(
            f"Cube lattice size {size} requires {expected_count} sample rows; "
            f"found {len(samples)}.",
            code="CUBE_STRUCTURE_INVALID",
            reason="too_few_sample_rows",
            context=_bounded_context(
                ("actual_rows", len(samples)),
                ("expected_rows", expected_count),
                ("lattice_size", size),
            ),
        )
    return PortableCube(size=size, sample_bits=tuple(samples))


def serialize_portable_cube(cube: PortableCube) -> bytes:
    """Serialize a Portable Cube canonically as Basic Latin text with LF."""

    if not isinstance(cube, PortableCube):
        raise PortableCubeError(
            "Portable Cube serialization requires a PortableCube value.",
            code="CUBE_STRUCTURE_INVALID",
            reason="portable_cube_required",
        )
    lines = [f"LUT_3D_SIZE {cube.size}"]
    for sample in cube.sample_bits:
        lines.append(
            " ".join(
                format(_binary32_bits_to_float(bits), ".9g") for bits in sample
            )
        )
    return ("\n".join(lines) + "\n").encode("ascii")


def _lattice_axis_position(value: float, size: int) -> _LatticeAxisPosition:
    if value == 1.0:
        return _LatticeAxisPosition(size - 1, size - 1, 0.0)

    scaled = value * (size - 1)
    nearest_node = round(scaled)
    # Reconstruct the exact binary64 rational so adjacent values are not snapped.
    if value == nearest_node / (size - 1):
        return _LatticeAxisPosition(nearest_node, nearest_node, 0.0)

    lower = int(scaled)
    return _LatticeAxisPosition(lower, lower + 1, scaled - lower)


def _lerp(start: float, end: float, amount: float) -> float:
    if amount == 0.0:
        return start
    if amount == 1.0:
        return end
    return start + amount * (end - start)


def _evaluate_trilinear(cube: PortableCube, input_rgb: RGB) -> RGB:
    red_axis = _lattice_axis_position(input_rgb[0], cube.size)
    green_axis = _lattice_axis_position(input_rgb[1], cube.size)
    blue_axis = _lattice_axis_position(input_rgb[2], cube.size)

    if (
        red_axis.lower_index == red_axis.upper_index
        and green_axis.lower_index == green_axis.upper_index
        and blue_axis.lower_index == blue_axis.upper_index
    ):
        return cube.sample(
            red_axis.lower_index,
            green_axis.lower_index,
            blue_axis.lower_index,
        )

    result: list[float] = []
    for channel in range(3):
        c000 = cube.sample(
            red_axis.lower_index,
            green_axis.lower_index,
            blue_axis.lower_index,
        )[channel]
        c100 = cube.sample(
            red_axis.upper_index,
            green_axis.lower_index,
            blue_axis.lower_index,
        )[channel]
        c010 = cube.sample(
            red_axis.lower_index,
            green_axis.upper_index,
            blue_axis.lower_index,
        )[channel]
        c110 = cube.sample(
            red_axis.upper_index,
            green_axis.upper_index,
            blue_axis.lower_index,
        )[channel]
        c001 = cube.sample(
            red_axis.lower_index,
            green_axis.lower_index,
            blue_axis.upper_index,
        )[channel]
        c101 = cube.sample(
            red_axis.upper_index,
            green_axis.lower_index,
            blue_axis.upper_index,
        )[channel]
        c011 = cube.sample(
            red_axis.lower_index,
            green_axis.upper_index,
            blue_axis.upper_index,
        )[channel]
        c111 = cube.sample(
            red_axis.upper_index,
            green_axis.upper_index,
            blue_axis.upper_index,
        )[channel]

        red_00 = _lerp(c000, c100, red_axis.fraction)
        red_10 = _lerp(c010, c110, red_axis.fraction)
        red_01 = _lerp(c001, c101, red_axis.fraction)
        red_11 = _lerp(c011, c111, red_axis.fraction)
        green_0 = _lerp(red_00, red_10, green_axis.fraction)
        green_1 = _lerp(red_01, red_11, green_axis.fraction)
        result.append(_lerp(green_0, green_1, blue_axis.fraction))

    return cast(RGB, tuple(result))


def _evaluate_tetrahedral(cube: PortableCube, input_rgb: RGB) -> RGB:
    red_axis = _lattice_axis_position(input_rgb[0], cube.size)
    green_axis = _lattice_axis_position(input_rgb[1], cube.size)
    blue_axis = _lattice_axis_position(input_rgb[2], cube.size)

    if (
        red_axis.lower_index == red_axis.upper_index
        and green_axis.lower_index == green_axis.upper_index
        and blue_axis.lower_index == blue_axis.upper_index
    ):
        return cube.sample(
            red_axis.lower_index,
            green_axis.lower_index,
            blue_axis.lower_index,
        )

    c000 = cube.sample(
        red_axis.lower_index,
        green_axis.lower_index,
        blue_axis.lower_index,
    )
    c100 = cube.sample(
        red_axis.upper_index,
        green_axis.lower_index,
        blue_axis.lower_index,
    )
    c010 = cube.sample(
        red_axis.lower_index,
        green_axis.upper_index,
        blue_axis.lower_index,
    )
    c110 = cube.sample(
        red_axis.upper_index,
        green_axis.upper_index,
        blue_axis.lower_index,
    )
    c001 = cube.sample(
        red_axis.lower_index,
        green_axis.lower_index,
        blue_axis.upper_index,
    )
    c101 = cube.sample(
        red_axis.upper_index,
        green_axis.lower_index,
        blue_axis.upper_index,
    )
    c011 = cube.sample(
        red_axis.lower_index,
        green_axis.upper_index,
        blue_axis.upper_index,
    )
    c111 = cube.sample(
        red_axis.upper_index,
        green_axis.upper_index,
        blue_axis.upper_index,
    )

    red = red_axis.fraction
    green = green_axis.fraction
    blue = blue_axis.fraction

    # Strict comparisons retain deterministic tie routing across six regions.
    if red > green:
        if green > blue:
            weighted_vertices = (
                (1.0 - red, c000),
                (red - green, c100),
                (green - blue, c110),
                (blue, c111),
            )
        elif red > blue:
            weighted_vertices = (
                (1.0 - red, c000),
                (red - blue, c100),
                (blue - green, c101),
                (green, c111),
            )
        else:
            weighted_vertices = (
                (1.0 - blue, c000),
                (blue - red, c001),
                (red - green, c101),
                (green, c111),
            )
    elif blue > green:
        weighted_vertices = (
            (1.0 - blue, c000),
            (blue - green, c001),
            (green - red, c011),
            (red, c111),
        )
    elif blue > red:
        weighted_vertices = (
            (1.0 - green, c000),
            (green - blue, c010),
            (blue - red, c011),
            (red, c111),
        )
    else:
        weighted_vertices = (
            (1.0 - green, c000),
            (green - red, c010),
            (red - blue, c110),
            (blue, c111),
        )

    result: list[float] = []
    for channel in range(3):
        first, second, third, fourth = weighted_vertices
        value = first[0] * first[1][channel]
        value = value + second[0] * second[1][channel]
        value = value + third[0] * third[1][channel]
        value = value + fourth[0] * fourth[1][channel]
        result.append(value)
    return cast(RGB, tuple(result))


def _validated_input_rgb(input_rgb: RGB) -> RGB:
    try:
        components = tuple(input_rgb)
    except TypeError:
        raise PortableCubeError(
            "Evaluation input must contain exactly three finite numeric components.",
            code="EVALUATION_INPUT_INVALID",
            reason="rgb_triplet_required",
        ) from None
    if len(components) != 3:
        raise PortableCubeError(
            "Evaluation input must contain exactly three finite numeric components.",
            code="EVALUATION_INPUT_INVALID",
            reason="rgb_triplet_required",
            context=_bounded_context(("actual_components", len(components))),
        )

    normalized: list[float] = []
    for component, value in enumerate(components, start=1):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PortableCubeError(
                "Evaluation components must be finite numbers inside [0, 1].",
                code="EVALUATION_INPUT_INVALID",
                reason="numeric_component_required",
                context=_bounded_context(("component", component)),
            )
        try:
            number = float(value)
        except (OverflowError, ValueError):
            raise PortableCubeError(
                "Evaluation components must be finite numbers inside [0, 1].",
                code="EVALUATION_INPUT_INVALID",
                reason="non_finite_component",
                context=_bounded_context(("component", component)),
            ) from None
        if not math.isfinite(number):
            raise PortableCubeError(
                "Evaluation components must be finite numbers inside [0, 1].",
                code="EVALUATION_INPUT_INVALID",
                reason="non_finite_component",
                context=_bounded_context(("component", component)),
            )
        if number < 0.0 or number > 1.0:
            raise PortableCubeError(
                "Evaluation components must remain inside the closed domain [0, 1].",
                code="EVALUATION_INPUT_INVALID",
                reason="component_out_of_range",
                context=_bounded_context(
                    ("component", component),
                    ("minimum", 0.0),
                    ("maximum", 1.0),
                ),
            )
        normalized.append(number)
    return cast(RGB, tuple(normalized))


def evaluate_portable_cube(
    cube: PortableCube, input_rgb: RGB, interpolation: str
) -> RGB:
    """Evaluate a valid input without clamping or extrapolation."""

    if not isinstance(cube, PortableCube):
        raise PortableCubeError(
            "Portable Cube evaluation requires a PortableCube value.",
            code="CUBE_STRUCTURE_INVALID",
            reason="portable_cube_required",
        )
    if interpolation not in {"trilinear", "tetrahedral"}:
        raise PortableCubeError(
            "The selected interpolation is unsupported.",
            code="INTERPOLATION_UNSUPPORTED",
            reason="unsupported_interpolation",
            context=_bounded_context(("supported_interpolations", 2)),
        )

    validated_input = _validated_input_rgb(input_rgb)
    if interpolation == "trilinear":
        return _evaluate_trilinear(cube, validated_input)
    return _evaluate_tetrahedral(cube, validated_input)


__all__ = [
    "PortableCube",
    "PortableCubeError",
    "RGB",
    "evaluate_portable_cube",
    "parse_portable_cube",
    "serialize_portable_cube",
]
