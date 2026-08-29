"""Materialize deterministic Cube inputs for the complete test corpus."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = REPOSITORY_ROOT / "tests" / "fixtures"


class MaterializationError(Exception):
    """A generated fixture did not match its independently recorded bytes."""


@dataclass(frozen=True)
class GeneratedFixture:
    relative_path: Path
    lattice_size: int
    expected_byte_count: int
    expected_sha256: str
    transform_indices: Callable[[int, int, int], tuple[int, int, int]]


GENERATED_FIXTURES = (
    GeneratedFixture(
        relative_path=Path("identity-33") / "input.cube",
        lattice_size=33,
        expected_byte_count=738_357,
        expected_sha256=(
            "ed09443c84100f8d9620bb4fc22325e56b2777577b37323cc1ba940d0472ba60"
        ),
        transform_indices=lambda red, green, blue: (red, green, blue),
    ),
    GeneratedFixture(
        relative_path=Path("red-blue-swap-65") / "input.cube",
        lattice_size=65,
        expected_byte_count=6_514_965,
        expected_sha256=(
            "4664568c299ffcf31164a4d504524c322594fd5f7fe66da26874e81b96e08d30"
        ),
        transform_indices=lambda red, green, blue: (blue, green, red),
    ),
)


def _tracked_input_cubes() -> tuple[Path, ...]:
    return tuple(
        sorted(
            FIXTURES_ROOT.rglob("input.cube"),
            key=lambda path: path.relative_to(FIXTURES_ROOT).as_posix(),
        )
    )


def _copy_tracked_inputs(staging_root: Path) -> None:
    for source in _tracked_input_cubes():
        relative_path = source.relative_to(FIXTURES_ROOT)
        destination = staging_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def _write_generated_fixture(
    staging_root: Path, fixture: GeneratedFixture
) -> None:
    destination = staging_root / fixture.relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)

    denominator = fixture.lattice_size - 1
    axis_tokens = tuple(
        format(index / denominator, ".9g")
        for index in range(fixture.lattice_size)
    )
    digest = hashlib.sha256()
    byte_count = 0

    with destination.open("wb") as output:
        header = f"LUT_3D_SIZE {fixture.lattice_size}\n".encode("ascii")
        output.write(header)
        digest.update(header)
        byte_count += len(header)

        for blue in range(fixture.lattice_size):
            for green in range(fixture.lattice_size):
                for red in range(fixture.lattice_size):
                    output_indices = fixture.transform_indices(red, green, blue)
                    row = (
                        " ".join(axis_tokens[index] for index in output_indices)
                        + "\n"
                    ).encode("ascii")
                    output.write(row)
                    digest.update(row)
                    byte_count += len(row)

    actual_sha256 = digest.hexdigest()
    if (
        byte_count != fixture.expected_byte_count
        or actual_sha256 != fixture.expected_sha256
    ):
        raise MaterializationError(
            "Generated Cube bytes do not match the independently recorded "
            f"size and SHA-256 for {fixture.relative_path.as_posix()}."
        )


def materialize(output_directory: Path) -> None:
    if os.path.lexists(output_directory):
        raise FileExistsError(
            f"Output directory already exists: {output_directory}"
        )

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_directory.parent,
        prefix=".portable-cube-corpus-",
    ) as temporary_directory:
        staging_root = Path(temporary_directory) / "inputs"
        staging_root.mkdir()
        _copy_tracked_inputs(staging_root)
        for fixture in GENERATED_FIXTURES:
            _write_generated_fixture(staging_root, fixture)

        if os.path.lexists(output_directory):
            raise FileExistsError(
                f"Output directory already exists: {output_directory}"
            )
        staging_root.rename(output_directory)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize deterministic Cube inputs for the provisional test "
            "corpus."
        )
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        materialize(args.output_dir)
    except (FileExistsError, MaterializationError, OSError) as error:
        _parser().exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
