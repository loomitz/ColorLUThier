"""Headless command-line adapter for the provisional engine vertical."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from ._limits import PORTABLE_CUBE_ENCODED_BYTES, REFERENCE_ENCODED_BYTES
from . import (
    ColorDocument,
    CommandStatus,
    Diagnostic,
    DocumentCommand,
    Interpolation,
    JobId,
    JobState,
    LoadPortableCube,
    OpenReferenceImage,
    ProvisionalImageFormat,
    RequestCanonicalPortableCubeExport,
    RequestPreview,
    RevisionBasis,
)


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class _CliFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        context: tuple[tuple[str, bool | float | int | str], ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context

    @classmethod
    def from_engine(cls, diagnostic: Diagnostic | None) -> _CliFailure:
        if diagnostic is None:
            return cls(
                "ENGINE_COMMAND_REJECTED",
                "The engine rejected the command without a diagnostic.",
            )
        return cls(
            diagnostic.code,
            diagnostic.message,
            context=tuple((field.name, field.value) for field in diagnostic.context),
        )


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _CliFailure(
            "CLI_ARGUMENT_INVALID",
            "The command-line arguments are invalid.",
        )


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="python -m colorluthier_engine",
        description=(
            "Run the provisional ColorLUThier open, evaluate, and canonical "
            "Portable Cube export vertical without a display server."
        ),
    )
    parser.add_argument(
        "--reference",
        required=True,
        type=Path,
        metavar="FILE",
        help="RGB8 PPM P6 or non-interlaced RGB/RGBA PNG input.",
    )
    parser.add_argument(
        "--reference-format",
        choices=(
            "auto",
            ProvisionalImageFormat.PPM_P6_RGB8.value,
            ProvisionalImageFormat.PNG_RGB8.value,
        ),
        default="auto",
        help="Provisional decoder selection; auto uses the encoded signature.",
    )
    parser.add_argument(
        "--cube",
        required=True,
        type=Path,
        metavar="FILE",
        help="Strict Portable Cube input.",
    )
    parser.add_argument(
        "--interpolation",
        required=True,
        choices=tuple(mode.value for mode in Interpolation),
        help="Explicit CPU interpolation mode.",
    )
    parser.add_argument(
        "--mix",
        type=float,
        default=1.0,
        help="Provisional preview mix in the closed interval from 0 through 1.",
    )
    parser.add_argument(
        "--bypass",
        action="store_true",
        help="Preserve the loaded transformation while bypassing preview evaluation.",
    )
    parser.add_argument(
        "--export-output",
        type=Path,
        metavar="FILE",
        help=(
            "Optionally replace this file with provisional canonicalized imported "
            "Cube bytes; this is not a color-managed product export."
        ),
    )
    return parser


def _read_bounded(path: Path, maximum: int, *, role: str) -> bytes:
    descriptor: int | None = None
    try:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            encoded = stream.read(maximum + 1)
    except OSError:
        raise _CliFailure(
            "CLI_INPUT_UNAVAILABLE",
            "A required input is unavailable as a regular file.",
            context=(("role", role),),
        ) from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass

    if len(encoded) > maximum:
        raise _CliFailure(
            "CLI_INPUT_RESOURCE_LIMIT",
            "A required input exceeds its provisional byte limit.",
            context=(("maximum_bytes", maximum), ("role", role)),
        )
    return encoded


def _reference_format(
    selection: str,
    encoded: bytes,
) -> ProvisionalImageFormat:
    if selection != "auto":
        return ProvisionalImageFormat(selection)
    if encoded.startswith(b"P6"):
        return ProvisionalImageFormat.PPM_P6_RGB8
    if encoded.startswith(_PNG_SIGNATURE):
        return ProvisionalImageFormat.PNG_RGB8
    raise _CliFailure(
        "CLI_REFERENCE_FORMAT_UNDETECTED",
        "The provisional reference-image format could not be detected.",
    )


def _apply(document: ColorDocument, command: DocumentCommand) -> JobId | None:
    result = document.apply(command)
    if result.status is CommandStatus.REJECTED:
        raise _CliFailure.from_engine(result.diagnostic)
    return result.job_id


def _completed_job(document: ColorDocument, job_id: JobId | None) -> None:
    if job_id is None:
        raise _CliFailure(
            "ENGINE_JOB_ID_MISSING",
            "The engine accepted a job without returning its identifier.",
        )
    snapshot = document.snapshot()
    job = next((item for item in snapshot.jobs if item.job_id == job_id), None)
    if job is None:
        raise _CliFailure(
            "ENGINE_JOB_MISSING",
            "The accepted engine job is absent from the current snapshot.",
        )
    if job.state is JobState.SUCCEEDED:
        return
    if job.diagnostic is not None:
        raise _CliFailure.from_engine(job.diagnostic)
    raise _CliFailure(
        "ENGINE_JOB_INCOMPLETE",
        "The inline engine job did not complete successfully.",
        context=(("state", job.state.value),),
    )


def _write_atomically(path: Path, encoded: bytes) -> None:
    descriptor: int | None = None
    temporary_path: str | None = None
    try:
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError:
        raise _CliFailure(
            "CLI_EXPORT_PUBLICATION_FAILED",
            "The canonical Cube artifact could not be published atomically.",
        ) from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def _basis_record(basis: RevisionBasis) -> dict[str, int | None]:
    return {
        "document_revision": basis.document.value,
        "reference_revision": (
            None if basis.reference is None else basis.reference.value
        ),
        "transformation_revision": (
            None if basis.transformation is None else basis.transformation.value
        ),
    }


def _success_record(document: ColorDocument, *, export_written: bool) -> dict[str, Any]:
    snapshot = document.snapshot()
    preview = snapshot.preview
    artifact = snapshot.canonical_cube_export
    if preview is None or artifact is None:
        raise _CliFailure(
            "ENGINE_RESULT_MISSING",
            "The completed vertical did not publish every expected result.",
        )

    return {
        "canonical_export": {
            "artifact_id": artifact.artifact_id.value,
            "basis": _basis_record(artifact.basis),
            "byte_count": artifact.byte_count,
            "job_id": artifact.job_id.value,
            "ordinary_export_status": artifact.ordinary_export_status,
            "semantics": artifact.semantics,
            "written": export_written,
        },
        "document": {
            "document_revision": snapshot.document_revision.value,
            "reference_revision": (
                None if snapshot.reference is None else snapshot.reference.revision.value
            ),
            "snapshot_revision": snapshot.snapshot_revision.value,
            "transformation_revision": (
                None
                if snapshot.transformation is None
                else snapshot.transformation.revision.value
            ),
        },
        "jobs": [
            {
                "completed_units": job.progress.completed_units,
                "job_id": job.job_id.value,
                "purpose": job.purpose.value,
                "state": job.state.value,
                "total_units": job.progress.total_units,
            }
            for job in snapshot.jobs
        ],
        "ok": True,
        "preview": {
            "basis": _basis_record(preview.basis),
            "encoding": preview.processed.encoding.value,
            "height": preview.processed.height,
            "job_id": preview.job_id.value,
            "original_surface_id": preview.original.surface_id.value,
            "processed_surface_id": preview.processed.surface_id.value,
            "width": preview.processed.width,
        },
        "provisional": True,
    }


def _failure_record(error: _CliFailure) -> dict[str, Any]:
    return {
        "diagnostic": {
            "code": error.code,
            "context": [
                {"name": name, "value": value} for name, value in error.context
            ],
            "message": error.message,
        },
        "ok": False,
        "provisional": True,
    }


def _emit(record: dict[str, Any], *, stream: Any) -> None:
    stream.write(
        json.dumps(
            record,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def _run(arguments: argparse.Namespace) -> dict[str, Any]:
    reference_bytes = _read_bounded(
        arguments.reference,
        REFERENCE_ENCODED_BYTES,
        role="reference",
    )
    cube_bytes = _read_bounded(
        arguments.cube,
        PORTABLE_CUBE_ENCODED_BYTES,
        role="portable-cube",
    )
    image_format = _reference_format(arguments.reference_format, reference_bytes)

    document = ColorDocument()
    _apply(
        document,
        OpenReferenceImage(
            encoded=reference_bytes,
            image_format=image_format,
        ),
    )
    _apply(
        document,
        LoadPortableCube(
            encoded=cube_bytes,
            interpolation=Interpolation(arguments.interpolation),
            bypass=arguments.bypass,
            mix=arguments.mix,
        ),
    )
    preview_job_id = _apply(document, RequestPreview())
    _completed_job(document, preview_job_id)
    export_job_id = _apply(document, RequestCanonicalPortableCubeExport())
    _completed_job(document, export_job_id)

    artifact = document.snapshot().canonical_cube_export
    if artifact is None:
        raise _CliFailure(
            "ENGINE_EXPORT_MISSING",
            "The completed export job did not publish an artifact.",
        )

    export_written = arguments.export_output is not None
    if export_written:
        _write_atomically(arguments.export_output, artifact.encoded)
    return _success_record(document, export_written=export_written)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        record = _run(arguments)
    except _CliFailure as error:
        _emit(_failure_record(error), stream=sys.stderr)
        return 2
    except Exception:
        error = _CliFailure(
            "CLI_INTERNAL_ERROR",
            "The headless vertical failed without publishing a success record.",
        )
        _emit(_failure_record(error), stream=sys.stderr)
        return 3

    _emit(record, stream=sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
