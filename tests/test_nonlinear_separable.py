from __future__ import annotations

import hashlib
import itertools
import json
import math
import struct
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from typing import Any

from acceptance_support import (
    REPOSITORY_ROOT,
    assert_deterministic_success,
    run_harness,
)


FIXTURE_DIRECTORY = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "nonlinear-separable-5"
)
COEFFICIENT = Fraction(1, 2**15)
PASS_GATE = 2**-20
FAIL_GATE = 2**-22
LCG_INITIAL_STATE = 0x434C5554
LCG_FINAL_STATE = 0x13261934
EVALUATION_COUNT = 95
FAMILIES = (
    ("neutral", (1, 1, 1)),
    ("primary-red", (1, 0, 0)),
    ("primary-green", (0, 1, 0)),
    ("primary-blue", (0, 0, 1)),
    ("secondary-cyan", (0, 1, 1)),
    ("secondary-magenta", (1, 0, 1)),
    ("secondary-yellow", (1, 1, 0)),
)
EXPECTED_METRICS = {
    "maximum_absolute_error": 2**-21,
    "maximum_clf_normalized_error": 4.169651174994186e-06,
    "mean_absolute_error": float(
        Fraction(710218667, 4011018418126848)
    ),
    "p99_absolute_error": 2**-21,
}


def _descriptor(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIRECTORY / name).read_bytes())


def _binary32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def _analytic_fraction(value: float) -> Fraction:
    component = Fraction.from_float(value)
    return component + COEFFICIENT * component * (1 - component)


def _analytic(value: float) -> float:
    return float(_analytic_fraction(value))


def _lcg_inputs() -> tuple[list[list[float]], int]:
    state = LCG_INITIAL_STATE
    inputs = []
    for _ in range(32):
        components = []
        for _ in range(3):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            upper = state >> 16
            components.append((upper + 0.5) / 2**16)
        inputs.append(components)
    return inputs, state


def _expected_evaluations() -> list[dict[str, Any]]:
    evaluations = []
    for family, mask in FAMILIES:
        for index in range(9):
            level = index / 8
            input_rgb = [level * component for component in mask]
            evaluations.append(
                {
                    "expected": [_analytic(component) for component in input_rgb],
                    "id": f"ramp-{family}-{index:02d}",
                    "input": input_rgb,
                }
            )

    random_inputs, _ = _lcg_inputs()
    for index, input_rgb in enumerate(random_inputs):
        evaluations.append(
            {
                "expected": [_analytic(component) for component in input_rgb],
                "id": f"random-lcg32-{index:02d}",
                "input": input_rgb,
            }
        )
    return evaluations


def _cube_samples(path: Path) -> list[tuple[float, float, float]]:
    rows = []
    for line in path.read_text(encoding="ascii").splitlines():
        if not line or line.startswith("#") or line.startswith("LUT_3D_SIZE"):
            continue
        rows.append(tuple(_binary32(float(token)) for token in line.split()))
    return rows


def _chord_error(value: float) -> Fraction:
    component = Fraction.from_float(value)
    if component == 1:
        return Fraction()
    scaled = 4 * component
    lower_index = scaled.numerator // scaled.denominator
    lower = Fraction(lower_index, 4)
    upper = Fraction(lower_index + 1, 4)
    return COEFFICIENT * (component - lower) * (upper - component)


def _independent_metrics(
    evaluations: list[dict[str, Any]],
) -> dict[str, float]:
    components = [
        component
        for evaluation in evaluations
        for component in evaluation["input"]
    ]
    errors = [_chord_error(component) for component in components]
    ordered = sorted(errors)
    p99_index = math.ceil(0.99 * len(ordered)) - 1
    normalized = [
        float(error) / max(abs(_analytic(component)), 0.1)
        for component, error in zip(components, errors, strict=True)
    ]
    return {
        "maximum_absolute_error": float(max(errors)),
        "maximum_clf_normalized_error": max(normalized),
        "mean_absolute_error": float(sum(errors, Fraction()) / len(errors)),
        "p99_absolute_error": float(ordered[p99_index]),
    }


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


class NonlinearSeparableAcceptanceTest(unittest.TestCase):
    def test_both_interpolations_complete_the_public_round_trip(self) -> None:
        runs = {
            interpolation: assert_deterministic_success(
                self,
                FIXTURE_DIRECTORY,
                descriptor_name=f"{interpolation}.case.json",
                expected_report_name=None,
                require_zero_metrics=False,
            )
            for interpolation in ("trilinear", "tetrahedral")
        }

        self.assertEqual(runs["trilinear"].input_cube, runs["tetrahedral"].input_cube)
        self.assertEqual(
            runs["trilinear"].canonical_cube,
            runs["tetrahedral"].canonical_cube,
        )
        for interpolation, run in runs.items():
            report = run.report
            self.assertEqual(report["interpolation"], interpolation)
            self.assertEqual(report["lattice_size"], 5)
            self.assertEqual(report["sample_count"], 125)
            self.assertEqual(report["evaluation_count"], EVALUATION_COUNT)
            self.assertEqual(
                report["metrics"],
                {
                    "canonical_evaluation": EXPECTED_METRICS,
                    "input_evaluation": EXPECTED_METRICS,
                },
            )
            self.assertLessEqual(
                report["metrics"]["input_evaluation"][
                    "maximum_absolute_error"
                ],
                PASS_GATE,
            )

    def test_static_oracle_and_recorded_corpus_are_independent(self) -> None:
        trilinear = _descriptor("trilinear.case.json")
        tetrahedral = _descriptor("tetrahedral.case.json")
        expected_evaluations = _expected_evaluations()
        input_path = FIXTURE_DIRECTORY / "input.cube"
        canonical_path = FIXTURE_DIRECTORY / "expected.canonical.cube"
        input_bytes = input_path.read_bytes()

        self.assertEqual(trilinear["cube"], tetrahedral["cube"])
        self.assertEqual(trilinear["evaluations"], tetrahedral["evaluations"])
        self.assertEqual(trilinear["gates"], tetrahedral["gates"])
        self.assertEqual(trilinear["oracle"], tetrahedral["oracle"])
        self.assertEqual(trilinear["test_case_schema_version"], 1)
        self.assertEqual(tetrahedral["test_case_schema_version"], 1)
        self.assertEqual(
            trilinear["cube"]["sha256"], hashlib.sha256(input_bytes).hexdigest()
        )
        self.assertEqual(
            trilinear["gates"],
            {
                "maximum_absolute_error": PASS_GATE,
                "require_finite_outputs": True,
                "require_node_binary32_identity": True,
                "require_serialization_binary32_identity": True,
            },
        )

        self.assertEqual(trilinear["evaluations"], expected_evaluations)
        self.assertEqual(len(expected_evaluations), EVALUATION_COUNT)
        self.assertEqual(
            len({evaluation["id"] for evaluation in expected_evaluations}),
            EVALUATION_COUNT,
        )
        for family, _ in FAMILIES:
            self.assertEqual(
                sum(
                    evaluation["id"].startswith(f"ramp-{family}-")
                    for evaluation in expected_evaluations
                ),
                9,
            )

        random_inputs, final_state = _lcg_inputs()
        self.assertEqual(final_state, LCG_FINAL_STATE)
        self.assertEqual(len({tuple(value) for value in random_inputs}), 32)
        self.assertTrue(
            all(
                0.0 < component < 1.0
                and component not in {0.0, 0.25, 0.5, 0.75, 1.0}
                for value in random_inputs
                for component in value
            )
        )
        self.assertEqual(
            {
                tuple(component >= 0.5 for component in value)
                for value in random_inputs
            },
            set(itertools.product((False, True), repeat=3)),
        )

        node_values = tuple(_binary32(_analytic(index / 4)) for index in range(5))
        expected_samples = [
            (node_values[red], node_values[green], node_values[blue])
            for blue in range(5)
            for green in range(5)
            for red in range(5)
        ]
        self.assertEqual(_cube_samples(input_path), expected_samples)
        self.assertEqual(_cube_samples(canonical_path), expected_samples)
        self.assertEqual(_independent_metrics(expected_evaluations), EXPECTED_METRICS)

    def test_valid_strict_gate_case_fails_deterministically(self) -> None:
        descriptor = _descriptor("trilinear.case.json")
        self.assertEqual(
            descriptor["gates"]["maximum_absolute_error"], PASS_GATE
        )
        descriptor["case_id"] = "nonlinear-separable-5-trilinear-strict-gate"
        descriptor["gates"]["maximum_absolute_error"] = FAIL_GATE
        expected_cube = (
            FIXTURE_DIRECTORY / "expected.canonical.cube"
        ).read_bytes()

        with (
            tempfile.TemporaryDirectory() as first_temp,
            tempfile.TemporaryDirectory() as second_temp,
        ):
            descriptor_path = Path(first_temp) / "strict-gate.case.json"
            descriptor_path.write_bytes(_json_bytes(descriptor))
            outputs = [
                Path(first_temp) / "artifacts",
                Path(second_temp) / "different-artifacts",
            ]
            results = [
                run_harness(
                    descriptor=descriptor_path,
                    cube=FIXTURE_DIRECTORY / "input.cube",
                    output_directory=output,
                )
                for output in outputs
            ]

            report_bytes = []
            canonical_bytes = []
            for result, output in zip(results, outputs, strict=True):
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(
                    sorted(path.name for path in output.iterdir()),
                    ["canonical.cube", "report.json"],
                )
                report = (output / "report.json").read_bytes()
                canonical = (output / "canonical.cube").read_bytes()
                self.assertEqual(result.stdout, report)
                self.assertEqual(canonical, expected_cube)
                report_bytes.append(report)
                canonical_bytes.append(canonical)

            self.assertEqual(report_bytes[0], report_bytes[1])
            self.assertEqual(canonical_bytes[0], canonical_bytes[1])
            report = json.loads(report_bytes[0])
            self.assertEqual(
                report["case_id"],
                "nonlinear-separable-5-trilinear-strict-gate",
            )
            self.assertEqual(report["overall_result"], "fail")
            self.assertEqual(report["validation"], {"errors": [], "result": "pass"})
            self.assertEqual(
                report["metrics"],
                {
                    "canonical_evaluation": EXPECTED_METRICS,
                    "input_evaluation": EXPECTED_METRICS,
                },
            )
            self.assertGreater(
                report["metrics"]["input_evaluation"][
                    "maximum_absolute_error"
                ],
                FAIL_GATE,
            )
            self.assertEqual(
                report["round_trip"],
                {
                    "canonical_node_evaluation_binary32_identical": True,
                    "canonical_reevaluation_passed": False,
                    "input_node_evaluation_binary32_identical": True,
                    "serialization_binary32_identical": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
