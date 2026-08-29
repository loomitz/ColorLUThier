from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from acceptance_support import (
    REPOSITORY_ROOT,
    assert_deterministic_invalid_command,
    deterministic_json_bytes,
    run_harness,
)


FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "identity-2"
DESCRIPTOR_PATH = FIXTURE_DIRECTORY / "case.json"
CUBE_PATH = FIXTURE_DIRECTORY / "input.cube"
RAW_NUMBER_SENTINEL = "descriptor-raw-number-sentinel"


@dataclass(frozen=True)
class InvalidDescriptorCase:
    name: str
    descriptor_bytes: bytes
    code: str


def _base_descriptor() -> dict[str, Any]:
    return json.loads(DESCRIPTOR_PATH.read_bytes())


def _container_at(root: object, path: tuple[str | int, ...]) -> object:
    current = root
    for component in path:
        if isinstance(component, int):
            if not isinstance(current, list):
                raise AssertionError(f"Expected list before path component {component!r}")
            current = current[component]
        else:
            if not isinstance(current, dict):
                raise AssertionError(f"Expected object before path component {component!r}")
            current = current[component]
    return current


def _descriptor_with(path: tuple[str | int, ...], value: object) -> bytes:
    descriptor = copy.deepcopy(_base_descriptor())
    parent = _container_at(descriptor, path[:-1])
    field = path[-1]
    if isinstance(field, int):
        if not isinstance(parent, list):
            raise AssertionError("Descriptor mutation expected a list")
        parent[field] = value
    else:
        if not isinstance(parent, dict):
            raise AssertionError("Descriptor mutation expected an object")
        parent[field] = value
    return deterministic_json_bytes(descriptor)


def _descriptor_without(path: tuple[str | int, ...]) -> bytes:
    descriptor = copy.deepcopy(_base_descriptor())
    parent = _container_at(descriptor, path[:-1])
    field = path[-1]
    if isinstance(field, int):
        if not isinstance(parent, list):
            raise AssertionError("Descriptor mutation expected a list")
        del parent[field]
    else:
        if not isinstance(parent, dict):
            raise AssertionError("Descriptor mutation expected an object")
        del parent[field]
    return deterministic_json_bytes(descriptor)


def _descriptor_with_raw_number(
    path: tuple[str | int, ...], token: str
) -> bytes:
    encoded = _descriptor_with(path, RAW_NUMBER_SENTINEL)
    quoted_sentinel = json.dumps(RAW_NUMBER_SENTINEL).encode("ascii")
    if encoded.count(quoted_sentinel) != 1:
        raise AssertionError("Raw-number sentinel must occur exactly once")
    return encoded.replace(quoted_sentinel, token.encode("ascii"), 1)


def _descriptor_with_duplicate_case_id() -> bytes:
    encoded = deterministic_json_bytes(_base_descriptor())
    original = b'  "case_id": "identity-2-trilinear",\n'
    replacement = (
        b'  "case_id": "duplicate-field-must-be-rejected",\n' + original
    )
    if encoded.count(original) != 1:
        raise AssertionError("Identity descriptor case_id layout changed")
    return encoded.replace(original, replacement, 1)


def _prepare_blocked_report_target(output_directory: Path) -> None:
    output_directory.mkdir()
    (output_directory / "report.json").mkdir()


def _assert_blocked_report_target(
    test: unittest.TestCase, output_directory: Path
) -> None:
    test.assertTrue(output_directory.is_dir())
    test.assertFalse((output_directory / "canonical.cube").exists())
    test.assertTrue((output_directory / "report.json").is_dir())
    test.assertFalse((output_directory / "report.json").is_file())
    test.assertEqual(
        sorted(path.name for path in output_directory.iterdir()),
        ["report.json"],
    )


class DescriptorDiagnosticsAcceptanceTest(unittest.TestCase):
    def _assert_deterministic_rejection(
        self, case: InvalidDescriptorCase
    ) -> None:
        assert_deterministic_invalid_command(
            self,
            descriptor_bytes=case.descriptor_bytes,
            cube=CUBE_PATH,
            expected_code=case.code,
        )

    def test_malformed_descriptor_envelopes_are_rejected(self) -> None:
        cases = (
            InvalidDescriptorCase(
                name="invalid-utf8",
                descriptor_bytes=b'{"test_case_schema_version":1,"case_id":"\xff"}\n',
                code="DESCRIPTOR_ENCODING_INVALID",
            ),
            InvalidDescriptorCase(
                name="truncated-json",
                descriptor_bytes=b'{"test_case_schema_version": 1',
                code="DESCRIPTOR_JSON_INVALID",
            ),
            InvalidDescriptorCase(
                name="duplicate-json-field",
                descriptor_bytes=_descriptor_with_duplicate_case_id(),
                code="DESCRIPTOR_JSON_INVALID",
            ),
            InvalidDescriptorCase(
                name="root-is-not-an-object",
                descriptor_bytes=b"[]\n",
                code="DESCRIPTOR_SCHEMA_INVALID",
            ),
        )

        for case in cases:
            with self.subTest(case=case.name):
                self._assert_deterministic_rejection(case)

    def test_required_fields_are_rejected_when_missing(self) -> None:
        required_paths_and_codes = (
            (("test_case_schema_version",), "DESCRIPTOR_SCHEMA_INVALID"),
            (("case_id",), "DESCRIPTOR_SCHEMA_INVALID"),
            (("cube",), "DESCRIPTOR_SCHEMA_INVALID"),
            (("cube", "sha256"), "DESCRIPTOR_SCHEMA_INVALID"),
            (("interpolation",), "INTERPOLATION_REQUIRED"),
            (("oracle",), "DESCRIPTOR_SCHEMA_INVALID"),
            (("oracle", "kind"), "DESCRIPTOR_SCHEMA_INVALID"),
            (("oracle", "provenance"), "DESCRIPTOR_SCHEMA_INVALID"),
            (("evaluations",), "DESCRIPTOR_SCHEMA_INVALID"),
            (("evaluations", 0, "id"), "DESCRIPTOR_SCHEMA_INVALID"),
            (("evaluations", 0, "input"), "EVALUATION_INPUT_INVALID"),
            (("evaluations", 0, "expected"), "DESCRIPTOR_SCHEMA_INVALID"),
            (("gates",), "DESCRIPTOR_SCHEMA_INVALID"),
            (("gates", "maximum_absolute_error"), "DESCRIPTOR_SCHEMA_INVALID"),
            (("gates", "require_finite_outputs"), "DESCRIPTOR_SCHEMA_INVALID"),
            (
                ("gates", "require_node_binary32_identity"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            (
                ("gates", "require_serialization_binary32_identity"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
        )

        for path, code in required_paths_and_codes:
            name = "missing-" + "-".join(str(component) for component in path)
            with self.subTest(case=name):
                self._assert_deterministic_rejection(
                    InvalidDescriptorCase(
                        name=name,
                        descriptor_bytes=_descriptor_without(path),
                        code=code,
                    )
                )

    def test_schema_types_identifiers_oracle_and_gates_are_rejected(self) -> None:
        descriptor = _base_descriptor()
        duplicate_evaluation_id = descriptor["evaluations"][0]["id"]
        cases = (
            InvalidDescriptorCase(
                "schema-version-boolean",
                _descriptor_with(("test_case_schema_version",), True),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "schema-version-float",
                _descriptor_with(("test_case_schema_version",), 1.0),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "schema-version-string",
                _descriptor_with(("test_case_schema_version",), "1"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "schema-version-unsupported",
                _descriptor_with(("test_case_schema_version",), 2),
                "DESCRIPTOR_SCHEMA_UNSUPPORTED",
            ),
            InvalidDescriptorCase(
                "case-id-wrong-type",
                _descriptor_with(("case_id",), 1),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "case-id-invalid-format",
                _descriptor_with(("case_id",), "Invalid Case ID"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "cube-metadata-wrong-type",
                _descriptor_with(("cube",), []),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "checksum-wrong-type",
                _descriptor_with(("cube", "sha256"), 1),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "checksum-invalid-format",
                _descriptor_with(("cube", "sha256"), "0" * 63),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "interpolation-wrong-type",
                _descriptor_with(("interpolation",), 1),
                "INTERPOLATION_UNSUPPORTED",
            ),
            InvalidDescriptorCase(
                "oracle-wrong-type",
                _descriptor_with(("oracle",), []),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "oracle-kind-unsupported",
                _descriptor_with(("oracle", "kind"), "harness_evaluator"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "oracle-provenance-empty",
                _descriptor_with(("oracle", "provenance"), "   "),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "evaluations-wrong-type",
                _descriptor_with(("evaluations",), {}),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "evaluations-empty",
                _descriptor_with(("evaluations",), []),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "evaluation-item-wrong-type",
                _descriptor_with(("evaluations", 0), []),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "evaluation-id-wrong-type",
                _descriptor_with(("evaluations", 0, "id"), 1),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "evaluation-id-invalid-format",
                _descriptor_with(("evaluations", 0, "id"), "Invalid ID"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "evaluation-id-duplicate",
                _descriptor_with(
                    ("evaluations", 1, "id"), duplicate_evaluation_id
                ),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "expected-vector-wrong-type",
                _descriptor_with(("evaluations", 0, "expected"), "0 0 0"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "expected-vector-wrong-length",
                _descriptor_with(("evaluations", 0, "expected"), [0, 0]),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "expected-component-wrong-type",
                _descriptor_with(("evaluations", 0, "expected", 0), True),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "expected-component-non-finite",
                _descriptor_with_raw_number(
                    ("evaluations", 0, "expected", 0), "1e9999"
                ),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "gates-wrong-type",
                _descriptor_with(("gates",), []),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "maximum-error-boolean",
                _descriptor_with(("gates", "maximum_absolute_error"), True),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "maximum-error-negative",
                _descriptor_with(("gates", "maximum_absolute_error"), -0.01),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "maximum-error-non-finite",
                _descriptor_with_raw_number(
                    ("gates", "maximum_absolute_error"), "1e9999"
                ),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "finite-output-gate-wrong-type",
                _descriptor_with(("gates", "require_finite_outputs"), 1),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "node-gate-wrong-type",
                _descriptor_with(
                    ("gates", "require_node_binary32_identity"), 1
                ),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "serialization-gate-wrong-type",
                _descriptor_with(
                    ("gates", "require_serialization_binary32_identity"), 1
                ),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "clamping-request-is-not-schema",
                _descriptor_with(("clamp",), True),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "extrapolation-request-is-not-schema",
                _descriptor_with(("extrapolation",), "linear"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "explicit-domain-is-not-schema",
                _descriptor_with(("domain",), [0, 1]),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "cube-member-is-not-schema",
                _descriptor_with(("cube", "path"), "input.cube"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "oracle-member-is-not-schema",
                _descriptor_with(("oracle", "engine"), "harness"),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "evaluation-clamping-member-is-not-schema",
                _descriptor_with(("evaluations", 0, "clamp"), True),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
            InvalidDescriptorCase(
                "gate-member-is-not-schema",
                _descriptor_with(("gates", "relative_error"), 0.0),
                "DESCRIPTOR_SCHEMA_INVALID",
            ),
        )

        for case in cases:
            with self.subTest(case=case.name):
                self._assert_deterministic_rejection(case)

    def test_checksum_mismatch_is_rejected_before_cube_evaluation(self) -> None:
        self._assert_deterministic_rejection(
            InvalidDescriptorCase(
                name="cube-checksum-mismatch",
                descriptor_bytes=_descriptor_with(
                    ("cube", "sha256"), "0" * 64
                ),
                code="CUBE_CHECKSUM_MISMATCH",
            )
        )

    def test_blocked_report_target_creates_no_partial_success_artifact(self) -> None:
        assert_deterministic_invalid_command(
            self,
            descriptor=DESCRIPTOR_PATH,
            cube=CUBE_PATH,
            expected_code="INPUT_INVALID",
            prepare_output=_prepare_blocked_report_target,
            assert_output=_assert_blocked_report_target,
        )

    def test_invalid_evaluation_inputs_are_never_clamped_or_extrapolated(
        self,
    ) -> None:
        huge_integer = "1" + "0" * 400
        cases = (
            InvalidDescriptorCase(
                "input-nan-json-constant",
                _descriptor_with_raw_number(
                    ("evaluations", 0, "input", 0), "NaN"
                ),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-positive-infinity-json-constant",
                _descriptor_with_raw_number(
                    ("evaluations", 0, "input", 1), "Infinity"
                ),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-negative-infinity-json-constant",
                _descriptor_with_raw_number(
                    ("evaluations", 0, "input", 2), "-Infinity"
                ),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-vector-wrong-type",
                _descriptor_with(("evaluations", 0, "input"), "0 0 0"),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-vector-too-short",
                _descriptor_with(("evaluations", 0, "input"), [0, 0]),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-vector-too-long",
                _descriptor_with(("evaluations", 0, "input"), [0, 0, 0, 0]),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-component-boolean",
                _descriptor_with(("evaluations", 0, "input", 0), True),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-component-string",
                _descriptor_with(("evaluations", 0, "input", 1), "0.5"),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-positive-infinity-from-json-number",
                _descriptor_with_raw_number(
                    ("evaluations", 0, "input", 0), "1e9999"
                ),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-negative-infinity-from-json-number",
                _descriptor_with_raw_number(
                    ("evaluations", 0, "input", 1), "-1e9999"
                ),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-integer-too-large-for-binary64",
                _descriptor_with_raw_number(
                    ("evaluations", 0, "input", 2), huge_integer
                ),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-below-domain",
                _descriptor_with(("evaluations", 0, "input", 0), -0.0001),
                "EVALUATION_INPUT_INVALID",
            ),
            InvalidDescriptorCase(
                "input-above-domain",
                _descriptor_with(("evaluations", 0, "input", 2), 1.0001),
                "EVALUATION_INPUT_INVALID",
            ),
        )

        for case in cases:
            with self.subTest(case=case.name):
                self._assert_deterministic_rejection(case)

    def test_unexpected_internal_failure_has_exact_stable_error_record(
        self,
    ) -> None:
        expected_stderr = deterministic_json_bytes(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": (
                        "The provisional conformance harness failed unexpectedly."
                    ),
                },
                "evidence_status": "provisional",
                "report_schema_version": 1,
            }
        )
        injected_message = "injected-internal-error-must-not-leak"

        with (
            tempfile.TemporaryDirectory() as injection_temp,
            tempfile.TemporaryDirectory() as first_temp,
            tempfile.TemporaryDirectory() as second_temp,
        ):
            injection_directory = Path(injection_temp)
            (injection_directory / "sitecustomize.py").write_text(
                "\n".join(
                    (
                        "from pathlib import Path",
                        "",
                        "def _raise_unexpected_error(self):",
                        f"    raise RuntimeError({injected_message!r})",
                        "",
                        "Path.read_bytes = _raise_unexpected_error",
                        "",
                    )
                ),
                encoding="ascii",
                newline="\n",
            )

            environment = os.environ.copy()
            existing_python_path = environment.get("PYTHONPATH")
            python_paths = [str(injection_directory)]
            if existing_python_path:
                python_paths.append(existing_python_path)
            environment["PYTHONPATH"] = os.pathsep.join(python_paths)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            output_directories = (
                Path(first_temp) / "first-artifacts",
                Path(second_temp) / "second-artifacts",
            )
            results = tuple(
                run_harness(
                    descriptor=DESCRIPTOR_PATH,
                    cube=CUBE_PATH,
                    output_directory=output_directory,
                    environment=environment,
                )
                for output_directory in output_directories
            )

            for result, output_directory in zip(
                results, output_directories, strict=True
            ):
                self.assertEqual(result.returncode, 3)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, expected_stderr)
                self.assertNotIn(injected_message.encode("ascii"), result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertFalse(output_directory.exists())
                self.assertFalse((output_directory / "canonical.cube").exists())
                self.assertFalse((output_directory / "report.json").exists())

            self.assertEqual(results[0].stderr, results[1].stderr)


if __name__ == "__main__":
    unittest.main()
