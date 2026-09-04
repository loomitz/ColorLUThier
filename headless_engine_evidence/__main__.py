# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Collect or compare provisional public headless engine evidence."""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
from pathlib import Path

from . import (
    ARTIFACT_SHA256, CLI_SHA256, CORPUS_SHA256, PLATFORMS, RECORD_LIMIT,
    SCHEMA_VERSION, EvidenceError, canonical_json, deterministic_record, digest,
    environment_record, error_record, parse_json, require, validate_counts, validate_record,
)
from ._process import SUITE_TIMEOUT, command_environment, read_file, run_command

ROOT = Path(__file__).resolve().parents[1]


def _check_result(result, stage: str, exit_code: int = 0, *, empty_stderr: bool = True):
    require(result.returncode == exit_code, stage, "COMMAND_FAILED")
    if empty_stderr:
        require(result.stderr == b"", stage)


def _output_location(output: Path) -> Path:
    target = None
    try:
        target = output.absolute()
        resolved = target.resolve()
        require(not resolved.is_relative_to(ROOT), "publication", "PUBLICATION_FAILED")
        require(not target.exists() and not target.is_symlink() and target.parent.is_dir(),
                "publication", "PUBLICATION_FAILED")
    except OSError:
        target = None
    require(target is not None, "publication", "PUBLICATION_FAILED")
    return target


def _publish(output: Path, record: dict) -> None:
    files = {"deterministic.json": canonical_json(record["deterministic"]),
             "evidence.json": canonical_json(record)}
    require(all(len(payload) <= RECORD_LIMIT for payload in files.values()), "publication", "FILE_LIMIT")
    created = False
    failed = False
    try:
        output.mkdir()
        created = True
        for name, payload in files.items():
            with (output / name).open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    except OSError:
        failed = True
    if failed:
        if created:
            # Only this invocation's fixed artifacts are eligible for rollback.
            for name in files:
                try:
                    (output / name).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                output.rmdir()
            except OSError:
                pass
        raise EvidenceError("PUBLICATION_FAILED", "publication")


def collect(output: Path, *, runner=run_command) -> dict:
    output = _output_location(output)
    environment = environment_record()
    with tempfile.TemporaryDirectory(prefix="colorluthier-evidence-") as temporary:
        temporary_root = Path(temporary)
        env = command_environment(temporary_root)

        def run(stage, arguments, *, command_env=None, timeout=120):
            return runner([sys.executable, "-B", *arguments], cwd=ROOT,
                          env=env if command_env is None else command_env, stage=stage,
                          temporary_root=temporary_root, timeout=timeout)

        counts = {}
        for scope in ("focused", "full", "parity"):
            stage = scope + "_tests"
            result = run(stage, ["-m", "headless_engine_evidence", "_suite", "--scope", scope],
                         timeout=SUITE_TIMEOUT)
            _check_result(result, stage)
            counts[scope] = parse_json(result.stdout, stage)
            validate_counts(counts[scope], scope, stage)

        compile_env = dict(env, PYTHONPYCACHEPREFIX=str(temporary_root / "pycache"))
        compiled = run("compileall", ["-m", "compileall", "-q", "colorluthier_engine",
                       "portable_cube_harness", "internal_test_ui_adapter", "internal_test_ui_prototype",
                       "headless_engine_evidence", "tests"], command_env=compile_env)
        _check_result(compiled, "compileall")
        require(compiled.stdout == b"", "compileall")
        require(any((temporary_root / "pycache").rglob("*.pyc")), "compileall")

        materialized = run("materialize_corpus", ["tests/materialize_portable_cube_corpus.py",
                           "--output-dir", str(temporary_root / "inputs")])
        _check_result(materialized, "materialize_corpus")
        require(materialized.stdout == b"" and (temporary_root / "inputs").is_dir() and
                len(list((temporary_root / "inputs").rglob("*.cube"))) == 7,
                "materialize_corpus")
        corpus_dir = temporary_root / "corpus"
        corpus = run("portable_cube_corpus", ["-m", "portable_cube_harness", "--descriptor",
                     "tests/fixtures", "--cube", str(temporary_root / "inputs"),
                     "--output-dir", str(corpus_dir)])
        _check_result(corpus, "portable_cube_corpus")
        report = read_file(corpus_dir / "report.json", "portable_cube_corpus", RECORD_LIMIT)
        require(report == corpus.stdout and len(report) == 3150 and digest(report) == CORPUS_SHA256,
                "portable_cube_corpus")
        # The independent harness report commits to every canonical/per-case digest.
        corpus_record = parse_json(report, "portable_cube_corpus", pretty=True)
        require(corpus_record["case_count"] == 10 and corpus_record["passed_case_count"] == 10 and
                corpus_record["failed_case_count"] == 0 and corpus_record["overall_result"] == "pass",
                "portable_cube_corpus")
        for case in corpus_record["cases"]:
            case_dir = corpus_dir / "cases" / case["case_id"]
            require(digest(read_file(case_dir / "canonical.cube", "portable_cube_corpus")) == case["canonical_cube_sha256"] and
                    digest(read_file(case_dir / "report.json", "portable_cube_corpus", RECORD_LIMIT)) == case["report_sha256"],
                    "portable_cube_corpus")

        reference = temporary_root / "reference.ppm"
        reference.write_bytes(b"P6\n1 1\n255\n" + bytes((64, 128, 192)))

        def cli_arguments(reference_path, artifact):
            return ["-m", "colorluthier_engine", "--reference", str(reference_path),
                    "--cube", "tests/fixtures/identity-2/input.cube", "--interpolation",
                    "tetrahedral", "--export-output", str(artifact)]

        positives = []
        for index in range(2):
            artifact_path = temporary_root / f"canonical-{index}.cube"
            result = run("cli_positive", cli_arguments(reference, artifact_path))
            _check_result(result, "cli_positive")
            artifact = read_file(artifact_path, "cli_positive", 62)
            require(len(result.stdout) == 837 and digest(result.stdout) == CLI_SHA256 and
                    len(artifact) == 62 and digest(artifact) == ARTIFACT_SHA256, "cli_positive")
            positives.append((result.stdout, artifact))
        require(positives[0] == positives[1], "cli_positive")

        malformed = temporary_root / "malformed.ppm"
        malformed.write_bytes(b"not-a-reference\n")
        for stage, source, code in (
            ("cli_missing_reference", temporary_root / "absent.ppm", "CLI_INPUT_UNAVAILABLE"),
            ("cli_malformed_reference", malformed, "CLI_REFERENCE_FORMAT_UNDETECTED"),
        ):
            artifact = temporary_root / (stage + ".cube")
            result = run(stage, cli_arguments(source, artifact))
            _check_result(result, stage, 2, empty_stderr=False)
            require(result.stdout == b"" and not artifact.exists() and not artifact.is_symlink(), stage)
            failure = parse_json(result.stderr, stage)
            require(set(failure) == {"diagnostic", "ok", "provisional"} and
                    failure["ok"] is False and failure["provisional"] is True and
                    type(failure["diagnostic"]) is dict and
                    set(failure["diagnostic"]) == {"code", "context", "message"} and
                    failure["diagnostic"]["code"] == code, stage)

        record = {"schema_version": SCHEMA_VERSION, "environment": environment,
                  "deterministic": deterministic_record(counts["focused"], counts["full"], counts["parity"])}
        validate_record(record)
    _publish(output, record)
    return record


def _regular_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _entry_names(path: Path, maximum: int) -> set[str]:
    names = set()
    with os.scandir(path) as entries:
        for entry in entries:
            names.add(entry.name)
            require(len(names) <= maximum, "comparison", "ARTIFACT_SET_INVALID")
    return names


def compare(artifacts: Path) -> dict:
    stage = "comparison"
    require(_regular_directory(artifacts), stage, "ARTIFACT_SET_INVALID")
    expected = {"headless-engine-evidence-" + platform for platform in PLATFORMS}
    require(_entry_names(artifacts, 3) == expected, stage, "ARTIFACT_SET_INVALID")
    payloads = []
    for platform in PLATFORMS:
        directory = artifacts / ("headless-engine-evidence-" + platform)
        require(_regular_directory(directory) and
                _entry_names(directory, 2) == {"evidence.json", "deterministic.json"},
                stage, "ARTIFACT_SET_INVALID")
        record = parse_json(read_file(directory / "evidence.json", stage, RECORD_LIMIT), stage)
        validate_record(record, platform)
        deterministic = read_file(directory / "deterministic.json", stage, RECORD_LIMIT)
        require(deterministic == canonical_json(record["deterministic"]), stage, "RECORD_INVALID")
        payloads.append(deterministic)
    require(len(set(payloads)) == 1, stage, "EVIDENCE_DIVERGED")
    return {"schema_version": SCHEMA_VERSION, "evidence": "provisional", "comparison": "pass",
            "platforms": list(PLATFORMS), "deterministic_sha256": digest(payloads[0])}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise EvidenceError("ARGUMENT_INVALID", "arguments")


def main(argv=None) -> int:
    try:
        parser = _Parser(prog="python -B -m headless_engine_evidence")
        commands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
        commands.add_parser("collect").add_argument("--output-dir", required=True, type=Path)
        commands.add_parser("compare").add_argument("--artifacts-dir", required=True, type=Path)
        commands.add_parser("_suite", help=argparse.SUPPRESS).add_argument("--scope", choices=("focused", "full", "parity"), required=True)
        arguments = parser.parse_args(argv)
        environment_record()  # The worker and comparator also require Python 3.12.
        status = 0
        if arguments.command == "collect":
            record = collect(arguments.output_dir)
        elif arguments.command == "compare":
            record = compare(arguments.artifacts_dir)
        else:
            from ._suite import run_suite
            record, status = run_suite(arguments.scope, ROOT)
    except EvidenceError as error:
        sys.stderr.buffer.write(canonical_json(error_record(error)))
        return 2
    except Exception:
        sys.stderr.buffer.write(canonical_json(error_record(EvidenceError("COLLECTOR_INTERNAL_ERROR", "arguments"))))
        return 3
    sys.stdout.buffer.write(canonical_json(record))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
