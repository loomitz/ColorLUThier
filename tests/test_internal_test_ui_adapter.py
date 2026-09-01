# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import get_args

import internal_test_ui_adapter
from colorluthier_engine import (
    ColorContextDeclaration,
    ColorManagementLane,
    CommandStatus,
    ContentIdentity,
    DisplayColorContext,
    EncodingIdentity,
    ExportColorContext,
    HostFormatProfileIdentity,
    IccColorContextIdentity,
    InlineExecutor,
    Interpolation,
    JobPurpose,
    JobState,
    KnownColorContext,
    ProofColorContext,
    ProvisionalImageFormat,
    RgbBounds,
    WorkingColorContext,
)
from colorluthier_engine.testing import ControlledExecutor
from internal_test_ui_adapter import (
    ORDINARY_EXPORT_BLOCKED,
    CancelJobIntent,
    ConfigureTransformationIntent,
    DeclareColorContextsIntent,
    InspectCanonicalArtifactIntent,
    InternalTestUiAdapter,
    LoadPortableCubeIntent,
    OpenReferenceIntent,
    RenderState,
    RenderUpdate,
    RequestFullResolutionIntent,
    RequestPreviewIntent,
    SnapshotDisposition,
    UiIntent,
)


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


def ppm(width: int = 2, height: int = 2) -> bytes:
    pixels = bytes((index * 29) % 256 for index in range(width * height * 3))
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels


def content_identity(digit: str) -> ContentIdentity:
    return ContentIdentity(digit * 64)


def known_context(identity_digit: str, encoding_digit: str) -> KnownColorContext:
    return KnownColorContext(
        lane=ColorManagementLane.ICC,
        identity=IccColorContextIdentity(content_identity(identity_digit)),
        encoding=EncodingIdentity(
            identifier="rgb-values-v1",
            specification=content_identity(encoding_digit),
        ),
    )


def complete_declaration() -> ColorContextDeclaration:
    working = known_context("1", "2")
    proof = known_context("3", "4")
    display = known_context("5", "6")
    export_input = known_context("7", "8")
    export_output = known_context("9", "a")
    bounds = RgbBounds(
        minimum=(0.0, 0.0, 0.0),
        maximum=(1.0, 1.0, 1.0),
    )
    return ColorContextDeclaration(
        selected_lane=ColorManagementLane.ICC,
        working=WorkingColorContext(working),
        proof=ProofColorContext(proof),
        display=DisplayColorContext(
            display,
            viewing_interpretation=content_identity("b"),
        ),
        export_context=ExportColorContext(
            input_context=export_input,
            output_context=export_output,
            numeric_domain=bounds,
            numeric_range=bounds,
            interpolation=Interpolation.TETRAHEDRAL,
            profile=HostFormatProfileIdentity(
                identifier="portable-cube",
                version="1",
                specification=content_identity("c"),
            ),
        ),
    )


def job_by_id(state: RenderState, job_id):
    return next(job for job in state.snapshot.jobs if job.job_id == job_id)


class RejectSecondSubmissionExecutor:
    def __init__(self) -> None:
        self._delegate = InlineExecutor()
        self._submissions = 0

    def submit(self, job_id: int, step) -> None:
        self._submissions += 1
        if self._submissions == 2:
            raise RuntimeError(f"rejected job {job_id}")
        self._delegate.submit(job_id, step)


class InternalTestUiAdapterAcceptanceTest(unittest.TestCase):
    def ready_adapter(
        self,
        executor: ControlledExecutor | None = None,
        *,
        width: int = 2,
        height: int = 2,
    ) -> InternalTestUiAdapter:
        adapter = InternalTestUiAdapter(executor)
        opened = adapter.dispatch(
            OpenReferenceIntent(
                encoded=ppm(width, height),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        loaded = adapter.dispatch(
            LoadPortableCubeIntent(
                encoded=IDENTITY_CUBE,
                interpolation=Interpolation.TRILINEAR,
            )
        )
        self.assertEqual(opened.state.command_status, CommandStatus.COMMITTED)
        self.assertEqual(loaded.state.command_status, CommandStatus.COMMITTED)
        return adapter

    def test_all_intents_map_to_public_commands_and_observable_snapshots(self) -> None:
        executor = ControlledExecutor()
        adapter = InternalTestUiAdapter(executor)

        opened = adapter.dispatch(
            OpenReferenceIntent(
                ppm(),
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(opened.state.command_status, CommandStatus.COMMITTED)
        self.assertEqual(
            opened.state.snapshot.reference.image_format,
            ProvisionalImageFormat.PPM_P6_RGB8,
        )

        loaded = adapter.dispatch(
            LoadPortableCubeIntent(
                IDENTITY_CUBE,
                Interpolation.TRILINEAR,
                bypass=False,
                mix=0.75,
            )
        )
        self.assertEqual(loaded.state.command_status, CommandStatus.COMMITTED)
        self.assertEqual(loaded.state.snapshot.transformation.mix, 0.75)

        configured = adapter.dispatch(
            ConfigureTransformationIntent(
                interpolation=Interpolation.TETRAHEDRAL,
                bypass=True,
                mix=0.5,
            )
        )
        transformation = configured.state.snapshot.transformation
        self.assertEqual(configured.state.command_status, CommandStatus.COMMITTED)
        self.assertEqual(transformation.interpolation, Interpolation.TETRAHEDRAL)
        self.assertTrue(transformation.bypass)
        self.assertEqual(transformation.mix, 0.5)

        declaration = complete_declaration()
        declared = adapter.dispatch(
            DeclareColorContextsIntent(
                declaration=declaration,
                expected=adapter.current.snapshot.color_contexts.revision_basis,
            )
        )
        self.assertEqual(declared.state.command_status, CommandStatus.COMMITTED)
        self.assertEqual(
            declared.state.snapshot.color_contexts.declaration,
            declaration,
        )

        preview = adapter.dispatch(RequestPreviewIntent())
        full = adapter.dispatch(RequestFullResolutionIntent())
        canonical = adapter.dispatch(InspectCanonicalArtifactIntent())
        expected_purposes = {
            preview.state.submitted_job_id: JobPurpose.PREVIEW,
            full.state.submitted_job_id: JobPurpose.FULL_RESOLUTION_EVALUATION,
            canonical.state.submitted_job_id:
                JobPurpose.CANONICAL_PORTABLE_CUBE_EXPORT,
        }
        self.assertTrue(
            all(
                update.state.command_status is CommandStatus.ACCEPTED
                and update.state.submitted_job_id is not None
                for update in (preview, full, canonical)
            )
        )
        observed_job_ids = {
            job.job_id
            for job in canonical.state.snapshot.jobs
            if job.job_id in expected_purposes
        }
        self.assertEqual(observed_job_ids, set(expected_purposes))
        for job in canonical.state.snapshot.jobs:
            if job.job_id in expected_purposes:
                self.assertEqual(job.purpose, expected_purposes[job.job_id])

        cancelled = adapter.dispatch(CancelJobIntent(full.state.submitted_job_id))
        self.assertEqual(cancelled.state.command_status, CommandStatus.ACCEPTED)
        self.assertEqual(
            job_by_id(cancelled.state, full.state.submitted_job_id).state,
            JobState.CANCELLED,
        )

    def test_work_steps_refresh_progress_and_publish_atomically(self) -> None:
        executor = ControlledExecutor()
        adapter = self.ready_adapter(executor, width=2, height=3)
        requested = adapter.dispatch(RequestFullResolutionIntent())
        job_id = requested.state.submitted_job_id
        self.assertEqual(job_by_id(adapter.current, job_id).progress.completed_units, 0)
        self.assertIsNone(adapter.current.snapshot.full_resolution)

        self.assertFalse(executor.run_next(job_id.value))
        after_one_row = adapter.current
        self.assertEqual(job_by_id(after_one_row, job_id).progress.completed_units, 1)
        self.assertIsNone(after_one_row.snapshot.full_resolution)

        executor.run_all(job_id.value)
        completed = adapter.current
        self.assertEqual(job_by_id(completed, job_id).state, JobState.SUCCEEDED)
        self.assertEqual(
            job_by_id(completed, job_id).progress.completed_units,
            job_by_id(completed, job_id).progress.total_units,
        )
        self.assertEqual(completed.snapshot.full_resolution.job_id, job_id)

    def test_equal_revision_rejection_updates_code_and_context_without_parsing(self) -> None:
        adapter = InternalTestUiAdapter()
        before = adapter.current
        rejected = adapter.dispatch(
            OpenReferenceIntent(
                b"not a PPM",
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )

        self.assertEqual(rejected.disposition, SnapshotDisposition.ACCEPTED)
        self.assertEqual(rejected.state.watermark, before.watermark)
        self.assertIsNot(rejected.state, before)
        self.assertEqual(rejected.state.command_status, CommandStatus.REJECTED)
        self.assertEqual(
            rejected.state.diagnostic_code,
            "REFERENCE_STRUCTURE_INVALID",
        )
        self.assertEqual(
            tuple((field.name, field.value) for field in rejected.state.diagnostic_context),
            (("reason", "ppm_magic_invalid"),),
        )

    def test_older_snapshot_is_rejected_without_changing_current(self) -> None:
        adapter = InternalTestUiAdapter()
        old_snapshot = adapter.current.snapshot
        adapter.dispatch(
            OpenReferenceIntent(ppm(), ProvisionalImageFormat.PPM_P6_RGB8)
        )
        current = adapter.current

        rejected = adapter.accept_snapshot(old_snapshot)

        self.assertEqual(rejected.disposition, SnapshotDisposition.REJECTED_OLDER)
        self.assertEqual(rejected.candidate_revision, old_snapshot.snapshot_revision)
        self.assertIs(rejected.state, current)
        self.assertIs(adapter.current, current)

        equal = adapter.accept_snapshot(current.snapshot)
        self.assertEqual(equal.disposition, SnapshotDisposition.ACCEPTED)
        self.assertIs(equal.state.snapshot, current.snapshot)

    def test_cancel_and_malformed_input_preserve_last_valid_result(self) -> None:
        executor = ControlledExecutor()
        adapter = self.ready_adapter(executor)
        first = adapter.dispatch(RequestFullResolutionIntent())
        executor.run_all(first.state.submitted_job_id.value)
        valid = adapter.current.snapshot.full_resolution
        valid_reference = adapter.current.snapshot.reference

        second = adapter.dispatch(RequestFullResolutionIntent())
        self.assertFalse(executor.run_next(second.state.submitted_job_id.value))
        cancelled = adapter.dispatch(CancelJobIntent(second.state.submitted_job_id))
        self.assertIs(cancelled.state.snapshot.full_resolution, valid)
        self.assertEqual(
            job_by_id(cancelled.state, second.state.submitted_job_id).state,
            JobState.CANCELLED,
        )
        self.assertTrue(executor.run_next(second.state.submitted_job_id.value))
        self.assertIs(adapter.current.snapshot.full_resolution, valid)

        malformed = adapter.dispatch(
            OpenReferenceIntent(
                b"not a PPM",
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(malformed.state.command_status, CommandStatus.REJECTED)
        self.assertIs(malformed.state.snapshot.reference, valid_reference)
        self.assertIs(malformed.state.snapshot.full_resolution, valid)

    def test_stale_completion_cannot_replace_latest_valid_result(self) -> None:
        executor = ControlledExecutor()
        adapter = self.ready_adapter(executor)
        older = adapter.dispatch(RequestFullResolutionIntent())
        older_id = older.state.submitted_job_id
        adapter.dispatch(ConfigureTransformationIntent(mix=0.5))
        newer = adapter.dispatch(RequestFullResolutionIntent())
        newer_id = newer.state.submitted_job_id

        executor.run_all(newer_id.value)
        latest_result = adapter.current.snapshot.full_resolution
        self.assertEqual(latest_result.job_id, newer_id)

        executor.run_all(older_id.value)
        completed = adapter.current
        self.assertEqual(job_by_id(completed, older_id).state, JobState.STALE)
        self.assertIs(completed.snapshot.full_resolution, latest_result)

    def test_failed_submission_is_public_and_has_a_stable_code(self) -> None:
        adapter = InternalTestUiAdapter(RejectSecondSubmissionExecutor())
        adapter.dispatch(
            LoadPortableCubeIntent(IDENTITY_CUBE, Interpolation.TRILINEAR)
        )
        first = adapter.dispatch(InspectCanonicalArtifactIntent())
        last_valid = first.state.canonical_artifact
        failed = adapter.dispatch(InspectCanonicalArtifactIntent())
        job = job_by_id(failed.state, failed.state.submitted_job_id)

        self.assertEqual(failed.state.command_status, CommandStatus.ACCEPTED)
        self.assertEqual(job.state, JobState.FAILED)
        self.assertEqual(job.diagnostic.code, "EXECUTOR_SUBMISSION_FAILED")
        self.assertIs(failed.state.canonical_artifact, last_valid)

    def test_canonical_artifact_is_inspectable_and_ordinary_export_stays_blocked(
        self,
    ) -> None:
        adapter = self.ready_adapter()
        inspected = adapter.dispatch(InspectCanonicalArtifactIntent())
        artifact = inspected.state.canonical_artifact

        self.assertIs(artifact, inspected.state.snapshot.canonical_cube_export)
        self.assertEqual(artifact.encoded, IDENTITY_CUBE)
        self.assertEqual(artifact.byte_count, len(artifact.encoded))
        self.assertEqual(artifact.ordinary_export_status, ORDINARY_EXPORT_BLOCKED)
        self.assertEqual(inspected.state.ordinary_export_status, ORDINARY_EXPORT_BLOCKED)
        self.assertFalse(
            any("OrdinaryExport" in intent.__name__ for intent in get_args(UiIntent))
        )
        self.assertFalse(
            any("OrdinaryExport" in name for name in internal_test_ui_adapter.__all__)
        )

    def test_render_state_retains_the_exact_snapshot_and_public_values_are_frozen(
        self,
    ) -> None:
        adapter = InternalTestUiAdapter()
        snapshot = adapter.current.snapshot
        update = adapter.accept_snapshot(snapshot)
        intent = LoadPortableCubeIntent(
            IDENTITY_CUBE,
            Interpolation.TRILINEAR,
        )

        self.assertIs(update.state.snapshot, snapshot)
        self.assertEqual(
            tuple(field.name for field in fields(RenderState)),
            (
                "snapshot",
                "command_status",
                "submitted_job_id",
                "diagnostic",
                "ordinary_export_status",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            intent.mix = 0.5
        with self.assertRaises(FrozenInstanceError):
            update.state.command_status = CommandStatus.REJECTED
        with self.assertRaises(FrozenInstanceError):
            update.disposition = SnapshotDisposition.REJECTED_OLDER
        with self.assertRaises(TypeError):
            RenderState(
                snapshot=snapshot,
                ordinary_export_status="ready",
            )
        self.assertIsInstance(update, RenderUpdate)

    def test_adapter_imports_only_engine_root_and_no_runtime_or_toolkit(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        adapter_sources = tuple(
            repository_root / relative
            for relative in (
                "internal_test_ui_adapter/__init__.py",
                "internal_test_ui_adapter/_adapter.py",
                "internal_test_ui_adapter/_types.py",
            )
        )
        forbidden_roots = {
            "AppKit",
            "PyQt5",
            "PyQt6",
            "PySide2",
            "PySide6",
            "portable_cube_harness",
            "tkinter",
        }
        forbidden_names = {
            "ControlledExecutor",
            "_image_source",
            "_portable_cube",
            "_processing",
            "parser",
            "serializer",
        }

        for source_path in adapter_sources:
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(source_path))
            imported_roots = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_roots.update(
                        alias.name.split(".", maxsplit=1)[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_roots.add(node.module.split(".", maxsplit=1)[0])
                    if node.module.startswith("colorluthier_engine"):
                        self.assertEqual(node.module, "colorluthier_engine")
            self.assertTrue(forbidden_roots.isdisjoint(imported_roots))
            for forbidden_name in forbidden_names:
                self.assertNotIn(forbidden_name, source)


if __name__ == "__main__":
    unittest.main()
