# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

from colorluthier_engine import (
    CommandStatus,
    Interpolation,
    JobPurpose,
    JobState,
    ProvisionalImageFormat,
)
from internal_test_ui_adapter import (
    ConfigureTransformationIntent,
    InternalTestUiAdapter,
    LoadPortableCubeIntent,
    OpenReferenceIntent,
    RenderState,
    RequestPreviewIntent,
    SnapshotDisposition,
)
from internal_test_ui_prototype import ManualExecutor, PrototypeApplication, render_page

from internal_test_ui_e2e_support import (
    AccessiblePage,
    BrowserSurfaceUnavailable,
    PrototypeServerProcess,
    SafariSurfaceController,
    parse_accessible_page,
)


_ORDINARY_EXPORT_BLOCKED = "blocked-pending-explicit-color-contexts"


def _basis_fields(page: AccessiblePage) -> dict[str, str]:
    form = page.form("declare-contexts-form")
    return {
        name: form.field(name)
        for name in (
            "expected-interpretation",
            "expected-viewing",
            "expected-export",
        )
    }


def _job_snapshot(application: PrototypeApplication, job_id: int):
    return next(
        job
        for job in application.current.snapshot.jobs
        if job.job_id.value == job_id
    )


def _render(application: PrototypeApplication) -> AccessiblePage:
    return parse_accessible_page(render_page(application))


def _last_valid_visible_state(page: AccessiblePage) -> tuple[object, ...]:
    return (
        page.element("snapshot-revisions").definition("Snapshot revision"),
        page.element("reference-metadata").definitions,
        page.element("transformation-metadata").definitions,
        page.element("color-contexts").definitions,
        page.element("canonical-artifact").definitions,
        tuple(
            (surface.test_id, surface.definitions)
            for surface in page.elements_with_prefix("surface-")
        ),
        tuple(page.jobs),
        page.element("ordinary-export-status").text,
    )


class InternalTestUiHeadlessAcceptanceTest(unittest.TestCase):
    def test_public_intents_translate_to_snapshot_backed_render_state(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        executor = ManualExecutor()
        adapter = InternalTestUiAdapter(executor)

        opened = adapter.dispatch(
            OpenReferenceIntent(
                b"P6\n1 1\n255\n\x40\x80\xc0",
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(opened.disposition, SnapshotDisposition.ACCEPTED)
        self.assertIs(opened.state, adapter.current)
        self.assertIs(opened.state.snapshot, adapter.current.snapshot)
        self.assertIsNotNone(opened.state.snapshot.reference)

        loaded = adapter.dispatch(
            LoadPortableCubeIntent(
                (repository_root / "tests/fixtures/identity-2/input.cube").read_bytes(),
                Interpolation.TRILINEAR,
            )
        )
        self.assertEqual(loaded.disposition, SnapshotDisposition.ACCEPTED)
        configured = adapter.dispatch(
            ConfigureTransformationIntent(
                interpolation=Interpolation.TETRAHEDRAL,
                bypass=True,
                mix=0.5,
            )
        )
        self.assertEqual(configured.disposition, SnapshotDisposition.ACCEPTED)
        self.assertEqual(
            configured.state.snapshot.transformation.interpolation,
            Interpolation.TETRAHEDRAL,
        )
        self.assertTrue(configured.state.snapshot.transformation.bypass)
        self.assertEqual(configured.state.snapshot.transformation.mix, 0.5)

        submitted = adapter.dispatch(RequestPreviewIntent())
        self.assertEqual(submitted.disposition, SnapshotDisposition.ACCEPTED)
        preview_id = submitted.state.submitted_job_id.value
        self.assertEqual(submitted.state.snapshot.jobs[-1].state, JobState.QUEUED)
        executor.step(preview_id)
        progressed = adapter.current
        self.assertIsInstance(progressed, RenderState)
        self.assertEqual(progressed.snapshot.jobs[-1].state, JobState.RUNNING)
        self.assertGreater(progressed.snapshot.jobs[-1].progress.completed_units, 0)
        executor.run_to_terminal(preview_id)
        published = adapter.current
        self.assertEqual(published.snapshot.jobs[-1].state, JobState.SUCCEEDED)
        self.assertIsNotNone(published.snapshot.preview)

        rejected = adapter.dispatch(
            OpenReferenceIntent(
                b"not a Reference image",
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(rejected.state.command_status, CommandStatus.REJECTED)
        self.assertEqual(rejected.state.diagnostic_code, "REFERENCE_STRUCTURE_INVALID")
        self.assertIs(rejected.state.snapshot.reference, published.snapshot.reference)
        self.assertIs(
            rejected.state.snapshot.transformation,
            published.snapshot.transformation,
        )
        self.assertIs(rejected.state.snapshot.preview, published.snapshot.preview)

    def test_intent_snapshot_render_flow_preserves_last_valid_state(self) -> None:
        application = PrototypeApplication()
        initial_page = _render(application)
        self.assertEqual(initial_page.status, 200)
        self.assertEqual(initial_page.form("reference-path-form").method, "post")
        self.assertEqual(initial_page.form("cube-path-form").target, "/action")
        self.assertEqual(initial_page.form("configure-form").action, "configure-transformation")
        self.assertEqual(initial_page.form("declare-contexts-form").action, "declare-contexts")
        self.assertEqual(
            set(_basis_fields(initial_page)),
            {"expected-interpretation", "expected-viewing", "expected-export"},
        )

        application.dispatch_action("load-synthetic", {})
        application.dispatch_action(
            "configure-transformation",
            {
                "interpolation": "tetrahedral",
                "bypass": "on",
                "mix": "0.5",
            },
        )
        configured = application.current.snapshot.transformation
        self.assertIsNotNone(configured)
        self.assertEqual(configured.interpolation, Interpolation.TETRAHEDRAL)
        self.assertTrue(configured.bypass)
        self.assertEqual(configured.mix, 0.5)

        application.dispatch_action("declare-contexts", _basis_fields(_render(application)))
        contexts = application.current.snapshot.color_contexts
        self.assertIsNotNone(contexts.proof)
        self.assertIsNotNone(contexts.display)
        self.assertIsNotNone(contexts.export_context)
        self.assertEqual(contexts.export_context.interpolation, Interpolation.TETRAHEDRAL)
        self.assertNotEqual(contexts.export_context.input_context, contexts.proof.value)
        self.assertNotEqual(contexts.export_context.output_context, contexts.display.value)

        application.dispatch_action("request-preview", {})
        preview_id = application.current.submitted_job_id.value
        preview_job = _job_snapshot(application, preview_id)
        self.assertEqual(preview_job.purpose, JobPurpose.PREVIEW)
        self.assertEqual(preview_job.state, JobState.QUEUED)
        application.dispatch_action("step-job", {"job-id": str(preview_id)})
        preview_job = _job_snapshot(application, preview_id)
        self.assertEqual(preview_job.state, JobState.RUNNING)
        self.assertGreater(preview_job.progress.completed_units, 0)
        self.assertLess(
            preview_job.progress.completed_units,
            preview_job.progress.total_units,
        )
        application.dispatch_action("run-job", {"job-id": str(preview_id)})
        self.assertEqual(_job_snapshot(application, preview_id).state, JobState.SUCCEEDED)
        self.assertIsNotNone(application.current.snapshot.preview)

        application.dispatch_action("request-full", {})
        cancelled_id = application.current.submitted_job_id.value
        application.dispatch_action("step-job", {"job-id": str(cancelled_id)})
        application.dispatch_action("cancel-job", {"job-id": str(cancelled_id)})
        self.assertEqual(_job_snapshot(application, cancelled_id).state, JobState.CANCELLED)
        self.assertIsNone(application.current.snapshot.full_resolution)

        application.dispatch_action("stale-demo", {})
        full_jobs = tuple(
            job
            for job in application.current.snapshot.jobs
            if job.purpose is JobPurpose.FULL_RESOLUTION_EVALUATION
        )
        older, newer = full_jobs[-2:]
        self.assertEqual(older.state, JobState.STALE)
        self.assertEqual(newer.state, JobState.SUCCEEDED)
        self.assertEqual(
            application.current.snapshot.full_resolution.job_id,
            newer.job_id,
        )

        application.dispatch_action("inspect-canonical", {})
        canonical_id = application.current.submitted_job_id.value
        application.dispatch_action("run-job", {"job-id": str(canonical_id)})
        artifact = application.current.canonical_artifact
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact.job_id.value, canonical_id)
        self.assertEqual(artifact.ordinary_export_status, _ORDINARY_EXPORT_BLOCKED)

        before_snapshot = application.current.snapshot
        before_page = _render(application)
        before_visible = _last_valid_visible_state(before_page)
        application.dispatch_action("malformed-reference", {})
        rejected = application.current
        after_page = _render(application)

        self.assertEqual(rejected.command_status, CommandStatus.REJECTED)
        self.assertEqual(rejected.diagnostic_code, "REFERENCE_STRUCTURE_INVALID")
        self.assertIs(rejected.snapshot.reference, before_snapshot.reference)
        self.assertIs(rejected.snapshot.transformation, before_snapshot.transformation)
        self.assertIs(rejected.snapshot.preview, before_snapshot.preview)
        self.assertIs(rejected.snapshot.full_resolution, before_snapshot.full_resolution)
        self.assertIs(
            rejected.snapshot.canonical_cube_export,
            before_snapshot.canonical_cube_export,
        )
        self.assertEqual(_last_valid_visible_state(after_page), before_visible)
        self.assertEqual(
            after_page.element("command-diagnostic").definition("Code"),
            "REFERENCE_STRUCTURE_INVALID",
        )
        self.assertEqual(
            after_page.element("ordinary-export-status").text,
            _ORDINARY_EXPORT_BLOCKED,
        )


class InternalTestUiHttpAcceptanceTest(unittest.TestCase):
    def test_full_loopback_http_flow_is_accessible_and_deterministic(self) -> None:
        with PrototypeServerProcess() as server:
            initial = server.get()
            self.assertEqual(initial.status, 200)
            self.assertEqual(initial.content_type, "text/html; charset=utf-8")
            self.assertIn("NOT PRODUCT UI", initial.element("prototype-banner").text)
            self.assertEqual(initial.form("reference-path-form").target, "/action")
            self.assertEqual(initial.form("cube-path-form").target, "/action")

            page = server.post("load-synthetic")
            self.assertEqual(
                page.element("reference-metadata").definition("Format"),
                "ppm-p6-rgb8",
            )
            self.assertEqual(
                page.element("transformation-metadata").definition("Interpolation"),
                "trilinear",
            )
            page = server.post(
                "configure-transformation",
                {
                    "interpolation": "tetrahedral",
                    "bypass": "on",
                    "mix": "0.5",
                },
            )
            transformation = page.element("transformation-metadata")
            self.assertEqual(transformation.definition("Interpolation"), "tetrahedral")
            self.assertEqual(transformation.definition("Bypass"), "true")
            self.assertEqual(transformation.definition("Mix"), "0.5")

            page = server.post("declare-contexts", _basis_fields(page))
            rendered_contexts = page.element("color-contexts")
            self.assertIn("ProofColorContext", rendered_contexts.definition("Declaration"))
            self.assertIn(
                "ExportColorContext",
                rendered_contexts.definition("Export independent"),
            )
            self.assertIn("interpolation=<Interpolation.TETRAHEDRAL", rendered_contexts.text)

            page = server.post("request-preview")
            preview = page.latest_job
            self.assertEqual(preview.purpose, "preview")
            self.assertEqual(preview.state, "queued")
            page = server.post("step-job", {"job-id": str(preview.job_id)})
            stepped_preview = page.job(preview.job_id)
            self.assertEqual(stepped_preview.state, "running")
            self.assertGreater(stepped_preview.completed_units, 0)
            self.assertLess(stepped_preview.completed_units, stepped_preview.total_units)
            page = server.post("run-job", {"job-id": str(preview.job_id)})
            self.assertEqual(page.job(preview.job_id).state, "succeeded")
            self.assertEqual(len(page.elements_with_prefix("surface-")), 2)

            page = server.post("request-full")
            cancelled = page.latest_job
            self.assertEqual(cancelled.purpose, "full-resolution-evaluation")
            page = server.post("step-job", {"job-id": str(cancelled.job_id)})
            self.assertGreater(page.job(cancelled.job_id).completed_units, 0)
            page = server.post("cancel-job", {"job-id": str(cancelled.job_id)})
            self.assertEqual(page.job(cancelled.job_id).state, "cancelled")
            self.assertEqual(len(page.elements_with_prefix("surface-")), 2)

            page = server.post("stale-demo")
            full_jobs = tuple(
                job
                for job in page.jobs
                if job.purpose == "full-resolution-evaluation"
            )
            older, newer = full_jobs[-2:]
            self.assertLess(older.job_id, newer.job_id)
            self.assertEqual(older.state, "stale")
            self.assertEqual(newer.state, "succeeded")
            full_surfaces = tuple(
                surface
                for surface in page.elements_with_prefix("surface-")
                if surface.definition("Purpose") == "processed-full-resolution"
            )
            self.assertEqual(len(full_surfaces), 1)

            page = server.post("inspect-canonical")
            canonical_job = page.latest_job
            self.assertEqual(canonical_job.purpose, "canonical-portable-cube-export")
            page = server.post("run-job", {"job-id": str(canonical_job.job_id)})
            canonical = page.element("canonical-artifact")
            self.assertEqual(canonical.definition("Job ID"), str(canonical_job.job_id))
            self.assertEqual(canonical.definition("Byte count"), "62")
            self.assertEqual(len(canonical.definition("SHA-256")), 64)
            self.assertIn("LUT_3D_SIZE 2", canonical.definition("Canonical bytes"))
            self.assertEqual(
                page.element("ordinary-export-status").text,
                _ORDINARY_EXPORT_BLOCKED,
            )

            before_visible = _last_valid_visible_state(page)
            page = server.post("malformed-reference")
            self.assertEqual(
                page.element("command-diagnostic").definition("Code"),
                "REFERENCE_STRUCTURE_INVALID",
            )
            self.assertEqual(_last_valid_visible_state(page), before_visible)


class InternalTestUiMacOsSurfaceAcceptanceTest(unittest.TestCase):
    def test_documented_command_opens_and_closes_only_its_real_surface(self) -> None:
        controller = SafariSurfaceController()
        process = PrototypeServerProcess(
            open_browser=True,
            extra_environment=controller.browser_environment,
        )
        self.assertEqual(
            process.command,
            ("python3.12", "-m", "internal_test_ui_prototype"),
        )
        url: str | None = None
        surface_control_available = True
        try:
            url = process.start()
            exact_count = controller.wait_for_exact_url(url)
            self.assertEqual(exact_count, 1)
            page = process.get()
            self.assertEqual(page.status, 200)
            self.assertIn("NOT PRODUCT UI", page.element("prototype-banner").text)
        except BrowserSurfaceUnavailable:
            surface_control_available = False
            process.stop(check=False)
            raise
        finally:
            if url is not None and surface_control_available:
                try:
                    if controller.count_exact_url(url) > 0:
                        closed_count = controller.close_exact_url(url)
                        self.assertEqual(closed_count, 1)
                        controller.wait_until_closed(url)
                finally:
                    if process.url is not None:
                        process.stop(check=sys.exc_info()[0] is None)
        self.assertIsNone(process.url)


class InternalTestUiE2eBoundaryAuditTest(unittest.TestCase):
    def test_acceptance_sources_use_only_public_runtime_and_stdlib(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        sources = (
            repository_root / "tests" / "internal_test_ui_e2e_support.py",
            repository_root / "tests" / "test_internal_test_ui_e2e.py",
        )
        forbidden_text = (
            "portable_cube_" + "harness",
            "color " + "math",
            "sl" + "eep(",
            "str" + "uct",
            "zl" + "ib",
        )

        for source_path in sources:
            source = source_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(source_path))
            for text in forbidden_text:
                self.assertNotIn(text, source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module is not None:
                    if node.module.startswith("colorluthier_engine"):
                        self.assertEqual(node.module, "colorluthier_engine")
                    if node.module.startswith("internal_test_ui_adapter"):
                        self.assertEqual(node.module, "internal_test_ui_adapter")
                    if node.module.startswith("internal_test_ui_prototype"):
                        self.assertEqual(node.module, "internal_test_ui_prototype")


if __name__ == "__main__":
    unittest.main()
