from __future__ import annotations

import hashlib
import json
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "identity-2"


def _sample_bits(cube_bytes: bytes) -> list[tuple[bytes, bytes, bytes]]:
    text = cube_bytes.decode("ascii")
    rows = [
        line.split()
        for line in text.splitlines()
        if line and not line.startswith("#") and not line.startswith("LUT_3D_SIZE")
    ]
    return [
        tuple(struct.pack(">f", float(token)) for token in row)  # type: ignore[misc]
        for row in rows
    ]


class IdentityRoundTripAcceptanceTest(unittest.TestCase):
    def _run(self, output_directory: Path) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "portable_cube_harness",
                "--descriptor",
                str(FIXTURE_DIRECTORY / "case.json"),
                "--cube",
                str(FIXTURE_DIRECTORY / "input.cube"),
                "--output-dir",
                str(output_directory),
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
        )

    def test_identity_round_trip_through_public_command(self) -> None:
        input_cube = (FIXTURE_DIRECTORY / "input.cube").read_bytes()
        expected_cube = (FIXTURE_DIRECTORY / "expected.canonical.cube").read_bytes()
        expected_report = (FIXTURE_DIRECTORY / "expected.report.json").read_bytes()

        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            first_output = Path(first_temp) / "artifacts"
            second_output = Path(second_temp) / "different-artifacts"
            first = self._run(first_output)
            second = self._run(second_output)

            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)
            self.assertEqual(first.stderr, b"")
            self.assertEqual(second.stderr, b"")

            first_cube = (first_output / "canonical.cube").read_bytes()
            second_cube = (second_output / "canonical.cube").read_bytes()
            first_report = (first_output / "report.json").read_bytes()
            second_report = (second_output / "report.json").read_bytes()

            self.assertEqual(first.stdout, first_report)
            self.assertEqual(first_cube, expected_cube)
            self.assertEqual(first_report, expected_report)
            self.assertEqual(second.stdout, first.stdout)
            self.assertEqual(second_cube, first_cube)
            self.assertEqual(second_report, first_report)

            first_cube.decode("ascii")
            self.assertNotIn(b"\r", first_cube)
            self.assertTrue(first_cube.endswith(b"\n"))
            self.assertEqual(_sample_bits(input_cube), _sample_bits(first_cube))

            report = json.loads(first_report)
            self.assertEqual(report["report_schema_version"], 1)
            self.assertEqual(report["harness_version"], "0.1.0")
            self.assertEqual(report["case_id"], "identity-2-trilinear")
            self.assertEqual(report["interpolation"], "trilinear")
            self.assertEqual(report["lattice_size"], 2)
            self.assertEqual(report["sample_count"], 8)
            self.assertEqual(report["evaluation_count"], 9)
            self.assertEqual(report["overall_result"], "pass")
            self.assertEqual(
                report["evidence"],
                {
                    "compatibility_claims": [],
                    "host_validation": "not_performed",
                    "status": "provisional",
                },
            )
            self.assertEqual(
                report["hashes"]["input_cube_sha256"],
                hashlib.sha256(input_cube).hexdigest(),
            )
            self.assertEqual(
                report["hashes"]["canonical_cube_sha256"],
                hashlib.sha256(first_cube).hexdigest(),
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
            self.assertTrue(
                report["round_trip"]["canonical_reevaluation_passed"]
            )
            for evaluation_metrics in report["metrics"].values():
                self.assertEqual(
                    evaluation_metrics,
                    {
                        "maximum_absolute_error": 0.0,
                        "maximum_clf_normalized_error": 0.0,
                        "mean_absolute_error": 0.0,
                        "p99_absolute_error": 0.0,
                    },
                )

            report_text = first_report.decode("ascii")
            self.assertNotIn(str(first_output), report_text)
            self.assertNotIn(str(second_output), report_text)
            self.assertNotIn(socket.gethostname(), report_text)
            self.assertNotIn("Photoshop", report_text)
            self.assertNotIn("Resolve", report_text)
            self.assertNotIn("timestamp", report_text.lower())


if __name__ == "__main__":
    unittest.main()
