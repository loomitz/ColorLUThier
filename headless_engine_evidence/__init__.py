# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Repository-local, provisional evidence tooling; not a production engine API."""

import hashlib
import json
import platform
import re
import sys

SCHEMA_VERSION = 1
RECORD_LIMIT = 64 * 1024
PLATFORMS = ("linux", "macos", "windows")
CORPUS_SHA256 = "b8e0144c08d6a768d1cda17d7fe2bbc5c7117e9199856eca9061ae8a6e29b2a6"
CLI_SHA256 = "bbe13ab9256575ba6c2cb2759a3710225ac2d20e91eb6f95ea003fc7ec04f0a2"
ARTIFACT_SHA256 = "c8bce4299c8606d5ca59a4724f46e484e430c42d506cfc2a3f30bbe84d5199cc"
LIMITATIONS = {
    "benchmark_wide_coverage": "not_assessed",
    "formal_gate_7": "not_completed",
    "host_compatibility": "not_validated",
    "professional_product_readiness": "not_assessed",
    "security_or_audit": "not_assessed",
}
STAGES = frozenset((
    "arguments", "environment", "focused_tests", "full_tests", "parity_tests",
    "compileall", "materialize_corpus", "portable_cube_corpus", "cli_positive",
    "cli_missing_reference", "cli_malformed_reference", "publication", "comparison",
))
ERROR_CODES = frozenset((
    "ARGUMENT_INVALID", "ENVIRONMENT_UNSUPPORTED", "COMMAND_FAILED",
    "COMMAND_TIMEOUT", "COMMAND_OUTPUT_LIMIT", "COMMAND_CLEANUP_FAILED",
    "FILE_LIMIT", "FILE_INVALID", "CHECK_FAILED", "RECORD_INVALID",
    "ARTIFACT_SET_INVALID", "EVIDENCE_DIVERGED", "PUBLICATION_FAILED",
    "COLLECTOR_INTERNAL_ERROR",
))


class EvidenceError(Exception):
    """A fixed classifier, never a captured command, path, or exception message."""

    def __init__(self, code: str, stage: str):
        self.code = code if code in ERROR_CODES else "COLLECTOR_INTERNAL_ERROR"
        self.stage = stage if stage in STAGES else "arguments"
        super().__init__(self.code)


def require(condition: bool, stage: str, code: str = "CHECK_FAILED") -> None:
    if not condition:
        raise EvidenceError(code, stage)


def canonical_json(record: object) -> bytes:
    return (json.dumps(record, ensure_ascii=True, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def parse_json(payload: bytes, stage: str, *, pretty: bool = False) -> dict:
    """Require exact ASCII/LF canonical framing, including unique object keys."""
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    record = None
    try:
        if 0 < len(payload) <= RECORD_LIMIT:
            candidate = json.loads(payload.decode("ascii"), object_pairs_hook=unique)
            canonical = ((json.dumps(candidate, ensure_ascii=True, sort_keys=True, indent=2,
                                     allow_nan=False) + "\n").encode("ascii")
                         if pretty else canonical_json(candidate))
            if type(candidate) is dict and canonical == payload:
                record = candidate
    except (UnicodeError, ValueError, TypeError, RecursionError):
        pass
    require(record is not None, stage, "RECORD_INVALID")
    return record


def environment_record() -> dict:
    os_family = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(platform.system())
    architecture = {"arm64": "arm64", "aarch64": "arm64", "amd64": "x86_64", "x86_64": "x86_64"}.get(platform.machine().lower())
    require(os_family is not None and architecture is not None and sys.version_info[:2] == (3, 12),
            "environment", "ENVIRONMENT_UNSUPPORTED")
    return {"architecture": architecture, "os_family": os_family,
            "python_version": ".".join(str(part) for part in sys.version_info[:3])}


def validate_counts(counts: object, scope: str, stage: str) -> None:
    fields = {"run", "passed", "skipped", "failures", "errors", "expected_failures",
              "unexpected_successes", "unexpected_skips", "test_inventory_sha256"}
    require(type(counts) is dict and set(counts) == fields, stage, "RECORD_INVALID")
    for key in fields - {"test_inventory_sha256"}:
        require(type(counts[key]) is int and 0 <= counts[key] <= 10000, stage, "RECORD_INVALID")
    require(type(counts["test_inventory_sha256"]) is str and
            re.fullmatch(r"[0-9a-f]{64}", counts["test_inventory_sha256"]) is not None,
            stage, "RECORD_INVALID")
    minimum = {"focused": 55, "full": 123, "parity": 6}[scope]
    require(counts["run"] >= minimum and (scope != "parity" or counts["run"] == 6), stage)
    require(counts["skipped"] == (1 if scope == "full" else 0), stage)
    require(counts["passed"] + counts["skipped"] == counts["run"], stage)
    require(all(counts[key] == 0 for key in ("failures", "errors", "expected_failures",
                                           "unexpected_successes", "unexpected_skips")), stage)


def deterministic_record(focused: dict, full: dict, parity: dict) -> dict:
    """Construct only fixed contractual fields and validated numeric summaries."""
    for scope, counts in (("focused", focused), ("full", full), ("parity", parity)):
        validate_counts(counts, scope, scope + "_tests")
    negative = lambda code: {"artifact_count": 0, "diagnostic_code": code, "exit_code": 2,
                             "stderr": "one_json_diagnostic", "stdout_bytes": 0}
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence": "provisional",
        "limitations": dict(LIMITATIONS),
        "tests": {"focused": focused, "full": full},
        "compileall": {"exit_code": 0, "status": "pass"},
        "portable_cube_corpus": {"report_bytes": 3150, "report_sha256": CORPUS_SHA256,
                                 "case_count": 10, "exit_code": 0, "status": "pass"},
        "cli": {
            "positive": {"exit_code": 0, "runs": 2, "byte_identical": True,
                         "stdout_bytes": 837, "stdout_sha256": CLI_SHA256, "stderr_bytes": 0},
            "missing_reference": negative("CLI_INPUT_UNAVAILABLE"),
            "malformed_reference": negative("CLI_REFERENCE_FORMAT_UNDETECTED"),
        },
        "canonical_artifact": {"bytes": 62, "sha256": ARTIFACT_SHA256,
                               "ordinary_export_status": "blocked-pending-explicit-color-contexts"},
        "preview_full_resolution_parity": {
            "source": "test_preview_full_resolution_parity",
            "oracle": "independent-analytic-binary32", "status": "pass", "tests": parity,
        },
    }


def validate_record(record: object, expected_platform: str | None = None) -> None:
    stage = "comparison"
    require(type(record) is dict and set(record) == {"schema_version", "deterministic", "environment"},
            stage, "RECORD_INVALID")
    require(type(record["schema_version"]) is int and record["schema_version"] == SCHEMA_VERSION,
            stage, "RECORD_INVALID")
    env = record["environment"]
    require(type(env) is dict and set(env) == {"architecture", "os_family", "python_version"}, stage, "RECORD_INVALID")
    require(env["os_family"] in PLATFORMS and env["architecture"] in ("arm64", "x86_64"), stage, "RECORD_INVALID")
    require(type(env["python_version"]) is str and re.fullmatch(r"3\.12\.(0|[1-9][0-9]{0,2})", env["python_version"]) is not None,
            stage, "RECORD_INVALID")
    require(expected_platform is None or env["os_family"] == expected_platform, stage, "ARTIFACT_SET_INVALID")
    value = record["deterministic"]
    require(type(value) is dict and type(value.get("tests")) is dict and
            set(value["tests"]) == {"focused", "full"} and
            type(value.get("preview_full_resolution_parity")) is dict,
            stage, "RECORD_INVALID")
    parity = value["preview_full_resolution_parity"].get("tests")
    expected = deterministic_record(value["tests"]["focused"], value["tests"]["full"], parity)
    # Comparing canonical bytes also rejects bool-for-int and float-for-int aliases.
    require(canonical_json(value) == canonical_json(expected), stage, "RECORD_INVALID")


def error_record(error: EvidenceError) -> dict:
    return {"schema_version": SCHEMA_VERSION, "evidence": "provisional",
            "error": {"code": error.code, "stage": error.stage}}
