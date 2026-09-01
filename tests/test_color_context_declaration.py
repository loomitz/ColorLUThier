from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
import unittest

from colorluthier_engine import (
    ColorContextDeclaration,
    ColorContextRevisionBasis,
    ColorContextUnknownReason,
    ColorDocument,
    ColorManagementLane,
    CommandStatus,
    ContentIdentity,
    DeclareColorContexts,
    DisplayColorContext,
    EncodingIdentity,
    ExportColorContext,
    ExportRevision,
    HostFormatProfileIdentity,
    IccColorContextIdentity,
    InterpretationRevision,
    Interpolation,
    JobId,
    JobState,
    KnownColorContext,
    LoadPortableCube,
    OcioAcesColorContextIdentity,
    OpenReferenceImage,
    ProofColorContext,
    ProvisionalImageFormat,
    RequestCanonicalPortableCubeExport,
    RequestPreview,
    RevisionBasis,
    RgbBounds,
    SourceColorContext,
    UnknownColorContext,
    ViewingRevision,
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


def content_identity(digit: str) -> ContentIdentity:
    return ContentIdentity(digit * 64)


def encoding_identity(digit: str) -> EncodingIdentity:
    return EncodingIdentity("rgb-values-v1", content_identity(digit))


def known_context(
    lane: ColorManagementLane,
    *,
    identity_digit: str,
    encoding_digit: str,
) -> KnownColorContext:
    identity = (
        IccColorContextIdentity(content_identity(identity_digit))
        if lane is ColorManagementLane.ICC
        else OcioAcesColorContextIdentity(
            content_identity(identity_digit),
            "ACEScg",
        )
    )
    return KnownColorContext(
        lane=lane,
        identity=identity,
        encoding=encoding_identity(encoding_digit),
    )


def export_context(
    lane: ColorManagementLane = ColorManagementLane.ICC,
) -> ExportColorContext:
    bounds = RgbBounds(
        minimum=(0.0, 0.0, 0.0),
        maximum=(1.0, 1.0, 1.0),
    )
    return ExportColorContext(
        input_context=known_context(
            lane,
            identity_digit="4",
            encoding_digit="5",
        ),
        output_context=known_context(
            lane,
            identity_digit="6",
            encoding_digit="7",
        ),
        numeric_domain=bounds,
        numeric_range=bounds,
        interpolation=Interpolation.TETRAHEDRAL,
        profile=HostFormatProfileIdentity(
            "portable-cube",
            "1",
            content_identity("8"),
        ),
    )


def icc_declaration(
    *,
    working_identity_digit: str = "1",
    display_identity_digit: str | None = None,
    export: ExportColorContext | None = None,
) -> ColorContextDeclaration:
    display = None
    if display_identity_digit is not None:
        display = DisplayColorContext(
            known_context(
                ColorManagementLane.ICC,
                identity_digit=display_identity_digit,
                encoding_digit="3",
            ),
            viewing_interpretation=content_identity("9"),
        )
    return ColorContextDeclaration(
        selected_lane=ColorManagementLane.ICC,
        working=WorkingColorContext(
            known_context(
                ColorManagementLane.ICC,
                identity_digit=working_identity_digit,
                encoding_digit="2",
            )
        ),
        proof=None,
        display=display,
        export_context=export,
    )


def ocio_declaration() -> ColorContextDeclaration:
    return ColorContextDeclaration(
        selected_lane=ColorManagementLane.OCIO_ACES,
        working=WorkingColorContext(
            known_context(
                ColorManagementLane.OCIO_ACES,
                identity_digit="a",
                encoding_digit="b",
            )
        ),
    )


def ppm(red: int, green: int, blue: int, *, width: int = 2) -> bytes:
    pixel = bytes((red, green, blue))
    return f"P6\n{width} 1\n255\n".encode("ascii") + pixel * width


class ColorContextDeclarationAcceptanceTest(unittest.TestCase):
    def job(self, document: ColorDocument, job_id: JobId):
        matches = tuple(
            job for job in document.snapshot().jobs if job.job_id == job_id
        )
        self.assertEqual(len(matches), 1)
        return matches[0]

    def declare(
        self,
        document: ColorDocument,
        declaration: ColorContextDeclaration,
    ):
        return document.apply(
            DeclareColorContexts(
                declaration=declaration,
                expected=document.snapshot().color_contexts.revision_basis,
            )
        )

    def ready_document(
        self,
        executor: ControlledExecutor,
    ) -> ColorDocument:
        document = ColorDocument(executor=executor)
        opened = document.apply(
            OpenReferenceImage(
                encoded=ppm(12, 34, 56),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(opened.status, CommandStatus.COMMITTED)
        loaded = document.apply(
            LoadPortableCube(
                encoded=IDENTITY_CUBE,
                interpolation=Interpolation.TETRAHEDRAL,
            )
        )
        self.assertEqual(loaded.status, CommandStatus.COMMITTED)
        declared = self.declare(
            document,
            icc_declaration(display_identity_digit="c"),
        )
        self.assertEqual(declared.status, CommandStatus.COMMITTED)
        return document

    def publish_preview_and_canonical(
        self,
        document: ColorDocument,
        executor: ControlledExecutor,
    ) -> None:
        preview = document.apply(RequestPreview())
        canonical = document.apply(RequestCanonicalPortableCubeExport())
        executor.run_all(preview.job_id.value)
        executor.run_all(canonical.job_id.value)
        self.assertEqual(self.job(document, preview.job_id).state, JobState.SUCCEEDED)
        self.assertEqual(
            self.job(document, canonical.job_id).state,
            JobState.SUCCEEDED,
        )

    def test_revision_values_and_initial_projection_are_immutable(self) -> None:
        revision_types = (
            InterpretationRevision,
            ViewingRevision,
            ExportRevision,
        )
        for revision_type in revision_types:
            with self.subTest(revision_type=revision_type.__name__):
                zero = revision_type(0)
                one = revision_type(1)
                self.assertLess(zero, one)
                with self.assertRaises(ValueError):
                    revision_type(-1)
                with self.assertRaises(FrozenInstanceError):
                    zero.value = 2

        zero_basis = ColorContextRevisionBasis(
            interpretation=InterpretationRevision(0),
            viewing=ViewingRevision(0),
            export=ExportRevision(0),
        )
        snapshot = ColorDocument().snapshot().color_contexts
        expected_declaration = ColorContextDeclaration(
            selected_lane=None,
            working=WorkingColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_DECLARED)
            ),
        )

        self.assertEqual(snapshot.declaration, expected_declaration)
        self.assertEqual(snapshot.revision_basis, zero_basis)
        self.assertEqual(snapshot.export_context, None)
        self.assertTrue(snapshot.inspection_only)
        with self.assertRaises(FrozenInstanceError):
            zero_basis.interpretation = InterpretationRevision(3)

        document = ColorDocument()
        opened = document.apply(
            OpenReferenceImage(
                encoded=ppm(1, 2, 3),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        ).snapshot
        default_semantic_basis = RevisionBasis(
            document=opened.document_revision,
            reference=opened.reference.revision,
            transformation=None,
        )
        captured_basis = opened.revision_basis()
        self.assertNotEqual(captured_basis, default_semantic_basis)
        self.assertEqual(
            captured_basis.interpretation,
            InterpretationRevision(1),
        )
        self.assertEqual(captured_basis, replace(captured_basis))

        semantic_fields = {
            field.name: field for field in fields(RevisionBasis)
        }
        semantic_variants = (
            replace(
                captured_basis,
                interpretation=InterpretationRevision(2),
            ),
            replace(captured_basis, viewing=ViewingRevision(1)),
            replace(captured_basis, export=ExportRevision(1)),
        )
        for field_name, variant in zip(
            ("interpretation", "viewing", "export"),
            semantic_variants,
            strict=True,
        ):
            with self.subTest(field_name=field_name):
                self.assertTrue(semantic_fields[field_name].compare)
                self.assertNotEqual(captured_basis, variant)
        self.assertEqual(len({captured_basis, *semantic_variants}), 4)

    def test_declaration_validates_lane_and_does_not_own_source(self) -> None:
        self.assertNotIn(
            "source",
            tuple(field.name for field in fields(ColorContextDeclaration)),
        )
        self.assertNotIn(
            "source_color_context",
            tuple(field.name for field in fields(ColorContextDeclaration)),
        )

        with self.assertRaises(ValueError):
            ColorContextDeclaration(
                selected_lane=None,
                working=WorkingColorContext(
                    known_context(
                        ColorManagementLane.ICC,
                        identity_digit="1",
                        encoding_digit="2",
                    )
                ),
            )
        unknown_proof = ColorContextDeclaration(
            selected_lane=None,
            working=WorkingColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_DECLARED)
            ),
            proof=ProofColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_AVAILABLE)
            ),
        )
        self.assertIsNone(unknown_proof.selected_lane)
        with self.assertRaises(ValueError):
            ColorContextDeclaration(
                selected_lane=ColorManagementLane.ICC,
                working=WorkingColorContext(
                    known_context(
                        ColorManagementLane.OCIO_ACES,
                        identity_digit="a",
                        encoding_digit="b",
                    )
                ),
            )
        with self.assertRaises(ValueError):
            ColorContextDeclaration(
                selected_lane=ColorManagementLane.ICC,
                working=WorkingColorContext(
                    known_context(
                        ColorManagementLane.ICC,
                        identity_digit="1",
                        encoding_digit="2",
                    )
                ),
                export_context=export_context(ColorManagementLane.OCIO_ACES),
            )

        document = ColorDocument()
        opened = document.apply(
            OpenReferenceImage(
                encoded=ppm(64, 128, 192),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        source_before = opened.snapshot.reference.source_color_context
        declared = self.declare(document, icc_declaration())

        self.assertEqual(declared.status, CommandStatus.COMMITTED)
        self.assertEqual(
            declared.snapshot.reference.source_color_context,
            source_before,
        )
        self.assertEqual(
            source_before,
            SourceColorContext(
                UnknownColorContext(
                    ColorContextUnknownReason.SOURCE_METADATA_MISSING
                )
            ),
        )

    def test_whole_value_commit_revisions_idempotence_and_conflict(self) -> None:
        document = ColorDocument()
        initial = document.snapshot()
        stale_basis = initial.color_contexts.revision_basis
        working = icc_declaration()

        first = document.apply(
            DeclareColorContexts(declaration=working, expected=stale_basis)
        )
        self.assertEqual(first.status, CommandStatus.COMMITTED)
        self.assertEqual(
            first.snapshot.document_revision.value,
            initial.document_revision.value + 1,
        )
        self.assertEqual(
            first.snapshot.snapshot_revision.value,
            initial.snapshot_revision.value + 1,
        )
        self.assertEqual(
            first.snapshot.color_contexts.revision_basis,
            ColorContextRevisionBasis(
                interpretation=InterpretationRevision(1),
                viewing=ViewingRevision(0),
                export=ExportRevision(0),
            ),
        )

        display_only = replace(
            working,
            display=DisplayColorContext(
                known_context(
                    ColorManagementLane.ICC,
                    identity_digit="c",
                    encoding_digit="3",
                ),
                viewing_interpretation=content_identity("9"),
            ),
        )
        second = self.declare(document, display_only)
        self.assertEqual(second.status, CommandStatus.COMMITTED)
        self.assertEqual(
            second.snapshot.document_revision.value,
            first.snapshot.document_revision.value,
        )
        self.assertEqual(
            second.snapshot.snapshot_revision.value,
            first.snapshot.snapshot_revision.value + 1,
        )
        self.assertEqual(
            second.snapshot.color_contexts.revision_basis,
            ColorContextRevisionBasis(
                interpretation=InterpretationRevision(1),
                viewing=ViewingRevision(1),
                export=ExportRevision(0),
            ),
        )

        export_only = replace(display_only, export_context=export_context())
        third = self.declare(document, export_only)
        self.assertEqual(third.status, CommandStatus.COMMITTED)
        self.assertEqual(
            third.snapshot.document_revision,
            second.snapshot.document_revision,
        )
        self.assertEqual(
            third.snapshot.color_contexts.revision_basis,
            ColorContextRevisionBasis(
                interpretation=InterpretationRevision(1),
                viewing=ViewingRevision(1),
                export=ExportRevision(1),
            ),
        )

        interpretation_only = replace(
            export_only,
            working=icc_declaration(
                working_identity_digit="d"
            ).working,
        )
        fourth = self.declare(document, interpretation_only)
        self.assertEqual(fourth.status, CommandStatus.COMMITTED)
        self.assertEqual(
            fourth.snapshot.document_revision.value,
            third.snapshot.document_revision.value + 1,
        )
        self.assertEqual(
            fourth.snapshot.color_contexts.revision_basis,
            ColorContextRevisionBasis(
                interpretation=InterpretationRevision(2),
                viewing=ViewingRevision(1),
                export=ExportRevision(1),
            ),
        )

        unchanged = document.apply(
            DeclareColorContexts(
                declaration=interpretation_only,
                expected=stale_basis,
            )
        )
        self.assertEqual(unchanged.status, CommandStatus.UNCHANGED)
        self.assertEqual(unchanged.snapshot, fourth.snapshot)

        conflict = document.apply(
            DeclareColorContexts(
                declaration=replace(
                    interpretation_only,
                    export_context=None,
                ),
                expected=stale_basis,
            )
        )
        self.assertEqual(conflict.status, CommandStatus.REJECTED)
        self.assertEqual(conflict.diagnostic.code, "COLOR_CONTEXT_REVISION_CONFLICT")
        self.assertEqual(conflict.snapshot, fourth.snapshot)
        self.assertEqual(document.snapshot(), fourth.snapshot)

    def test_one_declaration_advances_every_semantic_revision_once(self) -> None:
        document = ColorDocument()
        first = self.declare(document, icc_declaration())
        before = first.snapshot
        combined = replace(
            before.color_contexts.declaration,
            working=icc_declaration(working_identity_digit="d").working,
            display=DisplayColorContext(
                known_context(
                    ColorManagementLane.ICC,
                    identity_digit="c",
                    encoding_digit="3",
                ),
                viewing_interpretation=content_identity("9"),
            ),
            export_context=export_context(),
        )

        changed = self.declare(document, combined)

        self.assertEqual(changed.status, CommandStatus.COMMITTED)
        self.assertEqual(
            changed.snapshot.document_revision.value,
            before.document_revision.value + 1,
        )
        self.assertEqual(
            changed.snapshot.snapshot_revision.value,
            before.snapshot_revision.value + 1,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.revision_basis,
            ColorContextRevisionBasis(
                interpretation=InterpretationRevision(
                    before.color_contexts.interpretation_revision.value + 1
                ),
                viewing=ViewingRevision(
                    before.color_contexts.viewing_revision.value + 1
                ),
                export=ExportRevision(
                    before.color_contexts.export_revision.value + 1
                ),
            ),
        )

    def test_selected_lane_cannot_be_removed_or_changed(self) -> None:
        document = ColorDocument()
        accepted = self.declare(document, icc_declaration())
        self.assertEqual(accepted.status, CommandStatus.COMMITTED)
        accepted_snapshot = accepted.snapshot

        undeclared = ColorContextDeclaration(
            selected_lane=None,
            working=WorkingColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_DECLARED)
            ),
        )
        removed = self.declare(document, undeclared)
        self.assertEqual(removed.status, CommandStatus.REJECTED)
        self.assertEqual(
            removed.diagnostic.code,
            "COLOR_MANAGEMENT_LANE_CHANGE_REQUIRES_NEW_SCOPE",
        )
        self.assertEqual(removed.snapshot, accepted_snapshot)

        changed = self.declare(document, ocio_declaration())
        self.assertEqual(changed.status, CommandStatus.REJECTED)
        self.assertEqual(
            changed.diagnostic.code,
            "COLOR_MANAGEMENT_LANE_CHANGE_REQUIRES_NEW_SCOPE",
        )
        self.assertEqual(changed.snapshot, accepted_snapshot)
        self.assertEqual(document.snapshot(), accepted_snapshot)

    def test_working_change_invalidates_only_preview_purpose(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        self.publish_preview_and_canonical(document, executor)
        before = document.snapshot()
        published_canonical = before.canonical_cube_export
        preview_request = document.apply(RequestPreview())
        canonical_request = document.apply(RequestCanonicalPortableCubeExport())
        changed_declaration = replace(
            before.color_contexts.declaration,
            working=icc_declaration(working_identity_digit="d").working,
        )

        changed = self.declare(document, changed_declaration)

        self.assertEqual(changed.status, CommandStatus.COMMITTED)
        self.assertEqual(
            changed.snapshot.document_revision.value,
            before.document_revision.value + 1,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.interpretation_revision,
            InterpretationRevision(
                before.color_contexts.interpretation_revision.value + 1
            ),
        )
        self.assertEqual(
            changed.snapshot.color_contexts.viewing_revision,
            before.color_contexts.viewing_revision,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.export_revision,
            before.color_contexts.export_revision,
        )
        self.assertIsNone(changed.snapshot.preview)
        self.assertEqual(
            changed.snapshot.canonical_cube_export,
            published_canonical,
        )

        executor.run_all(preview_request.job_id.value)
        executor.run_all(canonical_request.job_id.value)
        self.assertEqual(
            self.job(document, preview_request.job_id).state,
            JobState.STALE,
        )
        self.assertEqual(
            self.job(document, canonical_request.job_id).state,
            JobState.SUCCEEDED,
        )

    def test_reference_noop_and_rejection_preserve_declared_contexts(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        before = document.snapshot()

        identical = document.apply(
            OpenReferenceImage(
                encoded=ppm(12, 34, 56),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(identical.status, CommandStatus.UNCHANGED)
        self.assertEqual(identical.snapshot, before)

        rejected = document.apply(
            OpenReferenceImage(
                encoded=b"not a PPM",
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(rejected.status, CommandStatus.REJECTED)
        self.assertEqual(rejected.snapshot, before)
        self.assertEqual(document.snapshot(), before)

    def test_display_change_invalidates_only_preview_purpose(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        self.publish_preview_and_canonical(document, executor)
        published_canonical = document.snapshot().canonical_cube_export

        preview_request = document.apply(RequestPreview())
        canonical_request = document.apply(RequestCanonicalPortableCubeExport())
        before = document.snapshot()
        changed_declaration = replace(
            before.color_contexts.declaration,
            display=DisplayColorContext(
                known_context(
                    ColorManagementLane.ICC,
                    identity_digit="d",
                    encoding_digit="3",
                ),
                viewing_interpretation=content_identity("e"),
            ),
        )
        changed = document.apply(
            DeclareColorContexts(
                declaration=changed_declaration,
                expected=before.color_contexts.revision_basis,
            )
        )

        self.assertEqual(changed.status, CommandStatus.COMMITTED)
        self.assertIsNone(changed.snapshot.preview)
        self.assertEqual(
            changed.snapshot.canonical_cube_export,
            published_canonical,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.interpretation_revision,
            before.color_contexts.interpretation_revision,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.viewing_revision,
            ViewingRevision(before.color_contexts.viewing_revision.value + 1),
        )
        self.assertEqual(
            changed.snapshot.color_contexts.export_revision,
            before.color_contexts.export_revision,
        )

        executor.run_all(preview_request.job_id.value)
        executor.run_all(canonical_request.job_id.value)
        self.assertEqual(
            self.job(document, preview_request.job_id).state,
            JobState.STALE,
        )
        self.assertEqual(
            self.job(document, canonical_request.job_id).state,
            JobState.SUCCEEDED,
        )
        self.assertIsNone(document.snapshot().preview)
        self.assertEqual(
            document.snapshot().canonical_cube_export.job_id,
            canonical_request.job_id,
        )

    def test_export_change_preserves_outputs_and_inflight_preview(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        self.publish_preview_and_canonical(document, executor)
        before = document.snapshot()
        published_preview = before.preview
        published_canonical = before.canonical_cube_export
        preview_request = document.apply(RequestPreview())

        export_only = replace(
            document.snapshot().color_contexts.declaration,
            export_context=export_context(),
        )
        changed = self.declare(document, export_only)

        self.assertEqual(changed.status, CommandStatus.COMMITTED)
        self.assertEqual(changed.snapshot.preview, published_preview)
        self.assertEqual(
            changed.snapshot.canonical_cube_export,
            published_canonical,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.interpretation_revision,
            before.color_contexts.interpretation_revision,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.viewing_revision,
            before.color_contexts.viewing_revision,
        )
        self.assertEqual(
            changed.snapshot.color_contexts.export_revision,
            ExportRevision(before.color_contexts.export_revision.value + 1),
        )

        executor.run_all(preview_request.job_id.value)
        completed = document.snapshot()
        self.assertEqual(
            self.job(document, preview_request.job_id).state,
            JobState.SUCCEEDED,
        )
        self.assertEqual(completed.preview.job_id, preview_request.job_id)
        self.assertEqual(completed.canonical_cube_export, published_canonical)
        self.assertEqual(
            completed.canonical_cube_export.ordinary_export_status,
            "blocked-pending-explicit-color-contexts",
        )

    def test_removing_optional_contexts_invalidates_only_preview(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        complete_declaration = replace(
            document.snapshot().color_contexts.declaration,
            proof=ProofColorContext(
                known_context(
                    ColorManagementLane.ICC,
                    identity_digit="a",
                    encoding_digit="b",
                )
            ),
            export_context=export_context(),
        )
        declared = self.declare(document, complete_declaration)
        self.assertEqual(declared.status, CommandStatus.COMMITTED)
        self.publish_preview_and_canonical(document, executor)
        published = document.snapshot()
        published_canonical = published.canonical_cube_export
        self.assertIsNotNone(published.color_contexts.proof)
        self.assertIsNotNone(published.color_contexts.display)
        self.assertIsNotNone(published.color_contexts.export_context)

        preview_request = document.apply(RequestPreview())
        canonical_request = document.apply(RequestCanonicalPortableCubeExport())
        before_removal = document.snapshot()
        removal = replace(
            before_removal.color_contexts.declaration,
            proof=None,
            display=None,
            export_context=None,
        )

        removed = document.apply(
            DeclareColorContexts(
                declaration=removal,
                expected=before_removal.color_contexts.revision_basis,
            )
        )

        self.assertEqual(removed.status, CommandStatus.COMMITTED)
        self.assertEqual(
            removed.snapshot.snapshot_revision.value,
            before_removal.snapshot_revision.value + 1,
        )
        self.assertEqual(
            removed.snapshot.document_revision,
            before_removal.document_revision,
        )
        self.assertEqual(
            removed.snapshot.color_contexts.interpretation_revision,
            before_removal.color_contexts.interpretation_revision,
        )
        self.assertEqual(
            removed.snapshot.color_contexts.viewing_revision,
            ViewingRevision(
                before_removal.color_contexts.viewing_revision.value + 1
            ),
        )
        self.assertEqual(
            removed.snapshot.color_contexts.export_revision,
            ExportRevision(
                before_removal.color_contexts.export_revision.value + 1
            ),
        )
        self.assertIsNone(removed.snapshot.color_contexts.proof)
        self.assertIsNone(removed.snapshot.color_contexts.display)
        self.assertIsNone(removed.snapshot.color_contexts.export_context)
        self.assertIsNone(removed.snapshot.preview)
        self.assertEqual(
            removed.snapshot.canonical_cube_export,
            published_canonical,
        )

        executor.run_all(preview_request.job_id.value)
        executor.run_all(canonical_request.job_id.value)
        completed = document.snapshot()
        self.assertEqual(
            self.job(document, preview_request.job_id).state,
            JobState.STALE,
        )
        self.assertEqual(
            self.job(document, canonical_request.job_id).state,
            JobState.SUCCEEDED,
        )
        self.assertIsNone(completed.preview)
        self.assertEqual(
            completed.canonical_cube_export.job_id,
            canonical_request.job_id,
        )

    def test_new_reference_advances_interpretation_only(self) -> None:
        executor = ControlledExecutor()
        document = self.ready_document(executor)
        self.publish_preview_and_canonical(document, executor)
        before = document.snapshot()
        published_canonical = before.canonical_cube_export
        declaration = before.color_contexts.declaration
        preview_request = document.apply(RequestPreview())
        canonical_request = document.apply(RequestCanonicalPortableCubeExport())

        opened = document.apply(
            OpenReferenceImage(
                encoded=ppm(90, 80, 70),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )

        self.assertEqual(opened.status, CommandStatus.COMMITTED)
        self.assertEqual(opened.snapshot.color_contexts.declaration, declaration)
        self.assertEqual(
            opened.snapshot.color_contexts.interpretation_revision,
            InterpretationRevision(
                before.color_contexts.interpretation_revision.value + 1
            ),
        )
        self.assertEqual(
            opened.snapshot.color_contexts.viewing_revision,
            before.color_contexts.viewing_revision,
        )
        self.assertEqual(
            opened.snapshot.color_contexts.export_revision,
            before.color_contexts.export_revision,
        )
        self.assertIsNone(opened.snapshot.preview)
        self.assertEqual(
            opened.snapshot.canonical_cube_export,
            published_canonical,
        )
        self.assertEqual(
            opened.snapshot.reference.source_color_context,
            SourceColorContext(
                UnknownColorContext(
                    ColorContextUnknownReason.SOURCE_METADATA_MISSING
                )
            ),
        )

        executor.run_all(preview_request.job_id.value)
        executor.run_all(canonical_request.job_id.value)
        self.assertEqual(
            self.job(document, preview_request.job_id).state,
            JobState.STALE,
        )
        self.assertEqual(
            self.job(document, canonical_request.job_id).state,
            JobState.SUCCEEDED,
        )
        self.assertIsNone(document.snapshot().preview)
        self.assertEqual(
            document.snapshot().canonical_cube_export.job_id,
            canonical_request.job_id,
        )


if __name__ == "__main__":
    unittest.main()
