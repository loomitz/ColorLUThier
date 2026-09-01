from __future__ import annotations

import itertools
import struct
import unittest
from collections.abc import Callable

from colorluthier_engine import (
    ColorContextDeclaration,
    ColorContextUnknownReason,
    ColorDocument,
    CommandStatus,
    ConfigureColorTransformation,
    DeclareColorContexts,
    Interpolation,
    JobId,
    JobPurpose,
    JobSnapshot,
    JobState,
    LoadPortableCube,
    OpenReferenceImage,
    ProofColorContext,
    ProvisionalImageFormat,
    RequestFullResolutionEvaluation,
    RequestPreview,
    RevisionBasis,
    SurfacePurpose,
    UnknownColorContext,
)
from colorluthier_engine.testing import ControlledExecutor


RGB8 = tuple[int, int, int]
RGB = tuple[float, float, float]
Oracle = Callable[[RGB], RGB]

_NODE_LEVELS = (0, 85, 170, 255)
_ENDPOINTS = frozenset((0, 255))
_INTERIOR_NODE_LEVELS = frozenset((85, 170))


def _cyclic_affine_cube() -> bytes:
    """Return a size-4 red-fastest Cube for (r, g, b) -> (b, r, g)."""

    tokens = (
        "0",
        "0.333333333333333333",
        "0.666666666666666667",
        "1",
    )
    lines = ["LUT_3D_SIZE 4"]
    for blue_index in range(4):
        for green_index in range(4):
            for red_index in range(4):
                lines.append(
                    " ".join(
                        (
                            tokens[blue_index],
                            tokens[red_index],
                            tokens[green_index],
                        )
                    )
                )
    return ("\n".join(lines) + "\n").encode("ascii")


CYCLIC_AFFINE_CUBE = _cyclic_affine_cube()

PAIR_PRODUCT_CUBE = (
    b"LUT_3D_SIZE 2\n"
    b"0 0 0\n"
    b"0 0 0\n"
    b"0 0 0\n"
    b"1 0 0\n"
    b"0 0 0\n"
    b"0 1 0\n"
    b"0 0 1\n"
    b"1 1 1\n"
)


NODE_PROBES: tuple[RGB8, ...] = tuple(
    itertools.product(_NODE_LEVELS, repeat=3)
)


def _edge_probes() -> tuple[RGB8, ...]:
    varying_values = (37, 149, 223)
    probes: list[RGB8] = []
    for varying_axis in range(3):
        for fixed_values in itertools.product((0, 255), repeat=2):
            components = list(fixed_values)
            components.insert(varying_axis, varying_values[varying_axis])
            probes.append((components[0], components[1], components[2]))
    return tuple(probes)


def _face_probes() -> tuple[RGB8, ...]:
    free_values = ((41, 203), (73, 211), (29, 157))
    probes: list[RGB8] = []
    for fixed_axis in range(3):
        for endpoint in (0, 255):
            components = list(free_values[fixed_axis])
            components.insert(fixed_axis, endpoint)
            probes.append((components[0], components[1], components[2]))
    return tuple(probes)


def _cell_plane_probes() -> tuple[RGB8, ...]:
    free_values = ((37, 211), (53, 229), (19, 143))
    probes: list[RGB8] = []
    for fixed_axis in range(3):
        for boundary in (85, 170):
            components = list(free_values[fixed_axis])
            components.insert(fixed_axis, boundary)
            probes.append((components[0], components[1], components[2]))
    return tuple(probes)


EDGE_PROBES = _edge_probes()
FACE_PROBES = _face_probes()
CELL_PLANE_PROBES = _cell_plane_probes()
ASYMMETRIC_INTERIOR_PROBES: tuple[RGB8, ...] = (
    (17, 103, 229),
    (43, 131, 211),
    (74, 149, 238),
    (231, 92, 14),
)
GEOMETRY_PROBES = (
    NODE_PROBES
    + EDGE_PROBES
    + FACE_PROBES
    + CELL_PLANE_PROBES
    + ASYMMETRIC_INTERIOR_PROBES
)

ASYMMETRIC_ORDER_PROBES: tuple[RGB8, ...] = tuple(
    itertools.permutations((211, 137, 43))
)
TETRAHEDRAL_BOUNDARY_PROBES: tuple[RGB8, ...] = (
    (191, 191, 64),
    (192, 191, 64),
    (190, 191, 64),
    (191, 64, 191),
    (192, 64, 191),
    (190, 64, 191),
    (64, 191, 191),
    (64, 192, 191),
    (64, 190, 191),
    (128, 128, 128),
)
PAIR_PRODUCT_PROBES = (
    ASYMMETRIC_ORDER_PROBES + TETRAHEDRAL_BOUNDARY_PROBES
)


def _ppm(pixels: tuple[RGB8, ...]) -> bytes:
    payload = bytes(component for pixel in pixels for component in pixel)
    return f"P6\n{len(pixels)} 1\n255\n".encode("ascii") + payload


def _normalized(pixel: RGB8) -> RGB:
    red, green, blue = pixel
    return (red / 255.0, green / 255.0, blue / 255.0)


def _cyclic_affine(source: RGB) -> RGB:
    red, green, blue = source
    return (blue, red, green)


def _pair_product(source: RGB) -> RGB:
    red, green, blue = source
    return (red * green, red * blue, green * blue)


def _pair_minimum(source: RGB) -> RGB:
    red, green, blue = source
    return (min(red, green), min(red, blue), min(green, blue))


def _source_bytes(pixels: tuple[RGB8, ...]) -> bytes:
    return b"".join(struct.pack(">fff", *_normalized(pixel)) for pixel in pixels)


def _expected_bytes(
    pixels: tuple[RGB8, ...],
    oracle: Oracle,
    *,
    bypass: bool,
    mix: float,
) -> bytes:
    packed = bytearray()
    for pixel in pixels:
        source = _normalized(pixel)
        if bypass:
            output = source
        else:
            evaluated = oracle(source)
            output = tuple(
                source_component
                + mix * (evaluated_component - source_component)
                for source_component, evaluated_component in zip(
                    source,
                    evaluated,
                    strict=True,
                )
            )
        packed.extend(struct.pack(">fff", *output))
    return bytes(packed)


class PreviewFullResolutionParityTest(unittest.TestCase):
    def ready_document(
        self,
        pixels: tuple[RGB8, ...],
        cube: bytes,
        interpolation: Interpolation,
        *,
        executor: ControlledExecutor | None = None,
        bypass: bool = False,
        mix: float = 1.0,
    ) -> tuple[ColorDocument, RevisionBasis]:
        document = (
            ColorDocument() if executor is None else ColorDocument(executor)
        )
        opened = document.apply(
            OpenReferenceImage(
                encoded=_ppm(pixels),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        loaded = document.apply(
            LoadPortableCube(
                encoded=cube,
                interpolation=interpolation,
                bypass=bypass,
                mix=mix,
            )
        )
        self.assertEqual(opened.status, CommandStatus.COMMITTED)
        self.assertEqual(loaded.status, CommandStatus.COMMITTED)
        return document, document.snapshot().revision_basis()

    def job(self, document: ColorDocument, job_id: JobId) -> JobSnapshot:
        matches = tuple(
            job for job in document.snapshot().jobs if job.job_id == job_id
        )
        self.assertEqual(len(matches), 1)
        return matches[0]

    def assert_exact_public_paths(
        self,
        *,
        pixels: tuple[RGB8, ...],
        cube: bytes,
        interpolation: Interpolation,
        oracle: Oracle,
        bypass: bool = False,
        mix: float = 1.0,
    ) -> None:
        document, basis = self.ready_document(
            pixels,
            cube,
            interpolation,
            bypass=bypass,
            mix=mix,
        )
        expected = _expected_bytes(
            pixels,
            oracle,
            bypass=bypass,
            mix=mix,
        )

        preview_request = document.apply(RequestPreview())
        full_request = document.apply(RequestFullResolutionEvaluation())
        self.assertEqual(preview_request.status, CommandStatus.ACCEPTED)
        self.assertEqual(full_request.status, CommandStatus.ACCEPTED)

        snapshot = document.snapshot()
        preview = snapshot.preview
        full_resolution = snapshot.full_resolution
        self.assertEqual(snapshot.revision_basis(), basis)
        self.assertEqual(preview.basis, basis)
        self.assertEqual(preview.processed.basis, basis)
        self.assertEqual(full_resolution.basis, basis)
        self.assertEqual(full_resolution.processed.basis, basis)
        self.assertEqual(preview.original.pixels, _source_bytes(pixels))
        self.assertEqual(preview.processed.pixels, expected)
        self.assertEqual(full_resolution.processed.pixels, expected)
        self.assertEqual(
            preview.processed.pixels,
            full_resolution.processed.pixels,
        )
        self.assertEqual(
            preview.processed.purpose,
            SurfacePurpose.PROCESSED_PREVIEW,
        )
        self.assertEqual(
            full_resolution.processed.purpose,
            SurfacePurpose.PROCESSED_FULL_RESOLUTION,
        )
        self.assertEqual(
            self.job(document, preview_request.job_id).state,
            JobState.SUCCEEDED,
        )
        self.assertEqual(
            self.job(document, full_request.job_id).state,
            JobState.SUCCEEDED,
        )

    def test_probe_manifest_covers_geometry_and_tetrahedral_regions(self) -> None:
        self.assertEqual(CYCLIC_AFFINE_CUBE.count(b"\n"), 65)
        self.assertEqual(len(NODE_PROBES), 64)
        node_categories = {"corner": 0, "edge": 0, "face": 0, "volume": 0}
        for probe in NODE_PROBES:
            endpoint_count = sum(component in _ENDPOINTS for component in probe)
            category = {3: "corner", 2: "edge", 1: "face", 0: "volume"}[
                endpoint_count
            ]
            node_categories[category] += 1
        self.assertEqual(
            node_categories,
            {"corner": 8, "edge": 24, "face": 24, "volume": 8},
        )
        self.assertEqual(len(EDGE_PROBES), 12)
        self.assertTrue(
            all(
                sum(component in _ENDPOINTS for component in probe) == 2
                for probe in EDGE_PROBES
            )
        )
        self.assertEqual(len(FACE_PROBES), 6)
        self.assertTrue(
            all(
                sum(component in _ENDPOINTS for component in probe) == 1
                for probe in FACE_PROBES
            )
        )
        self.assertEqual(len(CELL_PLANE_PROBES), 6)
        self.assertTrue(
            all(
                sum(
                    component in _INTERIOR_NODE_LEVELS for component in probe
                )
                == 1
                for probe in CELL_PLANE_PROBES
            )
        )
        self.assertTrue(
            all(
                len(set(probe)) == 3
                and all(component not in _NODE_LEVELS for component in probe)
                for probe in ASYMMETRIC_INTERIOR_PROBES
            )
        )
        self.assertEqual(len(GEOMETRY_PROBES), len(set(GEOMETRY_PROBES)))

        self.assertEqual(
            set(ASYMMETRIC_ORDER_PROBES),
            set(itertools.permutations((211, 137, 43))),
        )
        boundary_axes = ((0, 1), (0, 2), (1, 2))
        for group_index, (first_axis, second_axis) in enumerate(boundary_axes):
            boundary, first_side, second_side = TETRAHEDRAL_BOUNDARY_PROBES[
                group_index * 3 : group_index * 3 + 3
            ]
            self.assertEqual(boundary[first_axis], boundary[second_axis])
            self.assertGreater(first_side[first_axis], first_side[second_axis])
            self.assertLess(second_side[first_axis], second_side[second_axis])
        self.assertEqual(TETRAHEDRAL_BOUNDARY_PROBES[-1], (128, 128, 128))

    def test_cyclic_affine_geometry_is_exact_for_both_public_paths(self) -> None:
        for interpolation in Interpolation:
            with self.subTest(interpolation=interpolation):
                self.assert_exact_public_paths(
                    pixels=GEOMETRY_PROBES,
                    cube=CYCLIC_AFFINE_CUBE,
                    interpolation=interpolation,
                    oracle=_cyclic_affine,
                )

    def test_pair_product_divergence_mix_and_bypass_are_exact(self) -> None:
        for probe in ASYMMETRIC_ORDER_PROBES:
            trilinear = _expected_bytes(
                (probe,),
                _pair_product,
                bypass=False,
                mix=1.0,
            )
            tetrahedral = _expected_bytes(
                (probe,),
                _pair_minimum,
                bypass=False,
                mix=1.0,
            )
            self.assertNotEqual(trilinear, tetrahedral)

        for interpolation, oracle in (
            (Interpolation.TRILINEAR, _pair_product),
            (Interpolation.TETRAHEDRAL, _pair_minimum),
        ):
            for bypass, mix in (
                (False, 1.0),
                (False, 0.25),
                (True, 0.25),
            ):
                with self.subTest(
                    interpolation=interpolation,
                    bypass=bypass,
                    mix=mix,
                ):
                    self.assert_exact_public_paths(
                        pixels=PAIR_PRODUCT_PROBES,
                        cube=PAIR_PRODUCT_CUBE,
                        interpolation=interpolation,
                        oracle=oracle,
                        bypass=bypass,
                        mix=mix,
                    )

    def test_transformation_change_invalidates_and_stales_both_purposes(
        self,
    ) -> None:
        executor = ControlledExecutor()
        document, basis = self.ready_document(
            ASYMMETRIC_ORDER_PROBES,
            PAIR_PRODUCT_CUBE,
            Interpolation.TRILINEAR,
            executor=executor,
        )
        initial_preview = document.apply(RequestPreview())
        initial_full = document.apply(RequestFullResolutionEvaluation())
        executor.run_in_order(
            (initial_preview.job_id.value, initial_full.job_id.value)
        )
        self.assertIsNotNone(document.snapshot().preview)
        self.assertIsNotNone(document.snapshot().full_resolution)

        refresh_preview = document.apply(RequestPreview())
        refresh_full = document.apply(RequestFullResolutionEvaluation())
        self.assertEqual(self.job(document, refresh_preview.job_id).basis, basis)
        self.assertEqual(self.job(document, refresh_full.job_id).basis, basis)

        changed = document.apply(ConfigureColorTransformation(mix=0.5))
        self.assertEqual(changed.status, CommandStatus.COMMITTED)
        self.assertIsNone(changed.snapshot.preview)
        self.assertIsNone(changed.snapshot.full_resolution)
        self.assertNotEqual(changed.snapshot.revision_basis(), basis)

        executor.run_in_order(
            (refresh_preview.job_id.value, refresh_full.job_id.value)
        )
        final = document.snapshot()
        self.assertIsNone(final.preview)
        self.assertIsNone(final.full_resolution)
        for request in (refresh_preview, refresh_full):
            job = self.job(document, request.job_id)
            self.assertEqual(job.state, JobState.STALE)
            self.assertEqual(job.diagnostic.code, "STALE_JOB_RESULT")

    def test_viewing_change_stales_only_preview_purpose(self) -> None:
        executor = ControlledExecutor()
        document, basis = self.ready_document(
            ASYMMETRIC_ORDER_PROBES,
            PAIR_PRODUCT_CUBE,
            Interpolation.TRILINEAR,
            executor=executor,
        )
        initial_preview = document.apply(RequestPreview())
        initial_full = document.apply(RequestFullResolutionEvaluation())
        executor.run_in_order(
            (initial_preview.job_id.value, initial_full.job_id.value)
        )
        published_full = document.snapshot().full_resolution

        refresh_preview = document.apply(RequestPreview())
        refresh_full = document.apply(RequestFullResolutionEvaluation())
        contexts = document.snapshot().color_contexts
        changed = document.apply(
            DeclareColorContexts(
                declaration=ColorContextDeclaration(
                    selected_lane=contexts.selected_lane,
                    working=contexts.working,
                    proof=ProofColorContext(
                        UnknownColorContext(
                            ColorContextUnknownReason.NOT_AVAILABLE
                        )
                    ),
                    display=contexts.display,
                    export_context=contexts.export_context,
                ),
                expected=contexts.revision_basis,
            )
        )
        self.assertEqual(changed.status, CommandStatus.COMMITTED)
        current_basis = changed.snapshot.revision_basis()
        self.assertEqual(current_basis.reference, basis.reference)
        self.assertEqual(current_basis.transformation, basis.transformation)
        self.assertEqual(current_basis.interpretation, basis.interpretation)
        self.assertNotEqual(current_basis.viewing, basis.viewing)
        self.assertEqual(current_basis.export, basis.export)
        self.assertIsNone(changed.snapshot.preview)
        self.assertEqual(changed.snapshot.full_resolution, published_full)

        executor.run_all(refresh_full.job_id.value)
        refreshed_full = document.snapshot().full_resolution
        self.assertEqual(refreshed_full.job_id, refresh_full.job_id)
        self.assertEqual(refreshed_full.basis, basis)
        self.assertEqual(
            refreshed_full.processed.pixels,
            _expected_bytes(
                ASYMMETRIC_ORDER_PROBES,
                _pair_product,
                bypass=False,
                mix=1.0,
            ),
        )
        self.assertEqual(
            self.job(document, refresh_full.job_id).state,
            JobState.SUCCEEDED,
        )

        executor.run_all(refresh_preview.job_id.value)
        final = document.snapshot()
        self.assertIsNone(final.preview)
        self.assertEqual(final.full_resolution, refreshed_full)
        stale_preview = self.job(document, refresh_preview.job_id)
        self.assertEqual(stale_preview.state, JobState.STALE)
        self.assertEqual(stale_preview.diagnostic.code, "STALE_JOB_RESULT")

    def test_latest_request_wins_independently_for_each_purpose(self) -> None:
        executor = ControlledExecutor()
        document, basis = self.ready_document(
            ASYMMETRIC_ORDER_PROBES,
            PAIR_PRODUCT_CUBE,
            Interpolation.TETRAHEDRAL,
            executor=executor,
        )
        older_preview = document.apply(RequestPreview())
        older_full = document.apply(RequestFullResolutionEvaluation())
        newer_preview = document.apply(RequestPreview())
        newer_full = document.apply(RequestFullResolutionEvaluation())

        for request, purpose in (
            (older_preview, JobPurpose.PREVIEW),
            (older_full, JobPurpose.FULL_RESOLUTION_EVALUATION),
            (newer_preview, JobPurpose.PREVIEW),
            (newer_full, JobPurpose.FULL_RESOLUTION_EVALUATION),
        ):
            job = self.job(document, request.job_id)
            self.assertEqual(job.purpose, purpose)
            self.assertEqual(job.basis, basis)

        executor.run_in_order(
            (newer_preview.job_id.value, newer_full.job_id.value)
        )
        published = document.snapshot()
        expected = _expected_bytes(
            ASYMMETRIC_ORDER_PROBES,
            _pair_minimum,
            bypass=False,
            mix=1.0,
        )
        self.assertEqual(published.preview.job_id, newer_preview.job_id)
        self.assertEqual(published.full_resolution.job_id, newer_full.job_id)
        self.assertEqual(published.preview.processed.pixels, expected)
        self.assertEqual(published.full_resolution.processed.pixels, expected)

        executor.run_in_order(
            (older_preview.job_id.value, older_full.job_id.value)
        )
        final = document.snapshot()
        self.assertEqual(final.preview, published.preview)
        self.assertEqual(final.full_resolution, published.full_resolution)
        for request in (older_preview, older_full):
            job = self.job(document, request.job_id)
            self.assertEqual(job.state, JobState.STALE)
            self.assertEqual(job.diagnostic.code, "STALE_JOB_RESULT")


if __name__ == "__main__":
    unittest.main()
