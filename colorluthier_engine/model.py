"""Immutable public vocabulary for the provisional headless engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


DiagnosticValue: TypeAlias = bool | float | int | str


class ProvisionalImageFormat(StrEnum):
    """Bootstrap image encodings; this is not the professional I/O contract."""

    PPM_P6_RGB8 = "ppm-p6-rgb8"
    PNG_RGB8 = "png-rgb8"


class Interpolation(StrEnum):
    TRILINEAR = "trilinear"
    TETRAHEDRAL = "tetrahedral"


class CommandStatus(StrEnum):
    COMMITTED = "committed"
    ACCEPTED = "accepted"
    UNCHANGED = "unchanged"
    REJECTED = "rejected"


class JobPurpose(StrEnum):
    PREVIEW = "preview"
    CANONICAL_PORTABLE_CUBE_EXPORT = "canonical-portable-cube-export"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


class SurfacePurpose(StrEnum):
    ORIGINAL_PREVIEW = "original-preview"
    PROCESSED_PREVIEW = "processed-preview"


class SurfaceEncoding(StrEnum):
    RGB_F32_BE = "rgb-f32be"


@dataclass(frozen=True, slots=True, order=True)
class SnapshotRevision:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("A snapshot revision cannot be negative.")


@dataclass(frozen=True, slots=True, order=True)
class DocumentRevision:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("A document revision cannot be negative.")


@dataclass(frozen=True, slots=True, order=True)
class TransformationRevision:
    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ValueError("A transformation revision cannot be negative.")


@dataclass(frozen=True, slots=True, order=True)
class JobId:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("A job identifier must be positive.")


@dataclass(frozen=True, slots=True, order=True)
class SurfaceId:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("A surface identifier must be positive.")


@dataclass(frozen=True, slots=True, order=True)
class ArtifactId:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError("An artifact identifier must be positive.")


@dataclass(frozen=True, slots=True)
class DiagnosticField:
    name: str
    value: DiagnosticValue


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Stable classifier plus bounded informational English context."""

    code: str
    message: str
    context: tuple[DiagnosticField, ...] = ()


@dataclass(frozen=True, slots=True)
class OpenReferenceImage:
    encoded: bytes
    image_format: ProvisionalImageFormat


@dataclass(frozen=True, slots=True)
class LoadPortableCube:
    encoded: bytes
    interpolation: Interpolation
    bypass: bool = False
    mix: float = 1.0


@dataclass(frozen=True, slots=True)
class ConfigureColorTransformation:
    interpolation: Interpolation | None = None
    bypass: bool | None = None
    mix: float | None = None


@dataclass(frozen=True, slots=True)
class RequestPreview:
    pass


@dataclass(frozen=True, slots=True)
class RequestCanonicalPortableCubeExport:
    """Request file-ready canonical bytes, not an ordinary color export.

    The export vocabulary identifies the revision-bound output operation
    required by this vertical.  ``ordinary_export_status`` remains blocked
    until a later gate introduces an explicit Export color context.
    """

    pass


@dataclass(frozen=True, slots=True)
class CancelJob:
    job_id: JobId


DocumentCommand: TypeAlias = (
    OpenReferenceImage
    | LoadPortableCube
    | ConfigureColorTransformation
    | RequestPreview
    | RequestCanonicalPortableCubeExport
    | CancelJob
)


@dataclass(frozen=True, slots=True)
class Progress:
    completed_units: int
    total_units: int

    def __post_init__(self) -> None:
        if self.total_units <= 0:
            raise ValueError("Progress must have at least one total unit.")
        if not 0 <= self.completed_units <= self.total_units:
            raise ValueError("Progress completed units are outside the total.")

    @property
    def fraction(self) -> float:
        return self.completed_units / self.total_units


@dataclass(frozen=True, slots=True)
class RevisionBasis:
    document: DocumentRevision
    reference: DocumentRevision | None
    transformation: TransformationRevision | None


@dataclass(frozen=True, slots=True)
class ReferenceImageSnapshot:
    revision: DocumentRevision
    encoded_sha256: str
    width: int
    height: int
    image_format: ProvisionalImageFormat
    source_color_context_status: str = "unknown"
    interpretation_status: str = "provisional-inspection-only"


@dataclass(frozen=True, slots=True)
class ColorTransformationSnapshot:
    revision: TransformationRevision
    portable_cube_sha256: str
    lattice_size: int
    interpolation: Interpolation
    bypass: bool
    mix: float
    semantics: str = "provisional-imported-portable-cube"


@dataclass(frozen=True, slots=True)
class DerivedSurfaceSnapshot:
    surface_id: SurfaceId
    purpose: SurfacePurpose
    basis: RevisionBasis
    width: int
    height: int
    row_stride: int
    encoding: SurfaceEncoding
    pixels: bytes
    viewing_status: str = "provisional-unmanaged"


@dataclass(frozen=True, slots=True)
class PreviewBundle:
    job_id: JobId
    basis: RevisionBasis
    original: DerivedSurfaceSnapshot
    processed: DerivedSurfaceSnapshot
    evidence_status: str = "provisional"


@dataclass(frozen=True, slots=True)
class CanonicalPortableCubeArtifact:
    artifact_id: ArtifactId
    job_id: JobId
    basis: RevisionBasis
    encoded: bytes
    sha256: str
    byte_count: int
    semantics: str = "provisional-imported-lattice-canonicalization"
    ordinary_export_status: str = "blocked-pending-explicit-color-contexts"
    evidence_status: str = "provisional"


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    job_id: JobId
    purpose: JobPurpose
    state: JobState
    basis: RevisionBasis
    progress: Progress
    diagnostic: Diagnostic | None = None


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    snapshot_revision: SnapshotRevision
    document_revision: DocumentRevision
    reference: ReferenceImageSnapshot | None
    transformation: ColorTransformationSnapshot | None
    preview: PreviewBundle | None
    canonical_cube_export: CanonicalPortableCubeArtifact | None
    jobs: tuple[JobSnapshot, ...]
    provisional_behaviors: tuple[str, ...]

    def revision_basis(self) -> RevisionBasis:
        return RevisionBasis(
            document=self.document_revision,
            reference=None if self.reference is None else self.reference.revision,
            transformation=(
                None
                if self.transformation is None
                else self.transformation.revision
            ),
        )


@dataclass(frozen=True, slots=True)
class CommandResult:
    status: CommandStatus
    snapshot: DocumentSnapshot
    job_id: JobId | None = None
    diagnostic: Diagnostic | None = None
