# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Immutable intents and render projections for the Internal Test UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias

from colorluthier_engine import (
    CanonicalPortableCubeArtifact,
    ColorContextDeclaration,
    ColorContextRevisionBasis,
    CommandStatus,
    Diagnostic,
    DiagnosticField,
    DocumentSnapshot,
    Interpolation,
    JobId,
    ProvisionalImageFormat,
    SnapshotRevision,
)


ORDINARY_EXPORT_BLOCKED = "blocked-pending-explicit-color-contexts"


@dataclass(frozen=True, slots=True)
class OpenReferenceIntent:
    encoded: bytes
    image_format: ProvisionalImageFormat


@dataclass(frozen=True, slots=True)
class LoadPortableCubeIntent:
    encoded: bytes
    interpolation: Interpolation
    bypass: bool = False
    mix: float = 1.0


@dataclass(frozen=True, slots=True)
class ConfigureTransformationIntent:
    interpolation: Interpolation | None = None
    bypass: bool | None = None
    mix: float | None = None


@dataclass(frozen=True, slots=True)
class DeclareColorContextsIntent:
    """Replace the complete declaration prepared from an expected basis."""

    declaration: ColorContextDeclaration
    expected: ColorContextRevisionBasis


@dataclass(frozen=True, slots=True)
class RequestPreviewIntent:
    pass


@dataclass(frozen=True, slots=True)
class RequestFullResolutionIntent:
    pass


@dataclass(frozen=True, slots=True)
class InspectCanonicalArtifactIntent:
    pass


@dataclass(frozen=True, slots=True)
class CancelJobIntent:
    job_id: JobId


UiIntent: TypeAlias = (
    OpenReferenceIntent
    | LoadPortableCubeIntent
    | ConfigureTransformationIntent
    | DeclareColorContextsIntent
    | RequestPreviewIntent
    | RequestFullResolutionIntent
    | InspectCanonicalArtifactIntent
    | CancelJobIntent
)


class SnapshotDisposition(StrEnum):
    ACCEPTED = "accepted"
    REJECTED_OLDER = "rejected-older"
    REJECTED_NOT_OWNED = "rejected-not-owned"


@dataclass(frozen=True, slots=True)
class RenderState:
    """One engine snapshot plus UI feedback derived from public values."""

    snapshot: DocumentSnapshot
    command_status: CommandStatus | None = None
    submitted_job_id: JobId | None = None
    diagnostic: Diagnostic | None = None
    ordinary_export_status: str = field(
        default=ORDINARY_EXPORT_BLOCKED,
        init=False,
    )

    @property
    def watermark(self) -> SnapshotRevision:
        return self.snapshot.snapshot_revision

    @property
    def diagnostic_code(self) -> str | None:
        return None if self.diagnostic is None else self.diagnostic.code

    @property
    def diagnostic_context(self) -> tuple[DiagnosticField, ...]:
        return () if self.diagnostic is None else self.diagnostic.context

    @property
    def canonical_artifact(self) -> CanonicalPortableCubeArtifact | None:
        return self.snapshot.canonical_cube_export


@dataclass(frozen=True, slots=True)
class RenderUpdate:
    state: RenderState
    disposition: SnapshotDisposition
    candidate_revision: SnapshotRevision
