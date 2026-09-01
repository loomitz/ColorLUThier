# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""Serialized intent-to-snapshot coordination for an Internal Test UI."""

from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from colorluthier_engine import (
    CancelJob,
    ColorDocument,
    CommandResult,
    ConfigureColorTransformation,
    DeclareColorContexts,
    DocumentCommand,
    DocumentSnapshot,
    InlineExecutor,
    LoadPortableCube,
    OpenReferenceImage,
    RequestCanonicalPortableCubeExport,
    RequestFullResolutionEvaluation,
    RequestPreview,
    WorkExecutor,
)

from ._types import (
    CancelJobIntent,
    ConfigureTransformationIntent,
    DeclareColorContextsIntent,
    InspectCanonicalArtifactIntent,
    LoadPortableCubeIntent,
    OpenReferenceIntent,
    RenderState,
    RenderUpdate,
    RequestFullResolutionIntent,
    RequestPreviewIntent,
    SnapshotDisposition,
    UiIntent,
)


class _SerializedExecutor:
    """Serialize engine work with adapter operations and refresh afterward."""

    def __init__(self, delegate: WorkExecutor, lock: RLock) -> None:
        self._delegate = delegate
        self._lock = lock
        self._refresh: Callable[[], None] | None = None

    def bind_refresh(self, refresh: Callable[[], None]) -> None:
        self._refresh = refresh

    def submit(self, job_id: int, step: Callable[[], bool]) -> None:
        def serialized_step() -> bool:
            with self._lock:
                terminal = step()
                if self._refresh is not None:
                    self._refresh()
                return terminal

        self._delegate.submit(job_id, serialized_step)


class InternalTestUiAdapter:
    """Own one document and hide all command/job/snapshot coordination."""

    def __init__(self, executor: WorkExecutor | None = None) -> None:
        self._lock = RLock()
        serialized_executor = _SerializedExecutor(
            InlineExecutor() if executor is None else executor,
            self._lock,
        )
        self._document = ColorDocument(executor=serialized_executor)
        initial_snapshot = self._document.snapshot()
        self._current = RenderState(snapshot=initial_snapshot)
        serialized_executor.bind_refresh(self._refresh_after_work_step_unlocked)

    @property
    def current(self) -> RenderState:
        with self._lock:
            return self._current

    def dispatch(self, intent: UiIntent) -> RenderUpdate:
        with self._lock:
            result = self._document.apply(self._command_for(intent))
            return self._accept_snapshot_unlocked(result.snapshot, result)

    def accept_snapshot(self, snapshot: DocumentSnapshot) -> RenderUpdate:
        if not isinstance(snapshot, DocumentSnapshot):
            raise TypeError("snapshot must be a DocumentSnapshot")
        with self._lock:
            return self._accept_snapshot_unlocked(snapshot)

    def _command_for(self, intent: UiIntent) -> DocumentCommand:
        if isinstance(intent, OpenReferenceIntent):
            return OpenReferenceImage(intent.encoded, intent.image_format)
        if isinstance(intent, LoadPortableCubeIntent):
            return LoadPortableCube(
                intent.encoded,
                intent.interpolation,
                bypass=intent.bypass,
                mix=intent.mix,
            )
        if isinstance(intent, ConfigureTransformationIntent):
            return ConfigureColorTransformation(
                interpolation=intent.interpolation,
                bypass=intent.bypass,
                mix=intent.mix,
            )
        if isinstance(intent, DeclareColorContextsIntent):
            return DeclareColorContexts(
                declaration=intent.declaration,
                expected=intent.expected,
            )
        if isinstance(intent, RequestPreviewIntent):
            return RequestPreview()
        if isinstance(intent, RequestFullResolutionIntent):
            return RequestFullResolutionEvaluation()
        if isinstance(intent, InspectCanonicalArtifactIntent):
            return RequestCanonicalPortableCubeExport()
        if isinstance(intent, CancelJobIntent):
            return CancelJob(intent.job_id)
        raise TypeError(f"unsupported Internal Test UI intent: {type(intent).__name__}")

    def _refresh_after_work_step_unlocked(self) -> None:
        self._accept_snapshot_unlocked(self._document.snapshot())

    def _accept_snapshot_unlocked(
        self,
        snapshot: DocumentSnapshot,
        result: CommandResult | None = None,
    ) -> RenderUpdate:
        if snapshot.snapshot_revision < self._current.watermark:
            return RenderUpdate(
                state=self._current,
                disposition=SnapshotDisposition.REJECTED_OLDER,
                candidate_revision=snapshot.snapshot_revision,
            )
        if snapshot != self._document.snapshot():
            return RenderUpdate(
                state=self._current,
                disposition=SnapshotDisposition.REJECTED_NOT_OWNED,
                candidate_revision=snapshot.snapshot_revision,
            )

        self._current = RenderState(
            snapshot=snapshot,
            command_status=(
                self._current.command_status if result is None else result.status
            ),
            submitted_job_id=(
                self._current.submitted_job_id if result is None else result.job_id
            ),
            diagnostic=(
                self._current.diagnostic if result is None else result.diagnostic
            ),
        )
        return RenderUpdate(
            state=self._current,
            disposition=SnapshotDisposition.ACCEPTED,
            candidate_revision=snapshot.snapshot_revision,
        )
