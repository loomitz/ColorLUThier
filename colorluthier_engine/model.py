"""Immutable public vocabulary for the provisional headless engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


DiagnosticValue: TypeAlias = bool | float | int | str
_BASIC_LATIN_TOKEN_MAX_LENGTH = 128
_BASIC_LATIN_TEXT_MAX_LENGTH = 256


def _validate_basic_latin_token(value: object, label: str) -> None:
    if (
        type(value) is not str
        or not value
        or len(value) > _BASIC_LATIN_TOKEN_MAX_LENGTH
        or any(not "!" <= character <= "~" for character in value)
    ):
        raise ValueError(
            f"{label} must be a non-empty bounded Basic Latin token."
        )


def _validate_basic_latin_text(value: object, label: str) -> None:
    if (
        type(value) is not str
        or not value
        or len(value) > _BASIC_LATIN_TEXT_MAX_LENGTH
        or value != value.strip()
        or any(not " " <= character <= "~" for character in value)
    ):
        raise ValueError(
            f"{label} must be non-empty bounded Basic Latin text."
        )


def _validated_rgb_tuple(value: object, label: str) -> tuple[float, float, float]:
    if type(value) is not tuple or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three RGB values.")

    components: list[float] = []
    for component in value:
        if type(component) not in (float, int):
            raise ValueError(f"{label} must contain only finite numbers.")
        try:
            normalized = float(component)
        except (OverflowError, ValueError):
            raise ValueError(
                f"{label} must contain only finite numbers."
            ) from None
        if not math.isfinite(normalized):
            raise ValueError(f"{label} must contain only finite numbers.")
        components.append(normalized)
    return (components[0], components[1], components[2])


class ProvisionalImageFormat(StrEnum):
    """Bootstrap image encodings; this is not the professional I/O contract."""

    PPM_P6_RGB8 = "ppm-p6-rgb8"
    PNG_RGB8 = "png-rgb8"


class Interpolation(StrEnum):
    TRILINEAR = "trilinear"
    TETRAHEDRAL = "tetrahedral"


class ColorManagementLane(StrEnum):
    """One explicitly selected color-management semantic route."""

    ICC = "icc-still-image"
    OCIO_ACES = "ocio-aces"


class ColorContextUnknownReason(StrEnum):
    """Bounded reasons why a Color context identity is unavailable."""

    NOT_DECLARED = "not-declared"
    SOURCE_METADATA_MISSING = "source-metadata-missing"
    NOT_AVAILABLE = "not-available"


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
class ContentIdentity:
    """Lowercase SHA-256 content identity; names and paths are insufficient."""

    sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.sha256) is not str
            or len(self.sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.sha256
            )
        ):
            raise ValueError(
                "A content identity must be exactly 64 lowercase hexadecimal "
                "SHA-256 characters."
            )


@dataclass(frozen=True, slots=True)
class EncodingIdentity:
    """Explicit encoding token backed by a versioned specification identity."""

    identifier: str
    specification: ContentIdentity

    def __post_init__(self) -> None:
        _validate_basic_latin_token(self.identifier, "An encoding identifier")
        if not isinstance(self.specification, ContentIdentity):
            raise ValueError(
                "An encoding identity requires a content-identified specification."
            )


@dataclass(frozen=True, slots=True)
class UnknownColorContext:
    """An explicit unknown identity that permits inspection only."""

    reason: ColorContextUnknownReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, ColorContextUnknownReason):
            raise ValueError("An unknown Color context reason is invalid.")


@dataclass(frozen=True, slots=True)
class IccColorContextIdentity:
    """Identity of an ICC context governed by exact profile content."""

    profile: ContentIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.profile, ContentIdentity):
            raise ValueError("An ICC Color context requires a profile identity.")


@dataclass(frozen=True, slots=True)
class OcioAcesColorContextIdentity:
    """Identity of one fully resolved OCIO/ACES color-space operation.

    ``configuration_manifest`` identifies a deterministic manifest containing
    the configuration plus every resolved resource and context-variable
    binding. ``exact_color_space`` is a color-space name, never a role,
    default, configuration label, or filesystem path used as identity.
    """

    configuration_manifest: ContentIdentity
    exact_color_space: str

    def __post_init__(self) -> None:
        if not isinstance(self.configuration_manifest, ContentIdentity):
            raise ValueError(
                "An OCIO/ACES Color context requires a resolved configuration "
                "manifest identity."
            )
        _validate_basic_latin_text(
            self.exact_color_space,
            "An OCIO/ACES exact color-space name",
        )


_KnownColorContextIdentity: TypeAlias = (
    IccColorContextIdentity | OcioAcesColorContextIdentity
)


@dataclass(frozen=True, slots=True)
class KnownColorContext:
    """Content-identified Color context within one Color-management lane."""

    lane: ColorManagementLane
    identity: _KnownColorContextIdentity
    encoding: EncodingIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.lane, ColorManagementLane):
            raise ValueError("A known Color context lane is invalid.")
        if self.lane is ColorManagementLane.ICC and not isinstance(
            self.identity,
            IccColorContextIdentity,
        ):
            raise ValueError(
                "An ICC Color context requires an ICC profile identity."
            )
        if self.lane is ColorManagementLane.OCIO_ACES and not isinstance(
            self.identity,
            OcioAcesColorContextIdentity,
        ):
            raise ValueError(
                "An OCIO/ACES Color context requires a resolved OCIO/ACES "
                "identity."
            )
        if not isinstance(self.encoding, EncodingIdentity):
            raise ValueError("A known Color context requires an encoding identity.")


_ColorContextValue: TypeAlias = UnknownColorContext | KnownColorContext


def _validate_color_context_value(value: object, role: str) -> None:
    if not isinstance(value, (UnknownColorContext, KnownColorContext)):
        raise ValueError(
            f"A {role} Color context must contain an unknown or known value."
        )


@dataclass(frozen=True, slots=True)
class SourceColorContext:
    value: _ColorContextValue

    def __post_init__(self) -> None:
        _validate_color_context_value(self.value, "Source")


@dataclass(frozen=True, slots=True)
class WorkingColorContext:
    value: _ColorContextValue

    def __post_init__(self) -> None:
        _validate_color_context_value(self.value, "Working")


@dataclass(frozen=True, slots=True)
class ProofColorContext:
    value: _ColorContextValue

    def __post_init__(self) -> None:
        _validate_color_context_value(self.value, "Proof")


@dataclass(frozen=True, slots=True)
class DisplayColorContext:
    value: _ColorContextValue
    viewing_interpretation: ContentIdentity | None = None

    def __post_init__(self) -> None:
        _validate_color_context_value(self.value, "Display")
        if isinstance(self.value, KnownColorContext):
            if not isinstance(self.viewing_interpretation, ContentIdentity):
                raise ValueError(
                    "A known Display Color context requires an explicit viewing "
                    "interpretation identity."
                )
        elif self.viewing_interpretation is not None:
            raise ValueError(
                "An unknown Display Color context cannot claim a viewing "
                "interpretation identity."
            )


@dataclass(frozen=True, slots=True)
class RgbBounds:
    """Finite per-channel RGB bounds with a non-empty interval."""

    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    def __post_init__(self) -> None:
        minimum = _validated_rgb_tuple(self.minimum, "RGB minimum")
        maximum = _validated_rgb_tuple(self.maximum, "RGB maximum")
        if any(lower >= upper for lower, upper in zip(minimum, maximum)):
            raise ValueError(
                "Each RGB minimum value must be less than its maximum value."
            )
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)


@dataclass(frozen=True, slots=True)
class HostFormatProfileIdentity:
    """Versioned Host or format profile backed by normative content."""

    identifier: str
    version: str
    specification: ContentIdentity

    def __post_init__(self) -> None:
        _validate_basic_latin_token(
            self.identifier,
            "A Host or format profile identifier",
        )
        _validate_basic_latin_token(
            self.version,
            "A Host or format profile version",
        )
        if not isinstance(self.specification, ContentIdentity):
            raise ValueError(
                "A Host or format profile requires a content-identified "
                "specification."
            )


@dataclass(frozen=True, slots=True)
class ExportColorContext:
    """Complete ordinary-export semantics, excluding Proof and Display."""

    input_context: KnownColorContext
    output_context: KnownColorContext
    numeric_domain: RgbBounds
    numeric_range: RgbBounds
    interpolation: Interpolation
    profile: HostFormatProfileIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.input_context, KnownColorContext):
            raise ValueError("An Export input Color context must be known.")
        if not isinstance(self.output_context, KnownColorContext):
            raise ValueError("An Export output Color context must be known.")
        if self.input_context.lane is not self.output_context.lane:
            raise ValueError(
                "Export input and output Color contexts must use the same "
                "Color-management lane."
            )
        if not isinstance(self.numeric_domain, RgbBounds):
            raise ValueError("An Export numeric domain is invalid.")
        if not isinstance(self.numeric_range, RgbBounds):
            raise ValueError("An Export numeric range is invalid.")
        if not isinstance(self.interpolation, Interpolation):
            raise ValueError("An Export interpolation convention is invalid.")
        if not isinstance(self.profile, HostFormatProfileIdentity):
            raise ValueError("An Export Host or format profile is invalid.")


@dataclass(frozen=True, slots=True)
class ColorContextsSnapshot:
    """Immutable inspection-first scaffold for one authoring scope."""

    selected_lane: ColorManagementLane | None
    working: WorkingColorContext
    proof: ProofColorContext | None
    display: DisplayColorContext | None

    def __post_init__(self) -> None:
        if self.selected_lane is not None and not isinstance(
            self.selected_lane,
            ColorManagementLane,
        ):
            raise ValueError("The selected Color-management lane is invalid.")
        if not isinstance(self.working, WorkingColorContext):
            raise ValueError("The Working Color context is invalid.")
        if self.proof is not None and not isinstance(self.proof, ProofColorContext):
            raise ValueError("The Proof Color context is invalid.")
        if self.display is not None and not isinstance(
            self.display,
            DisplayColorContext,
        ):
            raise ValueError("The Display Color context is invalid.")
        values = (
            self.working.value,
            None if self.proof is None else self.proof.value,
            None if self.display is None else self.display.value,
        )
        known = tuple(
            value for value in values if isinstance(value, KnownColorContext)
        )
        if known and self.selected_lane is None:
            raise ValueError(
                "Known Color contexts require an explicitly selected lane."
            )
        if self.selected_lane is not None and any(
            value.lane is not self.selected_lane for value in known
        ):
            raise ValueError(
                "Every known Color context must use the selected "
                "Color-management lane."
            )

    @property
    def inspection_only(self) -> bool:
        """Gate 4A has no CMM or managed interpretation, so this stays true."""

        return True


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
    source_color_context: SourceColorContext = SourceColorContext(
        UnknownColorContext(ColorContextUnknownReason.SOURCE_METADATA_MISSING)
    )

    def __post_init__(self) -> None:
        if not isinstance(self.source_color_context, SourceColorContext):
            raise ValueError("The Source Color context is invalid.")
        expected_status = (
            "unknown"
            if isinstance(self.source_color_context.value, UnknownColorContext)
            else "known"
        )
        if self.source_color_context_status != expected_status:
            raise ValueError(
                "The legacy Source Color-context status must match the "
                "structured context."
            )
        if self.interpretation_status != "provisional-inspection-only":
            raise ValueError(
                "Gate 4A Reference images remain provisional inspection-only."
            )


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
    color_contexts: ColorContextsSnapshot = ColorContextsSnapshot(
        selected_lane=None,
        working=WorkingColorContext(
            UnknownColorContext(ColorContextUnknownReason.NOT_DECLARED)
        ),
        proof=None,
        display=None,
    )

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
