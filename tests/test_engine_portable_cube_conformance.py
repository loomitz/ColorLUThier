from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from colorluthier_engine import (
    ColorDocument,
    CommandStatus,
    ConfigureColorTransformation,
    Interpolation,
    JobState,
    LoadPortableCube,
    OpenReferenceImage,
    ProvisionalImageFormat,
    RequestCanonicalPortableCubeExport,
    RequestPreview,
)


RGB = tuple[float, float, float]
RGB8 = tuple[int, int, int]
Oracle = Callable[[RGB], RGB]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_ROOT = REPOSITORY_ROOT / "tests" / "fixtures"
CORPUS_MATERIALIZER = REPOSITORY_ROOT / "tests" / "materialize_portable_cube_corpus.py"

# A binary32 result in [0, 1] has an ulp no larger than 2^-23. This four-ulp
# allowance covers the documented binary64 interpolation accumulation followed
# by one binary32 surface rounding, while remaining four times stricter than the
# existing corpus gate of 2^-20.
DERIVED_BINARY32_TOLERANCE = 2.0**-21

# RGB8 makes every preview input independently recoverable as byte / 255. The
# asymmetric probes cover endpoints, interiors, pair-equality boundaries, and
# both sides of boundaries used by the interpolation-divergence fixture.
PROBE_PIXELS: tuple[RGB8, ...] = (
    (0, 0, 0),
    (255, 255, 255),
    (0, 255, 91),
    (255, 53, 197),
    (1, 57, 229),
    (254, 151, 17),
    (42, 107, 221),
    (191, 191, 64),
    (195, 191, 64),
    (187, 191, 64),
    (191, 64, 191),
    (64, 191, 191),
    (128, 128, 128),
)


def _identity(input_rgb: RGB) -> RGB:
    return input_rgb


def _red_blue_swap(input_rgb: RGB) -> RGB:
    red, green, blue = input_rgb
    return (blue, green, red)


def _affine_cross_channel(input_rgb: RGB) -> RGB:
    red, green, blue = input_rgb
    return (
        (((0.0625 + 0.5 * red) + 0.25 * green) + 0.125 * blue),
        (((0.125 + 0.125 * red) + 0.375 * green) + 0.25 * blue),
        (((0.1875 + 0.25 * red) + 0.125 * green) + 0.375 * blue),
    )


_NONLINEAR_BINARY32_KNOTS = (
    0.0,
    0.2500057220458984375,
    0.50000762939453125,
    0.7500057220458984375,
    1.0,
)


def _nonlinear_chord(component: float) -> float:
    position = component * 4.0
    lower_index = min(int(position), 3)
    fraction = position - lower_index
    lower = _NONLINEAR_BINARY32_KNOTS[lower_index]
    upper = _NONLINEAR_BINARY32_KNOTS[lower_index + 1]
    return lower + fraction * (upper - lower)


def _nonlinear_separable(input_rgb: RGB) -> RGB:
    return tuple(_nonlinear_chord(component) for component in input_rgb)  # type: ignore[return-value]


def _pair_product(input_rgb: RGB) -> RGB:
    red, green, blue = input_rgb
    return (red * green, red * blue, green * blue)


def _pair_minimum(input_rgb: RGB) -> RGB:
    red, green, blue = input_rgb
    return (min(red, green), min(red, blue), min(green, blue))


@dataclass(frozen=True)
class _ConformanceCase:
    name: str
    cube_path: Path
    canonical_path: Path
    trilinear_oracle: Oracle
    tetrahedral_oracle: Oracle
    require_exact_binary32: bool = False


def _ppm(pixels: tuple[RGB8, ...]) -> bytes:
    payload = bytes(component for pixel in pixels for component in pixel)
    return f"P6\n{len(pixels)} 1\n255\n".encode("ascii") + payload


def _normalized(pixel: RGB8) -> RGB:
    return tuple(component / 255.0 for component in pixel)  # type: ignore[return-value]


def _surface_pixels(encoded: bytes) -> tuple[RGB, ...]:
    return tuple(struct.iter_unpack(">fff", encoded))


class EnginePortableCubeConformanceTests(unittest.TestCase):
    def test_public_color_document_matches_the_synthetic_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            materialized_root = Path(temporary_directory) / "portable-cube-inputs"
            materialization = subprocess.run(
                [
                    sys.executable,
                    str(CORPUS_MATERIALIZER),
                    "--output-dir",
                    str(materialized_root),
                ],
                cwd=REPOSITORY_ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(materialization.returncode, 0, materialization.stderr)
            self.assertEqual(materialization.stdout, b"")
            self.assertEqual(materialization.stderr, b"")

            cases = (
                _ConformanceCase(
                    name="identity-33",
                    cube_path=materialized_root / "identity-33" / "input.cube",
                    canonical_path=(
                        materialized_root / "identity-33" / "input.cube"
                    ),
                    trilinear_oracle=_identity,
                    tetrahedral_oracle=_identity,
                    require_exact_binary32=True,
                ),
                _ConformanceCase(
                    name="red-blue-swap-65",
                    cube_path=(
                        materialized_root / "red-blue-swap-65" / "input.cube"
                    ),
                    canonical_path=(
                        materialized_root / "red-blue-swap-65" / "input.cube"
                    ),
                    trilinear_oracle=_red_blue_swap,
                    tetrahedral_oracle=_red_blue_swap,
                    require_exact_binary32=True,
                ),
                _ConformanceCase(
                    name="affine-cross-channel-3",
                    cube_path=(
                        FIXTURES_ROOT / "affine-cross-channel-3" / "input.cube"
                    ),
                    canonical_path=(
                        FIXTURES_ROOT
                        / "affine-cross-channel-3"
                        / "expected.canonical.cube"
                    ),
                    trilinear_oracle=_affine_cross_channel,
                    tetrahedral_oracle=_affine_cross_channel,
                ),
                _ConformanceCase(
                    name="nonlinear-separable-5",
                    cube_path=(
                        FIXTURES_ROOT / "nonlinear-separable-5" / "input.cube"
                    ),
                    canonical_path=(
                        FIXTURES_ROOT
                        / "nonlinear-separable-5"
                        / "expected.canonical.cube"
                    ),
                    trilinear_oracle=_nonlinear_separable,
                    tetrahedral_oracle=_nonlinear_separable,
                ),
                _ConformanceCase(
                    name="interpolation-divergence-2",
                    cube_path=(
                        FIXTURES_ROOT
                        / "interpolation-divergence-2"
                        / "input.cube"
                    ),
                    canonical_path=(
                        FIXTURES_ROOT
                        / "interpolation-divergence-2"
                        / "expected.canonical.cube"
                    ),
                    trilinear_oracle=_pair_product,
                    tetrahedral_oracle=_pair_minimum,
                ),
            )

            for case in cases:
                with self.subTest(case=case.name):
                    self._assert_case(case)

    def _assert_case(self, case: _ConformanceCase) -> None:
        cube_bytes = case.cube_path.read_bytes()
        expected_canonical = case.canonical_path.read_bytes()
        source_bytes = _ppm(PROBE_PIXELS)
        expected_original = b"".join(
            struct.pack(">fff", *_normalized(pixel)) for pixel in PROBE_PIXELS
        )

        document = ColorDocument()
        opened = document.apply(
            OpenReferenceImage(
                encoded=source_bytes,
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(opened.status, CommandStatus.COMMITTED)

        loaded = document.apply(
            LoadPortableCube(
                encoded=cube_bytes,
                interpolation=Interpolation.TRILINEAR,
            )
        )
        self.assertEqual(loaded.status, CommandStatus.COMMITTED)

        exported = document.apply(RequestCanonicalPortableCubeExport())
        self.assertEqual(exported.status, CommandStatus.ACCEPTED)
        self.assertIsNotNone(exported.snapshot.canonical_cube_export)
        artifact = exported.snapshot.canonical_cube_export
        self.assertEqual(artifact.encoded, expected_canonical)
        self.assertEqual(artifact.byte_count, len(expected_canonical))
        self.assertEqual(exported.snapshot.jobs[-1].state, JobState.SUCCEEDED)

        trilinear = document.apply(RequestPreview())
        self._assert_preview(
            trilinear,
            case.trilinear_oracle,
            expected_original,
            require_exact_binary32=case.require_exact_binary32,
        )

        configured = document.apply(
            ConfigureColorTransformation(interpolation=Interpolation.TETRAHEDRAL)
        )
        self.assertEqual(configured.status, CommandStatus.COMMITTED)
        tetrahedral = document.apply(RequestPreview())
        self._assert_preview(
            tetrahedral,
            case.tetrahedral_oracle,
            expected_original,
            require_exact_binary32=case.require_exact_binary32,
        )

    def _assert_preview(
        self,
        result,
        oracle: Oracle,
        expected_original: bytes,
        *,
        require_exact_binary32: bool,
    ) -> None:
        self.assertEqual(result.status, CommandStatus.ACCEPTED)
        self.assertIsNotNone(result.snapshot.preview)
        preview = result.snapshot.preview
        self.assertEqual(preview.original.pixels, expected_original)
        self.assertEqual(result.snapshot.jobs[-1].state, JobState.SUCCEEDED)

        actual_pixels = _surface_pixels(preview.processed.pixels)
        self.assertEqual(len(actual_pixels), len(PROBE_PIXELS))
        for pixel_index, (source_rgb8, actual) in enumerate(
            zip(PROBE_PIXELS, actual_pixels, strict=True)
        ):
            expected = oracle(_normalized(source_rgb8))
            if require_exact_binary32:
                self.assertEqual(
                    struct.pack(">fff", *actual),
                    struct.pack(">fff", *expected),
                    f"pixel {pixel_index}",
                )
                continue
            for channel, (actual_component, expected_component) in enumerate(
                zip(actual, expected, strict=True)
            ):
                self.assertAlmostEqual(
                    actual_component,
                    expected_component,
                    delta=DERIVED_BINARY32_TOLERANCE,
                    msg=f"pixel {pixel_index}, channel {channel}",
                )


if __name__ == "__main__":
    unittest.main()
