"""Command-line seam for the provisional Portable Cube conformance harness."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from ._workflow import (
    HarnessInputError,
    REPORT_SCHEMA_VERSION,
    _deterministic_json_bytes,
    run_case,
)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise HarnessInputError(f"The command invocation is invalid: {message}.")


def _error_bytes(code: str, message: str) -> bytes:
    return _deterministic_json_bytes(
        {
            "error": {"code": code, "message": message},
            "evidence_status": "provisional",
            "report_schema_version": REPORT_SCHEMA_VERSION,
        }
    )


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(
        prog="python -m portable_cube_harness",
        description=(
            "Run one provisional, test-only Portable Cube conformance case."
        ),
    )
    parser.add_argument("--descriptor", required=True, type=Path)
    parser.add_argument("--cube", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        exit_status, report_bytes = run_case(
            descriptor_path=args.descriptor,
            cube_path=args.cube,
            output_dir=args.output_dir,
        )
    except HarnessInputError as error:
        sys.stderr.buffer.write(_error_bytes("INPUT_INVALID", str(error)))
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
