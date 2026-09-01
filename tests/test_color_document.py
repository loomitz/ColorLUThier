from __future__ import annotations

import hashlib
import struct
import unittest
import zlib
from dataclasses import FrozenInstanceError

from colorluthier_engine import (
    CancelJob,
    ColorDocument,
    CommandStatus,
    ConfigureColorTransformation,
    DocumentRevision,
    Interpolation,
    JobId,
    JobState,
    LoadPortableCube,
    OpenReferenceImage,
    ProvisionalImageFormat,
    RequestCanonicalPortableCubeExport,
    RequestPreview,
    SurfacePurpose,
)
from colorluthier_engine.testing import ControlledExecutor


IDENTITY_CUBE = (
    b"LUT_3D_SIZE 2\n"
    b"0 0 0\n"
    b"1 0 0\n"
    b"0 1 0\n"
    b"1 1 0\n"
    b"0 0 1\n"
    b"1 0 1\n"
    b"0 1 1\n"
    b"1 1 1\n"
)

RED_BLUE_SWAP_CUBE = (
    b"LUT_3D_SIZE 2\n"
    b"0 0 0\n"
    b"0 0 1\n"
    b"0 1 0\n"
    b"0 1 1\n"
    b"1 0 0\n"
    b"1 0 1\n"
    b"1 1 0\n"
    b"1 1 1\n"
)


def synthetic_ppm(
    width: int,
    height: int,
    pixels_rgb8: bytes,
) -> bytes:
    if len(pixels_rgb8) != width * height * 3:
        raise ValueError("Synthetic RGB8 payload has the wrong size.")
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels_rgb8


def synthetic_png(
    width: int,
    height: int,
    pixels: bytes,
    *,
    channels: int,
) -> bytes:
    if channels not in (3, 4):
        raise ValueError("Synthetic PNGs must be RGB or RGBA.")
    if len(pixels) != width * height * channels:
        raise ValueError("Synthetic PNG payload has the wrong size.")

    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        return (
            struct.pack(">I", len(payload))
            + chunk_type
            + payload
            + struct.pack(">I", checksum)
        )

    scanlines = b"".join(
        b"\x00" + pixels[row * width * channels : (row + 1) * width * channels]
        for row in range(height)
    )
    color_type = 2 if channels == 3 else 6
    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def packed_rgb_f32(pixels_rgb8: bytes, *, swap_red_blue: bool = False) -> bytes:
    packed = bytearray()
    for offset in range(0, len(pixels_rgb8), 3):
        red, green, blue = pixels_rgb8[offset : offset + 3]
        components = (blue, green, red) if swap_red_blue else (red, green, blue)
        packed.extend(
            struct.pack(">fff", *(component / 255.0 for component in components))
        )
    return bytes(packed)


class ColorDocumentAcceptanceTest(unittest.TestCase):
    def ready_document(
        self,
        executor: ControlledExecutor,
        *,
        width: int = 2,
        height: int = 2,
        pixels_rgb8: bytes | None = None,
        cube: bytes = IDENTITY_CUBE,
        interpolation: Interpolation = Interpolation.TRILINEAR,
    ) -> ColorDocument:
        if pixels_rgb8 is None:
            pixels_rgb8 = bytes(
                (index * 37) % 256 for index in range(width * height * 3)
            )
        document = ColorDocument(executor=executor)
        reference_result = document.apply(
            OpenReferenceImage(
                encoded=synthetic_ppm(width, height, pixels_rgb8),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(reference_result.status, CommandStatus.COMMITTED)
        transformation_result = document.apply(
            LoadPortableCube(
                encoded=cube,
                interpolation=interpolation,
            )
        )
        self.assertEqual(transformation_result.status, CommandStatus.COMMITTED)
        return document

    def job(self, document: ColorDocument, job_id: JobId):
        matches = [
            job
            for job in document.snapshot().jobs
            if job.job_id == job_id
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_revisions_are_monotonic_and_snapshots_are_immutable(self) -> None:
        executor = ControlledExecutor()
        document = ColorDocument(executor=executor)
        initial = document.snapshot()

        opened = document.apply(
            OpenReferenceImage(
                encoded=synthetic_ppm(1, 1, bytes((12, 34, 56))),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        ).snapshot
        loaded = document.apply(
            LoadPortableCube(
                encoded=IDENTITY_CUBE,
                interpolation=Interpolation.TRILINEAR,
            )
        ).snapshot
        configured_result = document.apply(
            ConfigureColorTransformation(mix=0.5)
        )
        configured = configured_result.snapshot

        self.assertEqual(configured_result.status, CommandStatus.COMMITTED)
        self.assertEqual(
            [
                snapshot.document_revision.value
                for snapshot in (initial, opened, loaded, configured)
            ],
            [0, 1, 2, 3],
        )
        self.assertEqual(
            [
                snapshot.snapshot_revision.value
                for snapshot in (initial, opened, loaded, configured)
            ],
            [0, 1, 2, 3],
        )
        self.assertIsNone(initial.reference)
        self.assertEqual(opened.reference.revision, DocumentRevision(1))
        self.assertEqual(loaded.reference.revision, DocumentRevision(1))
        self.assertEqual(loaded.transformation.revision.value, 1)
        self.assertEqual(configured.transformation.revision.value, 2)
        self.assertEqual(loaded.transformation.mix, 1.0)
        self.assertEqual(configured.transformation.mix, 0.5)

        unchanged = document.apply(ConfigureColorTransformation(mix=0.5))
        self.assertEqual(unchanged.status, CommandStatus.UNCHANGED)
        self.assertEqual(unchanged.snapshot, configured)

        rejected = document.apply(
            LoadPortableCube(
                encoded=b"not a Portable Cube\n",
                interpolation=Interpolation.TRILINEAR,
            )
        )
        self.assertEqual(rejected.status, CommandStatus.REJECTED)
        self.assertEqual(rejected.snapshot, configured)
        self.assertEqual(document.snapshot(), configured)

        with self.assertRaises(FrozenInstanceError):
            configured.document_revision = DocumentRevision(99)
        with self.assertRaises(FrozenInstanceError):
            configured.transformation.mix = 0.25

    def test_preview_publishes_both_surfaces_atomically(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor, width=2, height=2)
        document_revision = document.snapshot().document_revision

        request = document.apply(RequestPreview())
        self.assertEqual(request.status, CommandStatus.ACCEPTED)
        self.assertIsNotNone(request.job_id)
        job_id = request.job_id
        self.assertIsNone(request.snapshot.preview)
        self.assertEqual(self.job(document, job_id).state, JobState.QUEUED)

        self.assertFalse(executor.run_next(job_id.value))
        after_first_row = document.snapshot()
        self.assertIsNone(after_first_row.preview)
        self.assertEqual(self.job(document, job_id).progress.completed_units, 1)

        self.assertFalse(executor.run_next(job_id.value))
        after_second_row = document.snapshot()
        self.assertIsNone(after_second_row.preview)
        self.assertEqual(self.job(document, job_id).progress.completed_units, 2)

        self.assertTrue(executor.run_next(job_id.value))
        completed = document.snapshot()
        self.assertEqual(completed.document_revision, document_revision)
        self.assertIsNotNone(completed.preview)
        preview = completed.preview
        self.assertEqual(preview.job_id, job_id)
        self.assertEqual(preview.basis, completed.revision_basis())
        self.assertEqual(preview.original.basis, preview.basis)
        self.assertEqual(preview.processed.basis, preview.basis)
        self.assertEqual(
            (preview.original.purpose, preview.processed.purpose),
            (
                SurfacePurpose.ORIGINAL_PREVIEW,
                SurfacePurpose.PROCESSED_PREVIEW,
            ),
        )
        self.assertNotEqual(
            preview.original.surface_id,
            preview.processed.surface_id,
        )
        self.assertEqual(len(preview.original.pixels), 2 * 2 * 12)
        self.assertEqual(len(preview.processed.pixels), 2 * 2 * 12)
        completed_job = self.job(document, job_id)
        self.assertEqual(completed_job.state, JobState.SUCCEEDED)
        self.assertEqual(
            completed_job.progress.completed_units,
            completed_job.progress.total_units,
        )

    def test_cancellation_before_and_during_processing_publishes_nothing(
        self,
    ) -> None:
        for completed_before_cancel in (0, 1):
            with self.subTest(completed_before_cancel=completed_before_cancel):
                executor = ControlledExecutor()
                document = self.ready_document(executor, width=2, height=3)
                request = document.apply(RequestPreview())
                job_id = request.job_id
                basis = request.snapshot.revision_basis()

                if completed_before_cancel:
                    self.assertFalse(executor.run_next(job_id.value))
                    self.assertEqual(
                        self.job(document, job_id).progress.completed_units,
                        completed_before_cancel,
                    )

                cancellation = document.apply(CancelJob(job_id=job_id))
                self.assertEqual(cancellation.status, CommandStatus.ACCEPTED)
                cancelled = self.job(document, job_id)
                self.assertEqual(cancelled.state, JobState.CANCELLED)
                self.assertEqual(
                    cancelled.progress.completed_units,
                    completed_before_cancel,
                )
                self.assertEqual(cancelled.basis, basis)
                self.assertIsNone(cancellation.snapshot.preview)
                self.assertEqual(cancelled.diagnostic.code, "JOB_CANCELLED")

                before_drain = document.snapshot()
                self.assertTrue(executor.run_next(job_id.value))
                self.assertEqual(document.snapshot(), before_drain)
                self.assertNotIn(job_id.value, executor.pending_job_ids)

    def test_progress_is_monotonic_bounded_and_driven_by_controlled_steps(
        self,
    ) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor, width=1, height=4)
        request = document.apply(RequestPreview())
        job_id = request.job_id
        document_revision = request.snapshot.document_revision

        snapshots = [request.snapshot]
        while job_id.value in executor.pending_job_ids:
            executor.run_next(job_id.value)
            snapshots.append(document.snapshot())

        jobs = [
            next(job for job in snapshot.jobs if job.job_id == job_id)
            for snapshot in snapshots
        ]
        completed_units = [job.progress.completed_units for job in jobs]
        total_units = [job.progress.total_units for job in jobs]
        snapshot_revisions = [
            snapshot.snapshot_revision.value for snapshot in snapshots
        ]

        self.assertEqual(completed_units, [0, 1, 2, 3, 4, 5])
        self.assertEqual(total_units, [5, 5, 5, 5, 5, 5])
        self.assertEqual(completed_units, sorted(completed_units))
        self.assertTrue(
            all(
                0.0 <= job.progress.fraction <= 1.0
                for job in jobs
            )
        )
        self.assertTrue(
            all(
                earlier < later
                for earlier, later in zip(
                    snapshot_revisions,
                    snapshot_revisions[1:],
                )
            )
        )
        self.assertTrue(
            all(
                snapshot.document_revision == document_revision
                for snapshot in snapshots
            )
        )
        self.assertEqual(jobs[0].state, JobState.QUEUED)
        self.assertTrue(all(job.state is JobState.RUNNING for job in jobs[1:-1]))
        self.assertEqual(jobs[-1].state, JobState.SUCCEEDED)

    def test_out_of_order_completion_rejects_the_obsolete_preview(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor, width=2, height=2)

        old_request = document.apply(RequestPreview())
        old_job_id = old_request.job_id
        old_basis = self.job(document, old_job_id).basis

        change = document.apply(ConfigureColorTransformation(mix=0.25))
        self.assertEqual(change.status, CommandStatus.COMMITTED)
        new_request = document.apply(RequestPreview())
        new_job_id = new_request.job_id
        new_basis = self.job(document, new_job_id).basis
        self.assertNotEqual(old_basis, new_basis)

        executor.run_all(new_job_id.value)
        fresh_snapshot = document.snapshot()
        fresh_preview = fresh_snapshot.preview
        self.assertEqual(fresh_preview.job_id, new_job_id)
        self.assertEqual(fresh_preview.basis, fresh_snapshot.revision_basis())

        executor.run_all(old_job_id.value)
        completed_out_of_order = document.snapshot()
        self.assertEqual(completed_out_of_order.preview, fresh_preview)
        obsolete_job = self.job(document, old_job_id)
        self.assertEqual(obsolete_job.state, JobState.STALE)
        self.assertEqual(obsolete_job.basis, old_basis)
        self.assertEqual(obsolete_job.diagnostic.code, "STALE_JOB_RESULT")
        self.assertEqual(self.job(document, new_job_id).state, JobState.SUCCEEDED)

    def test_latest_preview_wins_within_the_same_revision(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor, width=2, height=2)

        older = document.apply(RequestPreview())
        newer = document.apply(RequestPreview())
        older_basis = self.job(document, older.job_id).basis
        newer_basis = self.job(document, newer.job_id).basis
        self.assertEqual(older_basis, newer_basis)

        executor.run_all(newer.job_id.value)
        published = document.snapshot().preview
        self.assertEqual(published.job_id, newer.job_id)

        executor.run_all(older.job_id.value)
        final_snapshot = document.snapshot()
        self.assertEqual(final_snapshot.preview, published)
        self.assertEqual(self.job(document, older.job_id).state, JobState.STALE)
        self.assertEqual(
            self.job(document, older.job_id).diagnostic.code,
            "STALE_JOB_RESULT",
        )
        self.assertEqual(self.job(document, newer.job_id).state, JobState.SUCCEEDED)

    def test_obsolete_export_never_publishes_after_transformation_change(
        self,
    ) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        obsolete = document.apply(RequestCanonicalPortableCubeExport())
        obsolete_basis = self.job(document, obsolete.job_id).basis

        change = document.apply(ConfigureColorTransformation(mix=0.5))
        self.assertEqual(change.status, CommandStatus.COMMITTED)
        self.assertNotEqual(obsolete_basis, change.snapshot.revision_basis())

        self.assertFalse(executor.run_next(obsolete.job_id.value))
        self.assertIsNone(document.snapshot().canonical_cube_export)
        self.assertTrue(executor.run_next(obsolete.job_id.value))
        self.assertIsNone(document.snapshot().canonical_cube_export)
        self.assertEqual(self.job(document, obsolete.job_id).state, JobState.STALE)

        current = document.apply(RequestCanonicalPortableCubeExport())
        self.assertFalse(executor.run_next(current.job_id.value))
        self.assertIsNone(document.snapshot().canonical_cube_export)
        self.assertTrue(executor.run_next(current.job_id.value))
        snapshot = document.snapshot()
        self.assertEqual(
            snapshot.canonical_cube_export.job_id,
            current.job_id,
        )
        self.assertEqual(
            snapshot.canonical_cube_export.basis,
            snapshot.revision_basis(),
        )

    def test_export_cancellation_before_and_after_first_step_publishes_nothing(
        self,
    ) -> None:
        for completed_before_cancel in (0, 1):
            with self.subTest(completed_before_cancel=completed_before_cancel):
                executor = ControlledExecutor()
                document = self.ready_document(executor)
                request = document.apply(RequestCanonicalPortableCubeExport())
                job_id = request.job_id
                basis = request.snapshot.revision_basis()

                if completed_before_cancel:
                    self.assertFalse(executor.run_next(job_id.value))
                    self.assertIsNone(document.snapshot().canonical_cube_export)

                cancellation = document.apply(CancelJob(job_id=job_id))
                cancelled = self.job(document, job_id)
                self.assertEqual(cancellation.status, CommandStatus.ACCEPTED)
                self.assertEqual(cancelled.state, JobState.CANCELLED)
                self.assertEqual(cancelled.basis, basis)
                self.assertEqual(
                    (
                        cancelled.progress.completed_units,
                        cancelled.progress.total_units,
                    ),
                    (completed_before_cancel, 2),
                )
                self.assertEqual(cancelled.diagnostic.code, "JOB_CANCELLED")
                self.assertIsNone(cancellation.snapshot.canonical_cube_export)

                before_drain = document.snapshot()
                self.assertTrue(executor.run_next(job_id.value))
                self.assertEqual(document.snapshot(), before_drain)

    def test_export_progress_is_monotonic_bounded_and_publishes_atomically(
        self,
    ) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        request = document.apply(RequestCanonicalPortableCubeExport())
        job_id = request.job_id

        snapshots = [request.snapshot]
        self.assertFalse(executor.run_next(job_id.value))
        snapshots.append(document.snapshot())
        self.assertTrue(executor.run_next(job_id.value))
        snapshots.append(document.snapshot())

        jobs = [
            next(job for job in snapshot.jobs if job.job_id == job_id)
            for snapshot in snapshots
        ]
        self.assertEqual(
            [job.progress.completed_units for job in jobs],
            [0, 1, 2],
        )
        self.assertEqual(
            [job.progress.total_units for job in jobs],
            [2, 2, 2],
        )
        self.assertEqual(
            [job.progress.fraction for job in jobs],
            [0.0, 0.5, 1.0],
        )
        self.assertEqual(
            [job.state for job in jobs],
            [JobState.QUEUED, JobState.RUNNING, JobState.SUCCEEDED],
        )
        self.assertTrue(
            all(
                0.0 <= job.progress.fraction <= 1.0
                for job in jobs
            )
        )
        self.assertIsNone(snapshots[0].canonical_cube_export)
        self.assertIsNone(snapshots[1].canonical_cube_export)
        self.assertIsNotNone(snapshots[2].canonical_cube_export)
        self.assertEqual(
            snapshots[2].canonical_cube_export.basis,
            snapshots[2].revision_basis(),
        )
        self.assertEqual(
            {snapshot.document_revision for snapshot in snapshots},
            {request.snapshot.document_revision},
        )
        self.assertTrue(
            all(
                earlier.snapshot_revision < later.snapshot_revision
                for earlier, later in zip(snapshots, snapshots[1:])
            )
        )

    def test_cancelling_export_refresh_preserves_the_published_artifact(
        self,
    ) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        initial_request = document.apply(RequestCanonicalPortableCubeExport())
        executor.run_all(initial_request.job_id.value)
        published = document.snapshot().canonical_cube_export

        refresh = document.apply(RequestCanonicalPortableCubeExport())
        self.assertFalse(executor.run_next(refresh.job_id.value))
        cancellation = document.apply(CancelJob(job_id=refresh.job_id))

        self.assertEqual(cancellation.status, CommandStatus.ACCEPTED)
        self.assertEqual(cancellation.snapshot.canonical_cube_export, published)
        cancelled = self.job(document, refresh.job_id)
        self.assertEqual(cancelled.state, JobState.CANCELLED)
        self.assertEqual(
            (cancelled.progress.completed_units, cancelled.progress.total_units),
            (1, 2),
        )
        before_drain = document.snapshot()
        self.assertTrue(executor.run_next(refresh.job_id.value))
        self.assertEqual(document.snapshot(), before_drain)

    def test_stale_export_refresh_preserves_the_latest_published_artifact(
        self,
    ) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        initial = document.apply(RequestCanonicalPortableCubeExport())
        executor.run_all(initial.job_id.value)

        older_refresh = document.apply(RequestCanonicalPortableCubeExport())
        newer_refresh = document.apply(RequestCanonicalPortableCubeExport())
        self.assertEqual(
            self.job(document, older_refresh.job_id).basis,
            self.job(document, newer_refresh.job_id).basis,
        )

        executor.run_all(newer_refresh.job_id.value)
        latest = document.snapshot().canonical_cube_export
        self.assertEqual(latest.job_id, newer_refresh.job_id)

        executor.run_all(older_refresh.job_id.value)
        final_snapshot = document.snapshot()
        self.assertEqual(final_snapshot.canonical_cube_export, latest)
        rejected = self.job(document, older_refresh.job_id)
        self.assertEqual(rejected.state, JobState.STALE)
        self.assertEqual(rejected.diagnostic.code, "STALE_JOB_RESULT")

    def test_export_submission_error_preserves_the_published_artifact(
        self,
    ) -> None:
        executor = ControlledExecutor(capacity=1)
        document = self.ready_document(executor)
        initial = document.apply(RequestCanonicalPortableCubeExport())
        executor.run_all(initial.job_id.value)
        published = document.snapshot().canonical_cube_export

        pending_preview = document.apply(RequestPreview())
        failed_refresh = document.apply(RequestCanonicalPortableCubeExport())
        failed_job = self.job(document, failed_refresh.job_id)

        self.assertEqual(failed_refresh.status, CommandStatus.ACCEPTED)
        self.assertEqual(failed_job.state, JobState.FAILED)
        self.assertEqual(
            failed_job.diagnostic.code,
            "EXECUTOR_SUBMISSION_FAILED",
        )
        self.assertEqual(
            document.snapshot().canonical_cube_export,
            published,
        )

        document.apply(CancelJob(job_id=pending_preview.job_id))
        executor.run_next(pending_preview.job_id.value)

    def test_cancelling_preview_refresh_preserves_the_published_preview(
        self,
    ) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor, width=2, height=3)
        initial_request = document.apply(RequestPreview())
        executor.run_all(initial_request.job_id.value)
        published = document.snapshot().preview

        refresh = document.apply(RequestPreview())
        self.assertFalse(executor.run_next(refresh.job_id.value))
        cancellation = document.apply(CancelJob(job_id=refresh.job_id))

        self.assertEqual(cancellation.status, CommandStatus.ACCEPTED)
        self.assertEqual(cancellation.snapshot.preview, published)
        self.assertEqual(self.job(document, refresh.job_id).state, JobState.CANCELLED)
        before_drain = document.snapshot()
        self.assertTrue(executor.run_next(refresh.job_id.value))
        self.assertEqual(document.snapshot(), before_drain)

    def test_invalid_input_and_executor_error_preserve_last_valid_state(
        self,
    ) -> None:
        executor = ControlledExecutor(capacity=1)
        document = self.ready_document(executor, width=2, height=2)
        valid_request = document.apply(RequestPreview())
        executor.run_all(valid_request.job_id.value)
        valid_snapshot = document.snapshot()
        valid_preview = valid_snapshot.preview

        invalid = document.apply(
            LoadPortableCube(
                encoded=b"LUT_3D_SIZE 2\n0 0 0\n",
                interpolation=Interpolation.TETRAHEDRAL,
            )
        )
        self.assertEqual(invalid.status, CommandStatus.REJECTED)
        self.assertEqual(invalid.snapshot, valid_snapshot)

        pending_export = document.apply(RequestCanonicalPortableCubeExport())
        failed_preview = document.apply(RequestPreview())
        failed_job = self.job(document, failed_preview.job_id)
        after_failure = document.snapshot()

        self.assertEqual(pending_export.status, CommandStatus.ACCEPTED)
        self.assertEqual(failed_preview.status, CommandStatus.ACCEPTED)
        self.assertEqual(failed_job.state, JobState.FAILED)
        self.assertEqual(
            failed_job.diagnostic.code,
            "EXECUTOR_SUBMISSION_FAILED",
        )
        self.assertEqual(after_failure.preview, valid_preview)
        self.assertEqual(
            after_failure.document_revision,
            valid_snapshot.document_revision,
        )
        self.assertEqual(
            after_failure.transformation.revision,
            valid_snapshot.transformation.revision,
        )
        self.assertIsNone(after_failure.canonical_cube_export)

        document.apply(CancelJob(job_id=pending_export.job_id))
        executor.run_next(pending_export.job_id.value)

    def test_identity_preview_and_export_are_bound_to_the_current_revision(
        self,
    ) -> None:
        pixels = bytes((0, 0, 0, 64, 128, 255, 255, 17, 200))
        expected_pixels = packed_rgb_f32(pixels)

        for interpolation in Interpolation:
            with self.subTest(interpolation=interpolation):
                executor = ControlledExecutor()
                document = self.ready_document(
                    executor,
                    width=3,
                    height=1,
                    pixels_rgb8=pixels,
                    interpolation=interpolation,
                )
                preview_request = document.apply(RequestPreview())
                export_request = document.apply(
                    RequestCanonicalPortableCubeExport()
                )
                executor.run_in_order(
                    (export_request.job_id.value, preview_request.job_id.value)
                )

                snapshot = document.snapshot()
                basis = snapshot.revision_basis()
                preview = snapshot.preview
                artifact = snapshot.canonical_cube_export

                self.assertEqual(preview.basis, basis)
                self.assertEqual(preview.original.basis, basis)
                self.assertEqual(preview.processed.basis, basis)
                self.assertEqual(preview.original.pixels, expected_pixels)
                self.assertEqual(preview.processed.pixels, expected_pixels)
                self.assertEqual(artifact.basis, basis)
                self.assertEqual(artifact.encoded, IDENTITY_CUBE)
                self.assertEqual(artifact.byte_count, len(IDENTITY_CUBE))
                self.assertEqual(
                    artifact.ordinary_export_status,
                    "blocked-pending-explicit-color-contexts",
                )
                self.assertEqual(
                    artifact.sha256,
                    hashlib.sha256(IDENTITY_CUBE).hexdigest(),
                )
                self.assertEqual(
                    self.job(document, preview_request.job_id).state,
                    JobState.SUCCEEDED,
                )
                self.assertEqual(
                    self.job(document, export_request.job_id).state,
                    JobState.SUCCEEDED,
                )

    def test_portable_cube_channel_swap_matches_the_expected_cpu_result(
        self,
    ) -> None:
        pixels = bytes((11, 29, 251, 64, 128, 192, 255, 0, 17))
        expected_original = packed_rgb_f32(pixels)
        expected_processed = packed_rgb_f32(pixels, swap_red_blue=True)

        for interpolation in Interpolation:
            with self.subTest(interpolation=interpolation):
                executor = ControlledExecutor()
                document = self.ready_document(
                    executor,
                    width=3,
                    height=1,
                    pixels_rgb8=pixels,
                    cube=RED_BLUE_SWAP_CUBE,
                    interpolation=interpolation,
                )
                request = document.apply(RequestPreview())
                executor.run_all(request.job_id.value)
                preview = document.snapshot().preview

                self.assertEqual(preview.original.pixels, expected_original)
                self.assertEqual(preview.processed.pixels, expected_processed)

    def test_synthetic_rgb_and_rgba_pngs_flow_through_color_document(self) -> None:
        rgb_pixels = bytes((2, 31, 255, 99, 128, 7, 240, 11, 73, 0, 64, 192))
        rgba_pixels = bytes(
            (2, 31, 255, 0, 99, 128, 7, 85, 240, 11, 73, 170, 0, 64, 192, 255)
        )

        for channels, encoded_pixels, expected_rgb in (
            (3, rgb_pixels, rgb_pixels),
            (4, rgba_pixels, rgb_pixels),
        ):
            with self.subTest(channels=channels):
                executor = ControlledExecutor()
                document = ColorDocument(executor=executor)
                opened = document.apply(
                    OpenReferenceImage(
                        encoded=synthetic_png(
                            2,
                            2,
                            encoded_pixels,
                            channels=channels,
                        ),
                        image_format=ProvisionalImageFormat.PNG_RGB8,
                    )
                )
                self.assertEqual(opened.status, CommandStatus.COMMITTED)
                self.assertEqual(
                    (opened.snapshot.reference.width, opened.snapshot.reference.height),
                    (2, 2),
                )
                loaded = document.apply(
                    LoadPortableCube(
                        encoded=IDENTITY_CUBE,
                        interpolation=Interpolation.TETRAHEDRAL,
                    )
                )
                self.assertEqual(loaded.status, CommandStatus.COMMITTED)
                request = document.apply(RequestPreview())
                executor.run_all(request.job_id.value)
                preview = document.snapshot().preview
                expected = packed_rgb_f32(expected_rgb)

                self.assertEqual(preview.original.pixels, expected)
                self.assertEqual(preview.processed.pixels, expected)


if __name__ == "__main__":
    unittest.main()
