from __future__ import annotations

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SuccessfulConformanceRun:
    input_cube: bytes
    canonical_cube: bytes
    report_bytes: bytes
    report: dict[str, Any]
    first_output_directory: str
    second_output_directory: str


def run_harness(
    *, descriptor: Path, cube: Path, output_directory: Path
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "portable_cube_harness",
            "--descriptor",
            str(descriptor),
            "--cube",
            str(cube),
            "--output-dir",
            str(output_directory),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
    )


def cube_sample_bits(cube_bytes: bytes) -> list[tuple[bytes, bytes, bytes]]:
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


def assert_deterministic_success(
    test: unittest.TestCase, fixture_directory: Path
) -> SuccessfulConformanceRun:
    descriptor_path = fixture_directory / "case.json"
    cube_path = fixture_directory / "input.cube"
    input_cube = cube_path.read_bytes()
    expected_cube = (fixture_directory / "expected.canonical.cube").read_bytes()
    expected_report = (fixture_directory / "expected.report.json").read_bytes()

    with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
        first_output = Path(first_temp) / "artifacts"
        second_output = Path(second_temp) / "different-artifacts"
        first = run_harness(
            descriptor=descriptor_path,
            cube=cube_path,
            output_directory=first_output,
        )
        second = run_harness(
            descriptor=descriptor_path,
            cube=cube_path,
            output_directory=second_output,
        )

        test.assertEqual(first.returncode, 0)
        test.assertEqual(second.returncode, 0)
        test.assertEqual(first.stderr, b"")
        test.assertEqual(second.stderr, b"")

        first_cube = (first_output / "canonical.cube").read_bytes()
        second_cube = (second_output / "canonical.cube").read_bytes()
        first_report = (first_output / "report.json").read_bytes()
        second_report = (second_output / "report.json").read_bytes()

        test.assertEqual(first.stdout, first_report)
        test.assertEqual(first_cube, expected_cube)
        test.assertEqual(first_report, expected_report)
        test.assertEqual(second.stdout, first.stdout)
        test.assertEqual(second_cube, first_cube)
        test.assertEqual(second_report, first_report)
        test.assertEqual(cube_sample_bits(input_cube), cube_sample_bits(first_cube))

        report = json.loads(first_report)
        test.assertEqual(report["report_schema_version"], 1)
        test.assertEqual(report["harness_version"], "0.1.0")
        test.assertEqual(report["overall_result"], "pass")
        test.assertEqual(
            report["evidence"],
            {
                "compatibility_claims": [],
                "host_validation": "not_performed",
                "status": "provisional",
            },
        )
        test.assertEqual(
            report["hashes"]["input_cube_sha256"],
            hashlib.sha256(input_cube).hexdigest(),
        )
        test.assertEqual(
            report["hashes"]["canonical_cube_sha256"],
            hashlib.sha256(first_cube).hexdigest(),
        )
        test.assertTrue(
            report["round_trip"]["input_node_evaluation_binary32_identical"]
        )
        test.assertTrue(
            report["round_trip"]["canonical_node_evaluation_binary32_identical"]
        )
        test.assertTrue(report["round_trip"]["serialization_binary32_identical"])
        test.assertTrue(report["round_trip"]["canonical_reevaluation_passed"])
        for evaluation_metrics in report["metrics"].values():
            test.assertEqual(
                evaluation_metrics,
                {
                    "maximum_absolute_error": 0.0,
                    "maximum_clf_normalized_error": 0.0,
                    "mean_absolute_error": 0.0,
                    "p99_absolute_error": 0.0,
                },
            )

        return SuccessfulConformanceRun(
            input_cube=input_cube,
            canonical_cube=first_cube,
            report_bytes=first_report,
            report=report,
            first_output_directory=str(first_output),
            second_output_directory=str(second_output),
        )
