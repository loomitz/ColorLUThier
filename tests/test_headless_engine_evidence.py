# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Collector acceptance with bounded real workers and injected orchestration.

Full collect deliberately runs outside discovery (locally and twice per native
CI host). Invoking it from these tests would recursively discover this module.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from headless_engine_evidence import (
    ARTIFACT_SHA256, CLI_SHA256, CORPUS_SHA256, LIMITATIONS, PLATFORMS, RECORD_LIMIT,
    EvidenceError, canonical_json, deterministic_record, digest, environment_record,
    error_record, parse_json, validate_counts, validate_record,
)
from headless_engine_evidence.__main__ import ROOT, collect, compare
from headless_engine_evidence._process import (
    CommandResult, check_tree, command_environment, read_file, run_command,
)
from headless_engine_evidence._suite import SAFARI_SKIP, SummaryResult, run_suite


def counts(scope):
    total = {"focused": 55, "full": 150, "parity": 6}[scope]
    skipped = int(scope == "full")
    return {"run": total, "passed": total - skipped, "skipped": skipped,
            "failures": 0, "errors": 0, "expected_failures": 0, "unexpected_successes": 0,
            "unexpected_skips": 0, "test_inventory_sha256": "1" * 64}


def evidence(platform="macos"):
    return {"schema_version": 1,
            "environment": {"architecture": "arm64", "os_family": platform, "python_version": "3.12.1"},
            "deterministic": deterministic_record(counts("focused"), counts("full"), counts("parity"))}


def write_artifacts(root, records=None):
    records = [evidence(platform) for platform in PLATFORMS] if records is None else records
    for platform, record in zip(PLATFORMS, records, strict=True):
        directory = root / ("headless-engine-evidence-" + platform)
        directory.mkdir()
        (directory / "evidence.json").write_bytes(canonical_json(record))
        (directory / "deterministic.json").write_bytes(canonical_json(record["deterministic"]))


class EvidenceSchemaTest(unittest.TestCase):
    def test_json_is_ascii_sorted_compact_and_lf_canonical(self):
        payload = canonical_json({"z": "caf\u00e9", "a": 1})
        self.assertEqual(payload, b'{"a":1,"z":"caf\\u00e9"}\n')
        self.assertEqual(parse_json(payload, "comparison"), {"a": 1, "z": "caf\u00e9"})

    def test_parser_rejects_ambiguous_unbounded_or_noncanonical_json(self):
        for payload in (b"", b"{}", b"{}\r\n", b"{}\n\n", b"{}\n{}\n", b"[]\n",
                        b'{"a":1,"a":1}\n', b'{"a":NaN}\n', b'{"a":Infinity}\n',
                        b'{"z":1,"a":2}\n', b'{"a": 1}\n', b'{"a":"\xff"}\n',
                        b"[" * 2000, b" " * (RECORD_LIMIT + 1)):
            with self.subTest(payload_length=len(payload)), self.assertRaises(EvidenceError):
                parse_json(payload, "comparison")

    def test_external_harness_pretty_json_has_a_separate_framing_rule(self):
        payload = b'{\n  "a": 1\n}\n'
        self.assertEqual(parse_json(payload, "portable_cube_corpus", pretty=True), {"a": 1})
        with self.assertRaises(EvidenceError):
            parse_json(payload, "comparison")

    def test_closed_schema_rejects_unknown_keys_at_each_object_boundary(self):
        paths = ((), ("environment",), ("deterministic",), ("deterministic", "tests"),
                 ("deterministic", "tests", "full"), ("deterministic", "compileall"),
                 ("deterministic", "portable_cube_corpus"), ("deterministic", "cli"),
                 ("deterministic", "cli", "positive"), ("deterministic", "cli", "missing_reference"),
                 ("deterministic", "cli", "malformed_reference"), ("deterministic", "limitations"),
                 ("deterministic", "canonical_artifact"), ("deterministic", "preview_full_resolution_parity"))
        for path in paths:
            record = evidence()
            target = record
            for component in path:
                target = target[component]
            target["untrusted"] = "/private/synthetic-secret"
            with self.subTest(path=path), self.assertRaises(EvidenceError):
                validate_record(record)

    def test_schema_rejects_bool_and_float_aliases_and_failed_evidence(self):
        cases = (("schema_version", True), ("schema_version", 2), ("environment", {}))
        for field, value in cases:
            record = evidence()
            record[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(EvidenceError):
                validate_record(record)
        for path, field, value in (
            (("deterministic",), "schema_version", 1.0),
            (("deterministic", "compileall"), "exit_code", False),
            (("deterministic", "compileall"), "status", "fail"),
            (("deterministic", "tests", "full"), "run", True),
            (("deterministic", "tests", "full"), "skipped", 2),
            (("deterministic", "tests", "full"), "failures", 1),
            (("deterministic", "tests", "focused"), "run", 0),
            (("deterministic", "cli", "positive"), "runs", 0),
            (("deterministic", "preview_full_resolution_parity"), "status", "skipped"),
        ):
            record = evidence()
            target = record
            for component in path:
                target = target[component]
            target[field] = value
            with self.subTest(path=path, field=field), self.assertRaises(EvidenceError):
                validate_record(record)

    def test_formal_gate_and_host_claims_cannot_be_completed(self):
        for claim in LIMITATIONS:
            record = evidence()
            record["deterministic"]["limitations"][claim] = "completed"
            with self.subTest(claim=claim), self.assertRaises(EvidenceError):
                validate_record(record)

    def test_contract_hashes_are_fixed_and_cannot_be_replaced(self):
        self.assertEqual(CORPUS_SHA256, "b8e0144c08d6a768d1cda17d7fe2bbc5c7117e9199856eca9061ae8a6e29b2a6")
        self.assertEqual(CLI_SHA256, "bbe13ab9256575ba6c2cb2759a3710225ac2d20e91eb6f95ea003fc7ec04f0a2")
        self.assertEqual(ARTIFACT_SHA256, "c8bce4299c8606d5ca59a4724f46e484e430c42d506cfc2a3f30bbe84d5199cc")
        for section, field in (("portable_cube_corpus", "report_sha256"), ("canonical_artifact", "sha256")):
            record = evidence()
            record["deterministic"][section][field] = "f" * 64
            with self.subTest(section=section), self.assertRaises(EvidenceError):
                validate_record(record)

    def test_environment_normalizes_allowlists_without_host_or_python_paths(self):
        with mock.patch("platform.system", return_value="Darwin"), mock.patch("platform.machine", return_value="aarch64"):
            environment = environment_record()
        self.assertEqual(environment["os_family"], "macos")
        self.assertEqual(environment["architecture"], "arm64")
        self.assertEqual(set(environment), {"os_family", "architecture", "python_version"})
        with mock.patch("platform.machine", return_value="secret-host/private/path"), self.assertRaises(EvidenceError):
            environment_record()
        for value in ("3.12.1/private", "3.13.0", "3.12.01"):
            record = evidence()
            record["environment"]["python_version"] = value
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                validate_record(record)


class EvidenceComparisonTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_three_platforms_compare_with_separate_environment_metadata(self):
        records = [evidence(platform) for platform in PLATFORMS]
        records[0]["environment"].update(architecture="x86_64", python_version="3.12.9")
        write_artifacts(self.root, records)
        result = compare(self.root)
        self.assertEqual(result["comparison"], "pass")
        self.assertEqual(result["platforms"], list(PLATFORMS))
        self.assertEqual(result["deterministic_sha256"], digest(canonical_json(records[0]["deterministic"])))

    def test_missing_platform_cannot_pass(self):
        write_artifacts(self.root)
        shutil.rmtree(self.root / "headless-engine-evidence-windows")
        with self.assertRaises(EvidenceError) as raised:
            compare(self.root)
        self.assertEqual(raised.exception.code, "ARTIFACT_SET_INVALID")

    def test_duplicate_platform_cannot_pass(self):
        records = [evidence(platform) for platform in PLATFORMS]
        records[2]["environment"]["os_family"] = "linux"
        write_artifacts(self.root, records)
        with self.assertRaises(EvidenceError):
            compare(self.root)

    def test_extra_artifact_directory_or_file_cannot_pass(self):
        write_artifacts(self.root)
        (self.root / "duplicate").mkdir()
        with self.assertRaises(EvidenceError):
            compare(self.root)
        (self.root / "duplicate").rmdir()
        (self.root / "headless-engine-evidence-linux" / "extra.json").write_text("{}")
        with self.assertRaises(EvidenceError):
            compare(self.root)

    def test_corrupt_missing_or_mismatched_paired_records_cannot_pass(self):
        write_artifacts(self.root)
        directory = self.root / "headless-engine-evidence-linux"
        for payload in (b"not-json", b"{}\n", canonical_json(evidence()["deterministic"]) + b"\n"):
            (directory / "deterministic.json").write_bytes(payload)
            with self.subTest(payload_length=len(payload)), self.assertRaises(EvidenceError):
                compare(self.root)
        (directory / "deterministic.json").unlink()
        with self.assertRaises(EvidenceError):
            compare(self.root)

    def test_contractual_test_inventory_divergence_fails(self):
        records = [evidence(platform) for platform in PLATFORMS]
        records[1]["deterministic"]["tests"]["full"]["test_inventory_sha256"] = "2" * 64
        write_artifacts(self.root, records)
        with self.assertRaises(EvidenceError) as raised:
            compare(self.root)
        self.assertEqual(raised.exception.code, "EVIDENCE_DIVERGED")

    def test_three_identical_failures_do_not_form_success(self):
        records = [evidence(platform) for platform in PLATFORMS]
        for record in records:
            record["deterministic"]["compileall"]["status"] = "fail"
        write_artifacts(self.root, records)
        with self.assertRaises(EvidenceError):
            compare(self.root)

    def test_symlink_directory_metadata_is_rejected_without_following_it(self):
        with mock.patch.object(Path, "lstat", return_value=mock.Mock(st_mode=stat.S_IFLNK)), self.assertRaises(EvidenceError):
            compare(self.root)

    def test_public_compare_command_outputs_only_the_validated_summary(self):
        write_artifacts(self.root)
        result = subprocess.run([sys.executable, "-B", "-m", "headless_engine_evidence", "compare",
                                 "--artifacts-dir", str(self.root)], cwd=ROOT, capture_output=True,
                                timeout=30, env=command_environment(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(parse_json(result.stdout, "comparison"), compare(self.root))


class BoundedEvidenceProcessTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_python(self, source, **options):
        return run_command([sys.executable, "-B", "-c", source], cwd=ROOT,
                           env=command_environment(self.root), stage="focused_tests",
                           temporary_root=self.root, **options)

    def test_both_streams_and_nonzero_status_are_observed(self):
        result = self.run_python("import sys;sys.stdout.buffer.write(b'out');sys.stderr.buffer.write(b'err');sys.exit(7)")
        self.assertEqual(result, CommandResult(7, b"out", b"err"))

    def test_stdout_and_stderr_caps_fail_and_reap_readers(self):
        before = set(threading.enumerate())
        for stream in ("stdout", "stderr"):
            with self.subTest(stream=stream), self.assertRaises(EvidenceError) as raised:
                self.run_python(f"import sys;sys.{stream}.buffer.write(b'x'*4096);sys.{stream}.flush()", stream_limit=128)
            self.assertEqual(raised.exception.code, "COMMAND_OUTPUT_LIMIT")
        self.assertEqual(set(threading.enumerate()), before)

    def test_silent_timeout_kills_descendants_and_reaps_pipe_readers(self):
        before = set(threading.enumerate())
        source = ("import subprocess,sys,threading;"
                  "subprocess.Popen([sys.executable,'-B','-c','import threading;threading.Event().wait()']);"
                  "threading.Event().wait()")
        with self.assertRaises(EvidenceError) as raised:
            self.run_python(source, timeout=1)
        self.assertEqual(raised.exception.code, "COMMAND_TIMEOUT")
        self.assertEqual(set(threading.enumerate()), before)

    def test_launch_failure_is_sanitized(self):
        with self.assertRaises(EvidenceError) as raised:
            run_command([str(self.root / "synthetic-secret-executable")], cwd=ROOT,
                        env=command_environment(self.root), stage="focused_tests", temporary_root=self.root)
        self.assertEqual(str(raised.exception), "COMMAND_FAILED")

    def test_file_reads_enforce_size_and_regular_file_requirements(self):
        source = self.root / "file"
        source.write_bytes(b"1234")
        self.assertEqual(read_file(source, "comparison", 4), b"1234")
        for path, limit in ((source, 3), (self.root, 10), (self.root / "absent", 10)):
            with self.subTest(limit=limit), self.assertRaises(EvidenceError):
                read_file(path, "comparison", limit)
        with mock.patch.object(Path, "lstat", return_value=mock.Mock(st_mode=stat.S_IFLNK, st_size=4)), self.assertRaises(EvidenceError):
            read_file(source, "comparison")

    def test_tree_limits_cover_individual_total_and_entry_count(self):
        (self.root / "one").write_bytes(b"1234")
        (self.root / "two").write_bytes(b"1234")
        for options in ({"file_limit": 3}, {"tree_limit": 7}, {"entry_limit": 1}):
            with self.subTest(options=options), self.assertRaises(EvidenceError):
                check_tree(self.root, "comparison", **options)

    def test_file_budget_is_observed_while_a_silent_command_is_running(self):
        def small_budget(root, stage):
            check_tree(root, stage, file_limit=3)
        source = ("from pathlib import Path;import tempfile,threading;"
                  "Path(tempfile.gettempdir(),'oversize').write_bytes(b'1234');"
                  "threading.Event().wait()")
        before = set(threading.enumerate())
        with mock.patch("headless_engine_evidence._process.check_tree", side_effect=small_budget):
            with self.assertRaises(EvidenceError) as raised:
                self.run_python(source, timeout=10)
        self.assertEqual(raised.exception.code, "FILE_LIMIT")
        self.assertEqual(set(threading.enumerate()), before)

    def test_environment_removes_opt_in_ui_and_import_overrides(self):
        unsafe = {name: "synthetic-secret" for name in ("PYTHONHOME", "PYTHONPATH", "DISPLAY",
                  "WAYLAND_DISPLAY", "BROWSER", "COLORLUTHIER_RUN_REAL_SURFACE_SMOKE", "PYTHONPYCACHEPREFIX")}
        with mock.patch.dict(os.environ, unsafe):
            environment = command_environment(self.root)
        self.assertTrue(all(name not in environment for name in unsafe))
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(environment["PYTHONHASHSEED"], "0")

    def test_repeated_real_parity_workers_are_byte_identical(self):
        command = [sys.executable, "-B", "-m", "headless_engine_evidence", "_suite", "--scope", "parity"]
        results = [run_command(command, cwd=ROOT, env=command_environment(self.root), stage="parity_tests",
                               temporary_root=self.root, timeout=30) for _ in range(2)]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0].returncode, 0)
        self.assertEqual(results[0].stderr, b"")
        validate_counts(parse_json(results[0].stdout, "parity_tests"), "parity", "parity_tests")

    def test_public_argument_and_failure_records_do_not_echo_paths_or_secrets(self):
        private = str(self.root / "synthetic-secret")
        for arguments in (["--unrecognized", private], ["compare", "--artifacts-dir", private]):
            result = subprocess.run([sys.executable, "-B", "-m", "headless_engine_evidence", *arguments],
                                    cwd=ROOT, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"")
            record = parse_json(result.stderr, "arguments")
            self.assertEqual(record["evidence"], "provisional")
            for forbidden in (private, self.temporary.name, socket.gethostname(), "synthetic-secret"):
                self.assertNotIn(forbidden.encode(), result.stderr)


class EvidenceSuiteSummaryTest(unittest.TestCase):
    def test_summary_counts_all_outcomes_without_retaining_failure_payloads(self):
        result = SummaryResult()
        test = mock.Mock()
        test.id.return_value = SAFARI_SKIP
        test.failureException = AssertionError
        result.addSuccess(test)
        result.addSkip(test, "synthetic-secret-path")
        test.id.return_value = "unexpected"
        result.addSkip(test, "synthetic-secret-path")
        result.addFailure(test, (AssertionError, AssertionError("secret"), None))
        result.addError(test, (RuntimeError, RuntimeError("secret"), None))
        result.addExpectedFailure(test, None)
        result.addUnexpectedSuccess(test)
        result.addSubTest(test, None, (AssertionError, AssertionError("secret"), None))
        self.assertEqual(result.counts, {"passed": 1, "skipped": 2, "unexpected_skips": 1,
                                      "failures": 2, "errors": 1, "expected_failures": 1, "unexpected_successes": 1})
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.failures, [])
        self.assertEqual(result.errors, [])
        self.assertEqual(result.skipped, [])

    def test_empty_discovery_is_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "tests").mkdir()
            with self.assertRaises(EvidenceError):
                run_suite("full", root)


class EvidenceCollectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A real independent corpus and CLI supply immutable public output bytes.
        # They do not run test discovery or manufacture expected math.
        cls.workspace = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.workspace.cleanup)
        cls.source = Path(cls.workspace.name)
        environment = command_environment(cls.source)
        commands = (
            ["tests/materialize_portable_cube_corpus.py", "--output-dir", str(cls.source / "inputs")],
            ["-m", "portable_cube_harness", "--descriptor", "tests/fixtures", "--cube", str(cls.source / "inputs"),
             "--output-dir", str(cls.source / "corpus")],
        )
        for command in commands:
            result = run_command([sys.executable, "-B", *command], cwd=ROOT, env=environment,
                                 stage="portable_cube_corpus", temporary_root=cls.source)
            if result.returncode != 0 or result.stderr:
                raise AssertionError("Public corpus setup failed")
        reference = cls.source / "reference.ppm"
        reference.write_bytes(b"P6\n1 1\n255\n" + bytes((64, 128, 192)))
        cls.cli = run_command([sys.executable, "-B", "-m", "colorluthier_engine", "--reference", str(reference),
                               "--cube", "tests/fixtures/identity-2/input.cube", "--interpolation", "tetrahedral",
                               "--export-output", str(cls.source / "canonical.cube")], cwd=ROOT, env=environment,
                              stage="cli_positive", temporary_root=cls.source)
        if cls.cli.returncode != 0 or cls.cli.stderr:
            raise AssertionError("Public CLI setup failed")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stages = []

    def runner(self, arguments, *, stage, temporary_root, **kwargs):
        self.stages.append(stage)
        if stage.endswith("_tests"):
            return CommandResult(0, canonical_json(counts(stage.removesuffix("_tests"))), b"")
        if stage == "compileall":
            cache = temporary_root / "pycache"
            cache.mkdir()
            (cache / "compiled.pyc").write_bytes(b"compiled")
        elif stage == "materialize_corpus":
            directory = temporary_root / "inputs"
            directory.mkdir()
            for index in range(7):
                (directory / f"{index}.cube").write_bytes(b"synthetic")
        elif stage == "portable_cube_corpus":
            shutil.copytree(self.source / "corpus", temporary_root / "corpus")
            return CommandResult(0, (self.source / "corpus" / "report.json").read_bytes(), b"")
        elif stage == "cli_positive":
            Path(arguments[-1]).write_bytes((self.source / "canonical.cube").read_bytes())
            return self.cli
        elif stage.startswith("cli_"):
            code = {"cli_missing_reference": "CLI_INPUT_UNAVAILABLE",
                    "cli_malformed_reference": "CLI_REFERENCE_FORMAT_UNDETECTED"}[stage]
            diagnostic = {"ok": False, "provisional": True,
                          "diagnostic": {"code": code, "context": [], "message": "synthetic"}}
            return CommandResult(2, b"", canonical_json(diagnostic))
        return CommandResult(0, b"", b"")

    def test_collection_repeats_exact_bytes_and_separates_environment(self):
        first = collect(self.root / "one", runner=self.runner)
        second = collect(self.root / "two", runner=self.runner)
        self.assertEqual(first, second)
        self.assertEqual({entry.name for entry in (self.root / "one").iterdir()}, {"evidence.json", "deterministic.json"})
        for filename in ("evidence.json", "deterministic.json"):
            self.assertEqual((self.root / "one" / filename).read_bytes(), (self.root / "two" / filename).read_bytes())
        deterministic = (self.root / "one" / "deterministic.json").read_bytes()
        self.assertNotIn(b"python_version", deterministic)
        self.assertNotIn(b"os_family", deterministic)
        self.assertNotIn(b"architecture", deterministic)
        self.assertEqual(set(self.stages), {"focused_tests", "full_tests", "parity_tests", "compileall",
                                         "materialize_corpus", "portable_cube_corpus", "cli_positive",
                                         "cli_missing_reference", "cli_malformed_reference"})

    def test_every_failed_command_blocks_publication(self):
        stages = ("focused_tests", "full_tests", "parity_tests", "compileall", "materialize_corpus",
                  "portable_cube_corpus", "cli_positive", "cli_missing_reference", "cli_malformed_reference")
        for failed_stage in stages:
            def failing(arguments, **kwargs):
                if kwargs["stage"] == failed_stage:
                    return CommandResult(17, b"secret-payload", b"private/host")
                return self.runner(arguments, **kwargs)
            output = self.root / failed_stage
            with self.subTest(stage=failed_stage), self.assertRaises(EvidenceError) as raised:
                collect(output, runner=failing)
            self.assertEqual(raised.exception.stage, failed_stage)
            self.assertFalse(output.exists())
            self.assertNotIn(b"secret", canonical_json(error_record(raised.exception)))

    def test_empty_or_corrupt_success_evidence_blocks_publication(self):
        for failed_stage in ("focused_tests", "compileall", "materialize_corpus", "portable_cube_corpus", "cli_positive"):
            def empty(arguments, **kwargs):
                if kwargs["stage"] == failed_stage:
                    return CommandResult(0, b"", b"")
                return self.runner(arguments, **kwargs)
            output = self.root / failed_stage
            with self.subTest(stage=failed_stage), self.assertRaises(EvidenceError):
                collect(output, runner=empty)
            self.assertFalse(output.exists())

    def test_negative_smoke_success_or_published_artifact_is_rejected(self):
        for defect in ("exit_zero", "artifact", "stdout", "wrong_code"):
            def defective(arguments, **kwargs):
                result = self.runner(arguments, **kwargs)
                if kwargs["stage"] != "cli_missing_reference":
                    return result
                if defect == "exit_zero":
                    return CommandResult(0, result.stdout, result.stderr)
                if defect == "artifact":
                    Path(arguments[-1]).write_bytes(b"unexpected")
                if defect == "stdout":
                    return CommandResult(2, b"unexpected", result.stderr)
                if defect == "wrong_code":
                    return CommandResult(2, b"", result.stderr.replace(b"CLI_INPUT_UNAVAILABLE", b"WRONG_CODE"))
                return result
            with self.subTest(defect=defect), self.assertRaises(EvidenceError):
                collect(self.root / defect, runner=defective)

    def test_captured_paths_hostnames_secrets_and_payloads_never_enter_records(self):
        sensitive = " ".join((str(self.root), socket.gethostname(), "synthetic-secret", "private-identifier", "payload-content"))
        def noisy(arguments, **kwargs):
            result = self.runner(arguments, **kwargs)
            if kwargs["stage"] in ("cli_missing_reference", "cli_malformed_reference"):
                value = json.loads(result.stderr)
                value["diagnostic"]["message"] = sensitive
                value["diagnostic"]["context"] = [{"name": "secret", "value": sensitive}]
                return CommandResult(2, b"", canonical_json(value))
            return result
        record = collect(self.root / "private-filter", runner=noisy)
        payload = canonical_json(record)
        for forbidden in sensitive.split():
            self.assertNotIn(forbidden.encode(), payload)

    def test_existing_output_and_repository_output_are_rejected_before_commands(self):
        existing = self.root / "existing"
        existing.mkdir()
        sentinel = existing / "keep"
        sentinel.write_bytes(b"keep")
        for output in (existing, ROOT / "forbidden-evidence"):
            with self.subTest(output_name=output.name), self.assertRaises(EvidenceError):
                collect(output, runner=self.runner)
        self.assertEqual(self.stages, [])
        self.assertEqual(sentinel.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
