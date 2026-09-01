# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

"""In-memory action coordinator for the disposable browser prototype."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from colorluthier_engine import (
    ColorContextRevisionBasis,
    ExportRevision,
    Interpolation,
    InterpretationRevision,
    JobId,
    ProvisionalImageFormat,
    ViewingRevision,
)
from internal_test_ui_adapter import (
    CancelJobIntent,
    ConfigureTransformationIntent,
    DeclareColorContextsIntent,
    InspectCanonicalArtifactIntent,
    InternalTestUiAdapter,
    LoadPortableCubeIntent,
    OpenReferenceIntent,
    RenderState,
    RequestFullResolutionIntent,
    RequestPreviewIntent,
)

from ._executor import ManualExecutor
from ._synthetic import (
    SYNTHETIC_IDENTITY_CUBE,
    SYNTHETIC_REFERENCE_PPM,
    synthetic_color_context_declaration,
)


_MAX_LOCAL_INPUT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UiNotice:
    code: str
    message: str


class PrototypeApplication:
    """Own exactly one adapter and one bounded manual executor."""

    def __init__(self) -> None:
        self._executor = ManualExecutor()
        self._adapter = InternalTestUiAdapter(self._executor)
        self._notice: UiNotice | None = None

    @property
    def current(self) -> RenderState:
        return self._adapter.current

    @property
    def pending_job_ids(self) -> tuple[int, ...]:
        return self._executor.pending_job_ids

    @property
    def notice(self) -> UiNotice | None:
        return self._notice

    def dispatch_action(self, action: str, fields: Mapping[str, str]) -> None:
        self._notice = None
        try:
            self._dispatch_action(action, fields)
        except (TypeError, ValueError):
            self._notice = UiNotice(
                "UI_FORM_INVALID",
                "The submitted prototype form contains an invalid value.",
            )

    def _dispatch_action(self, action: str, fields: Mapping[str, str]) -> None:
        if action == "load-synthetic":
            self._open_synthetic_reference()
            self._load_synthetic_cube()
            return
        if action == "open-synthetic-reference":
            self._open_synthetic_reference()
            return
        if action == "load-synthetic-cube":
            self._load_synthetic_cube()
            return
        if action == "open-reference-path":
            encoded = self._read_local_input(fields.get("reference-path", ""))
            if encoded is not None:
                image_format = ProvisionalImageFormat(
                    fields.get(
                        "image-format",
                        ProvisionalImageFormat.PPM_P6_RGB8.value,
                    )
                )
                self._adapter.dispatch(OpenReferenceIntent(encoded, image_format))
            return
        if action == "load-cube-path":
            encoded = self._read_local_input(fields.get("cube-path", ""))
            if encoded is not None:
                self._adapter.dispatch(
                    LoadPortableCubeIntent(
                        encoded,
                        self._interpolation(fields),
                        bypass=self._checked(fields, "bypass"),
                        mix=float(fields.get("mix", "1.0")),
                    )
                )
            return
        if action == "configure-transformation":
            self._adapter.dispatch(
                ConfigureTransformationIntent(
                    interpolation=self._interpolation(fields),
                    bypass=self._checked(fields, "bypass"),
                    mix=float(fields.get("mix", "1.0")),
                )
            )
            return
        if action == "declare-contexts":
            self._adapter.dispatch(
                DeclareColorContextsIntent(
                    declaration=synthetic_color_context_declaration(),
                    expected=self._expected_basis(fields),
                )
            )
            return
        if action == "request-preview":
            self._adapter.dispatch(RequestPreviewIntent())
            return
        if action == "request-full":
            self._adapter.dispatch(RequestFullResolutionIntent())
            return
        if action == "inspect-canonical":
            self._adapter.dispatch(InspectCanonicalArtifactIntent())
            return
        if action == "step-job":
            self._executor.step(self._job_id(fields).value)
            return
        if action == "run-job":
            self._executor.run_to_terminal(self._job_id(fields).value)
            return
        if action == "cancel-job":
            job_id = self._job_id(fields)
            self._adapter.dispatch(CancelJobIntent(job_id))
            if job_id.value in self._executor.pending_job_ids:
                self._executor.step(job_id.value)
            return
        if action == "stale-demo":
            self._run_stale_demo()
            return
        if action == "malformed-reference":
            self._adapter.dispatch(
                OpenReferenceIntent(
                    b"not a PPM",
                    ProvisionalImageFormat.PPM_P6_RGB8,
                )
            )
            return
        self._notice = UiNotice(
            "UI_ACTION_UNKNOWN",
            "The requested prototype action is not supported.",
        )

    def _open_synthetic_reference(self) -> None:
        self._adapter.dispatch(
            OpenReferenceIntent(
                SYNTHETIC_REFERENCE_PPM,
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )

    def _load_synthetic_cube(self) -> None:
        self._adapter.dispatch(
            LoadPortableCubeIntent(
                SYNTHETIC_IDENTITY_CUBE,
                Interpolation.TRILINEAR,
            )
        )

    def _run_stale_demo(self) -> None:
        older = self._adapter.dispatch(RequestFullResolutionIntent())
        older_id = older.state.submitted_job_id
        transformation = self._adapter.current.snapshot.transformation
        if older_id is None or transformation is None:
            return
        self._adapter.dispatch(
            ConfigureTransformationIntent(bypass=not transformation.bypass)
        )
        newer = self._adapter.dispatch(RequestFullResolutionIntent())
        newer_id = newer.state.submitted_job_id
        if newer_id is None:
            return
        self._executor.run_to_terminal(newer_id.value)
        self._executor.run_to_terminal(older_id.value)

    def _read_local_input(self, raw_path: str) -> bytes | None:
        if not raw_path.strip():
            self._notice = UiNotice(
                "UI_PATH_REQUIRED",
                "Enter a local input path before submitting the form.",
            )
            return None
        candidate = Path(raw_path).expanduser()
        try:
            if candidate.stat().st_size > _MAX_LOCAL_INPUT_BYTES:
                self._notice = UiNotice(
                    "UI_PATH_TOO_LARGE",
                    "The selected local input exceeds the prototype read limit.",
                )
                return None
            return candidate.read_bytes()
        except OSError:
            self._notice = UiNotice(
                "UI_PATH_READ_FAILED",
                "The selected local input could not be read.",
            )
            return None

    @staticmethod
    def _checked(fields: Mapping[str, str], name: str) -> bool:
        return fields.get(name) == "on"

    @staticmethod
    def _interpolation(fields: Mapping[str, str]) -> Interpolation:
        return Interpolation(fields.get("interpolation", Interpolation.TRILINEAR))

    @staticmethod
    def _job_id(fields: Mapping[str, str]) -> JobId:
        return JobId(int(fields.get("job-id", "0")))

    @staticmethod
    def _expected_basis(
        fields: Mapping[str, str],
    ) -> ColorContextRevisionBasis:
        return ColorContextRevisionBasis(
            interpretation=InterpretationRevision(
                int(fields.get("expected-interpretation", "-1"))
            ),
            viewing=ViewingRevision(int(fields.get("expected-viewing", "-1"))),
            export=ExportRevision(int(fields.get("expected-export", "-1"))),
        )
