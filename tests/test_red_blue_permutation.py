from __future__ import annotations

import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path

from acceptance_support import (
    REPOSITORY_ROOT,
    assert_deterministic_success,
    cube_sample_bits,
    run_harness,
)


FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "red-blue-swap-2"


class RedBluePermutationAcceptanceTest(unittest.TestCase):
    def test_red_fastest_swap_round_trip_through_public_command(self) -> None:
        run = assert_deterministic_success(self, FIXTURE_DIRECTORY)
        expected_red_fastest_samples = [
            tuple(
                struct.pack(">f", float(component))
                for component in (blue, green, red)
            )
            for blue in (0, 1)
            for green in (0, 1)
            for red in (0, 1)
        ]
        self.assertEqual(
            cube_sample_bits(run.input_cube), expected_red_fastest_samples
        )

        report = run.report
        self.assertEqual(report["case_id"], "red-blue-swap-2-trilinear")
        self.assertEqual(report["evaluation_count"], 17)

        descriptor = json.loads((FIXTURE_DIRECTORY / "case.json").read_bytes())
        self.assertEqual(
            {evaluation["id"] for evaluation in descriptor["evaluations"]},
            {
                "node-000",
                "node-100",
                "node-010",
                "node-110",
                "node-001",
                "node-101",
                "node-011",
                "node-111",
                "primary-red-quarter",
                "primary-green-half",
                "primary-blue-three-quarter",
                "secondary-yellow",
                "secondary-cyan",
                "secondary-magenta",
                "neutral-quarter",
                "neutral-half",
                "neutral-three-quarter",
            },
        )
        self.assertTrue(
            all(
                set(evaluation) == {"id", "input", "expected"}
                for evaluation in descriptor["evaluations"]
            )
        )
        for evaluation in descriptor["evaluations"]:
            red, green, blue = evaluation["input"]
            self.assertEqual(evaluation["expected"], [blue, green, red])

    def test_blue_fastest_mutant_fails_observably(self) -> None:
        mutant_cube = (FIXTURE_DIRECTORY / "blue-fastest-mutant.cube").read_bytes()
        descriptor = json.loads((FIXTURE_DIRECTORY / "case.json").read_bytes())
        descriptor["cube"]["sha256"] = hashlib.sha256(mutant_cube).hexdigest()

        with tempfile.TemporaryDirectory() as temp:
            temporary_directory = Path(temp)
            descriptor_path = temporary_directory / "mutant-case.json"
            descriptor_path.write_bytes(
                (json.dumps(descriptor, sort_keys=True) + "\n").encode("ascii")
            )
            output_directory = temporary_directory / "artifacts"
            result = run_harness(
                descriptor=descriptor_path,
                cube=FIXTURE_DIRECTORY / "blue-fastest-mutant.cube",
                output_directory=output_directory,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, b"")
            report_bytes = (output_directory / "report.json").read_bytes()
            self.assertEqual(result.stdout, report_bytes)
            report = json.loads(report_bytes)
            self.assertEqual(report["overall_result"], "fail")
            self.assertEqual(report["validation"], {"errors": [], "result": "pass"})
            for evaluation_metrics in report["metrics"].values():
                self.assertEqual(
                    evaluation_metrics,
                    {
                        "maximum_absolute_error": 1.0,
                        "maximum_clf_normalized_error": 10.0,
                        "mean_absolute_error": 13 / 51,
                        "p99_absolute_error": 1.0,
                    },
                )
            self.assertTrue(
                report["round_trip"][
                    "input_node_evaluation_binary32_identical"
                ]
            )
            self.assertTrue(
                report["round_trip"][
                    "canonical_node_evaluation_binary32_identical"
                ]
            )
            self.assertTrue(
                report["round_trip"]["serialization_binary32_identical"]
            )
            self.assertFalse(
                report["round_trip"]["canonical_reevaluation_passed"]
            )


if __name__ == "__main__":
    unittest.main()
