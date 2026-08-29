"""Private implementation behind the repository-local conformance command."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any, cast


HARNESS_VERSION = "0.1.0"
REPORT_SCHEMA_VERSION = 1
TEST_CASE_SCHEMA_VERSION = 1

_DECIMAL_TOKEN = re.compile(
    r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$"
)
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STABLE_IDENTIFIER = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

RGB = tuple[float, float, float]
Binary32RGB = tuple[int, int, int]


class HarnessInputError(ValueError):
    """A descriptor, Cube artifact, or output request is invalid."""


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


def _reject_json_constant(value: str) -> None:
    raise HarnessInputError(f"The test descriptor contains invalid number {value!r}.")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HarnessInputError(f"Descriptor field {field!r} must be an object.")
    return value


def _required(mapping: dict[str, Any], field: str) -> Any:
    if field not in mapping:
        raise HarnessInputError(f"Descriptor field {field!r} is required.")
    return mapping[field]


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HarnessInputError(f"Descriptor field {field!r} must be a number.")
    result = float(value)
    if not math.isfinite(result):
        raise HarnessInputError(f"Descriptor field {field!r} must be finite.")
    return result


def _rgb_vector(value: Any, field: str, *, require_unit_domain: bool) -> RGB:
    if not isinstance(value, list) or len(value) != 3:
        raise HarnessInputError(f"Descriptor field {field!r} must contain three numbers.")
    result = tuple(
        _finite_number(component, f"{field}[{index}]")
        for index, component in enumerate(value)
    )
    if require_unit_domain and any(component < 0.0 or component > 1.0 for component in result):
        raise HarnessInputError(f"Descriptor field {field!r} must be inside [0,1].")
    return cast(RGB, result)


def _load_test_case(raw: bytes) -> TestCase:
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HarnessInputError("The test descriptor must be UTF-8 JSON.") from error

    try:
        parsed = json.loads(decoded, parse_constant=_reject_json_constant)
    except HarnessInputError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise HarnessInputError("The test descriptor is not valid JSON.") from error

    root = _mapping(parsed, "<root>")
    if _required(root, "test_case_schema_version") != TEST_CASE_SCHEMA_VERSION:
        raise HarnessInputError("The test descriptor schema version is unsupported.")

    case_id = _required(root, "case_id")
    if not isinstance(case_id, str) or _STABLE_IDENTIFIER.fullmatch(case_id) is None:
        raise HarnessInputError("Descriptor field 'case_id' is invalid.")

    cube_metadata = _mapping(_required(root, "cube"), "cube")
    cube_sha256 = _required(cube_metadata, "sha256")
    if not isinstance(cube_sha256, str) or _HEX_SHA256.fullmatch(cube_sha256) is None:
        raise HarnessInputError("Descriptor field 'cube.sha256' is invalid.")

    interpolation = _required(root, "interpolation")
    if interpolation != "trilinear":
        raise HarnessInputError("This case must explicitly select trilinear interpolation.")

    oracle = _mapping(_required(root, "oracle"), "oracle")
    if _required(oracle, "kind") != "explicit_expected_values":
        raise HarnessInputError("The identity case requires explicit independent expected values.")
    provenance = _required(oracle, "provenance")
    if not isinstance(provenance, str) or not provenance.strip():
        raise HarnessInputError("Descriptor field 'oracle.provenance' is invalid.")

    raw_evaluations = _required(root, "evaluations")
    if not isinstance(raw_evaluations, list) or not raw_evaluations:
        raise HarnessInputError("Descriptor field 'evaluations' must be a non-empty array.")

    evaluations: list[Evaluation] = []
    identifiers: set[str] = set()
    for index, raw_evaluation in enumerate(raw_evaluations):
        item = _mapping(raw_evaluation, f"evaluations[{index}]")
        identifier = _required(item, "id")
        if not isinstance(identifier, str) or _STABLE_IDENTIFIER.fullmatch(identifier) is None:
            raise HarnessInputError(f"Descriptor field 'evaluations[{index}].id' is invalid.")
        if identifier in identifiers:
            raise HarnessInputError("Evaluation identifiers must be unique.")
        identifiers.add(identifier)
        evaluations.append(
            Evaluation(
                identifier=identifier,
                input_rgb=_rgb_vector(
                    _required(item, "input"),
                    f"evaluations[{index}].input",
                    require_unit_domain=True,
                ),
                expected_rgb=_rgb_vector(
                    _required(item, "expected"),
                    f"evaluations[{index}].expected",
                    require_unit_domain=False,
                ),
            )
        )

    gates = _mapping(_required(root, "gates"), "gates")
    maximum_absolute_error = _finite_number(
        _required(gates, "maximum_absolute_error"),
        "gates.maximum_absolute_error",
    )
    if maximum_absolute_error < 0.0:
        raise HarnessInputError("The maximum absolute error gate cannot be negative.")

    required_boolean_gates = (
        "require_finite_outputs",
        "require_node_binary32_identity",
        "require_serialization_binary32_identity",
    )
    boolean_gates: dict[str, bool] = {}
    for field in required_boolean_gates:
        value = _required(gates, field)
        if not isinstance(value, bool):
            raise HarnessInputError(f"Descriptor field 'gates.{field}' must be boolean.")
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


def _decimal_to_binary32_bits(token: str) -> int:
    if _DECIMAL_TOKEN.fullmatch(token) is None:
        raise HarnessInputError(f"Cube sample token {token!r} is not a decimal number.")

    try:
        value = Decimal(token)
    except InvalidOperation as error:
        raise HarnessInputError(f"Cube sample token {token!r} is malformed.") from error

    sign = 1 if value.is_signed() else 0
    if value.is_zero():
        return sign << 31

    # Built-in abs() applies the active Decimal context and can round the token.
    magnitude = value.copy_abs()
    adjusted_exponent = magnitude.adjusted()
    if adjusted_exponent > 38:
        raise HarnessInputError("A Cube sample is outside the finite binary32 range.")
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
            raise HarnessInputError("A Cube sample is outside the finite binary32 range.")

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
        raise HarnessInputError("The Cube artifact must use Basic Latin text.") from error

    size: int | None = None
    samples: list[Binary32RGB] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if size is None:
            if not stripped or stripped.startswith("#"):
                continue
            tokens = stripped.split()
            if len(tokens) != 2 or tokens[0] != "LUT_3D_SIZE":
                raise HarnessInputError(
                    f"Cube line {line_number} must declare LUT_3D_SIZE."
                )
            if not tokens[1].isdigit():
                raise HarnessInputError("The Cube lattice size must be an integer.")
            size = int(tokens[1])
            if size < 2 or size > 65:
                raise HarnessInputError("The Cube lattice size must be between 2 and 65.")
            continue

        if not stripped or stripped.startswith("#"):
            raise HarnessInputError(
                f"Cube line {line_number} is invalid inside the sample table."
            )
        tokens = stripped.split()
        if len(tokens) != 3:
            raise HarnessInputError(
                f"Cube line {line_number} must contain exactly three samples."
            )
        samples.append(
            cast(
                Binary32RGB,
                tuple(_decimal_to_binary32_bits(token) for token in tokens),
            )
        )

    if size is None:
        raise HarnessInputError("The Cube artifact is missing LUT_3D_SIZE.")
    expected_count = size**3
    if len(samples) != expected_count:
        raise HarnessInputError(
            f"The Cube artifact must contain exactly {expected_count} sample rows."
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


def _evaluate_case(
    cube: Cube, evaluations: tuple[Evaluation, ...]
) -> tuple[RGB, ...]:
    return tuple(
        _evaluate_trilinear(cube, evaluation.input_rgb)
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


def _nodes_are_binary32_identical(cube: Cube) -> bool:
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
                output = _evaluate_trilinear(cube, input_rgb)
                output_bits = tuple(_float_to_binary32_bits(value) for value in output)
                if output_bits != cube.sample_bits[index]:
                    return False
                index += 1
    return True


def _evaluate_cube(
    cube: Cube, evaluations: tuple[Evaluation, ...]
) -> EvaluationRun:
    outputs = _evaluate_case(cube, evaluations)
    return EvaluationRun(
        metrics=_metrics(outputs, evaluations),
        finite=_outputs_are_finite(outputs),
        nodes_binary32_identical=_nodes_are_binary32_identical(cube),
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


def _write_outputs(output_dir: Path, canonical_cube: bytes, report: bytes) -> None:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "canonical.cube").write_bytes(canonical_cube)
        (output_dir / "report.json").write_bytes(report)
    except OSError as error:
        raise HarnessInputError("The output artifacts could not be written.") from error


def run_case(
    *, descriptor_path: Path, cube_path: Path, output_dir: Path
) -> tuple[int, bytes]:
    descriptor = _load_test_case(_read_bytes(descriptor_path, "test descriptor"))
    input_cube_bytes = _read_bytes(cube_path, "Cube artifact")
    input_cube_sha256 = hashlib.sha256(input_cube_bytes).hexdigest()
    if input_cube_sha256 != descriptor.cube_sha256:
        raise HarnessInputError("The Cube artifact does not match its descriptor checksum.")

    input_cube = _parse_cube(input_cube_bytes)
    input_run = _evaluate_cube(input_cube, descriptor.evaluations)

    canonical_cube_bytes = _serialize_cube(input_cube)
    canonical_cube_sha256 = hashlib.sha256(canonical_cube_bytes).hexdigest()
    canonical_cube = _parse_cube(canonical_cube_bytes)
    serialization_identical = canonical_cube.sample_bits == input_cube.sample_bits
    canonical_run = _evaluate_cube(canonical_cube, descriptor.evaluations)

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
        "evidence": {
            "compatibility_claims": [],
            "host_validation": "not_performed",
            "status": "provisional",
        },
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
