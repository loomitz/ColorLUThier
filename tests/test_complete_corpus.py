from __future__ import annotations

import hashlib
import itertools
import json
import os
import socket
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from acceptance_support import (
    HARNESS_VERSION,
    METRIC_FIELDS,
    PROVISIONAL_EVIDENCE,
    REPOSITORY_ROOT,
    TIMESTAMP_PATTERN,
    UUID_PATTERN,
    assert_deterministic_invalid_command,
    assert_deterministic_json_document,
    deterministic_json_bytes,
    run_corpus_materializer,
    run_harness,
)


FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures"
EXPECTED_CASE_IDS = (
    "affine-cross-channel-3-tetrahedral",
    "affine-cross-channel-3-trilinear",
    "identity-2-trilinear",
    "identity-33-trilinear",
    "interpolation-divergence-2-tetrahedral",
    "interpolation-divergence-2-trilinear",
    "nonlinear-separable-5-tetrahedral",
    "nonlinear-separable-5-trilinear",
    "red-blue-swap-2-trilinear",
    "red-blue-swap-65-tetrahedral",
)
AGGREGATE_FIELDS = {
    "case_count",
    "cases",
    "evidence",
    "failed_case_count",
    "harness_version",
    "overall_result",
    "passed_case_count",
    "report_schema_version",
}
AGGREGATE_CASE_FIELDS = {
    "canonical_cube_sha256",
    "case_id",
    "overall_result",
    "report_sha256",
}
PROFESSIONAL_EVALUATION_IDS = {
    "node-center",
    "node-corner-000",
    "node-corner-001",
    "node-corner-010",
    "node-corner-011",
    "node-corner-100",
    "node-corner-101",
    "node-corner-110",
    "node-corner-111",
    "node-edge-asymmetric",
    "node-face-asymmetric",
    "node-interior-asymmetric-high",
    "node-interior-asymmetric-low",
    "probe-interior-dyadic-asymmetric",
}


@dataclass(frozen=True)
class ProfessionalCaseSpec:
    byte_count: int
    cube_sha256: str
    edge: tuple[int, int, int]
    face: tuple[int, int, int]
    interiors: tuple[tuple[int, int, int], tuple[int, int, int]]
    interpolation: Literal["trilinear", "tetrahedral"]
    lattice_size: int
    off_node: tuple[float, float, float]
    transform: Literal["identity", "red_blue_swap"]


PROFESSIONAL_CASES = {
    "identity-33-trilinear": ProfessionalCaseSpec(
        byte_count=738_357,
        cube_sha256=(
            "ed09443c84100f8d9620bb4fc22325e56b2777577b37323cc1ba940d0472ba60"
        ),
        edge=(0, 32, 11),
        face=(32, 7, 25),
        interiors=((1, 7, 29), (31, 19, 5)),
        interpolation="trilinear",
        lattice_size=33,
        off_node=(21 / 128, 27 / 64, 111 / 128),
        transform="identity",
    ),
    "red-blue-swap-65-tetrahedral": ProfessionalCaseSpec(
        byte_count=6_514_965,
        cube_sha256=(
            "4664568c299ffcf31164a4d504524c322594fd5f7fe66da26874e81b96e08d30"
        ),
        edge=(0, 64, 27),
        face=(64, 13, 47),
        interiors=((1, 7, 61), (63, 37, 3)),
        interpolation="tetrahedral",
        lattice_size=65,
        off_node=(39 / 256, 63 / 128, 213 / 256),
        transform="red_blue_swap",
    ),
}
PRESERVED_OUTPUT_BYTES = b"pre-existing corpus output must remain unchanged\n"


def _prepare_existing_corpus_output(output_directory: Path) -> None:
    output_directory.mkdir()
    (output_directory / "user-owned.txt").write_bytes(PRESERVED_OUTPUT_BYTES)


def _assert_existing_corpus_output(
    test: unittest.TestCase,
    output_directory: Path,
) -> None:
    test.assertTrue(output_directory.is_dir())
    test.assertEqual(
        sorted(path.name for path in output_directory.iterdir()),
        ["user-owned.txt"],
    )
    test.assertEqual(
        (output_directory / "user-owned.txt").read_bytes(),
        PRESERVED_OUTPUT_BYTES,
    )


def _environment(hash_seed: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = hash_seed
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def _is_descriptor(path: Path) -> bool:
    return path.name == "case.json" or path.name.endswith(".case.json")


def _descriptor_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and _is_descriptor(path)
    )


def _copy_descriptor_corpus(source: Path, destination: Path, *, reverse: bool) -> None:
    paths = _descriptor_paths(source)
    if reverse:
        paths.reverse()
    for path in paths:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())


def _descriptors_by_case_id(root: Path) -> dict[str, tuple[Path, dict[str, Any]]]:
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    for path in _descriptor_paths(root):
        descriptor: dict[str, Any] = json.loads(path.read_bytes())
        case_id = descriptor["case_id"]
        if case_id in result:
            raise AssertionError(f"Duplicate fixture case identifier: {case_id}")
        result[case_id] = (path, descriptor)
    return result


def _cubes_by_sha256(root: Path) -> dict[str, tuple[Path, bytes]]:
    result: dict[str, tuple[Path, bytes]] = {}
    for path in sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.name.endswith(".cube")
    ):
        cube_bytes = path.read_bytes()
        digest = hashlib.sha256(cube_bytes).hexdigest()
        if digest in result and result[digest][1] != cube_bytes:
            raise AssertionError("A SHA-256 collision occurred in the fixture corpus")
        result.setdefault(digest, (path, cube_bytes))
    return result


def _move_cubes_away_from_fixture_relative_paths(root: Path) -> None:
    source_paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name.endswith(".cube")
    )
    destination_root = root / "content-addressed-inputs"
    destination_root.mkdir()
    for index, source in enumerate(reversed(source_paths)):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        source.rename(destination_root / f"{index:02d}-{digest[:16]}.cube")


def _artifact_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(
            candidate for candidate in root.rglob("*") if candidate.is_file()
        )
    }


def _transform(
    input_rgb: tuple[float, float, float],
    kind: Literal["identity", "red_blue_swap"],
) -> tuple[float, float, float]:
    if kind == "identity":
        return input_rgb
    red, green, blue = input_rgb
    return (blue, green, red)


def _professional_node_indices(
    specification: ProfessionalCaseSpec,
) -> set[tuple[int, int, int]]:
    last_index = specification.lattice_size - 1
    corners = set(itertools.product((0, last_index), repeat=3))
    center_index = last_index // 2
    return corners | {
        (center_index, center_index, center_index),
        specification.edge,
        specification.face,
        *specification.interiors,
    }


class CompleteCorpusAcceptanceTest(unittest.TestCase):
    def _materialize(self, output_directory: Path, hash_seed: str) -> None:
        result = run_corpus_materializer(
            output_directory=output_directory,
            environment=_environment(hash_seed),
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        self.assertEqual(result.stderr, b"")

    def _assert_report_privacy(
        self,
        report_bytes: bytes,
        *,
        forbidden_paths: tuple[Path, ...],
    ) -> dict[str, Any]:
        report = assert_deterministic_json_document(self, report_bytes)
        report_text = report_bytes.decode("ascii")
        for path in forbidden_paths:
            self.assertNotIn(str(path), report_text)
            self.assertNotIn(str(path.resolve()), report_text)
        self.assertNotIn(str(REPOSITORY_ROOT), report_text)
        self.assertNotIn(socket.gethostname(), report_text)
        self.assertIsNone(TIMESTAMP_PATTERN.search(report_text))
        self.assertIsNone(UUID_PATTERN.search(report_text))
        self.assertNotIn("Photoshop", report_text)
        self.assertNotIn("Resolve", report_text)
        self.assertNotIn("hostname", report_text.lower())
        self.assertNotIn("timestamp", report_text.lower())
        return report

    def _assert_exact_tree(
        self, output_directory: Path, case_ids: tuple[str, ...]
    ) -> None:
        expected_files = {"report.json"}
        expected_directories = {"cases"}
        for case_id in case_ids:
            expected_directories.add(f"cases/{case_id}")
            expected_files.add(f"cases/{case_id}/canonical.cube")
            expected_files.add(f"cases/{case_id}/report.json")

        actual_files = {
            path.relative_to(output_directory).as_posix()
            for path in output_directory.rglob("*")
            if path.is_file()
        }
        actual_directories = {
            path.relative_to(output_directory).as_posix()
            for path in output_directory.rglob("*")
            if path.is_dir()
        }
        self.assertEqual(actual_files, expected_files)
        self.assertEqual(actual_directories, expected_directories)

    def _assert_corpus_output(
        self,
        *,
        result: Any,
        output_directory: Path,
        descriptors: Mapping[str, tuple[Path, dict[str, Any]]],
        expected_results: Mapping[str, str],
        forbidden_paths: tuple[Path, ...],
    ) -> dict[str, bytes]:
        case_ids = tuple(sorted(expected_results))
        expected_status = 1 if "fail" in expected_results.values() else 0
        self.assertEqual(result.returncode, expected_status)
        self.assertEqual(result.stderr, b"")
        self._assert_exact_tree(output_directory, case_ids)

        aggregate_bytes = (output_directory / "report.json").read_bytes()
        self.assertEqual(result.stdout, aggregate_bytes)
        aggregate = self._assert_report_privacy(
            aggregate_bytes,
            forbidden_paths=forbidden_paths,
        )
        self.assertEqual(set(aggregate), AGGREGATE_FIELDS)
        self.assertEqual(aggregate["report_schema_version"], 1)
        self.assertEqual(aggregate["harness_version"], HARNESS_VERSION)
        self.assertEqual(aggregate["evidence"], PROVISIONAL_EVIDENCE)
        self.assertEqual(aggregate["case_count"], len(case_ids))
        self.assertEqual(
            aggregate["passed_case_count"],
            sum(result == "pass" for result in expected_results.values()),
        )
        self.assertEqual(
            aggregate["failed_case_count"],
            sum(result == "fail" for result in expected_results.values()),
        )
        self.assertEqual(
            aggregate["overall_result"],
            "fail" if expected_status == 1 else "pass",
        )

        entries = aggregate["cases"]
        self.assertIsInstance(entries, list)
        self.assertEqual([entry["case_id"] for entry in entries], list(case_ids))
        for entry in entries:
            self.assertEqual(set(entry), AGGREGATE_CASE_FIELDS)
            case_id = entry["case_id"]
            canonical_bytes = (
                output_directory / "cases" / case_id / "canonical.cube"
            ).read_bytes()
            case_report_bytes = (
                output_directory / "cases" / case_id / "report.json"
            ).read_bytes()
            case_report = self._assert_report_privacy(
                case_report_bytes,
                forbidden_paths=forbidden_paths,
            )
            descriptor = descriptors[case_id][1]

            self.assertEqual(entry["overall_result"], expected_results[case_id])
            self.assertEqual(case_report["case_id"], case_id)
            self.assertEqual(case_report["overall_result"], expected_results[case_id])
            self.assertEqual(case_report["harness_version"], HARNESS_VERSION)
            self.assertEqual(case_report["evidence"], PROVISIONAL_EVIDENCE)
            self.assertEqual(
                entry["canonical_cube_sha256"],
                hashlib.sha256(canonical_bytes).hexdigest(),
            )
            self.assertEqual(
                entry["canonical_cube_sha256"],
                case_report["hashes"]["canonical_cube_sha256"],
            )
            self.assertEqual(
                entry["report_sha256"],
                hashlib.sha256(case_report_bytes).hexdigest(),
            )
            self.assertEqual(
                case_report["hashes"]["input_cube_sha256"],
                descriptor["cube"]["sha256"],
            )

        return _artifact_bytes(output_directory)

    def _assert_professional_fixture(
        self,
        *,
        case_id: str,
        descriptor: dict[str, Any],
        input_cube: bytes,
        canonical_cube: bytes,
        report: dict[str, Any],
    ) -> None:
        specification = PROFESSIONAL_CASES[case_id]
        size = specification.lattice_size
        last_index = size - 1
        expected_node_indices = _professional_node_indices(specification)
        expected_inputs = {
            tuple(index / last_index for index in indices)
            for indices in expected_node_indices
        }
        expected_inputs.add(specification.off_node)
        expected_pairs = {
            (input_rgb, _transform(input_rgb, specification.transform))
            for input_rgb in expected_inputs
        }
        actual_pairs = {
            (tuple(evaluation["input"]), tuple(evaluation["expected"]))
            for evaluation in descriptor["evaluations"]
        }

        self.assertEqual(descriptor["case_id"], case_id)
        self.assertEqual(descriptor["interpolation"], specification.interpolation)
        self.assertEqual(descriptor["cube"]["sha256"], specification.cube_sha256)
        self.assertEqual(len(descriptor["evaluations"]), 14)
        self.assertEqual(actual_pairs, expected_pairs)
        self.assertEqual(
            {evaluation["id"] for evaluation in descriptor["evaluations"]},
            PROFESSIONAL_EVALUATION_IDS,
        )
        self.assertEqual(
            descriptor["gates"],
            {
                "maximum_absolute_error": 2**-20,
                "require_finite_outputs": True,
                "require_node_binary32_identity": True,
                "require_serialization_binary32_identity": True,
            },
        )
        self.assertEqual(descriptor["oracle"]["kind"], "explicit_expected_values")
        self.assertIn(
            "generator did not produce these expectations",
            descriptor["oracle"]["provenance"].lower(),
        )

        self.assertEqual(len(input_cube), specification.byte_count)
        self.assertEqual(
            hashlib.sha256(input_cube).hexdigest(), specification.cube_sha256
        )
        self.assertEqual(canonical_cube, input_cube)
        input_cube.decode("ascii")
        self.assertNotIn(b"\r", input_cube)
        self.assertTrue(input_cube.endswith(b"\n"))
        rows = input_cube.splitlines()
        self.assertEqual(rows[0], f"LUT_3D_SIZE {size}".encode("ascii"))
        self.assertEqual(len(rows), size**3 + 1)
        for red_index, green_index, blue_index in expected_node_indices:
            row_index = red_index + size * green_index + size * size * blue_index
            actual = tuple(float(token) for token in rows[row_index + 1].split())
            input_rgb = (
                red_index / last_index,
                green_index / last_index,
                blue_index / last_index,
            )
            self.assertEqual(actual, _transform(input_rgb, specification.transform))

        self.assertEqual(report["lattice_size"], size)
        self.assertEqual(report["sample_count"], size**3)
        self.assertEqual(report["evaluation_count"], 14)
        self.assertEqual(report["interpolation"], specification.interpolation)
        self.assertEqual(report["overall_result"], "pass")
        for metrics in report["metrics"].values():
            self.assertEqual(metrics, {field: 0.0 for field in METRIC_FIELDS})
        self.assertEqual(
            report["round_trip"],
            {
                "canonical_node_evaluation_binary32_identical": True,
                "canonical_reevaluation_passed": True,
                "input_node_evaluation_binary32_identical": True,
                "serialization_binary32_identical": True,
            },
        )

    def test_complete_corpus_is_byte_identical_ordered_and_content_addressed(
        self,
    ) -> None:
        with (
            tempfile.TemporaryDirectory() as first_temp,
            tempfile.TemporaryDirectory() as second_temp,
        ):
            run_roots = (Path(first_temp), Path(second_temp))
            corpus_runs = []
            artifact_sets = []
            cube_sets = []

            for index, run_root in enumerate(run_roots):
                descriptor_root = run_root / "descriptors"
                cube_root = run_root / "materialized-cubes"
                output_root = run_root / "corpus-evidence"
                _copy_descriptor_corpus(
                    FIXTURE_ROOT,
                    descriptor_root,
                    reverse=bool(index),
                )
                self._materialize(cube_root, str(17 + index * 1000))
                if index:
                    _move_cubes_away_from_fixture_relative_paths(cube_root)
                descriptors = _descriptors_by_case_id(descriptor_root)
                cubes = _cubes_by_sha256(cube_root)
                self.assertEqual(tuple(sorted(descriptors)), EXPECTED_CASE_IDS)
                self.assertTrue(
                    all(
                        descriptor["cube"]["sha256"] in cubes
                        for _, descriptor in descriptors.values()
                    )
                )

                result = run_harness(
                    descriptor=descriptor_root,
                    cube=cube_root,
                    output_directory=output_root,
                    environment=_environment(str(31 + index * 2000)),
                )
                expected_results = {case_id: "pass" for case_id in EXPECTED_CASE_IDS}
                artifacts = self._assert_corpus_output(
                    result=result,
                    output_directory=output_root,
                    descriptors=descriptors,
                    expected_results=expected_results,
                    forbidden_paths=(descriptor_root, cube_root, output_root, run_root),
                )
                corpus_runs.append(
                    (
                        descriptor_root,
                        cube_root,
                        output_root,
                        descriptors,
                        cubes,
                        result,
                    )
                )
                artifact_sets.append(artifacts)
                cube_sets.append({digest: value[1] for digest, value in cubes.items()})

            self.assertEqual(cube_sets[0], cube_sets[1])
            self.assertEqual(artifact_sets[0], artifact_sets[1])
            self.assertEqual(corpus_runs[0][5].stdout, corpus_runs[1][5].stdout)
            self.assertEqual(
                hashlib.sha256(corpus_runs[0][5].stdout).hexdigest(),
                hashlib.sha256(corpus_runs[1][5].stdout).hexdigest(),
            )

            (
                descriptor_root,
                cube_root,
                output_root,
                descriptors,
                cubes,
                _,
            ) = corpus_runs[0]
            for case_id in EXPECTED_CASE_IDS:
                descriptor_path, descriptor = descriptors[case_id]
                cube_path, input_cube = cubes[descriptor["cube"]["sha256"]]
                single_output = run_roots[0] / "single-case-evidence" / case_id
                result = run_harness(
                    descriptor=descriptor_path,
                    cube=cube_path,
                    output_directory=single_output,
                    environment=_environment("424242"),
                )
                corpus_case_root = output_root / "cases" / case_id
                corpus_report_bytes = (corpus_case_root / "report.json").read_bytes()
                corpus_cube_bytes = (corpus_case_root / "canonical.cube").read_bytes()
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, b"")
                self.assertEqual(result.stdout, corpus_report_bytes)
                self.assertEqual(
                    (single_output / "report.json").read_bytes(), corpus_report_bytes
                )
                self.assertEqual(
                    (single_output / "canonical.cube").read_bytes(), corpus_cube_bytes
                )

                if case_id in PROFESSIONAL_CASES:
                    self._assert_professional_fixture(
                        case_id=case_id,
                        descriptor=descriptor,
                        input_cube=input_cube,
                        canonical_cube=corpus_cube_bytes,
                        report=json.loads(corpus_report_bytes),
                    )

    def test_valid_gate_failure_aggregates_status_one_and_all_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            cube_root = temporary_root / "materialized-cubes"
            descriptor_root = temporary_root / "descriptors"
            self._materialize(cube_root, "71")

            source_descriptors = _descriptors_by_case_id(FIXTURE_ROOT)
            passing = json.loads(
                deterministic_json_bytes(
                    source_descriptors["identity-2-trilinear"][1]
                )
            )
            passing["case_id"] = "a-valid-pass"
            failing = json.loads(
                deterministic_json_bytes(
                    source_descriptors["nonlinear-separable-5-trilinear"][1]
                )
            )
            failing["case_id"] = "z-valid-gate-fail"
            failing["gates"]["maximum_absolute_error"] = 0.0
            descriptor_root.mkdir()
            (descriptor_root / "z.case.json").write_bytes(
                deterministic_json_bytes(failing)
            )
            (descriptor_root / "a.case.json").write_bytes(
                deterministic_json_bytes(passing)
            )
            descriptors = _descriptors_by_case_id(descriptor_root)
            expected_results = {
                "a-valid-pass": "pass",
                "z-valid-gate-fail": "fail",
            }

            artifact_sets = []
            for index, seed in enumerate(("73", "79")):
                output_root = temporary_root / f"status-one-evidence-{index}"
                result = run_harness(
                    descriptor=descriptor_root,
                    cube=cube_root,
                    output_directory=output_root,
                    environment=_environment(seed),
                )
                artifact_sets.append(
                    self._assert_corpus_output(
                        result=result,
                        output_directory=output_root,
                        descriptors=descriptors,
                        expected_results=expected_results,
                        forbidden_paths=(
                            descriptor_root,
                            cube_root,
                            output_root,
                            temporary_root,
                        ),
                    )
                )

            self.assertEqual(artifact_sets[0], artifact_sets[1])

    def test_invalid_corpus_inputs_are_status_two_and_publish_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            cube_root = temporary_root / "materialized-cubes"
            self._materialize(cube_root, "83")
            cubes = _cubes_by_sha256(cube_root)
            source_descriptors = _descriptors_by_case_id(FIXTURE_ROOT)
            identity_path, identity = source_descriptors["identity-2-trilinear"]
            identity_cube_path = cubes[identity["cube"]["sha256"]][0]

            empty_root = temporary_root / "empty-descriptors"
            empty_root.mkdir()
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=empty_root,
                cube=cube_root,
                expected_reason="descriptor_set_empty",
                expected_context={"descriptor_count": 0},
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=identity_path,
                cube=cube_root,
                expected_reason="input_kind_mismatch",
                expected_context={"cube": "directory", "descriptor": "file"},
            )

            one_descriptor_root = temporary_root / "one-descriptor"
            one_descriptor_root.mkdir()
            (one_descriptor_root / "case.json").write_bytes(
                deterministic_json_bytes(identity)
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=one_descriptor_root,
                cube=identity_cube_path,
                expected_reason="input_kind_mismatch",
                expected_context={"cube": "file", "descriptor": "directory"},
            )

            missing_hash_root = temporary_root / "missing-hash"
            missing_hash = json.loads(deterministic_json_bytes(identity))
            missing_hash["case_id"] = "missing-cube-fixture"
            missing_hash["cube"]["sha256"] = "0" * 64
            missing_hash_root.mkdir()
            (missing_hash_root / "case.json").write_bytes(
                deterministic_json_bytes(missing_hash)
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=missing_hash_root,
                cube=cube_root,
                expected_reason="cube_fixture_not_found",
                expected_context={
                    "case_id": "missing-cube-fixture",
                    "cube_sha256": "0" * 64,
                },
            )

            duplicate_root = temporary_root / "duplicate-case-id"
            duplicate_root.mkdir()
            (duplicate_root / "case.json").write_bytes(
                deterministic_json_bytes(identity)
            )
            (duplicate_root / "duplicate.case.json").write_bytes(
                deterministic_json_bytes(identity)
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=duplicate_root,
                cube=cube_root,
                expected_reason="duplicate_case_id",
                expected_context={"case_id": "identity-2-trilinear"},
            )

            late_invalid_root = temporary_root / "late-invalid"
            valid = json.loads(deterministic_json_bytes(identity))
            valid["case_id"] = "a-valid-before-invalid"
            late_invalid = json.loads(deterministic_json_bytes(identity))
            late_invalid["case_id"] = "z-invalid-after-valid"
            late_invalid["cube"]["sha256"] = "f" * 64
            late_invalid_root.mkdir()
            (late_invalid_root / "a.case.json").write_bytes(
                deterministic_json_bytes(valid)
            )
            (late_invalid_root / "z.case.json").write_bytes(
                deterministic_json_bytes(late_invalid)
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=late_invalid_root,
                cube=cube_root,
                expected_reason="cube_fixture_not_found",
                expected_context={
                    "case_id": "z-invalid-after-valid",
                    "cube_sha256": "f" * 64,
                },
            )

            reserved_root = temporary_root / "reserved-case-id"
            reserved = json.loads(deterministic_json_bytes(identity))
            reserved["case_id"] = "con"
            reserved_root.mkdir()
            (reserved_root / "case.json").write_bytes(
                deterministic_json_bytes(reserved)
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=reserved_root,
                cube=cube_root,
                expected_reason="case_id_path_reserved",
                expected_context={"case_id": "con"},
            )

            long_case_id_root = temporary_root / "long-case-id"
            long_case_id = json.loads(deterministic_json_bytes(identity))
            long_case_id["case_id"] = "a" * 97
            long_case_id_root.mkdir()
            (long_case_id_root / "case.json").write_bytes(
                deterministic_json_bytes(long_case_id)
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=long_case_id_root,
                cube=cube_root,
                expected_reason="case_id_path_too_long",
                expected_context={"case_id_length": 97, "maximum_length": 96},
            )

            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=one_descriptor_root,
                cube=cube_root,
                expected_reason="output_path_exists",
                expected_context={"artifact": "corpus_output"},
                prepare_output=_prepare_existing_corpus_output,
                assert_output=_assert_existing_corpus_output,
            )

    def test_nested_matching_symlinks_are_rejected_without_output(self) -> None:
        identity_fixture = FIXTURE_ROOT / "identity-2"
        with tempfile.TemporaryDirectory() as temp:
            temporary_root = Path(temp)
            descriptor_root = temporary_root / "descriptor-files"
            descriptor_root.mkdir()
            (descriptor_root / "case.json").write_bytes(
                (identity_fixture / "case.json").read_bytes()
            )

            cube_symlink_root = temporary_root / "cube-symlink-root"
            (cube_symlink_root / "nested").mkdir(parents=True)
            try:
                (cube_symlink_root / "nested" / "linked.cube").symlink_to(
                    identity_fixture / "input.cube"
                )
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"The test platform cannot create symlinks: {error}")

            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=descriptor_root,
                cube=cube_symlink_root,
                expected_reason="input_entry_unsupported",
                expected_context={"artifact": "cube_directory"},
            )

            descriptor_symlink_root = temporary_root / "descriptor-symlink-root"
            (descriptor_symlink_root / "nested").mkdir(parents=True)
            (descriptor_symlink_root / "nested" / "linked.case.json").symlink_to(
                identity_fixture / "case.json"
            )
            cube_root = temporary_root / "cube-files"
            cube_root.mkdir()
            (cube_root / "renamed-input.cube").write_bytes(
                (identity_fixture / "input.cube").read_bytes()
            )
            assert_deterministic_invalid_command(
                self,
                expected_code="INPUT_INVALID",
                descriptor=descriptor_symlink_root,
                cube=cube_root,
                expected_reason="input_entry_unsupported",
                expected_context={"artifact": "descriptor_directory"},
            )

    def test_unexpected_corpus_failure_is_status_three_and_publish_nothing(
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
        injected_message = "injected-corpus-internal-error-must-not-leak"

        with (
            tempfile.TemporaryDirectory() as temp,
            tempfile.TemporaryDirectory() as injection_temp,
        ):
            temporary_root = Path(temp)
            injection_root = Path(injection_temp)
            descriptor_root = temporary_root / "descriptors"
            cube_root = temporary_root / "materialized-cubes"
            _copy_descriptor_corpus(FIXTURE_ROOT, descriptor_root, reverse=False)
            self._materialize(cube_root, "97")
            (injection_root / "sitecustomize.py").write_text(
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

            results = []
            for index, seed in enumerate(("101", "103")):
                environment = _environment(seed)
                existing_python_path = environment.get("PYTHONPATH")
                python_paths = [str(injection_root)]
                if existing_python_path:
                    python_paths.append(existing_python_path)
                environment["PYTHONPATH"] = os.pathsep.join(python_paths)
                output_root = temporary_root / f"internal-error-output-{index}"
                result = run_harness(
                    descriptor=descriptor_root,
                    cube=cube_root,
                    output_directory=output_root,
                    environment=environment,
                )
                self.assertEqual(result.returncode, 3)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(result.stderr, expected_stderr)
                self.assertNotIn(injected_message.encode("ascii"), result.stderr)
                self.assertNotIn(b"Traceback", result.stderr)
                self.assertFalse(output_root.exists())
                results.append(result)

            self.assertEqual(results[0].stderr, results[1].stderr)


if __name__ == "__main__":
    unittest.main()
