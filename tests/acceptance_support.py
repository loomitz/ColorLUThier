from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import struct
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HARNESS_VERSION = "0.6.0"
PROVISIONAL_EVIDENCE = {
    "compatibility_claims": [],
    "host_validation": "not_performed",
    "status": "provisional",
}
METRIC_FIELDS = {
    "maximum_absolute_error",
    "maximum_clf_normalized_error",
    "mean_absolute_error",
    "p99_absolute_error",
}
TIMESTAMP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"
)
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)


@dataclass(frozen=True)
class SuccessfulConformanceRun:
    input_cube: bytes
    canonical_cube: bytes
    report_bytes: bytes
    report: dict[str, Any]
    first_output_directory: str
    second_output_directory: str


def run_harness(
    *,
    descriptor: Path,
    cube: Path,
    output_directory: Path,
    environment: Mapping[str, str] | None = None,
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
        env=environment,
    )


def run_corpus_materializer(
    *,
    output_directory: Path,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "tests" / "materialize_portable_cube_corpus.py"),
            "--output-dir",
            str(output_directory),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        env=environment,
    )


def deterministic_json_bytes(value: object) -> bytes:
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


def assert_deterministic_json_document(
    test: unittest.TestCase,
    raw: bytes,
) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(raw)
    test.assertIsInstance(document, dict)
    test.assertEqual(raw, deterministic_json_bytes(document))
    return document


def assert_deterministic_invalid_command(
    test: unittest.TestCase,
    *,
    expected_code: str,
    descriptor: Path | None = None,
    descriptor_bytes: bytes | None = None,
    cube: Path | None = None,
    cube_bytes: bytes | None = None,
    expected_reason: str | None = None,
    expected_context: dict[str, object] | None = None,
    prepare_output: Callable[[Path], None] | None = None,
    assert_output: Callable[[unittest.TestCase, Path], None] | None = None,
) -> dict[str, Any]:
    if (descriptor is None) == (descriptor_bytes is None):
        raise ValueError("Provide exactly one descriptor path or descriptor byte string")
    if (cube is None) == (cube_bytes is None):
        raise ValueError("Provide exactly one Cube path or Cube byte string")

    results: list[subprocess.CompletedProcess[bytes]] = []
    output_directories: list[Path] = []
    temporary_roots: list[Path] = []
    with (
        tempfile.TemporaryDirectory() as first_temp,
        tempfile.TemporaryDirectory() as second_temp,
    ):
        for run_index, temporary_path in enumerate((first_temp, second_temp)):
            temporary_root = Path(temporary_path)
            descriptor_path = descriptor
            if descriptor_bytes is not None:
                descriptor_path = temporary_root / f"descriptor-{run_index}.case.json"
                descriptor_path.write_bytes(descriptor_bytes)
            cube_path = cube
            if cube_bytes is not None:
                cube_path = temporary_root / f"input-{run_index}.cube"
                cube_path.write_bytes(cube_bytes)
            if descriptor_path is None or cube_path is None:
                raise AssertionError("Invalid-command fixture materialization failed")

            output_directory = temporary_root / f"artifacts-{run_index}"
            if prepare_output is not None:
                prepare_output(output_directory)
            else:
                test.assertFalse(output_directory.exists())

            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = str(101 + run_index * 808)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            results.append(
                run_harness(
                    descriptor=descriptor_path,
                    cube=cube_path,
                    output_directory=output_directory,
                    environment=environment,
                )
            )
            output_directories.append(output_directory)
            temporary_roots.append(temporary_root)

        payloads: list[dict[str, Any]] = []
        for result, output_directory, temporary_root in zip(
            results,
            output_directories,
            temporary_roots,
            strict=True,
        ):
            test.assertEqual(result.returncode, 2)
            test.assertEqual(result.stdout, b"")
            if assert_output is None:
                test.assertFalse(output_directory.exists())
                test.assertFalse((output_directory / "canonical.cube").exists())
                test.assertFalse((output_directory / "report.json").exists())
            else:
                assert_output(test, output_directory)

            stderr_text = result.stderr.decode("ascii")
            test.assertNotIn(str(temporary_root), stderr_text)
            test.assertNotIn(str(REPOSITORY_ROOT), stderr_text)
            test.assertNotIn(socket.gethostname(), stderr_text)
            test.assertIsNone(TIMESTAMP_PATTERN.search(stderr_text))
            test.assertIsNone(UUID_PATTERN.search(stderr_text))
            test.assertNotIn("Traceback", stderr_text)
            test.assertLessEqual(len(result.stderr), 4096)

            payload = assert_deterministic_json_document(test, result.stderr)
            test.assertEqual(
                set(payload),
                {"error", "evidence_status", "report_schema_version"},
            )
            test.assertEqual(payload["evidence_status"], "provisional")
            test.assertEqual(payload["report_schema_version"], 1)

            error = payload["error"]
            test.assertIsInstance(error, dict)
            test.assertEqual(error["code"], expected_code)
            test.assertIsInstance(error["message"], str)
            test.assertTrue(error["message"])
            test.assertLessEqual(len(error["message"]), 512)
            error["message"].encode("ascii")
            if expected_reason is not None or expected_context is not None:
                test.assertEqual(
                    set(error), {"code", "context", "message", "reason"}
                )
                test.assertEqual(error["reason"], expected_reason)
                test.assertEqual(error["context"], expected_context)
            else:
                if "reason" in error:
                    test.assertIsInstance(error["reason"], str)
                    test.assertTrue(error["reason"])
                if "context" in error:
                    test.assertIsInstance(error["context"], dict)
            payloads.append(payload)

        test.assertEqual(results[0].stderr, results[1].stderr)
        test.assertEqual(payloads[0], payloads[1])
        return payloads[0]


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
    test: unittest.TestCase,
    fixture_directory: Path,
    *,
    descriptor_name: str = "case.json",
    expected_report_name: str | None = "expected.report.json",
    require_zero_metrics: bool = True,
) -> SuccessfulConformanceRun:
    descriptor_path = fixture_directory / descriptor_name
    cube_path = fixture_directory / "input.cube"
    input_cube = cube_path.read_bytes()
    expected_cube = (fixture_directory / "expected.canonical.cube").read_bytes()
    expected_report = (
        (fixture_directory / expected_report_name).read_bytes()
        if expected_report_name is not None
        else None
    )

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

        test.assertEqual(
            sorted(path.name for path in first_output.iterdir()),
            ["canonical.cube", "report.json"],
        )
        test.assertEqual(
            sorted(path.name for path in second_output.iterdir()),
            ["canonical.cube", "report.json"],
        )
        test.assertEqual(first.stdout, first_report)
        test.assertEqual(first_cube, expected_cube)
        if expected_report is not None:
            test.assertEqual(first_report, expected_report)
        test.assertEqual(second.stdout, first.stdout)
        test.assertEqual(second_cube, first_cube)
        test.assertEqual(second_report, first_report)
        test.assertEqual(cube_sample_bits(input_cube), cube_sample_bits(first_cube))

        report = json.loads(first_report)
        test.assertEqual(report["report_schema_version"], 1)
        test.assertEqual(report["harness_version"], HARNESS_VERSION)
        test.assertEqual(report["overall_result"], "pass")
        test.assertEqual(
            report["evidence"],
            PROVISIONAL_EVIDENCE,
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
            test.assertEqual(set(evaluation_metrics), METRIC_FIELDS)
            test.assertTrue(
                all(math.isfinite(value) for value in evaluation_metrics.values())
            )
            if require_zero_metrics:
                test.assertEqual(
                    evaluation_metrics,
                    {field: 0.0 for field in METRIC_FIELDS},
                )

        return SuccessfulConformanceRun(
            input_cube=input_cube,
            canonical_cube=first_cube,
            report_bytes=first_report,
            report=report,
            first_output_directory=str(first_output),
            second_output_directory=str(second_output),
        )
