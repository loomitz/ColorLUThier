"""Transactional public acceptance seam for the provisional headless engine."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Generator
from dataclasses import dataclass, replace
from typing import Any

from ._image_source import (
    DecodedImage,
    ImageSource,
    ImageSourceError,
    StdlibImageSource,
)
from ._portable_cube import PortableCube, PortableCubeError, parse_portable_cube
from ._processing import (
    ExportCandidate,
    PreviewCandidate,
    ProcessingError,
    export_plan,
    export_total_units,
    preview_plan,
    preview_total_units,
)
from .execution import InlineExecutor, WorkExecutor
from .model import (
    ArtifactId,
    CancelJob,
    CanonicalPortableCubeArtifact,
    ColorContextDeclaration,
    ColorContextRevisionBasis,
    ColorContextUnknownReason,
    ColorContextsSnapshot,
    ColorTransformationSnapshot,
    CommandResult,
    CommandStatus,
    ConfigureColorTransformation,
    DeclareColorContexts,
    DerivedSurfaceSnapshot,
    Diagnostic,
    DiagnosticField,
    DocumentCommand,
    DocumentRevision,
    DocumentSnapshot,
    ExportRevision,
    Interpolation,
    InterpretationRevision,
    JobId,
    JobPurpose,
    JobSnapshot,
    JobState,
    LoadPortableCube,
    OpenReferenceImage,
    PreviewBundle,
    Progress,
    ProvisionalImageFormat,
    ReferenceImageSnapshot,
    RequestCanonicalPortableCubeExport,
    RequestPreview,
    RevisionBasis,
    SnapshotRevision,
    SourceColorContext,
    SurfaceEncoding,
    SurfaceId,
    SurfacePurpose,
    TransformationRevision,
    UnknownColorContext,
    ViewingRevision,
    WorkingColorContext,
)


_MAX_ACTIVE_JOBS = 4
_JOB_HISTORY_LIMIT = 128
_TERMINAL_JOB_STATES = frozenset(
    {
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.STALE,
    }
)
_PROVISIONAL_BEHAVIORS = (
    "Reference-image decoding is limited to bounded RGB8 PPM P6 and PNG inputs.",
    "Reference-image color context is unknown and preview surfaces are unmanaged.",
    "Preview pixels are deterministic big-endian RGB binary32 values without "
    "display conversion.",
    "Canonical Cube artifacts are imported-lattice inspection data; ordinary "
    "color-managed export remains blocked.",
)
_INITIAL_COLOR_CONTEXTS = ColorContextsSnapshot(
    selected_lane=None,
    working=WorkingColorContext(
        UnknownColorContext(ColorContextUnknownReason.NOT_DECLARED)
    ),
    proof=None,
    display=None,
)


@dataclass(frozen=True, slots=True)
class _ReferenceState:
    public: ReferenceImageSnapshot
    decoded: DecodedImage
    original_encoded: bytes


@dataclass(frozen=True, slots=True)
class _TransformationState:
    public: ColorTransformationSnapshot
    cube: PortableCube


@dataclass(frozen=True, slots=True)
class _DocumentState:
    revision: DocumentRevision
    reference: _ReferenceState | None
    transformation: _TransformationState | None
    preview: PreviewBundle | None
    canonical_cube_export: CanonicalPortableCubeArtifact | None
    color_contexts: ColorContextsSnapshot


@dataclass(slots=True)
class _JobRecord:
    job_id: JobId
    purpose: JobPurpose
    basis: RevisionBasis
    state: JobState
    progress: Progress
    plan: Generator[int, None, PreviewCandidate | ExportCandidate]
    diagnostic: Diagnostic | None = None


class ColorDocument:
    """Own all mutable engine state behind one command/snapshot interface.

    The injected executor must invoke work steps serially. The domain neither
    imports nor selects a concrete threading, event-loop, UI, or GPU framework.
    """

    def __init__(
        self,
        executor: WorkExecutor | None = None,
        *,
        image_source: ImageSource | None = None,
    ) -> None:
        self._executor = InlineExecutor() if executor is None else executor
        self._image_source = (
            StdlibImageSource() if image_source is None else image_source
        )
        self._state = _DocumentState(
            revision=DocumentRevision(0),
            reference=None,
            transformation=None,
            preview=None,
            canonical_cube_export=None,
            color_contexts=_INITIAL_COLOR_CONTEXTS,
        )
        self._snapshot_revision = SnapshotRevision(0)
        self._next_job_id = 1
        self._next_surface_id = 1
        self._next_artifact_id = 1
        self._jobs: dict[int, _JobRecord] = {}
        self._latest_job_by_purpose: dict[JobPurpose, JobId] = {}

    def apply(self, command: DocumentCommand) -> CommandResult:
        """Apply one immutable command and return a complete immutable snapshot."""

        if isinstance(command, OpenReferenceImage):
            return self._open_reference(command)
        if isinstance(command, LoadPortableCube):
            return self._load_portable_cube(command)
        if isinstance(command, ConfigureColorTransformation):
            return self._configure_transformation(command)
        if isinstance(command, DeclareColorContexts):
            return self._declare_color_contexts(command)
        if isinstance(command, RequestPreview):
            return self._request_preview()
        if isinstance(command, RequestCanonicalPortableCubeExport):
            return self._request_canonical_cube_export()
        if isinstance(command, CancelJob):
            return self._cancel_job(command)
        return self._rejected(
            "COMMAND_UNSUPPORTED",
            "The command type is not supported by this ColorDocument.",
        )

    def snapshot(self) -> DocumentSnapshot:
        """Return the current immutable public projection without advancing it."""

        return DocumentSnapshot(
            snapshot_revision=self._snapshot_revision,
            document_revision=self._state.revision,
            reference=(
                None if self._state.reference is None else self._state.reference.public
            ),
            transformation=(
                None
                if self._state.transformation is None
                else self._state.transformation.public
            ),
            preview=self._state.preview,
            canonical_cube_export=self._state.canonical_cube_export,
            color_contexts=self._state.color_contexts,
            jobs=tuple(self._job_snapshot(record) for record in self._jobs.values()),
            provisional_behaviors=_PROVISIONAL_BEHAVIORS,
        )

    def _open_reference(self, command: OpenReferenceImage) -> CommandResult:
        if not isinstance(command.image_format, ProvisionalImageFormat):
            return self._rejected(
                "REFERENCE_FORMAT_INVALID",
                "The provisional reference-image format is invalid.",
            )
        if type(command.encoded) is not bytes:
            return self._rejected(
                "REFERENCE_PAYLOAD_INVALID",
                "The reference-image payload must be immutable bytes.",
            )

        try:
            decoded = self._image_source.decode(command.encoded, command.image_format)
        except ImageSourceError as error:
            return self._rejected_external(error)
        except Exception:
            return self._rejected(
                "IMAGE_SOURCE_FAILED",
                "The configured image source could not decode the reference image.",
            )
        if not isinstance(decoded, DecodedImage):
            return self._rejected(
                "IMAGE_SOURCE_RESULT_INVALID",
                "The configured image source returned an invalid decoded image.",
            )

        encoded_sha256 = hashlib.sha256(command.encoded).hexdigest()

        current = self._state.reference
        if (
            current is not None
            and current.public.encoded_sha256 == encoded_sha256
            and current.public.image_format is command.image_format
        ):
            return self._unchanged()

        revision = self._next_document_revision()
        public = ReferenceImageSnapshot(
            revision=revision,
            encoded_sha256=encoded_sha256,
            width=decoded.width,
            height=decoded.height,
            image_format=command.image_format,
            source_color_context=SourceColorContext(
                UnknownColorContext(
                    ColorContextUnknownReason.SOURCE_METADATA_MISSING
                )
            ),
        )
        self._state = replace(
            self._state,
            revision=revision,
            reference=_ReferenceState(
                public=public,
                decoded=decoded,
                original_encoded=command.encoded,
            ),
            preview=None,
            color_contexts=replace(
                self._state.color_contexts,
                interpretation_revision=InterpretationRevision(
                    self._state.color_contexts.interpretation_revision.value + 1
                ),
            ),
        )
        self._touch()
        return CommandResult(CommandStatus.COMMITTED, self.snapshot())

    def _load_portable_cube(self, command: LoadPortableCube) -> CommandResult:
        validation = self._validate_transformation_values(
            interpolation=command.interpolation,
            bypass=command.bypass,
            mix=command.mix,
        )
        if validation is not None:
            return self._rejected_diagnostic(validation)
        if type(command.encoded) is not bytes:
            return self._rejected(
                "CUBE_PAYLOAD_INVALID",
                "The Portable Cube payload must be immutable bytes.",
            )

        try:
            cube = parse_portable_cube(command.encoded)
        except PortableCubeError as error:
            return self._rejected_external(error)

        encoded_sha256 = hashlib.sha256(command.encoded).hexdigest()
        current = self._state.transformation
        if (
            current is not None
            and current.public.portable_cube_sha256 == encoded_sha256
            and current.public.interpolation is command.interpolation
            and current.public.bypass is command.bypass
            and current.public.mix == command.mix
        ):
            return self._unchanged()

        document_revision = self._next_document_revision()
        transformation_revision = self._next_transformation_revision()
        public = ColorTransformationSnapshot(
            revision=transformation_revision,
            portable_cube_sha256=encoded_sha256,
            lattice_size=cube.size,
            interpolation=command.interpolation,
            bypass=command.bypass,
            mix=float(command.mix),
        )
        self._state = replace(
            self._state,
            revision=document_revision,
            transformation=_TransformationState(public=public, cube=cube),
            preview=None,
            canonical_cube_export=None,
        )
        self._touch()
        return CommandResult(CommandStatus.COMMITTED, self.snapshot())

    def _configure_transformation(
        self,
        command: ConfigureColorTransformation,
    ) -> CommandResult:
        current = self._state.transformation
        if current is None:
            return self._rejected(
                "TRANSFORMATION_MISSING",
                "A Portable Cube transformation must be loaded first.",
            )
        if (
            command.interpolation is None
            and command.bypass is None
            and command.mix is None
        ):
            return self._rejected(
                "TRANSFORMATION_CHANGE_EMPTY",
                "At least one transformation setting must be provided.",
            )

        interpolation = (
            current.public.interpolation
            if command.interpolation is None
            else command.interpolation
        )
        bypass = current.public.bypass if command.bypass is None else command.bypass
        mix = current.public.mix if command.mix is None else command.mix
        validation = self._validate_transformation_values(
            interpolation=interpolation,
            bypass=bypass,
            mix=mix,
        )
        if validation is not None:
            return self._rejected_diagnostic(validation)
        if (
            current.public.interpolation is interpolation
            and current.public.bypass is bypass
            and current.public.mix == mix
        ):
            return self._unchanged()

        public = replace(
            current.public,
            revision=self._next_transformation_revision(),
            interpolation=interpolation,
            bypass=bypass,
            mix=float(mix),
        )
        self._state = replace(
            self._state,
            revision=self._next_document_revision(),
            transformation=_TransformationState(public=public, cube=current.cube),
            preview=None,
            canonical_cube_export=None,
        )
        self._touch()
        return CommandResult(CommandStatus.COMMITTED, self.snapshot())

    def _declare_color_contexts(
        self,
        command: DeclareColorContexts,
    ) -> CommandResult:
        if not isinstance(
            command.declaration,
            ColorContextDeclaration,
        ) or not isinstance(command.expected, ColorContextRevisionBasis):
            return self._rejected(
                "COLOR_CONTEXT_DECLARATION_INVALID",
                "The Color-context declaration or expected revisions are invalid.",
            )

        current = self._state.color_contexts
        desired = command.declaration
        if desired == current.declaration:
            return self._unchanged()

        if command.expected != current.revision_basis:
            return self._rejected(
                "COLOR_CONTEXT_REVISION_CONFLICT",
                "The Color-context declaration was prepared from stale revisions.",
                (
                    (
                        "expected_interpretation",
                        command.expected.interpretation.value,
                    ),
                    (
                        "current_interpretation",
                        current.interpretation_revision.value,
                    ),
                    ("expected_viewing", command.expected.viewing.value),
                    ("current_viewing", current.viewing_revision.value),
                    ("expected_export", command.expected.export.value),
                    ("current_export", current.export_revision.value),
                ),
            )

        if current.selected_lane is not None and (
            desired.selected_lane is not current.selected_lane
        ):
            return self._rejected(
                "COLOR_MANAGEMENT_LANE_CHANGE_REQUIRES_NEW_SCOPE",
                "Changing or removing the selected Color-management lane "
                "requires a new ColorDocument.",
            )

        interpretation_changed = (
            desired.selected_lane is not current.selected_lane
            or desired.working != current.working
        )
        viewing_changed = (
            desired.proof != current.proof
            or desired.display != current.display
        )
        export_changed = desired.export_context != current.export_context

        color_contexts = ColorContextsSnapshot(
            selected_lane=desired.selected_lane,
            working=desired.working,
            proof=desired.proof,
            display=desired.display,
            export_context=desired.export_context,
            interpretation_revision=InterpretationRevision(
                current.interpretation_revision.value
                + (1 if interpretation_changed else 0)
            ),
            viewing_revision=ViewingRevision(
                current.viewing_revision.value + (1 if viewing_changed else 0)
            ),
            export_revision=ExportRevision(
                current.export_revision.value + (1 if export_changed else 0)
            ),
        )
        self._state = replace(
            self._state,
            revision=(
                self._next_document_revision()
                if interpretation_changed
                else self._state.revision
            ),
            preview=(
                None
                if interpretation_changed or viewing_changed
                else self._state.preview
            ),
            color_contexts=color_contexts,
        )
        self._touch()
        return CommandResult(CommandStatus.COMMITTED, self.snapshot())

    def _request_preview(self) -> CommandResult:
        reference = self._state.reference
        transformation = self._state.transformation
        if reference is None or transformation is None:
            missing = "reference image" if reference is None else "transformation"
            return self._rejected(
                "PREVIEW_PREREQUISITE_MISSING",
                f"A {missing} must be loaded before requesting a preview.",
                (("missing", missing),),
            )

        plan = preview_plan(
            reference=reference.decoded,
            cube=transformation.cube,
            interpolation=transformation.public.interpolation.value,
            bypass=transformation.public.bypass,
            mix=transformation.public.mix,
        )
        return self._submit_job(
            purpose=JobPurpose.PREVIEW,
            plan=plan,
            total_units=preview_total_units(reference.decoded),
        )

    def _request_canonical_cube_export(self) -> CommandResult:
        transformation = self._state.transformation
        if transformation is None:
            return self._rejected(
                "EXPORT_PREREQUISITE_MISSING",
                "A Portable Cube transformation must be loaded before requesting "
                "an export.",
            )

        plan = export_plan(transformation.cube)
        return self._submit_job(
            purpose=JobPurpose.CANONICAL_PORTABLE_CUBE_EXPORT,
            plan=plan,
            total_units=export_total_units(transformation.cube),
        )

    def _cancel_job(self, command: CancelJob) -> CommandResult:
        if not isinstance(command.job_id, JobId):
            return self._rejected(
                "JOB_ID_INVALID",
                "The job identifier is invalid.",
            )
        record = self._jobs.get(command.job_id.value)
        if record is None:
            return self._rejected(
                "JOB_NOT_FOUND",
                "The requested job does not exist in this document history.",
                (("job_id", command.job_id.value),),
            )
        if record.state in _TERMINAL_JOB_STATES:
            return self._rejected(
                "JOB_NOT_CANCELLABLE",
                "The requested job is already terminal.",
                (("job_id", command.job_id.value),),
            )

        record.state = JobState.CANCELLED
        record.diagnostic = self._diagnostic(
            "JOB_CANCELLED",
            "The job was cancelled before publication.",
            (("job_id", command.job_id.value),),
        )
        try:
            record.plan.close()
        except Exception:
            # Cancellation is authoritative even if a third-party plan has a
            # defective close hook. No payload or exception detail is exposed.
            pass
        self._touch()
        return CommandResult(
            CommandStatus.ACCEPTED,
            self.snapshot(),
            job_id=command.job_id,
        )

    def _submit_job(
        self,
        *,
        purpose: JobPurpose,
        plan: Generator[int, None, PreviewCandidate | ExportCandidate],
        total_units: int,
    ) -> CommandResult:
        active_count = sum(
            record.state not in _TERMINAL_JOB_STATES
            for record in self._jobs.values()
        )
        if active_count >= _MAX_ACTIVE_JOBS:
            return self._rejected(
                "JOB_CAPACITY_EXHAUSTED",
                "The document already has the maximum number of active jobs.",
                (("maximum", _MAX_ACTIVE_JOBS),),
            )

        self._prune_job_history_for_insert()
        job_id = JobId(self._next_job_id)
        self._next_job_id += 1
        record = _JobRecord(
            job_id=job_id,
            purpose=purpose,
            basis=self._revision_basis(),
            state=JobState.QUEUED,
            progress=Progress(0, total_units),
            plan=plan,
        )
        self._jobs[job_id.value] = record
        self._latest_job_by_purpose[purpose] = job_id
        self._touch()

        try:
            self._executor.submit(job_id.value, lambda: self._advance_job(job_id))
        except Exception:
            if record.state not in _TERMINAL_JOB_STATES:
                self._fail_job(
                    record,
                    self._diagnostic(
                        "EXECUTOR_SUBMISSION_FAILED",
                        "The configured work executor rejected the job.",
                        (("job_id", job_id.value),),
                    ),
                )

        return CommandResult(
            CommandStatus.ACCEPTED,
            self.snapshot(),
            job_id=job_id,
        )

    def _advance_job(self, job_id: JobId) -> bool:
        record = self._jobs.get(job_id.value)
        if record is None or record.state in _TERMINAL_JOB_STATES:
            return True

        record.state = JobState.RUNNING
        try:
            completed_units = next(record.plan)
        except StopIteration as completed:
            candidate = completed.value
            try:
                if not isinstance(candidate, (PreviewCandidate, ExportCandidate)):
                    self._fail_job(
                        record,
                        self._diagnostic(
                            "JOB_RESULT_INVALID",
                            "The job completed without a valid result.",
                        ),
                    )
                else:
                    self._complete_job(record, candidate)
            except Exception:
                self._fail_job(
                    record,
                    self._diagnostic(
                        "JOB_PUBLICATION_FAILED",
                        "The complete job result could not be published.",
                        (("job_id", job_id.value),),
                    ),
                )
            return True
        except (ProcessingError, PortableCubeError) as error:
            self._fail_job(record, self._diagnostic_from_external(error))
            return True
        except Exception:
            self._fail_job(
                record,
                self._diagnostic(
                    "JOB_PROCESSING_FAILED",
                    "The job failed without publishing a partial result.",
                    (("job_id", job_id.value),),
                ),
            )
            return True

        if (
            isinstance(completed_units, bool)
            or not isinstance(completed_units, int)
            or completed_units <= record.progress.completed_units
            or completed_units >= record.progress.total_units
        ):
            self._fail_job(
                record,
                self._diagnostic(
                    "JOB_PROGRESS_INVALID",
                    "The job reported invalid progress and was stopped.",
                    (("job_id", job_id.value),),
                ),
            )
            return True

        record.progress = Progress(completed_units, record.progress.total_units)
        self._touch()
        return False

    def _complete_job(
        self,
        record: _JobRecord,
        candidate: PreviewCandidate | ExportCandidate,
    ) -> None:
        latest = self._latest_job_by_purpose.get(record.purpose)
        if latest != record.job_id or not self._job_basis_is_current(record):
            record.state = JobState.STALE
            record.diagnostic = self._diagnostic(
                "STALE_JOB_RESULT",
                "The job result was discarded because its revision is obsolete.",
                (("job_id", record.job_id.value),),
            )
            self._touch()
            return

        if record.purpose is JobPurpose.PREVIEW and isinstance(
            candidate,
            PreviewCandidate,
        ):
            original = self._new_surface(
                record,
                candidate,
                SurfacePurpose.ORIGINAL_PREVIEW,
                candidate.original_pixels,
            )
            processed = self._new_surface(
                record,
                candidate,
                SurfacePurpose.PROCESSED_PREVIEW,
                candidate.processed_pixels,
            )
            preview = PreviewBundle(
                job_id=record.job_id,
                basis=record.basis,
                original=original,
                processed=processed,
            )
            self._state = replace(self._state, preview=preview)
        elif (
            record.purpose is JobPurpose.CANONICAL_PORTABLE_CUBE_EXPORT
            and isinstance(candidate, ExportCandidate)
        ):
            artifact = CanonicalPortableCubeArtifact(
                artifact_id=ArtifactId(self._next_artifact_id),
                job_id=record.job_id,
                basis=record.basis,
                encoded=candidate.encoded,
                sha256=candidate.sha256,
                byte_count=len(candidate.encoded),
            )
            self._next_artifact_id += 1
            self._state = replace(self._state, canonical_cube_export=artifact)
        else:
            self._fail_job(
                record,
                self._diagnostic(
                    "JOB_RESULT_INVALID",
                    "The job result does not match the requested purpose.",
                ),
            )
            return

        record.state = JobState.SUCCEEDED
        record.progress = Progress(
            record.progress.total_units,
            record.progress.total_units,
        )
        record.diagnostic = None
        self._touch()

    def _new_surface(
        self,
        record: _JobRecord,
        candidate: PreviewCandidate,
        purpose: SurfacePurpose,
        pixels: bytes,
    ) -> DerivedSurfaceSnapshot:
        surface = DerivedSurfaceSnapshot(
            surface_id=SurfaceId(self._next_surface_id),
            purpose=purpose,
            basis=record.basis,
            width=candidate.width,
            height=candidate.height,
            row_stride=candidate.row_stride,
            encoding=SurfaceEncoding.RGB_F32_BE,
            pixels=pixels,
        )
        self._next_surface_id += 1
        return surface

    def _fail_job(self, record: _JobRecord, diagnostic: Diagnostic) -> None:
        record.state = JobState.FAILED
        record.diagnostic = diagnostic
        try:
            record.plan.close()
        except Exception:
            pass
        self._touch()

    def _validate_transformation_values(
        self,
        *,
        interpolation: Any,
        bypass: Any,
        mix: Any,
    ) -> Diagnostic | None:
        if not isinstance(interpolation, Interpolation):
            return self._diagnostic(
                "INTERPOLATION_INVALID",
                "The interpolation mode is invalid.",
            )
        if type(bypass) is not bool:
            return self._diagnostic(
                "BYPASS_INVALID",
                "The bypass setting must be a boolean.",
            )
        if type(mix) not in (float, int):
            return self._diagnostic(
                "MIX_INVALID",
                "The mix setting must be finite and between zero and one.",
            )
        try:
            normalized_mix = float(mix)
        except OverflowError:
            normalized_mix = math.nan
        if not math.isfinite(normalized_mix) or not 0.0 <= normalized_mix <= 1.0:
            return self._diagnostic(
                "MIX_INVALID",
                "The mix setting must be finite and between zero and one.",
            )
        return None

    def _next_document_revision(self) -> DocumentRevision:
        return DocumentRevision(self._state.revision.value + 1)

    def _next_transformation_revision(self) -> TransformationRevision:
        current = self._state.transformation
        return TransformationRevision(
            1 if current is None else current.public.revision.value + 1
        )

    def _revision_basis(self) -> RevisionBasis:
        contexts = self._state.color_contexts
        return RevisionBasis(
            document=self._state.revision,
            reference=(
                None
                if self._state.reference is None
                else self._state.reference.public.revision
            ),
            transformation=(
                None
                if self._state.transformation is None
                else self._state.transformation.public.revision
            ),
            interpretation=contexts.interpretation_revision,
            viewing=contexts.viewing_revision,
            export=contexts.export_revision,
        )

    def _job_basis_is_current(self, record: _JobRecord) -> bool:
        current = self._revision_basis()
        if record.purpose is JobPurpose.PREVIEW:
            return (
                record.basis.reference == current.reference
                and record.basis.transformation == current.transformation
                and record.basis.interpretation == current.interpretation
                and record.basis.viewing == current.viewing
            )
        if record.purpose is JobPurpose.CANONICAL_PORTABLE_CUBE_EXPORT:
            return record.basis.transformation == current.transformation
        return False

    def _job_snapshot(self, record: _JobRecord) -> JobSnapshot:
        return JobSnapshot(
            job_id=record.job_id,
            purpose=record.purpose,
            state=record.state,
            basis=record.basis,
            progress=record.progress,
            diagnostic=record.diagnostic,
        )

    def _prune_job_history_for_insert(self) -> None:
        while len(self._jobs) >= _JOB_HISTORY_LIMIT:
            terminal_id = next(
                (
                    job_id
                    for job_id, record in self._jobs.items()
                    if record.state in _TERMINAL_JOB_STATES
                ),
                None,
            )
            if terminal_id is None:
                break
            del self._jobs[terminal_id]

    def _touch(self) -> None:
        self._snapshot_revision = SnapshotRevision(
            self._snapshot_revision.value + 1
        )

    def _unchanged(self) -> CommandResult:
        return CommandResult(CommandStatus.UNCHANGED, self.snapshot())

    def _rejected_external(self, error: Any) -> CommandResult:
        return self._rejected_diagnostic(self._diagnostic_from_external(error))

    def _diagnostic_from_external(self, error: Any) -> Diagnostic:
        context = tuple(getattr(error, "context", ()))
        reason = getattr(error, "reason", None)
        if reason is not None:
            context = (("reason", reason), *context)
        return self._diagnostic(
            getattr(error, "code", "ENGINE_INPUT_INVALID"),
            str(error),
            context,
        )

    def _rejected(
        self,
        code: str,
        message: str,
        context: tuple[tuple[str, bool | float | int | str], ...] = (),
    ) -> CommandResult:
        return self._rejected_diagnostic(self._diagnostic(code, message, context))

    def _rejected_diagnostic(self, diagnostic: Diagnostic) -> CommandResult:
        return CommandResult(
            CommandStatus.REJECTED,
            self.snapshot(),
            diagnostic=diagnostic,
        )

    @staticmethod
    def _diagnostic(
        code: str,
        message: str,
        context: tuple[tuple[str, bool | float | int | str], ...] = (),
    ) -> Diagnostic:
        return Diagnostic(
            code=code,
            message=message,
            context=tuple(
                DiagnosticField(name=name, value=value) for name, value in context
            ),
        )
