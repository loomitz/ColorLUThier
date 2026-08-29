from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from acceptance_support import (
    REPOSITORY_ROOT,
    assert_deterministic_success,
    deterministic_json_bytes,
    run_harness,
)


FIXTURE_DIRECTORY = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "interpolation-divergence-2"
)


def _descriptor(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIRECTORY / name).read_bytes())


class InterpolationDivergenceAcceptanceTest(unittest.TestCase):
    def test_both_interpolations_complete_the_public_round_trip(self) -> None:
        trilinear = assert_deterministic_success(
            self,
            FIXTURE_DIRECTORY,
            descriptor_name="trilinear.case.json",
            expected_report_name="trilinear.expected.report.json",
        )
        tetrahedral = assert_deterministic_success(
            self,
            FIXTURE_DIRECTORY,
            descriptor_name="tetrahedral.case.json",
            expected_report_name="tetrahedral.expected.report.json",
        )

        self.assertEqual(trilinear.input_cube, tetrahedral.input_cube)
        self.assertEqual(trilinear.canonical_cube, tetrahedral.canonical_cube)
        self.assertEqual(trilinear.report["interpolation"], "trilinear")
        self.assertEqual(tetrahedral.report["interpolation"], "tetrahedral")
        self.assertEqual(trilinear.report["evaluation_count"], 19)
        self.assertEqual(tetrahedral.report["evaluation_count"], 19)

    def test_static_goldens_cover_regions_and_boundaries_independently(self) -> None:
        trilinear = _descriptor("trilinear.case.json")
        tetrahedral = _descriptor("tetrahedral.case.json")

        self.assertEqual(trilinear["cube"], tetrahedral["cube"])
        self.assertEqual(trilinear["gates"], tetrahedral["gates"])
        self.assertEqual(trilinear["interpolation"], "trilinear")
        self.assertEqual(tetrahedral["interpolation"], "tetrahedral")

        trilinear_evaluations = trilinear["evaluations"]
        tetrahedral_evaluations = tetrahedral["evaluations"]
        self.assertEqual(len(trilinear_evaluations), 19)
        self.assertEqual(len(tetrahedral_evaluations), 19)

        strict_regions: set[str] = set()
        boundary_ids: set[str] = set()
        for trilinear_item, tetrahedral_item in zip(
            trilinear_evaluations, tetrahedral_evaluations, strict=True
        ):
            self.assertEqual(trilinear_item["id"], tetrahedral_item["id"])
            self.assertEqual(trilinear_item["input"], tetrahedral_item["input"])
            self.assertNotEqual(
                trilinear_item["expected"], tetrahedral_item["expected"]
            )

            red, green, blue = trilinear_item["input"]
            self.assertEqual(
                trilinear_item["expected"],
                [red * green, red * blue, green * blue],
            )
            self.assertEqual(
                tetrahedral_item["expected"],
                [min(red, green), min(red, blue), min(green, blue)],
            )

            identifier = trilinear_item["id"]
            if identifier.endswith("-side"):
                channels = {"r": red, "g": green, "b": blue}
                strict_regions.add(
                    "".join(
                        channel
                        for channel, _ in sorted(
                            channels.items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )
                    )
                )
            if identifier.endswith("-boundary"):
                boundary_ids.add(identifier)

        self.assertEqual(
            strict_regions,
            {"rgb", "rbg", "brg", "bgr", "gbr", "grb"},
        )
        self.assertEqual(
            boundary_ids,
            {
                "rg-high-boundary",
                "rb-high-boundary",
                "gb-high-boundary",
                "rg-low-boundary",
                "rb-low-boundary",
                "gb-low-boundary",
            },
        )
        evaluations_by_id = {
            evaluation["id"]: evaluation
            for evaluation in trilinear_evaluations
        }
        channel_index = {"r": 0, "g": 1, "b": 2}
        for family in (
            "rg-high",
            "rb-high",
            "gb-high",
            "rg-low",
            "rb-low",
            "gb-low",
        ):
            pair = family[:2]
            first_channel, second_channel = pair
            first_index = channel_index[first_channel]
            second_index = channel_index[second_channel]
            boundary = evaluations_by_id[f"{family}-boundary"]["input"]
            first_side = evaluations_by_id[
                f"{family}-{first_channel}-side"
            ]["input"]
            second_side = evaluations_by_id[
                f"{family}-{second_channel}-side"
            ]["input"]

            self.assertEqual(boundary[first_index], boundary[second_index])
            self.assertEqual(
                first_side[first_index] - boundary[first_index], 1 / 64
            )
            self.assertEqual(
                second_side[first_index] - boundary[first_index], -1 / 64
            )
            self.assertGreater(
                first_side[first_index], first_side[second_index]
            )
            self.assertLess(
                second_side[first_index], second_side[second_index]
            )
        self.assertEqual(
            trilinear_evaluations[-1]["input"], [0.5, 0.5, 0.5]
        )

    def test_switching_only_the_interpolation_fails_observably(self) -> None:
        cases = (
            ("trilinear.case.json", "tetrahedral"),
            ("tetrahedral.case.json", "trilinear"),
        )
        for descriptor_name, replacement in cases:
            with self.subTest(descriptor=descriptor_name, replacement=replacement):
                descriptor = _descriptor(descriptor_name)
                descriptor["interpolation"] = replacement

                with tempfile.TemporaryDirectory() as temp:
                    temporary_directory = Path(temp)
                    descriptor_path = temporary_directory / "mutated.case.json"
                    descriptor_path.write_bytes(
                        deterministic_json_bytes(descriptor)
                    )
                    output_directory = temporary_directory / "artifacts"
                    result = run_harness(
                        descriptor=descriptor_path,
                        cube=FIXTURE_DIRECTORY / "input.cube",
                        output_directory=output_directory,
                    )

                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr, b"")
                    report_bytes = (output_directory / "report.json").read_bytes()
                    self.assertEqual(result.stdout, report_bytes)
                    self.assertTrue((output_directory / "canonical.cube").is_file())
                    report = json.loads(report_bytes)
                    self.assertEqual(report["overall_result"], "fail")
                    self.assertEqual(report["interpolation"], replacement)
                    self.assertGreater(
                        report["metrics"]["input_evaluation"][
                            "maximum_absolute_error"
                        ],
                        0.0,
                    )
                    self.assertFalse(
                        report["round_trip"]["canonical_reevaluation_passed"]
                    )

    def test_interpolation_diagnostics_are_stable_and_create_no_artifacts(
        self,
    ) -> None:
        cases = (
            (
                "missing",
                None,
                "INTERPOLATION_REQUIRED",
                "Descriptor field 'interpolation' is required.",
            ),
            (
                "unsupported",
                "nearest",
                "INTERPOLATION_UNSUPPORTED",
                "Descriptor field 'interpolation' must select 'trilinear' or "
                "'tetrahedral'.",
            ),
        )
        for name, selection, code, message in cases:
            with self.subTest(name=name):
                descriptor = _descriptor("trilinear.case.json")
                if selection is None:
                    del descriptor["interpolation"]
                else:
                    descriptor["interpolation"] = selection

                with tempfile.TemporaryDirectory() as temp:
                    temporary_directory = Path(temp)
                    descriptor_path = temporary_directory / f"{name}.case.json"
                    descriptor_path.write_bytes(
                        deterministic_json_bytes(descriptor)
                    )
                    output_directory = temporary_directory / "artifacts"
                    result = run_harness(
                        descriptor=descriptor_path,
                        cube=FIXTURE_DIRECTORY / "input.cube",
                        output_directory=output_directory,
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")
                    self.assertEqual(
                        result.stderr,
                        deterministic_json_bytes(
                            {
                                "error": {"code": code, "message": message},
                                "evidence_status": "provisional",
                                "report_schema_version": 1,
                            }
                        ),
                    )
                    self.assertFalse(output_directory.exists())


if __name__ == "__main__":
    unittest.main()
