"""Command-line seam for the provisional Portable Cube conformance harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from ._corpus import run_request
from ._workflow import (
    HarnessInputError,
    REPORT_SCHEMA_VERSION,
    _deterministic_json_bytes,
)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise HarnessInputError(f"The command invocation is invalid: {message}.")


def _error_bytes(
    code: str,
    message: str,
    *,
    reason: str | None = None,
    context: dict[str, object] | None = None,
) -> bytes:
    error: dict[str, object] = {"code": code, "message": message}
    if reason is not None:
        error["reason"] = reason
    if context is not None:
        error["context"] = context
    return _deterministic_json_bytes(
        {
            "error": error,
            "evidence_status": "provisional",
            "report_schema_version": REPORT_SCHEMA_VERSION,
        }
    )


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(
        prog="python -m portable_cube_harness",
        description=(
            "Run one case or corpus with the provisional, test-only Portable "
            "Cube conformance harness."
        ),
    )
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--cube", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        exit_status, report_bytes = run_request(
            descriptor_path=args.descriptor,
            cube_path=args.cube,
            output_dir=args.output_dir,
        )
    except HarnessInputError as error:
        sys.stderr.buffer.write(
            _error_bytes(
                error.code,
                str(error),
                reason=error.reason,
                context=error.context,
            )
        )
        return 2
    except Exception:
        sys.stderr.buffer.write(
            _error_bytes(
                "INTERNAL_ERROR",
                "The provisional conformance harness failed unexpectedly.",
            )
        )
        return 3

    sys.stdout.buffer.write(report_bytes)
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
