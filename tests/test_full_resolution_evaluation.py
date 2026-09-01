from __future__ import annotations

import unittest
from dataclasses import fields

from colorluthier_engine import (
    CancelJob,
    ColorContextDeclaration,
    ColorContextUnknownReason,
    ColorDocument,
    ColorManagementLane,
    CommandStatus,
    ConfigureColorTransformation,
    ContentIdentity,
    DeclareColorContexts,
    DisplayColorContext,
    EncodingIdentity,
    ExportColorContext,
    HostFormatProfileIdentity,
    IccColorContextIdentity,
    Interpolation,
    JobPurpose,
    JobState,
    KnownColorContext,
    LoadPortableCube,
    OpenReferenceImage,
    ProofColorContext,
    ProvisionalImageFormat,
    RequestFullResolutionEvaluation,
    RequestPreview,
    RgbBounds,
    SurfacePurpose,
    UnknownColorContext,
    WorkingColorContext,
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


def synthetic_ppm(width: int, height: int, pixels: bytes) -> bytes:
    if len(pixels) != width * height * 3:
        raise ValueError("Synthetic RGB8 payload has the wrong size.")
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels


def content_identity(digit: str) -> ContentIdentity:
    return ContentIdentity(digit * 64)


def known_context(identity_digit: str, encoding_digit: str) -> KnownColorContext:
    return KnownColorContext(
        lane=ColorManagementLane.ICC,
        identity=IccColorContextIdentity(content_identity(identity_digit)),
        encoding=EncodingIdentity(
            "rgb-values-v1",
            content_identity(encoding_digit),
        ),
    )


class FullResolutionEvaluationAcceptanceTest(unittest.TestCase):
    def ready_document(
        self,
        executor: ControlledExecutor | None,
        *,
        width: int = 2,
        height: int = 2,
        pixels: bytes | None = None,
        cube: bytes = IDENTITY_CUBE,
        interpolation: Interpolation = Interpolation.TRILINEAR,
        bypass: bool = False,
        mix: float = 1.0,
    ) -> ColorDocument:
        if pixels is None:
            pixels = bytes((index * 37) % 256 for index in range(width * height * 3))
        document = ColorDocument() if executor is None else ColorDocument(executor)
        opened = document.apply(
            OpenReferenceImage(
                synthetic_ppm(width, height, pixels),
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        loaded = document.apply(
            LoadPortableCube(
                cube,
                interpolation,
                bypass=bypass,
                mix=mix,
            )
        )
        self.assertEqual(opened.status, CommandStatus.COMMITTED)
        self.assertEqual(loaded.status, CommandStatus.COMMITTED)
        return document

    def job(self, document: ColorDocument, job_id):
        return next(job for job in document.snapshot().jobs if job.job_id == job_id)

    def test_request_is_distinct_and_publishes_after_scanlines_atomically(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor, width=2, height=3)

        request = document.apply(RequestFullResolutionEvaluation())
        self.assertEqual(request.status, CommandStatus.ACCEPTED)
        self.assertEqual(
            self.job(document, request.job_id).purpose,
            JobPurpose.FULL_RESOLUTION_EVALUATION,
        )
        self.assertIsNone(request.snapshot.full_resolution)

        observed_progress = [0]
        for expected_row in range(1, 4):
            self.assertFalse(executor.run_next(request.job_id.value))
            snapshot = document.snapshot()
            self.assertIsNone(snapshot.full_resolution)
            observed_progress.append(
                self.job(document, request.job_id).progress.completed_units
            )
            self.assertEqual(observed_progress[-1], expected_row)

        self.assertTrue(executor.run_next(request.job_id.value))
        completed = document.snapshot()
        result = completed.full_resolution
        observed_progress.append(
            self.job(document, request.job_id).progress.completed_units
        )
        self.assertEqual(observed_progress, [0, 1, 2, 3, 4])
        self.assertEqual(result.job_id, request.job_id)
        self.assertEqual(result.basis, result.processed.basis)
        self.assertEqual(
            result.processed.purpose,
            SurfacePurpose.PROCESSED_FULL_RESOLUTION,
        )
        self.assertEqual((result.processed.width, result.processed.height), (2, 3))
        self.assertEqual(result.processed.row_stride, 24)
        self.assertEqual(len(result.processed.pixels), 2 * 3 * 12)
        self.assertEqual(
            result.processed.viewing_status,
            "not-rendered-with-proof-or-display",
        )
        self.assertEqual(
            tuple(field.name for field in fields(type(result))),
            ("job_id", "basis", "processed", "evidence_status"),
        )

    def test_full_resolution_matches_preview_arithmetic_for_all_modes(self) -> None:
        pixels = bytes((11, 29, 251, 64, 128, 192, 255, 0, 17))
        for interpolation in Interpolation:
            for bypass in (False, True):
                with self.subTest(interpolation=interpolation, bypass=bypass):
                    executor = ControlledExecutor()
                    document = self.ready_document(
                        executor,
                        width=3,
                        height=1,
                        pixels=pixels,
                        cube=RED_BLUE_SWAP_CUBE,
                        interpolation=interpolation,
                        bypass=bypass,
                        mix=0.375,
                    )
                    preview = document.apply(RequestPreview())
                    full_resolution = document.apply(
                        RequestFullResolutionEvaluation()
                    )
                    executor.run_in_order(
                        (full_resolution.job_id.value, preview.job_id.value)
                    )
                    snapshot = document.snapshot()
                    self.assertEqual(
                        snapshot.full_resolution.processed.pixels,
                        snapshot.preview.processed.pixels,
                    )
                    if bypass:
                        self.assertEqual(
                            snapshot.full_resolution.processed.pixels,
                            snapshot.preview.original.pixels,
                        )

    def test_viewing_and_export_changes_do_not_stale_or_bake_the_result(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor, width=1, height=1)
        working = known_context("1", "2")
        proof = known_context("3", "4")
        display = known_context("5", "6")
        output = known_context("7", "8")
        bounds = RgbBounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        declaration = ColorContextDeclaration(
            selected_lane=ColorManagementLane.ICC,
            working=WorkingColorContext(working),
            proof=ProofColorContext(proof),
            display=DisplayColorContext(display, content_identity("9")),
            export_context=ExportColorContext(
                input_context=working,
                output_context=output,
                numeric_domain=bounds,
                numeric_range=bounds,
                interpolation=Interpolation.TRILINEAR,
                profile=HostFormatProfileIdentity(
                    "portable-cube",
                    "1",
                    content_identity("a"),
                ),
            ),
        )
        declared = document.apply(
            DeclareColorContexts(
                declaration,
                document.snapshot().color_contexts.revision_basis,
            )
        )
        request = document.apply(RequestFullResolutionEvaluation())
        captured_basis = self.job(document, request.job_id).basis

        removed = document.apply(
            DeclareColorContexts(
                ColorContextDeclaration(
                    selected_lane=ColorManagementLane.ICC,
                    working=WorkingColorContext(working),
                ),
                document.snapshot().color_contexts.revision_basis,
            )
        )
        self.assertEqual(
            removed.snapshot.document_revision,
            declared.snapshot.document_revision,
        )
        self.assertEqual(
            removed.snapshot.color_contexts.interpretation_revision,
            declared.snapshot.color_contexts.interpretation_revision,
        )
        self.assertGreater(
            removed.snapshot.color_contexts.viewing_revision,
            captured_basis.viewing,
        )
        self.assertGreater(
            removed.snapshot.color_contexts.export_revision,
            captured_basis.export,
        )

        executor.run_all(request.job_id.value)
        result = document.snapshot().full_resolution
        self.assertEqual(self.job(document, request.job_id).state, JobState.SUCCEEDED)
        self.assertEqual(result.basis, captured_basis)

        preview = document.apply(RequestPreview())
        executor.run_all(preview.job_id.value)
        self.assertEqual(
            result.processed.pixels,
            document.snapshot().preview.processed.pixels,
        )

    def test_reference_transformation_and_interpretation_changes_invalidate(
        self,
    ) -> None:
        for change in ("reference", "transformation", "interpretation"):
            with self.subTest(change=change):
                executor = ControlledExecutor()
                document = self.ready_document(executor, width=1, height=1)
                initial = document.apply(RequestFullResolutionEvaluation())
                executor.run_all(initial.job_id.value)
                self.assertIsNotNone(document.snapshot().full_resolution)
                refresh = document.apply(RequestFullResolutionEvaluation())

                if change == "reference":
                    changed = document.apply(
                        OpenReferenceImage(
                            synthetic_ppm(1, 1, bytes((1, 2, 3))),
                            ProvisionalImageFormat.PPM_P6_RGB8,
                        )
                    )
                elif change == "transformation":
                    changed = document.apply(ConfigureColorTransformation(mix=0.5))
                else:
                    changed = document.apply(
                        DeclareColorContexts(
                            ColorContextDeclaration(
                                selected_lane=None,
                                working=WorkingColorContext(
                                    UnknownColorContext(
                                        ColorContextUnknownReason.NOT_AVAILABLE
                                    )
                                ),
                            ),
                            document.snapshot().color_contexts.revision_basis,
                        )
                    )

                self.assertEqual(changed.status, CommandStatus.COMMITTED)
                self.assertIsNone(changed.snapshot.full_resolution)
                executor.run_all(refresh.job_id.value)
                self.assertEqual(
                    self.job(document, refresh.job_id).state,
                    JobState.STALE,
                )
                self.assertIsNone(document.snapshot().full_resolution)

    def test_cancel_failure_and_out_of_order_stale_preserve_latest_result(self) -> None:
        executor = ControlledExecutor(capacity=1)
        document = self.ready_document(executor, width=2, height=2)
        initial = document.apply(RequestFullResolutionEvaluation())
        executor.run_all(initial.job_id.value)
        published = document.snapshot().full_resolution

        cancelled = document.apply(RequestFullResolutionEvaluation())
        self.assertFalse(executor.run_next(cancelled.job_id.value))
        document.apply(CancelJob(cancelled.job_id))
        self.assertEqual(document.snapshot().full_resolution, published)
        self.assertEqual(self.job(document, cancelled.job_id).state, JobState.CANCELLED)
        self.assertTrue(executor.run_next(cancelled.job_id.value))

        pending_preview = document.apply(RequestPreview())
        failed = document.apply(RequestFullResolutionEvaluation())
        self.assertEqual(self.job(document, failed.job_id).state, JobState.FAILED)
        self.assertEqual(
            self.job(document, failed.job_id).diagnostic.code,
            "EXECUTOR_SUBMISSION_FAILED",
        )
        self.assertEqual(document.snapshot().full_resolution, published)
        document.apply(CancelJob(pending_preview.job_id))
        self.assertTrue(executor.run_next(pending_preview.job_id.value))

        stale_executor = ControlledExecutor()
        stale_document = self.ready_document(stale_executor, width=2, height=2)
        stale_initial = stale_document.apply(RequestFullResolutionEvaluation())
        stale_executor.run_all(stale_initial.job_id.value)
        older = stale_document.apply(RequestFullResolutionEvaluation())
        newer = stale_document.apply(RequestFullResolutionEvaluation())
        stale_executor.run_all(newer.job_id.value)
        latest = stale_document.snapshot().full_resolution
        stale_executor.run_all(older.job_id.value)
        self.assertEqual(stale_document.snapshot().full_resolution, latest)
        self.assertEqual(
            self.job(stale_document, older.job_id).state,
            JobState.STALE,
        )
        self.assertNotEqual(latest.job_id, stale_initial.job_id)

    def test_full_resolution_storage_boundary_and_rejection_are_deterministic(
        self,
    ) -> None:
        executor = ControlledExecutor()
        boundary_pixels = bytes(512 * 512 * 3)
        boundary = self.ready_document(
            executor,
            width=512,
            height=512,
            pixels=boundary_pixels,
            bypass=True,
        )
        accepted = boundary.apply(RequestFullResolutionEvaluation())
        self.assertEqual(accepted.status, CommandStatus.ACCEPTED)
        executor.run_all(accepted.job_id.value)
        self.assertEqual(
            len(boundary.snapshot().full_resolution.processed.pixels),
            3_145_728,
        )

        over = self.ready_document(
            ControlledExecutor(),
            width=513,
            height=512,
            pixels=bytes(513 * 512 * 3),
            bypass=True,
        )
        before = over.snapshot()
        rejected = over.apply(RequestFullResolutionEvaluation())
        self.assertEqual(rejected.status, CommandStatus.REJECTED)
        self.assertIsNone(rejected.job_id)
        self.assertEqual(rejected.snapshot, before)
        self.assertEqual(rejected.diagnostic.code, "FULL_RESOLUTION_RESOURCE_LIMIT")
        self.assertEqual(
            {field.name: field.value for field in rejected.diagnostic.context},
            {
                "maximum_pixels": 262_144,
                "maximum_output_bytes": 3_145_728,
                "maximum_scratch_bytes": 3_145_728,
            },
        )

    def test_active_queued_work_history_and_result_retention_are_bounded(self) -> None:
        active_executor = ControlledExecutor()
        active_document = self.ready_document(active_executor, width=1, height=1)
        active = [active_document.apply(RequestPreview()) for _ in range(4)]
        rejected_active = active_document.apply(RequestPreview())
        self.assertTrue(
            all(result.status is CommandStatus.ACCEPTED for result in active)
        )
        self.assertEqual(rejected_active.status, CommandStatus.REJECTED)
        self.assertEqual(rejected_active.diagnostic.code, "JOB_CAPACITY_EXHAUSTED")
        self.assertEqual(rejected_active.diagnostic.context[0].value, 4)

        work_executor = ControlledExecutor()
        work_document = self.ready_document(
            work_executor,
            width=1,
            height=4096,
            pixels=bytes(4096 * 3),
            bypass=True,
        )
        queued = [work_document.apply(RequestPreview()) for _ in range(2)]
        rejected_work = work_document.apply(RequestPreview())
        self.assertTrue(
            all(result.status is CommandStatus.ACCEPTED for result in queued)
        )
        self.assertEqual(rejected_work.status, CommandStatus.REJECTED)
        self.assertEqual(
            rejected_work.diagnostic.code,
            "JOB_WORK_CAPACITY_EXHAUSTED",
        )
        self.assertEqual(rejected_work.diagnostic.context[0].value, 8194)

        history_document = self.ready_document(None, width=1, height=1, bypass=True)
        authored_basis = history_document.snapshot().revision_basis()
        first = history_document.apply(RequestFullResolutionEvaluation())
        first_result = history_document.snapshot().full_resolution
        for _ in range(128):
            latest = history_document.apply(RequestFullResolutionEvaluation())
        snapshot = history_document.snapshot()
        self.assertEqual(len(snapshot.jobs), 128)
        self.assertEqual(snapshot.jobs[0].job_id.value, first.job_id.value + 1)
        self.assertEqual(snapshot.jobs[-1].job_id, latest.job_id)
        self.assertEqual(snapshot.full_resolution.job_id, latest.job_id)
        self.assertNotEqual(snapshot.full_resolution, first_result)
        self.assertEqual(snapshot.revision_basis(), authored_basis)

    def test_prerequisites_fail_closed_without_creating_a_job(self) -> None:
        document = ColorDocument()
        missing_reference = document.apply(RequestFullResolutionEvaluation())
        self.assertEqual(missing_reference.status, CommandStatus.REJECTED)
        self.assertEqual(
            missing_reference.diagnostic.code,
            "FULL_RESOLUTION_PREREQUISITE_MISSING",
        )
        document.apply(
            OpenReferenceImage(
                synthetic_ppm(1, 1, bytes((0, 0, 0))),
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        missing_transformation = document.apply(
            RequestFullResolutionEvaluation()
        )
        self.assertEqual(missing_transformation.status, CommandStatus.REJECTED)
        self.assertEqual(len(missing_transformation.snapshot.jobs), 0)


if __name__ == "__main__":
    unittest.main()
