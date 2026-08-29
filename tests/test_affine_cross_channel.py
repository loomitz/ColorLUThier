from __future__ import annotations

import hashlib
import itertools
import json
import struct
import unittest
from fractions import Fraction
from pathlib import Path
from typing import Any

from acceptance_support import REPOSITORY_ROOT, assert_deterministic_success


FIXTURE_DIRECTORY = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "affine-cross-channel-3"
)
MAXIMUM_ABSOLUTE_ERROR_GATE = 2**-20
EVALUATION_COUNT = 67
COMPONENT_ERROR_COUNT = 3 * EVALUATION_COUNT
EXPECTED_METRICS = {
    "trilinear": {
        "maximum_absolute_error": 2**-54,
        "maximum_clf_normalized_error": (2**-54) / 0.24583333333333335,
        "mean_absolute_error": float(Fraction(1, 2**53 * COMPONENT_ERROR_COUNT)),
        "p99_absolute_error": 0.0,
    },
    "tetrahedral": {
        "maximum_absolute_error": 2**-53,
        "maximum_clf_normalized_error": (2**-53) / 0.36250000000000004,
        "mean_absolute_error": float(
            Fraction(13, 2**55 * COMPONENT_ERROR_COUNT)
        ),
        "p99_absolute_error": 2**-54,
    },
}


def _descriptor(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIRECTORY / name).read_bytes())


def _binary32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def _cube_samples() -> list[tuple[float, float, float]]:
    rows = []
    for line in (FIXTURE_DIRECTORY / "input.cube").read_text(
        encoding="ascii"
    ).splitlines():
        if not line or line.startswith("#") or line.startswith("LUT_3D_SIZE"):
            continue
        red, green, blue = line.split()
        rows.append(
            (_binary32(float(red)), _binary32(float(green)), _binary32(float(blue)))
        )
    return rows


def _affine_oracle(
    input_rgb: list[float], samples: list[tuple[float, float, float]]
) -> list[float]:
    origin = samples[0]
    axis_samples = (samples[1], samples[3], samples[9])
    columns = tuple(
        tuple(2.0 * (axis[channel] - origin[channel]) for channel in range(3))
        for axis in axis_samples
    )

    result = []
    for channel in range(3):
        value = origin[channel]
        value = value + input_rgb[0] * columns[0][channel]
        value = value + input_rgb[1] * columns[1][channel]
        value = value + input_rgb[2] * columns[2][channel]
        result.append(value)
    return result


class AffineCrossChannelAcceptanceTest(unittest.TestCase):
    def test_both_interpolations_complete_the_public_round_trip(self) -> None:
        trilinear = assert_deterministic_success(
            self,
            FIXTURE_DIRECTORY,
            descriptor_name="trilinear.case.json",
            expected_report_name=None,
            require_zero_metrics=False,
        )
        tetrahedral = assert_deterministic_success(
            self,
            FIXTURE_DIRECTORY,
            descriptor_name="tetrahedral.case.json",
            expected_report_name=None,
            require_zero_metrics=False,
        )

        self.assertEqual(trilinear.input_cube, tetrahedral.input_cube)
        self.assertEqual(trilinear.canonical_cube, tetrahedral.canonical_cube)
        for interpolation, run in (
            ("trilinear", trilinear),
            ("tetrahedral", tetrahedral),
        ):
            report = run.report
            self.assertEqual(report["interpolation"], interpolation)
            self.assertEqual(report["lattice_size"], 3)
            self.assertEqual(report["sample_count"], 27)
            self.assertEqual(report["evaluation_count"], EVALUATION_COUNT)
            self.assertEqual(
                report["metrics"]["input_evaluation"],
                report["metrics"]["canonical_evaluation"],
            )
            metrics = report["metrics"]["input_evaluation"]
            self.assertEqual(metrics, EXPECTED_METRICS[interpolation])
            self.assertLess(
                metrics["p99_absolute_error"], metrics["maximum_absolute_error"]
            )
            self.assertLessEqual(metrics["maximum_absolute_error"], 2**-52)
            self.assertLessEqual(
                metrics["maximum_absolute_error"],
                MAXIMUM_ABSOLUTE_ERROR_GATE,
            )

    def test_static_oracle_covers_lattice_geometry_independently(self) -> None:
        trilinear = _descriptor("trilinear.case.json")
        tetrahedral = _descriptor("tetrahedral.case.json")
        samples = _cube_samples()
        input_cube = (FIXTURE_DIRECTORY / "input.cube").read_bytes()

        self.assertEqual(len(samples), 27)
        self.assertEqual(
            trilinear["cube"]["sha256"], hashlib.sha256(input_cube).hexdigest()
        )
        self.assertEqual(trilinear["cube"], tetrahedral["cube"])
        self.assertEqual(trilinear["gates"], tetrahedral["gates"])
        self.assertEqual(
            trilinear["gates"],
            {
                "maximum_absolute_error": MAXIMUM_ABSOLUTE_ERROR_GATE,
                "require_finite_outputs": True,
                "require_node_binary32_identity": True,
                "require_serialization_binary32_identity": True,
            },
        )

        trilinear_evaluations = trilinear["evaluations"]
        tetrahedral_evaluations = tetrahedral["evaluations"]
        self.assertEqual(len(trilinear_evaluations), EVALUATION_COUNT)
        self.assertEqual(len(tetrahedral_evaluations), EVALUATION_COUNT)

        evaluation_ids = set()
        for trilinear_item, tetrahedral_item in zip(
            trilinear_evaluations, tetrahedral_evaluations, strict=True
        ):
            self.assertEqual(trilinear_item, tetrahedral_item)
            self.assertEqual(
                trilinear_item["expected"],
                _affine_oracle(trilinear_item["input"], samples),
            )
            evaluation_ids.add(trilinear_item["id"])
        self.assertEqual(len(evaluation_ids), EVALUATION_COUNT)

        node_inputs = set(itertools.product((0.0, 0.5, 1.0), repeat=3))
        node_items = [
            item for item in trilinear_evaluations if item["id"].startswith("node-")
        ]
        self.assertEqual(len(node_items), 27)
        self.assertEqual(
            {tuple(item["input"]) for item in node_items}, node_inputs
        )

        geometry_counts = {"corner": 0, "edge": 0, "face": 0, "center": 0}
        for item in node_items:
            endpoint_count = sum(value in {0.0, 1.0} for value in item["input"])
            category = {3: "corner", 2: "edge", 1: "face", 0: "center"}[
                endpoint_count
            ]
            geometry_counts[category] += 1
            red_index = int(item["id"].split("-r", 1)[1][0])
            green_index = int(item["id"].split("-g", 1)[1][0])
            blue_index = int(item["id"].split("-b", 1)[1][0])
            sample_index = red_index + 3 * green_index + 9 * blue_index
            self.assertEqual(item["expected"], list(samples[sample_index]))
        self.assertEqual(
            geometry_counts,
            {"corner": 8, "edge": 12, "face": 6, "center": 1},
        )

        edge_items = [
            item for item in trilinear_evaluations if item["id"].startswith("edge-")
        ]
        face_items = [
            item for item in trilinear_evaluations if item["id"].startswith("face-")
        ]
        cell_center_items = [
            item
            for item in trilinear_evaluations
            if item["id"].startswith("cell-center-")
        ]
        decimal_probes = [
            item
            for item in trilinear_evaluations
            if item["id"].startswith("probe-decimal-")
        ]
        dyadic_probes = [
            item
            for item in trilinear_evaluations
            if item["id"].startswith("probe-dyadic-")
        ]
        self.assertEqual(len(edge_items), 12)
        self.assertTrue(
            all(
                sum(value in {0.0, 1.0} for value in item["input"]) == 2
                for item in edge_items
            )
        )
        actual_edge_signatures = set()
        for item in edge_items:
            varying_axis = next(
                index
                for index, value in enumerate(item["input"])
                if value not in {0.0, 1.0}
            )
            fixed_values = tuple(
                value
                for index, value in enumerate(item["input"])
                if index != varying_axis
            )
            actual_edge_signatures.add((varying_axis, fixed_values))
        self.assertEqual(
            actual_edge_signatures,
            {
                (varying_axis, fixed_values)
                for varying_axis in range(3)
                for fixed_values in itertools.product((0.0, 1.0), repeat=2)
            },
        )
        self.assertEqual(len(face_items), 6)
        self.assertTrue(
            all(
                sum(value in {0.0, 1.0} for value in item["input"]) == 1
                for item in face_items
            )
        )
        actual_face_signatures = set()
        for item in face_items:
            fixed_axis = next(
                index
                for index, value in enumerate(item["input"])
                if value in {0.0, 1.0}
            )
            actual_face_signatures.add((fixed_axis, item["input"][fixed_axis]))
        self.assertEqual(
            actual_face_signatures,
            set(itertools.product(range(3), (0.0, 1.0))),
        )
        self.assertEqual(len(cell_center_items), 8)
        self.assertEqual(
            {tuple(item["input"]) for item in cell_center_items},
            set(itertools.product((0.25, 0.75), repeat=3)),
        )
        self.assertEqual(len(decimal_probes), 3)
        self.assertEqual(len(dyadic_probes), 11)
        self.assertGreater(
            max(
                abs(_binary32(value) - value)
                for item in decimal_probes
                for value in item["expected"]
            ),
            2**-30,
        )


if __name__ == "__main__":
    unittest.main()
