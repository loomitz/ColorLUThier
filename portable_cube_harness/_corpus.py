"""Deterministic corpus orchestration behind the public command."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ._workflow import (
    HARNESS_VERSION,
    REPORT_SCHEMA_VERSION,
    HarnessInputError,
    _deterministic_json_bytes,
    _load_test_case,
    _provisional_evidence,
    _read_bytes,
    _run_case_bytes,
    run_case,
)


_MAX_CASE_ID_PATH_LENGTH = 96
_WINDOWS_RESERVED_PATH_NAMES = frozenset(
    {
        "aux",
        "con",
        "nul",
        "prn",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)


@dataclass(frozen=True)
class _CorpusCase:
    case_id: str
    cube_bytes: bytes
    descriptor_bytes: bytes


def _input_kind(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unsupported"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "unsupported"


def _directory_files(
    root: Path,
    *,
    artifact: str,
    accepts: Callable[[str], bool],
) -> tuple[Path, ...]:
    paths: list[Path] = []

    def fail_walk(_: OSError) -> None:
        raise HarnessInputError(
            "An input directory could not be enumerated.",
            reason="input_directory_unreadable",
            context={"artifact": artifact},
        )

    try:
        for directory, directory_names, file_names in os.walk(
            root,
            topdown=True,
            onerror=fail_walk,
            followlinks=False,
        ):
            directory_names.sort()
            for entry_name in sorted([*directory_names, *file_names]):
                if not accepts(entry_name):
                    continue
                candidate = Path(directory) / entry_name
                try:
                    mode = candidate.lstat().st_mode
                except OSError as error:
                    raise HarnessInputError(
                        "An input directory contains an unsupported matching entry.",
                        reason="input_entry_unsupported",
                        context={"artifact": artifact},
                    ) from error
                if not stat.S_ISREG(mode):
                    raise HarnessInputError(
                        "An input directory contains an unsupported matching entry.",
                        reason="input_entry_unsupported",
                        context={"artifact": artifact},
                    )
                paths.append(candidate)
    except HarnessInputError:
        raise
    except OSError as error:
        raise HarnessInputError(
            "An input directory could not be enumerated.",
            reason="input_directory_unreadable",
            context={"artifact": artifact},
        ) from error

    return tuple(
        sorted(paths, key=lambda path: path.relative_to(root).as_posix())
    )


def _descriptor_paths(root: Path) -> tuple[Path, ...]:
    return _directory_files(
        root,
        artifact="descriptor_directory",
        accepts=lambda name: name == "case.json" or name.endswith(".case.json"),
    )


def _cube_paths(root: Path) -> tuple[Path, ...]:
    return _directory_files(
        root,
        artifact="cube_directory",
        accepts=lambda name: name.endswith(".cube"),
    )


def _validate_case_id_path(case_id: str) -> None:
    if case_id in _WINDOWS_RESERVED_PATH_NAMES:
        raise HarnessInputError(
            "A corpus case identifier is reserved as a filesystem device name.",
            reason="case_id_path_reserved",
            context={"case_id": case_id},
        )
    if len(case_id) > _MAX_CASE_ID_PATH_LENGTH:
        raise HarnessInputError(
            "A corpus case identifier is too long for a portable artifact path.",
            reason="case_id_path_too_long",
            context={
                "case_id_length": len(case_id),
                "maximum_length": _MAX_CASE_ID_PATH_LENGTH,
            },
        )


def _prepare_corpus(descriptor_dir: Path, cube_dir: Path) -> tuple[_CorpusCase, ...]:
    descriptor_paths = _descriptor_paths(descriptor_dir)
    if not descriptor_paths:
        raise HarnessInputError(
            "The descriptor directory contains no test descriptors.",
            reason="descriptor_set_empty",
            context={"descriptor_count": 0},
        )

    descriptors = []
    for descriptor_path in descriptor_paths:
        descriptor_bytes = _read_bytes(descriptor_path, "test descriptor")
        descriptor = _load_test_case(descriptor_bytes)
        _validate_case_id_path(descriptor.case_id)
        descriptors.append(
            (descriptor.case_id, descriptor.cube_sha256, descriptor_bytes)
        )
    descriptors.sort(key=lambda item: item[0])

    for previous, current in zip(descriptors, descriptors[1:]):
        if previous[0] == current[0]:
            raise HarnessInputError(
                "The descriptor directory contains a duplicate case identifier.",
                reason="duplicate_case_id",
                context={"case_id": current[0]},
            )

    cube_index: dict[str, bytes] = {}
    for cube_path in _cube_paths(cube_dir):
        cube_bytes = _read_bytes(cube_path, "Cube fixture")
        cube_index.setdefault(hashlib.sha256(cube_bytes).hexdigest(), cube_bytes)

    cases: list[_CorpusCase] = []
    for case_id, cube_sha256, descriptor_bytes in descriptors:
        cube_bytes = cube_index.get(cube_sha256)
        if cube_bytes is None:
            raise HarnessInputError(
                "A descriptor Cube checksum is not available in the Cube directory.",
                reason="cube_fixture_not_found",
                context={"case_id": case_id, "cube_sha256": cube_sha256},
            )
        cases.append(
            _CorpusCase(
                case_id=case_id,
                cube_bytes=cube_bytes,
                descriptor_bytes=descriptor_bytes,
            )
        )
    return tuple(cases)


def _aggregate_bytes(entries: list[dict[str, object]]) -> bytes:
    failed_case_count = sum(entry["overall_result"] == "fail" for entry in entries)
    passed_case_count = len(entries) - failed_case_count
    return _deterministic_json_bytes(
        {
            "case_count": len(entries),
            "cases": entries,
            "evidence": _provisional_evidence(),
            "failed_case_count": failed_case_count,
            "harness_version": HARNESS_VERSION,
            "overall_result": "fail" if failed_case_count else "pass",
            "passed_case_count": passed_case_count,
            "report_schema_version": REPORT_SCHEMA_VERSION,
        }
    )


def _publish_corpus(
    cases: tuple[_CorpusCase, ...], output_dir: Path
) -> tuple[int, bytes]:
    if os.path.lexists(output_dir):
        raise HarnessInputError(
            "The corpus output directory must not already exist.",
            reason="output_path_exists",
            context={"artifact": "corpus_output"},
        )

    try:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_path = Path(
            tempfile.mkdtemp(
                dir=output_dir.parent,
                prefix=".portable-cube-corpus-",
            )
        )
    except OSError as error:
        raise HarnessInputError(
            "The corpus output could not be staged.",
            reason="output_staging_failed",
            context={"artifact": "corpus_output"},
        ) from error

    claimed_output = False
    published = False
    try:
        entries: list[dict[str, object]] = []
        overall_status = 0
        for corpus_case in cases:
            case_output = staging_path / "cases" / corpus_case.case_id
            case_status, report_bytes = _run_case_bytes(
                descriptor_bytes=corpus_case.descriptor_bytes,
                input_cube_bytes=corpus_case.cube_bytes,
                output_dir=case_output,
            )
            overall_status = max(overall_status, case_status)
            canonical_cube = (case_output / "canonical.cube").read_bytes()
            entries.append(
                {
                    "canonical_cube_sha256": hashlib.sha256(
                        canonical_cube
                    ).hexdigest(),
                    "case_id": corpus_case.case_id,
                    "overall_result": "pass" if case_status == 0 else "fail",
                    "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
                }
            )

        aggregate_bytes = _aggregate_bytes(entries)
        (staging_path / "report.json").write_bytes(aggregate_bytes)
        try:
            output_dir.mkdir()
        except FileExistsError as error:
            raise HarnessInputError(
                "The corpus output directory must not already exist.",
                reason="output_path_exists",
                context={"artifact": "corpus_output"},
            ) from error
        claimed_output = True
        os.rename(staging_path / "cases", output_dir / "cases")
        os.rename(staging_path / "report.json", output_dir / "report.json")
        published = True
        return overall_status, aggregate_bytes
    except HarnessInputError:
        raise
    except OSError as error:
        raise HarnessInputError(
            "The corpus output could not be written.",
            reason="output_publish_failed",
            context={"artifact": "corpus_output"},
        ) from error
    finally:
        if claimed_output and not published:
            shutil.rmtree(output_dir, ignore_errors=True)
        shutil.rmtree(staging_path, ignore_errors=True)


def run_corpus(
    *, descriptor_dir: Path, cube_dir: Path, output_dir: Path
) -> tuple[int, bytes]:
    cases = _prepare_corpus(descriptor_dir, cube_dir)
    return _publish_corpus(cases, output_dir)


def run_request(
    *, descriptor_path: Path, cube_path: Path, output_dir: Path
) -> tuple[int, bytes]:
    descriptor_kind = _input_kind(descriptor_path)
    cube_kind = _input_kind(cube_path)
    if descriptor_kind == "file" and cube_kind == "file":
        return run_case(
            descriptor_path=descriptor_path,
            cube_path=cube_path,
            output_dir=output_dir,
        )
    if descriptor_kind == "directory" and cube_kind == "directory":
        return run_corpus(
            descriptor_dir=descriptor_path,
            cube_dir=cube_path,
            output_dir=output_dir,
        )
    raise HarnessInputError(
        "Descriptor and Cube inputs must both be files or both be directories.",
        reason="input_kind_mismatch",
        context={"cube": cube_kind, "descriptor": descriptor_kind},
    )
