"""Private implementation behind the repository-local conformance command."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import struct
import tempfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, cast


HARNESS_VERSION = "0.6.0"
REPORT_SCHEMA_VERSION = 1
TEST_CASE_SCHEMA_VERSION = 1

_DECIMAL_TOKEN = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STABLE_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_HEADER_TOKEN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UNSUPPORTED_CUBE_DIRECTIVES = {
    "DOMAIN_MAX",
    "DOMAIN_MIN",
    "LUT_1D_INPUT_RANGE",
    "LUT_1D_SIZE",
    "LUT_3D_INPUT_RANGE",
    "TITLE",
}
_UNKNOWN_HEADER_PREVIEW_LENGTH = 64
_UNKNOWN_DESCRIPTOR_FIELD_PREVIEW_LENGTH = 64

_ROOT_DESCRIPTOR_FIELDS = {
    "case_id",
    "cube",
    "evaluations",
    "gates",
    "interpolation",
    "oracle",
    "test_case_schema_version",
}
_CUBE_METADATA_FIELDS = {"sha256"}
_ORACLE_METADATA_FIELDS = {"kind", "provenance"}
_EVALUATION_FIELDS = {"expected", "id", "input"}
_GATE_FIELDS = {
    "maximum_absolute_error",
    "require_finite_outputs",
    "require_node_binary32_identity",
    "require_serialization_binary32_identity",
}

RGB = tuple[float, float, float]
Binary32RGB = tuple[int, int, int]


class HarnessInputError(ValueError):
    """A descriptor, Cube artifact, or output request is invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INPUT_INVALID",
        reason: str | None = None,
        context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.context = context


class _CubeParseFailure(ValueError):
    """A private semantic failure while parsing Cube artifact bytes."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        reason: str,
        context: dict[str, object],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.context = context


@dataclass(frozen=True)
class _NonFiniteJSONNumber:
    token: str


@dataclass(frozen=True)
class Evaluation:
    identifier: str
    input_rgb: RGB
    expected_rgb: RGB


@dataclass(frozen=True)
class TestCase:
    case_id: str
    cube_sha256: str
    interpolation: str
    evaluations: tuple[Evaluation, ...]
    maximum_absolute_error: float
    require_finite_outputs: bool
    require_node_binary32_identity: bool
    require_serialization_binary32_identity: bool


@dataclass(frozen=True)
class Cube:
    size: int
    sample_bits: tuple[Binary32RGB, ...]

    @property
    def sample_count(self) -> int:
        return len(self.sample_bits)

    def sample(self, red: int, green: int, blue: int) -> RGB:
        index = red + self.size * green + self.size * self.size * blue
        return cast(
            RGB,
            tuple(
                _binary32_bits_to_float(bits) for bits in self.sample_bits[index]
            ),
        )


@dataclass(frozen=True)
class LatticeAxisPosition:
    lower_index: int
    upper_index: int
    fraction: float


@dataclass(frozen=True)
class EvaluationRun:
    metrics: dict[str, float]
    finite: bool
    nodes_binary32_identical: bool


def _read_bytes(path: Path, artifact_name: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise HarnessInputError(f"The {artifact_name} could not be read.") from error


def _json_constant(value: str) -> _NonFiniteJSONNumber:
    return _NonFiniteJSONNumber(value)


def _bounded_member_context(member: str) -> dict[str, object]:
    return {
        "member_length": len(member),
        "member_prefix": member[:_UNKNOWN_DESCRIPTOR_FIELD_PREVIEW_LENGTH],
    }


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for member, value in pairs:
        if member in result:
            raise HarnessInputError(
                "The test descriptor contains a duplicate JSON object member.",
                code="DESCRIPTOR_JSON_INVALID",
                reason="duplicate_object_member",
                context=_bounded_member_context(member),
            )
        result[member] = value
    return result


def _mapping(
    value: Any,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HarnessInputError(
            f"Descriptor field {field!r} must be an object.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="object_required",
            context={"field": field},
        )
    return value


def _closed_mapping(
    value: Any,
    field: str,
    allowed_fields: set[str],
) -> dict[str, Any]:
    mapping = _mapping(value, field)
    unexpected_fields = sorted(set(mapping) - allowed_fields)
    if unexpected_fields:
        member = unexpected_fields[0]
        raise HarnessInputError(
            f"Descriptor field {field!r} contains an unsupported member.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="unsupported_object_member",
            context={"field": field, **_bounded_member_context(member)},
        )
    return mapping


def _required(
    mapping: dict[str, Any],
    field: str,
    *,
    parent: str | None = None,
    code: str = "DESCRIPTOR_SCHEMA_INVALID",
) -> Any:
    if field not in mapping:
        qualified_field = field if parent is None else f"{parent}.{field}"
        raise HarnessInputError(
            f"Descriptor field {qualified_field!r} is required.",
            code=code,
            reason="required_field_missing",
            context={"field": qualified_field},
        )
    return mapping[field]


def _finite_number(
    value: Any,
    field: str,
    *,
    code: str = "DESCRIPTOR_SCHEMA_INVALID",
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        reason = (
            "non_finite_number"
            if isinstance(value, _NonFiniteJSONNumber)
            else "number_required"
        )
        raise HarnessInputError(
            f"Descriptor field {field!r} must be a finite number.",
            code=code,
            reason=reason,
            context={"field": field},
        )
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise HarnessInputError(
            f"Descriptor field {field!r} must be a finite number.",
            code=code,
            reason="non_finite_number",
            context={"field": field},
        ) from error
    if not math.isfinite(result):
        raise HarnessInputError(
            f"Descriptor field {field!r} must be a finite number.",
            code=code,
            reason="non_finite_number",
            context={"field": field},
        )
    return result


def _rgb_vector(
    value: Any,
    field: str,
    *,
    code: str,
    require_unit_domain: bool,
) -> RGB:
    if not isinstance(value, list) or len(value) != 3:
        raise HarnessInputError(
            f"Descriptor field {field!r} must contain three finite numbers.",
            code=code,
            reason="rgb_vector_required",
            context={"field": field},
        )
    result = tuple(
        _finite_number(component, f"{field}[{index}]", code=code)
        for index, component in enumerate(value)
    )
    if require_unit_domain and any(
        component < 0.0 or component > 1.0 for component in result
    ):
        component = next(
            index
            for index, value_component in enumerate(result)
            if value_component < 0.0 or value_component > 1.0
        )
        raise HarnessInputError(
            f"Descriptor field {field!r} must be inside [0,1].",
            code=code,
            reason="outside_unit_domain",
            context={
                "field": f"{field}[{component}]",
                "maximum": 1.0,
                "minimum": 0.0,
            },
        )
    return cast(RGB, result)


def _load_test_case(raw: bytes) -> TestCase:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HarnessInputError(
            "The test descriptor must use valid UTF-8.",
            code="DESCRIPTOR_ENCODING_INVALID",
            reason="invalid_utf8",
            context={
                "byte_offset": error.start,
                "byte_value": raw[error.start],
            },
        ) from error

    try:
        parsed = json.loads(
            decoded,
            object_pairs_hook=_json_object,
            parse_constant=_json_constant,
        )
    except HarnessInputError:
        raise
    except json.JSONDecodeError as error:
        raise HarnessInputError(
            "The test descriptor is not valid JSON.",
            code="DESCRIPTOR_JSON_INVALID",
            reason="malformed_json",
            context={"column": error.colno, "line": error.lineno},
        ) from error
    except RecursionError as error:
        raise HarnessInputError(
            "The test descriptor exceeds the supported JSON nesting depth.",
            code="DESCRIPTOR_JSON_INVALID",
            reason="nesting_too_deep",
            context={"document": "test_descriptor"},
        ) from error
    except ValueError as error:
        raise HarnessInputError(
            "The test descriptor contains a JSON number that is too large "
            "to parse safely.",
            code="DESCRIPTOR_JSON_INVALID",
            reason="numeric_token_too_large",
            context={"document": "test_descriptor"},
        ) from error

    root = _closed_mapping(parsed, "<root>", _ROOT_DESCRIPTOR_FIELDS)
    schema_version = _required(root, "test_case_schema_version")
    if type(schema_version) is not int:
        raise HarnessInputError(
            "Descriptor field 'test_case_schema_version' must be an integer.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="integer_required",
            context={"field": "test_case_schema_version"},
        )
    if schema_version != TEST_CASE_SCHEMA_VERSION:
        raise HarnessInputError(
            "The test descriptor schema version is unsupported.",
            code="DESCRIPTOR_SCHEMA_UNSUPPORTED",
            reason="unsupported_schema_version",
            context={"supported_version": TEST_CASE_SCHEMA_VERSION},
        )

    case_id = _required(root, "case_id")
    if (
        not isinstance(case_id, str)
        or _STABLE_IDENTIFIER.fullmatch(case_id) is None
    ):
        raise HarnessInputError(
            "Descriptor field 'case_id' must be a stable lowercase identifier.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="stable_identifier_required",
            context={"field": "case_id"},
        )

    cube_metadata = _closed_mapping(
        _required(root, "cube"),
        "cube",
        _CUBE_METADATA_FIELDS,
    )
    cube_sha256 = _required(cube_metadata, "sha256", parent="cube")
    if (
        not isinstance(cube_sha256, str)
        or _HEX_SHA256.fullmatch(cube_sha256) is None
    ):
        raise HarnessInputError(
            "Descriptor field 'cube.sha256' must be a lowercase SHA-256 digest.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="sha256_required",
            context={"field": "cube.sha256"},
        )

    if "interpolation" not in root:
        raise HarnessInputError(
            "Descriptor field 'interpolation' is required.",
            code="INTERPOLATION_REQUIRED",
        )
    interpolation = root["interpolation"]
    if not isinstance(interpolation, str) or interpolation not in {
        "trilinear",
        "tetrahedral",
    }:
        raise HarnessInputError(
            "Descriptor field 'interpolation' must select 'trilinear' or "
            "'tetrahedral'.",
            code="INTERPOLATION_UNSUPPORTED",
        )

    oracle = _closed_mapping(
        _required(root, "oracle"),
        "oracle",
        _ORACLE_METADATA_FIELDS,
    )
    if _required(oracle, "kind", parent="oracle") != "explicit_expected_values":
        raise HarnessInputError(
            "Descriptor field 'oracle.kind' is unsupported.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="unsupported_oracle_kind",
            context={"field": "oracle.kind"},
        )
    provenance = _required(oracle, "provenance", parent="oracle")
    if not isinstance(provenance, str) or not provenance.strip():
        raise HarnessInputError(
            "Descriptor field 'oracle.provenance' must be a non-empty string.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="non_empty_string_required",
            context={"field": "oracle.provenance"},
        )

    raw_evaluations = _required(root, "evaluations")
    if not isinstance(raw_evaluations, list) or not raw_evaluations:
        raise HarnessInputError(
            "Descriptor field 'evaluations' must be a non-empty array.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="non_empty_array_required",
            context={"field": "evaluations"},
        )

    evaluations: list[Evaluation] = []
    identifiers: set[str] = set()
    for index, raw_evaluation in enumerate(raw_evaluations):
        field = f"evaluations[{index}]"
        item = _closed_mapping(raw_evaluation, field, _EVALUATION_FIELDS)
        identifier = _required(item, "id", parent=field)
        if (
            not isinstance(identifier, str)
            or _STABLE_IDENTIFIER.fullmatch(identifier) is None
        ):
            raise HarnessInputError(
                f"Descriptor field '{field}.id' must be a stable lowercase "
                "identifier.",
                code="DESCRIPTOR_SCHEMA_INVALID",
                reason="stable_identifier_required",
                context={"field": f"{field}.id"},
            )
        if identifier in identifiers:
            raise HarnessInputError(
                "Descriptor evaluation identifiers must be unique.",
                code="DESCRIPTOR_SCHEMA_INVALID",
                reason="duplicate_evaluation_identifier",
                context={"field": f"{field}.id"},
            )
        identifiers.add(identifier)
        evaluations.append(
            Evaluation(
                identifier=identifier,
                input_rgb=_rgb_vector(
                    _required(
                        item,
                        "input",
                        parent=field,
                        code="EVALUATION_INPUT_INVALID",
                    ),
                    f"{field}.input",
                    code="EVALUATION_INPUT_INVALID",
                    require_unit_domain=True,
                ),
                expected_rgb=_rgb_vector(
                    _required(item, "expected", parent=field),
                    f"{field}.expected",
                    code="DESCRIPTOR_SCHEMA_INVALID",
                    require_unit_domain=False,
                ),
            )
        )

    gates = _closed_mapping(
        _required(root, "gates"),
        "gates",
        _GATE_FIELDS,
    )
    maximum_absolute_error = _finite_number(
        _required(gates, "maximum_absolute_error", parent="gates"),
        "gates.maximum_absolute_error",
    )
    if maximum_absolute_error < 0.0:
        raise HarnessInputError(
            "Descriptor field 'gates.maximum_absolute_error' cannot be negative.",
            code="DESCRIPTOR_SCHEMA_INVALID",
            reason="negative_gate_threshold",
            context={"field": "gates.maximum_absolute_error"},
        )

    required_boolean_gates = (
        "require_finite_outputs",
        "require_node_binary32_identity",
        "require_serialization_binary32_identity",
    )
    boolean_gates: dict[str, bool] = {}
    for field in required_boolean_gates:
        value = _required(gates, field, parent="gates")
        if not isinstance(value, bool):
            raise HarnessInputError(
                f"Descriptor field 'gates.{field}' must be boolean.",
                code="DESCRIPTOR_SCHEMA_INVALID",
                reason="boolean_required",
                context={"field": f"gates.{field}"},
            )
        boolean_gates[field] = value

    return TestCase(
        case_id=case_id,
        cube_sha256=cube_sha256,
        interpolation=interpolation,
        evaluations=tuple(evaluations),
        maximum_absolute_error=maximum_absolute_error,
        require_finite_outputs=boolean_gates["require_finite_outputs"],
        require_node_binary32_identity=boolean_gates[
            "require_node_binary32_identity"
        ],
        require_serialization_binary32_identity=boolean_gates[
            "require_serialization_binary32_identity"
        ],
    )


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


def _sample_value_failure(
    *,
    line_number: int,
    sample_row: int,
    component: int,
    reason: str,
    message: str,
) -> _CubeParseFailure:
    return _CubeParseFailure(
        message,
        code="CUBE_SAMPLE_VALUE_INVALID",
        reason=reason,
        context={
            "component": component,
            "line": line_number,
            "sample_row": sample_row,
        },
    )


def _outside_binary32_failure(
    *, line_number: int, sample_row: int, component: int
) -> _CubeParseFailure:
    return _sample_value_failure(
        line_number=line_number,
        sample_row=sample_row,
        component=component,
        reason="outside_binary32_range",
        message=(
            f"Cube line {line_number} component {component} is outside the finite "
            "binary32 range."
        ),
    )


def _non_finite_token(token: str) -> bool:
    return token.lower().lstrip("+-") in {"inf", "infinity", "nan"}


def _unsupported_directive_failure(
    token: str, *, line_number: int, section: str
) -> _CubeParseFailure:
    return _CubeParseFailure(
        f"Cube line {line_number} uses unsupported directive {token!r}.",
        code="CUBE_STRUCTURE_INVALID",
        reason="unsupported_directive",
        context={
            "directive": token,
            "line": line_number,
            "section": section,
        },
    )


def _unknown_header_failure(
    token: str, *, line_number: int, section: str
) -> _CubeParseFailure:
    context: dict[str, object] = {
        "line": line_number,
        "section": section,
    }
    if len(token) <= _UNKNOWN_HEADER_PREVIEW_LENGTH:
        context["header"] = token
        message = f"Cube line {line_number} contains unknown header {token!r}."
    else:
        preview = token[:_UNKNOWN_HEADER_PREVIEW_LENGTH]
        context["header_length"] = len(token)
        context["header_preview"] = preview
        message = (
            f"Cube line {line_number} contains an unknown header beginning "
            f"{preview!r}."
        )
    return _CubeParseFailure(
        message,
        code="CUBE_STRUCTURE_INVALID",
        reason="unknown_header",
        context=context,
    )


def _decimal_to_binary32_bits(
    token: str, *, line_number: int, sample_row: int, component: int
) -> int:
    if _DECIMAL_TOKEN.fullmatch(token) is None:
        normalized = token.lower().lstrip("+-")
        if _non_finite_token(token):
            reason = "non_finite_number"
            message = (
                f"Cube line {line_number} component {component} must be finite."
            )
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
        raise _sample_value_failure(
            line_number=line_number,
            sample_row=sample_row,
            component=component,
            reason=reason,
            message=message,
        )

    try:
        value = Decimal(token)
    except InvalidOperation as error:
        raise _sample_value_failure(
            line_number=line_number,
            sample_row=sample_row,
            component=component,
            reason="malformed_decimal",
            message=(
                f"Cube line {line_number} component {component} must be a decimal "
                "number."
            ),
        ) from error

    sign = 1 if value.is_signed() else 0
    if value.is_zero():
        return sign << 31

    # Built-in abs() applies the active Decimal context and can round the token.
    magnitude = value.copy_abs()
    adjusted_exponent = magnitude.adjusted()
    if adjusted_exponent > 38:
        raise _outside_binary32_failure(
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
            raise _outside_binary32_failure(
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


def _float_to_binary32_bits(value: float) -> int:
    try:
        packed = struct.pack(">f", value)
    except (OverflowError, struct.error) as error:
        raise HarnessInputError("An evaluated value is outside the finite binary32 range.") from error
    return struct.unpack(">I", packed)[0]


def _parse_cube(raw: bytes) -> Cube:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as error:
        raise _CubeParseFailure(
            "The Cube artifact must use Basic Latin text.",
            code="CUBE_ENCODING_INVALID",
            reason="non_ascii_text",
            context={
                "byte_offset": error.start,
                "byte_value": raw[error.start],
            },
        ) from error

    size: int | None = None
    samples: list[Binary32RGB] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if size is None:
            if not stripped or stripped.startswith("#"):
                continue
            tokens = stripped.split()
            first_token = tokens[0]
            if first_token in _UNSUPPORTED_CUBE_DIRECTIVES:
                raise _unsupported_directive_failure(
                    first_token,
                    line_number=line_number,
                    section="preamble",
                )
            if first_token != "LUT_3D_SIZE":
                if _HEADER_TOKEN.fullmatch(first_token) is not None:
                    raise _unknown_header_failure(
                        first_token,
                        line_number=line_number,
                        section="preamble",
                    )
                raise _CubeParseFailure(
                    f"Cube line {line_number} appears before LUT_3D_SIZE.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="missing_size_declaration",
                    context={"declaration": "LUT_3D_SIZE"},
                )
            if len(tokens) != 2:
                raise _CubeParseFailure(
                    f"Cube line {line_number} must contain LUT_3D_SIZE and one "
                    "integer value.",
                    code="CUBE_STRUCTURE_INVALID",
                    reason="malformed_size_declaration",
                    context={
                        "actual_tokens": len(tokens),
                        "declaration": "LUT_3D_SIZE",
                        "expected_tokens": 2,
                        "line": line_number,
                    },
                )

            size_token = tokens[1]
            if not size_token.isdigit():
                raise _CubeParseFailure(
                    f"Cube line {line_number} lattice size must be an integer.",
                    code="CUBE_LATTICE_SIZE_INVALID",
                    reason="size_not_integer",
                    context={
                        "line": line_number,
                        "maximum": 65,
                        "minimum": 2,
                    },
                )

            normalized_size = size_token.lstrip("0") or "0"
            if len(normalized_size) > 2:
                raise _CubeParseFailure(
                    f"Cube line {line_number} lattice size must be between 2 and 65.",
                    code="CUBE_LATTICE_SIZE_INVALID",
                    reason="size_out_of_range",
                    context={
                        "line": line_number,
                        "maximum": 65,
                        "minimum": 2,
                        "value_digits": len(normalized_size),
                    },
                )
            size = int(normalized_size)
            if size < 2 or size > 65:
                raise _CubeParseFailure(
                    f"Cube line {line_number} lattice size must be between 2 and 65.",
                    code="CUBE_LATTICE_SIZE_INVALID",
                    reason="size_out_of_range",
                    context={
                        "line": line_number,
                        "maximum": 65,
                        "minimum": 2,
                        "value": size,
                    },
                )
            continue

        if not stripped:
            raise _CubeParseFailure(
                f"Cube line {line_number} is blank after LUT_3D_SIZE.",
                code="CUBE_STRUCTURE_INVALID",
                reason="blank_line_after_size",
                context={"line": line_number, "section": "sample_table"},
            )
        if "#" in stripped:
            raise _CubeParseFailure(
                f"Cube line {line_number} contains a comment after LUT_3D_SIZE.",
                code="CUBE_STRUCTURE_INVALID",
                reason="comment_after_size",
                context={"line": line_number, "section": "sample_table"},
            )
        tokens = stripped.split()
        first_token = tokens[0]
        if first_token == "LUT_3D_SIZE":
            raise _CubeParseFailure(
                f"Cube line {line_number} repeats LUT_3D_SIZE.",
                code="CUBE_STRUCTURE_INVALID",
                reason="duplicate_size_declaration",
                context={
                    "declaration": "LUT_3D_SIZE",
                    "line": line_number,
                },
            )
        if first_token in _UNSUPPORTED_CUBE_DIRECTIVES:
            raise _unsupported_directive_failure(
                first_token,
                line_number=line_number,
                section="sample_table",
            )
        if (
            _HEADER_TOKEN.fullmatch(first_token) is not None
            and not _non_finite_token(first_token)
        ):
            raise _unknown_header_failure(
                first_token,
                line_number=line_number,
                section="sample_table",
            )

        expected_count = size**3
        sample_row = len(samples) + 1
        if sample_row > expected_count:
            raise _CubeParseFailure(
                f"Cube lattice size {size} requires {expected_count} sample rows; "
                f"line {line_number} starts row {sample_row}.",
                code="CUBE_STRUCTURE_INVALID",
                reason="too_many_sample_rows",
                context={
                    "actual_rows": sample_row,
                    "expected_rows": expected_count,
                    "lattice_size": size,
                    "line": line_number,
                },
            )
        if len(tokens) != 3:
            raise _CubeParseFailure(
                f"Cube line {line_number} must contain exactly three sample values.",
                code="CUBE_STRUCTURE_INVALID",
                reason="sample_token_count",
                context={
                    "actual_tokens": len(tokens),
                    "expected_tokens": 3,
                    "line": line_number,
                    "sample_row": sample_row,
                },
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

    if size is None:
        raise _CubeParseFailure(
            "The Cube artifact is missing LUT_3D_SIZE.",
            code="CUBE_STRUCTURE_INVALID",
            reason="missing_size_declaration",
            context={"declaration": "LUT_3D_SIZE"},
        )
    expected_count = size**3
    if len(samples) != expected_count:
        raise _CubeParseFailure(
            f"Cube lattice size {size} requires {expected_count} sample rows; "
            f"found {len(samples)}.",
            code="CUBE_STRUCTURE_INVALID",
            reason="too_few_sample_rows",
            context={
                "actual_rows": len(samples),
                "expected_rows": expected_count,
                "lattice_size": size,
            },
        )
    return Cube(size=size, sample_bits=tuple(samples))


def _serialize_cube(cube: Cube) -> bytes:
    lines = [f"LUT_3D_SIZE {cube.size}"]
    for sample in cube.sample_bits:
        lines.append(
            " ".join(format(_binary32_bits_to_float(bits), ".9g") for bits in sample)
        )
    return ("\n".join(lines) + "\n").encode("ascii")


def _lattice_axis_position(value: float, size: int) -> LatticeAxisPosition:
    if value == 1.0:
        return LatticeAxisPosition(size - 1, size - 1, 0.0)

    scaled = value * (size - 1)
    nearest_node = round(scaled)
    # Reconstructing the same binary64 rational identifies conceptual nodes
    # without snapping a genuinely adjacent input to the node.
    if value == nearest_node / (size - 1):
        return LatticeAxisPosition(nearest_node, nearest_node, 0.0)

    lower = int(scaled)
    return LatticeAxisPosition(lower, lower + 1, scaled - lower)


def _lerp(start: float, end: float, amount: float) -> float:
    if amount == 0.0:
        return start
    if amount == 1.0:
        return end
    return start + amount * (end - start)


def _evaluate_trilinear(
    cube: Cube, input_rgb: RGB
) -> RGB:
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


def _evaluate_tetrahedral(cube: Cube, input_rgb: RGB) -> RGB:
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

    # The strict comparisons and adjacent tie routing mirror the operational
    # six-region convention used by the OpenColorIO reference implementation.
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


def _evaluate(cube: Cube, input_rgb: RGB, interpolation: str) -> RGB:
    if interpolation == "trilinear":
        return _evaluate_trilinear(cube, input_rgb)
    if interpolation == "tetrahedral":
        return _evaluate_tetrahedral(cube, input_rgb)
    raise HarnessInputError(
        "The selected interpolation is unsupported.",
        code="INTERPOLATION_UNSUPPORTED",
    )


def _evaluate_case(
    cube: Cube, evaluations: tuple[Evaluation, ...], interpolation: str
) -> tuple[RGB, ...]:
    return tuple(
        _evaluate(cube, evaluation.input_rgb, interpolation)
        for evaluation in evaluations
    )


def _metrics(
    outputs: tuple[RGB, ...],
    evaluations: tuple[Evaluation, ...],
) -> dict[str, float]:
    absolute_errors: list[float] = []
    normalized_errors: list[float] = []
    for output, evaluation in zip(outputs, evaluations, strict=True):
        for actual, expected in zip(output, evaluation.expected_rgb, strict=True):
            absolute_error = abs(actual - expected)
            absolute_errors.append(absolute_error)
            normalized_errors.append(absolute_error / max(abs(expected), 0.1))

    ordered = sorted(absolute_errors)
    p99_index = math.ceil(0.99 * len(ordered)) - 1
    exact_sum = sum((Fraction.from_float(value) for value in absolute_errors), Fraction())
    mean = float(exact_sum / len(absolute_errors))
    return {
        "maximum_absolute_error": max(absolute_errors),
        "maximum_clf_normalized_error": max(normalized_errors),
        "mean_absolute_error": mean,
        "p99_absolute_error": ordered[p99_index],
    }


def _outputs_are_finite(outputs: tuple[RGB, ...]) -> bool:
    return all(math.isfinite(component) for output in outputs for component in output)


def _nodes_are_binary32_identical(cube: Cube, interpolation: str) -> bool:
    index = 0
    denominator = cube.size - 1
    for blue in range(cube.size):
        for green in range(cube.size):
            for red in range(cube.size):
                input_rgb = (
                    red / denominator,
                    green / denominator,
                    blue / denominator,
                )
                output = _evaluate(cube, input_rgb, interpolation)
                output_bits = tuple(_float_to_binary32_bits(value) for value in output)
                if output_bits != cube.sample_bits[index]:
                    return False
                index += 1
    return True


def _evaluate_cube(
    cube: Cube, evaluations: tuple[Evaluation, ...], interpolation: str
) -> EvaluationRun:
    outputs = _evaluate_case(cube, evaluations, interpolation)
    return EvaluationRun(
        metrics=_metrics(outputs, evaluations),
        finite=_outputs_are_finite(outputs),
        nodes_binary32_identical=_nodes_are_binary32_identical(
            cube, interpolation
        ),
    )


def _deterministic_json_bytes(value: object) -> bytes:
    text = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    return (text + "\n").encode("ascii")


def _provisional_evidence() -> dict[str, object]:
    return {
        "compatibility_claims": [],
        "host_validation": "not_performed",
        "status": "provisional",
    }


def _rollback_outputs(
    artifacts: tuple[tuple[Path, Path], ...],
    published: set[Path],
) -> None:
    for final_path, backup_path in reversed(artifacts):
        try:
            if os.path.lexists(backup_path):
                os.replace(backup_path, final_path)
            elif final_path in published:
                final_path.unlink(missing_ok=True)
        except OSError:
            # The original output error remains authoritative. Rollback is
            # deliberately best-effort so cleanup cannot leak filesystem paths.
            pass


def _write_outputs(output_dir: Path, canonical_cube: bytes, report: bytes) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        final_artifacts = (
            (output_dir / "canonical.cube", canonical_cube),
            (output_dir / "report.json", report),
        )
        existing_artifacts: set[Path] = set()
        for final_path, _ in final_artifacts:
            try:
                mode = final_path.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(mode):
                raise HarnessInputError(
                    "The output artifacts could not be written."
                )
            existing_artifacts.add(final_path)

        with tempfile.TemporaryDirectory(
            dir=output_dir,
            ignore_cleanup_errors=True,
            prefix=".portable-cube-harness-",
        ) as staging_directory_text:
            staging_directory = Path(staging_directory_text)
            staged_artifacts = tuple(
                (
                    final_path,
                    staging_directory / f"{final_path.name}.next",
                    staging_directory / f"{final_path.name}.previous",
                    artifact_bytes,
                )
                for final_path, artifact_bytes in final_artifacts
            )
            for _, staged_path, _, artifact_bytes in staged_artifacts:
                staged_path.write_bytes(artifact_bytes)

            rollback_artifacts = tuple(
                (final_path, backup_path)
                for final_path, _, backup_path, _ in staged_artifacts
            )
            published: set[Path] = set()
            try:
                for final_path, _, backup_path, _ in staged_artifacts:
                    if final_path in existing_artifacts:
                        os.replace(final_path, backup_path)
                for final_path, staged_path, _, _ in staged_artifacts:
                    os.replace(staged_path, final_path)
                    published.add(final_path)
            except Exception:
                _rollback_outputs(rollback_artifacts, published)
                raise
    except HarnessInputError:
        raise
    except OSError as error:
        raise HarnessInputError("The output artifacts could not be written.") from error


def _run_case_bytes(
    *, descriptor_bytes: bytes, input_cube_bytes: bytes, output_dir: Path
) -> tuple[int, bytes]:
    descriptor = _load_test_case(descriptor_bytes)
    input_cube_sha256 = hashlib.sha256(input_cube_bytes).hexdigest()
    if input_cube_sha256 != descriptor.cube_sha256:
        raise HarnessInputError(
            "The Cube artifact does not match its descriptor checksum.",
            code="CUBE_CHECKSUM_MISMATCH",
            reason="sha256_mismatch",
            context={
                "actual_sha256": input_cube_sha256,
                "expected_sha256": descriptor.cube_sha256,
            },
        )

    try:
        input_cube = _parse_cube(input_cube_bytes)
    except _CubeParseFailure as error:
        raise HarnessInputError(
            str(error),
            code=error.code,
            reason=error.reason,
            context=error.context,
        ) from error
    input_run = _evaluate_cube(
        input_cube, descriptor.evaluations, descriptor.interpolation
    )

    canonical_cube_bytes = _serialize_cube(input_cube)
    canonical_cube_sha256 = hashlib.sha256(canonical_cube_bytes).hexdigest()
    canonical_cube = _parse_cube(canonical_cube_bytes)
    serialization_identical = canonical_cube.sample_bits == input_cube.sample_bits
    canonical_run = _evaluate_cube(
        canonical_cube, descriptor.evaluations, descriptor.interpolation
    )

    input_evaluation_passed = (
        input_run.metrics["maximum_absolute_error"]
        <= descriptor.maximum_absolute_error
        and (input_run.finite or not descriptor.require_finite_outputs)
    )
    canonical_evaluation_passed = (
        canonical_run.metrics["maximum_absolute_error"]
        <= descriptor.maximum_absolute_error
        and (canonical_run.finite or not descriptor.require_finite_outputs)
    )
    node_round_trip_passed = (
        input_run.nodes_binary32_identical
        and canonical_run.nodes_binary32_identical
    ) or not descriptor.require_node_binary32_identity
    serialization_round_trip_passed = (
        serialization_identical
        or not descriptor.require_serialization_binary32_identity
    )
    overall_passed = (
        input_evaluation_passed
        and canonical_evaluation_passed
        and node_round_trip_passed
        and serialization_round_trip_passed
    )

    report = {
        "case_id": descriptor.case_id,
        "evidence": _provisional_evidence(),
        "evaluation_count": len(descriptor.evaluations),
        "harness_version": HARNESS_VERSION,
        "hashes": {
            "canonical_cube_sha256": canonical_cube_sha256,
            "input_cube_sha256": input_cube_sha256,
        },
        "interpolation": descriptor.interpolation,
        "lattice_size": input_cube.size,
        "metrics": {
            "canonical_evaluation": canonical_run.metrics,
            "input_evaluation": input_run.metrics,
        },
        "overall_result": "pass" if overall_passed else "fail",
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "round_trip": {
            "canonical_node_evaluation_binary32_identical": canonical_run.nodes_binary32_identical,
            "canonical_reevaluation_passed": canonical_evaluation_passed,
            "input_node_evaluation_binary32_identical": input_run.nodes_binary32_identical,
            "serialization_binary32_identical": serialization_identical,
        },
        "sample_count": input_cube.sample_count,
        "validation": {"errors": [], "result": "pass"},
    }
    report_bytes = _deterministic_json_bytes(report)
    _write_outputs(output_dir, canonical_cube_bytes, report_bytes)
    return (0 if overall_passed else 1), report_bytes


def run_case(
    *, descriptor_path: Path, cube_path: Path, output_dir: Path
) -> tuple[int, bytes]:
    return _run_case_bytes(
        descriptor_bytes=_read_bytes(descriptor_path, "test descriptor"),
        input_cube_bytes=_read_bytes(cube_path, "Cube artifact"),
        output_dir=output_dir,
    )
