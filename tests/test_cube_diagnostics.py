from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from acceptance_support import (
    REPOSITORY_ROOT,
    assert_deterministic_invalid_command,
    deterministic_json_bytes,
    run_harness,
)


IDENTITY_FIXTURE_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures" / "identity-2"
IDENTITY_DESCRIPTOR_PATH = IDENTITY_FIXTURE_DIRECTORY / "case.json"
IDENTITY_SAMPLE_ROWS = (
    "0.0 0.0 0.0",
    "1.0 0.0 0.0",
    "0.0 1.0 0.0",
    "1.0 1.0 0.0",
    "0.0 0.0 1.0",
    "1.0 0.0 1.0",
    "0.0 1.0 1.0",
    "1.0 1.0 1.0",
)


@dataclass(frozen=True)
class InvalidCubeCase:
    name: str
    cube_bytes: bytes
    code: str
    reason: str
    context: dict[str, object]


def _cube_bytes(*lines: str) -> bytes:
    return ("\n".join(lines) + "\n").encode("ascii")


def _identity_cube_with_first_row(first_row: str) -> bytes:
    return _cube_bytes(
        "# Provisional ColorLUThier malformed Cube fixture.",
        "LUT_3D_SIZE 2",
        first_row,
        *IDENTITY_SAMPLE_ROWS[1:],
    )


def _descriptor_bytes_for(cube_bytes: bytes) -> bytes:
    descriptor = json.loads(IDENTITY_DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    descriptor["cube"]["sha256"] = hashlib.sha256(cube_bytes).hexdigest()
    return deterministic_json_bytes(descriptor)


class CubeDiagnosticsAcceptanceTest(unittest.TestCase):
    def test_malformed_and_non_portable_cube_artifacts_have_stable_diagnostics(
        self,
    ) -> None:
        huge_header = "H" * 5000
        huge_size = "9" * 5000
        cases = (
            InvalidCubeCase(
                name="non-ascii-text",
                cube_bytes=(
                    b"# \xc3\xa9\nLUT_3D_SIZE 2\n"
                    + ("\n".join(IDENTITY_SAMPLE_ROWS) + "\n").encode("ascii")
                ),
                code="CUBE_ENCODING_INVALID",
                reason="non_ascii_text",
                context={"byte_offset": 2, "byte_value": 195},
            ),
            InvalidCubeCase(
                name="missing-size-declaration",
                cube_bytes=_cube_bytes(
                    "# Cube fixture without a size declaration.",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="missing_size_declaration",
                context={"declaration": "LUT_3D_SIZE"},
            ),
            InvalidCubeCase(
                name="duplicate-size-declaration",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a duplicate size declaration.",
                    "LUT_3D_SIZE 2",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="duplicate_size_declaration",
                context={"declaration": "LUT_3D_SIZE", "line": 3},
            ),
            InvalidCubeCase(
                name="size-declaration-missing-token",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a malformed size declaration.",
                    "LUT_3D_SIZE",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="malformed_size_declaration",
                context={
                    "actual_tokens": 1,
                    "declaration": "LUT_3D_SIZE",
                    "expected_tokens": 2,
                    "line": 2,
                },
            ),
            InvalidCubeCase(
                name="size-declaration-extra-token",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a malformed size declaration.",
                    "LUT_3D_SIZE 2 extra",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="malformed_size_declaration",
                context={
                    "actual_tokens": 3,
                    "declaration": "LUT_3D_SIZE",
                    "expected_tokens": 2,
                    "line": 2,
                },
            ),
            InvalidCubeCase(
                name="unsupported-lut-1d-size-directive",
                cube_bytes=_cube_bytes(
                    "LUT_1D_SIZE 2",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unsupported_directive",
                context={
                    "directive": "LUT_1D_SIZE",
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="unsupported-title-directive",
                cube_bytes=_cube_bytes(
                    'TITLE "Unsupported title"',
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unsupported_directive",
                context={
                    "directive": "TITLE",
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="unsupported-domain-min-directive",
                cube_bytes=_cube_bytes(
                    "DOMAIN_MIN 0.0 0.0 0.0",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unsupported_directive",
                context={
                    "directive": "DOMAIN_MIN",
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="unsupported-domain-max-directive",
                cube_bytes=_cube_bytes(
                    "DOMAIN_MAX 1.0 1.0 1.0",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unsupported_directive",
                context={
                    "directive": "DOMAIN_MAX",
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="unsupported-lut-1d-input-range-directive",
                cube_bytes=_cube_bytes(
                    "LUT_1D_INPUT_RANGE 0.0 1.0",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unsupported_directive",
                context={
                    "directive": "LUT_1D_INPUT_RANGE",
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="unsupported-lut-3d-input-range-directive",
                cube_bytes=_cube_bytes(
                    "LUT_3D_INPUT_RANGE 0.0 1.0",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unsupported_directive",
                context={
                    "directive": "LUT_3D_INPUT_RANGE",
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="unsupported-directive-after-size",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with an unsupported sample-table directive.",
                    "LUT_3D_SIZE 2",
                    "DOMAIN_MIN 0.0 0.0 0.0",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unsupported_directive",
                context={
                    "directive": "DOMAIN_MIN",
                    "line": 3,
                    "section": "sample_table",
                },
            ),
            InvalidCubeCase(
                name="unknown-header",
                cube_bytes=_cube_bytes(
                    "UNKNOWN_HEADER 0.0 1.0",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unknown_header",
                context={
                    "header": "UNKNOWN_HEADER",
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="unknown-header-after-size",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with an unknown sample-table header.",
                    "LUT_3D_SIZE 2",
                    "UNKNOWN_HEADER 0.0 1.0",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unknown_header",
                context={
                    "header": "UNKNOWN_HEADER",
                    "line": 3,
                    "section": "sample_table",
                },
            ),
            InvalidCubeCase(
                name="huge-unknown-header-has-bounded-context",
                cube_bytes=_cube_bytes(
                    huge_header,
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="unknown_header",
                context={
                    "header_length": 5000,
                    "header_preview": "H" * 64,
                    "line": 1,
                    "section": "preamble",
                },
            ),
            InvalidCubeCase(
                name="standalone-comment-after-size",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a comment after the size declaration.",
                    "LUT_3D_SIZE 2",
                    "# Comments are not portable in the sample table.",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="comment_after_size",
                context={"line": 3, "section": "sample_table"},
            ),
            InvalidCubeCase(
                name="inline-comment-after-size",
                cube_bytes=_identity_cube_with_first_row(
                    "0.0 0.0 0.0 # Inline comments are not portable."
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="comment_after_size",
                context={"line": 3, "section": "sample_table"},
            ),
            InvalidCubeCase(
                name="blank-line-after-size",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a blank line after the size declaration.",
                    "LUT_3D_SIZE 2",
                    "",
                    *IDENTITY_SAMPLE_ROWS,
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="blank_line_after_size",
                context={"line": 3, "section": "sample_table"},
            ),
            InvalidCubeCase(
                name="too-few-sample-rows",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with too few sample rows.",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS[:-1],
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="too_few_sample_rows",
                context={
                    "actual_rows": 7,
                    "expected_rows": 8,
                    "lattice_size": 2,
                },
            ),
            InvalidCubeCase(
                name="too-many-sample-rows",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with too many sample rows.",
                    "LUT_3D_SIZE 2",
                    *IDENTITY_SAMPLE_ROWS,
                    "0.5 0.5 0.5",
                ),
                code="CUBE_STRUCTURE_INVALID",
                reason="too_many_sample_rows",
                context={
                    "actual_rows": 9,
                    "expected_rows": 8,
                    "lattice_size": 2,
                    "line": 11,
                },
            ),
            InvalidCubeCase(
                name="too-few-sample-tokens",
                cube_bytes=_identity_cube_with_first_row("0.0 0.0"),
                code="CUBE_STRUCTURE_INVALID",
                reason="sample_token_count",
                context={
                    "actual_tokens": 2,
                    "expected_tokens": 3,
                    "line": 3,
                    "sample_row": 1,
                },
            ),
            InvalidCubeCase(
                name="too-many-sample-tokens",
                cube_bytes=_identity_cube_with_first_row("0.0 0.0 0.0 0.0"),
                code="CUBE_STRUCTURE_INVALID",
                reason="sample_token_count",
                context={
                    "actual_tokens": 4,
                    "expected_tokens": 3,
                    "line": 3,
                    "sample_row": 1,
                },
            ),
            InvalidCubeCase(
                name="size-not-integer",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a non-integer lattice size.",
                    "LUT_3D_SIZE 2.0",
                ),
                code="CUBE_LATTICE_SIZE_INVALID",
                reason="size_not_integer",
                context={"line": 2, "maximum": 65, "minimum": 2},
            ),
            InvalidCubeCase(
                name="lattice-size-below-minimum",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a lattice size below the minimum.",
                    "LUT_3D_SIZE 1",
                ),
                code="CUBE_LATTICE_SIZE_INVALID",
                reason="size_out_of_range",
                context={"line": 2, "maximum": 65, "minimum": 2, "value": 1},
            ),
            InvalidCubeCase(
                name="lattice-size-above-maximum",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with a lattice size above the maximum.",
                    "LUT_3D_SIZE 66",
                ),
                code="CUBE_LATTICE_SIZE_INVALID",
                reason="size_out_of_range",
                context={"line": 2, "maximum": 65, "minimum": 2, "value": 66},
            ),
            InvalidCubeCase(
                name="huge-lattice-size",
                cube_bytes=_cube_bytes(
                    "# Cube fixture with an excessively large lattice size.",
                    f"LUT_3D_SIZE {huge_size}",
                ),
                code="CUBE_LATTICE_SIZE_INVALID",
                reason="size_out_of_range",
                context={
                    "line": 2,
                    "maximum": 65,
                    "minimum": 2,
                    "value_digits": 5000,
                },
            ),
            InvalidCubeCase(
                name="malformed-decimal",
                cube_bytes=_identity_cube_with_first_row("0..0 0.0 0.0"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="malformed_decimal",
                context={"component": 1, "line": 3, "sample_row": 1},
            ),
            InvalidCubeCase(
                name="hexadecimal-number",
                cube_bytes=_identity_cube_with_first_row("0.0 0x1p+0 0.0"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="hexadecimal_number",
                context={"component": 2, "line": 3, "sample_row": 1},
            ),
            InvalidCubeCase(
                name="locale-dependent-number",
                cube_bytes=_identity_cube_with_first_row("0.0 0.0 0,5"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="locale_dependent_number",
                context={"component": 3, "line": 3, "sample_row": 1},
            ),
            InvalidCubeCase(
                name="nan-number",
                cube_bytes=_identity_cube_with_first_row("NaN 0.0 0.0"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="non_finite_number",
                context={"component": 1, "line": 3, "sample_row": 1},
            ),
            InvalidCubeCase(
                name="uppercase-nan-number",
                cube_bytes=_identity_cube_with_first_row("NAN 0.0 0.0"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="non_finite_number",
                context={"component": 1, "line": 3, "sample_row": 1},
            ),
            InvalidCubeCase(
                name="positive-infinity-number",
                cube_bytes=_identity_cube_with_first_row("0.0 Infinity 0.0"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="non_finite_number",
                context={"component": 2, "line": 3, "sample_row": 1},
            ),
            InvalidCubeCase(
                name="negative-infinity-number",
                cube_bytes=_identity_cube_with_first_row("0.0 0.0 -Infinity"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="non_finite_number",
                context={"component": 3, "line": 3, "sample_row": 1},
            ),
            InvalidCubeCase(
                name="number-outside-binary32-range",
                cube_bytes=_identity_cube_with_first_row("1e39 0.0 0.0"),
                code="CUBE_SAMPLE_VALUE_INVALID",
                reason="outside_binary32_range",
                context={"component": 1, "line": 3, "sample_row": 1},
            ),
        )

        for case in cases:
            with self.subTest(case=case.name):
                assert_deterministic_invalid_command(
                    self,
                    descriptor_bytes=_descriptor_bytes_for(case.cube_bytes),
                    cube_bytes=case.cube_bytes,
                    expected_code=case.code,
                    expected_reason=case.reason,
                    expected_context=case.context,
                )

    def test_leading_blank_lines_and_comments_remain_valid(self) -> None:
        cube_bytes = _cube_bytes(
            "",
            "# First leading Portable Cube comment.",
            "",
            "# Second leading Portable Cube comment.",
            "LUT_3D_SIZE 2",
            *IDENTITY_SAMPLE_ROWS,
        )

        with tempfile.TemporaryDirectory() as temp:
            temporary_directory = Path(temp)
            cube_path = temporary_directory / "leading-blanks-and-comments.cube"
            descriptor_path = temporary_directory / "leading-blanks-and-comments.case.json"
            output_directory = temporary_directory / "artifacts"
            cube_path.write_bytes(cube_bytes)
            descriptor_path.write_bytes(_descriptor_bytes_for(cube_bytes))

            result = run_harness(
                descriptor=descriptor_path,
                cube=cube_path,
                output_directory=output_directory,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, b"")
            self.assertEqual(
                sorted(path.name for path in output_directory.iterdir()),
                ["canonical.cube", "report.json"],
            )
            report_bytes = (output_directory / "report.json").read_bytes()
            self.assertEqual(result.stdout, report_bytes)
            report = json.loads(report_bytes)
            self.assertEqual(
                report["hashes"]["input_cube_sha256"],
                hashlib.sha256(cube_bytes).hexdigest(),
            )
            self.assertEqual(report["overall_result"], "pass")


if __name__ == "__main__":
    unittest.main()
