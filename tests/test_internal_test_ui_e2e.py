# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import errno
import io
import os
import stat
import subprocess
import sys
import traceback
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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

import internal_test_ui_e2e_support as e2e_support
from internal_test_ui_e2e_support import (
    AccessiblePage,
    BrowserSurfaceUnavailable,
    PrototypeServerProcess,
    SafariSurfaceController,
    parse_accessible_page,
)


_ORDINARY_EXPORT_BLOCKED = "blocked-pending-explicit-color-contexts"
_SYNTHETIC_REFERENCE_PPM = (
    b"P6\n2 2\n255\n"
    b"\x00\x00\x00"
    b"\xff\x00\x00"
    b"\x00\xff\x00"
    b"\x00\x00\xff"
)
_SYNTHETIC_IDENTITY_CUBE = (
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


def _full_surface_state(page: AccessiblePage) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (surface.test_id, surface.definitions)
        for surface in page.elements_with_prefix("surface-")
        if surface.definition("Purpose") == "processed-full-resolution"
    )


def _input_inventory(root: Path) -> tuple[tuple[object, ...], ...]:
    inventory = []
    for path in sorted(root.iterdir()):
        metadata = path.stat()
        inventory.append(
            (
                path.name,
                path.read_bytes(),
                stat.S_IMODE(metadata.st_mode),
                metadata.st_mtime_ns,
            )
        )
    return tuple(inventory)


class PrototypeServerProcessTest(unittest.TestCase):
    def _assert_exception_graph_omits(
        self,
        error: BaseException,
        marker: bytes,
    ) -> None:
        self.assertIsNone(error.__cause__)
        self.assertIsNone(error.__context__)
        formatted = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        self.assertNotIn(marker.decode("ascii"), formatted)

    def test_process_driver_uses_current_interpreter_without_alias(self) -> None:
        process = PrototypeServerProcess()
        self.assertEqual(process.command[0], sys.executable)

        with mock.patch(
            "shutil.which",
            side_effect=AssertionError("process driver must not resolve a Python alias"),
        ):
            with process as server:
                self.assertEqual(server.get().status, 200)

    def test_process_driver_uses_bounded_windows_shutdown_without_hiding_crashes(
        self,
    ) -> None:
        controlled = mock.Mock()
        controlled.poll.return_value = None
        controlled.communicate.return_value = (b"", b"")
        controlled.returncode = 1
        process = PrototypeServerProcess()
        process._process = controlled

        with mock.patch.object(e2e_support.os, "name", "nt"):
            self.assertEqual(process.stop(), 1)

        controlled.terminate.assert_called_once_with()
        controlled.send_signal.assert_not_called()

        crashed = mock.Mock()
        crashed.poll.return_value = 7
        marker = b"SYNTHETIC_SENTINEL_NOT_FOR_LOGS"
        captured_stderr = b"A" * 5_000 + marker
        crashed.communicate.return_value = (b"", captured_stderr)
        crashed.returncode = 7
        process = PrototypeServerProcess()
        process._process = crashed

        with mock.patch.object(e2e_support.os, "name", "nt"):
            with self.assertRaises(AssertionError) as raised:
                process.stop()

        self.assertEqual(
            str(raised.exception),
            f"prototype exited 7; stderr bytes {len(captured_stderr)}",
        )
        self._assert_exception_graph_omits(raised.exception, marker)

        crashed.terminate.assert_not_called()
        crashed.send_signal.assert_not_called()

    def test_process_driver_diagnostics_never_embed_captured_output(self) -> None:
        marker = b"SYNTHETIC_SENTINEL_NOT_FOR_LOGS"
        captured = b"B" * 5_000 + marker
        cases = (
            (
                b"",
                captured,
                f"prototype printed unexpected stderr; stderr bytes {len(captured)}",
            ),
            (
                captured,
                b"",
                "prototype printed unexpected stdout after readiness; "
                f"stdout bytes {len(captured)}",
            ),
        )

        for stdout, stderr, expected in cases:
            with self.subTest(expected=expected):
                child = mock.Mock()
                child.poll.return_value = 0
                child.communicate.return_value = (stdout, stderr)
                child.returncode = 0
                process = PrototypeServerProcess()
                process._process = child

                with self.assertRaises(AssertionError) as raised:
                    process.stop()

                self.assertEqual(str(raised.exception), expected)
                self._assert_exception_graph_omits(raised.exception, marker)

    def test_process_driver_forced_cleanup_has_only_bounded_waits(self) -> None:
        marker = b"SYNTHETIC_SENTINEL_NOT_FOR_LOGS"
        child = mock.Mock()
        child.poll.return_value = None
        child.communicate.side_effect = (
            subprocess.TimeoutExpired(
                ("synthetic-child",),
                10,
                output=marker,
                stderr=marker,
            ),
            (b"", b""),
        )
        child.returncode = -9
        process = PrototypeServerProcess()
        process._process = child

        with self.assertRaises(AssertionError) as recovered:
            process.stop()

        self.assertEqual(
            str(recovered.exception),
            "prototype did not stop before forced termination",
        )
        self._assert_exception_graph_omits(recovered.exception, marker)
        self.assertEqual(
            child.communicate.call_args_list,
            [mock.call(timeout=10), mock.call(timeout=10)],
        )
        child.kill.assert_called_once_with()
        self.assertIsNone(process._process)

        stuck = mock.Mock()
        stuck.poll.return_value = None
        stuck.communicate.side_effect = (
            subprocess.TimeoutExpired(
                ("synthetic-child",),
                10,
                output=marker,
                stderr=marker,
            ),
            subprocess.TimeoutExpired(
                ("synthetic-child",),
                10,
                output=marker,
                stderr=marker,
            ),
        )
        process = PrototypeServerProcess()
        process._process = stuck

        with self.assertRaises(AssertionError) as unrecovered:
            process.stop(check=False)

        self.assertEqual(
            str(unrecovered.exception),
            "prototype did not stop after forced termination",
        )
        self._assert_exception_graph_omits(unrecovered.exception, marker)
        self.assertEqual(
            stuck.communicate.call_args_list,
            [mock.call(timeout=10), mock.call(timeout=10)],
        )
        stuck.kill.assert_called_once_with()
        self.assertIs(process._process, stuck)


class AccessibleFormDriverTest(unittest.TestCase):
    def test_select_defaults_selected_options_and_checked_boxes_are_submitted(
        self,
    ) -> None:
        page = parse_accessible_page(
            b"""<!doctype html>
            <form method="post" action="/action" data-testid="form-under-test">
              <input type="hidden" name="action" value="configure-transformation">
              <input type="text" name="mix" value="1.0">
              <select name="default-choice">
                <option value="first">First</option>
                <option value="second">Second</option>
              </select>
              <select name="selected-choice">
                <option value="first">First</option>
                <option value="second" selected>Second</option>
              </select>
              <input type="checkbox" name="enabled" checked>
              <input type="checkbox" name="named-enabled" value="yes" checked>
              <input type="checkbox" name="disabled" value="no">
            </form>"""
        )
        form = page.form("form-under-test")

        self.assertEqual(form.field("default-choice"), "first")
        self.assertEqual(form.field("selected-choice"), "second")
        self.assertEqual(form.field("enabled"), "on")
        self.assertEqual(form.field("named-enabled"), "yes")
        with self.assertRaises(AssertionError):
            form.field("disabled")
        self.assertEqual(
            dict(form.submission({"mix": "0.5", "disabled": "on"})),
            {
                "action": "configure-transformation",
                "mix": "0.5",
                "default-choice": "first",
                "selected-choice": "second",
                "enabled": "on",
                "named-enabled": "yes",
                "disabled": "on",
            },
        )

    def test_duplicate_field_names_are_rejected_before_access_or_submission(
        self,
    ) -> None:
        page = parse_accessible_page(
            b"""<!doctype html>
            <form method="post" action="/action" data-testid="duplicate-form">
              <input type="hidden" name="action" value="load-synthetic">
              <input type="hidden" name="action" value="malformed-reference">
              <input type="text" name="unique" value="kept">
            </form>"""
        )
        form = page.form("duplicate-form")

        with self.assertRaisesRegex(AssertionError, "duplicate field name"):
            form.field("unique")
        with self.assertRaisesRegex(AssertionError, "duplicate field name"):
            form.submission({})

    def test_process_driver_accepts_only_post_action_forms(self) -> None:
        page = parse_accessible_page(
            b"""<!doctype html>
            <form method="get" action="/action" data-testid="wrong-method">
              <input type="hidden" name="action" value="load-synthetic">
            </form>
            <form method="post" action="/elsewhere" data-testid="wrong-target">
              <input type="hidden" name="action" value="load-synthetic">
            </form>"""
        )

        with PrototypeServerProcess() as server:
            with self.assertRaisesRegex(AssertionError, "POST /action"):
                server.submit(page.form("wrong-method"))
            with self.assertRaisesRegex(AssertionError, "POST /action"):
                server.submit(page.form("wrong-target"))


class _FakeHttpResponse:
    def __init__(self, body: bytes, content_length: str | None) -> None:
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length
        self._body = io.BytesIO(body)

    def read(self, maximum: int = -1) -> bytes:
        return self._body.read(maximum)


class BoundedIoDriverTest(unittest.TestCase):
    def _readiness(self, payload: bytes, *, maximum_bytes: int = 64) -> bytes:
        read_descriptor, write_descriptor = os.pipe()
        try:
            os.write(write_descriptor, payload)
        finally:
            os.close(write_descriptor)
        with os.fdopen(read_descriptor, "rb", buffering=0) as stream:
            return e2e_support.read_bounded_readiness(
                stream,
                timeout_seconds=0.1,
                maximum_bytes=maximum_bytes,
            )

    def test_readiness_requires_one_complete_bounded_line(self) -> None:
        self.assertEqual(
            self._readiness(b"http://127.0.0.1:1234/\n"),
            b"http://127.0.0.1:1234/",
        )
        with self.assertRaises(RuntimeError) as ended:
            self._readiness(b"")
        self.assertEqual(
            str(ended.exception),
            "prototype stream ended before readiness",
        )
        with self.assertRaises(RuntimeError) as unterminated:
            self._readiness(b"http://127.0.0.1:1234/")
        self.assertEqual(
            str(unterminated.exception),
            "prototype emitted an unterminated readiness record",
        )
        with self.assertRaises(RuntimeError) as over_limit:
            self._readiness(b"123456789\n", maximum_bytes=8)
        self.assertEqual(
            str(over_limit.exception),
            "prototype exceeded the readiness byte limit",
        )

    def test_readiness_retries_when_a_nonblocking_pipe_has_no_data(self) -> None:
        real_read = os.read

        windows_pipe_no_data = OSError(errno.EPIPE, "Windows pipe has no data")
        windows_pipe_no_data.winerror = 232
        unavailable_errors = (
            BlockingIOError(errno.EAGAIN, "pipe temporarily unavailable"),
            windows_pipe_no_data,
        )

        for unavailable_error in unavailable_errors:
            with self.subTest(error=repr(unavailable_error)):
                first_read = True

                def read_after_one_unavailable_attempt(
                    descriptor: int,
                    maximum_bytes: int,
                ) -> bytes:
                    nonlocal first_read
                    if first_read:
                        first_read = False
                        raise unavailable_error
                    return real_read(descriptor, maximum_bytes)

                with mock.patch.object(
                    e2e_support.os,
                    "read",
                    side_effect=read_after_one_unavailable_attempt,
                ):
                    self.assertEqual(self._readiness(b"ready\n"), b"ready")

    def test_default_readiness_budget_accepts_virtual_hosted_cold_start(self) -> None:
        class VirtualClock:
            def __init__(self) -> None:
                self.elapsed = 0.0

            def monotonic(self) -> float:
                return self.elapsed

            def wait(self, timeout_seconds: float) -> bool:
                self.elapsed += timeout_seconds
                return False

        clock = VirtualClock()
        readiness = iter(b"ready\n")

        def read_after_hosted_cold_start(
            descriptor: int,
            maximum_bytes: int,
        ) -> bytes:
            self.assertEqual(descriptor, 42)
            self.assertEqual(maximum_bytes, 1)
            if clock.elapsed < 35:
                raise BlockingIOError(errno.EAGAIN, "pipe temporarily unavailable")
            return bytes((next(readiness),))

        stream = mock.Mock()
        stream.fileno.return_value = 42
        poll_wait = mock.Mock()
        poll_wait.wait.side_effect = clock.wait
        with (
            mock.patch.object(e2e_support.time, "monotonic", clock.monotonic),
            mock.patch.object(e2e_support.threading, "Event", return_value=poll_wait),
            mock.patch.object(e2e_support.os, "get_blocking", return_value=True),
            mock.patch.object(e2e_support.os, "set_blocking") as set_blocking,
            mock.patch.object(
                e2e_support.os,
                "read",
                side_effect=read_after_hosted_cold_start,
            ),
            mock.patch.object(e2e_support, "_READINESS_POLL_INTERVAL_SECONDS", 1.0),
        ):
            self.assertEqual(e2e_support.read_bounded_readiness(stream), b"ready")

        self.assertEqual(
            set_blocking.call_args_list,
            [mock.call(42, False), mock.call(42, True)],
        )

    def test_readiness_timeout_leaves_no_concurrent_pipe_reader(self) -> None:
        read_descriptor, write_descriptor = os.pipe()
        try:
            os.write(write_descriptor, b"partial")
            with os.fdopen(read_descriptor, "rb", buffering=0) as stream:
                with self.assertRaisesRegex(RuntimeError, "readiness timed out"):
                    e2e_support.read_bounded_readiness(
                        stream,
                        timeout_seconds=0.01,
                        maximum_bytes=64,
                    )
                self.assertTrue(os.get_blocking(stream.fileno()))
                os.write(write_descriptor, b"fresh\n")
                self.assertEqual(
                    e2e_support.read_bounded_readiness(
                        stream,
                        timeout_seconds=0.1,
                        maximum_bytes=64,
                    ),
                    b"fresh",
                )
        finally:
            os.close(write_descriptor)

    def test_http_body_requires_exact_bounded_content_length(self) -> None:
        self.assertEqual(
            e2e_support.read_bounded_http_body(
                _FakeHttpResponse(b"body", "4"),
                maximum_bytes=8,
            ),
            b"body",
        )
        with self.assertRaisesRegex(RuntimeError, "Content-Length is missing"):
            e2e_support.read_bounded_http_body(
                _FakeHttpResponse(b"body", None),
                maximum_bytes=8,
            )
        with self.assertRaisesRegex(RuntimeError, "exceeds the byte limit"):
            e2e_support.read_bounded_http_body(
                _FakeHttpResponse(b"body", "9"),
                maximum_bytes=8,
            )
        with self.assertRaisesRegex(RuntimeError, "body length is not exact"):
            e2e_support.read_bounded_http_body(
                _FakeHttpResponse(b"part", "5"),
                maximum_bytes=8,
            )
        with self.assertRaisesRegex(RuntimeError, "body length is not exact"):
            e2e_support.read_bounded_http_body(
                _FakeHttpResponse(b"extra", "4"),
                maximum_bytes=8,
            )


class InternalTestUiHeadlessAcceptanceTest(unittest.TestCase):
    def test_public_intents_translate_to_snapshot_backed_render_state(self) -> None:
        executor = ManualExecutor()
        adapter = InternalTestUiAdapter(executor)

        opened = adapter.dispatch(
            OpenReferenceIntent(
                _SYNTHETIC_REFERENCE_PPM,
                ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )
        self.assertEqual(opened.disposition, SnapshotDisposition.ACCEPTED)
        self.assertIs(opened.state, adapter.current)
        self.assertIs(opened.state.snapshot, adapter.current.snapshot)
        self.assertIsNotNone(opened.state.snapshot.reference)

        loaded = adapter.dispatch(
            LoadPortableCubeIntent(
                _SYNTHETIC_IDENTITY_CUBE,
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

        valid_full_resolution = application.current.snapshot.full_resolution
        valid_full_surface = _full_surface_state(_render(application))
        application.dispatch_action("request-full", {})
        refresh_id = application.current.submitted_job_id.value
        application.dispatch_action("step-job", {"job-id": str(refresh_id)})
        application.dispatch_action("cancel-job", {"job-id": str(refresh_id)})
        self.assertEqual(_job_snapshot(application, refresh_id).state, JobState.CANCELLED)
        self.assertIs(
            application.current.snapshot.full_resolution,
            valid_full_resolution,
        )
        self.assertEqual(_full_surface_state(_render(application)), valid_full_surface)

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
    def test_path_forms_read_synthetic_inputs_without_mutating_them(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            input_root = Path(temporary_directory)
            reference = input_root / "synthetic-reference.ppm"
            cube = input_root / "synthetic-identity.cube"
            reference.write_bytes(_SYNTHETIC_REFERENCE_PPM)
            cube.write_bytes(_SYNTHETIC_IDENTITY_CUBE)
            before = _input_inventory(input_root)

            with PrototypeServerProcess() as server:
                page = server.get()
                page = server.submit(
                    page.form("reference-path-form"),
                    {
                        "reference-path": str(reference),
                        "image-format": "ppm-p6-rgb8",
                    },
                )
                page = server.submit(
                    page.form("cube-path-form"),
                    {
                        "cube-path": str(cube),
                        "interpolation": "tetrahedral",
                        "mix": "0.5",
                    },
                )

            self.assertEqual(
                page.element("reference-metadata").definition("Format"),
                "ppm-p6-rgb8",
            )
            self.assertEqual(
                page.element("transformation-metadata").definition("Interpolation"),
                "tetrahedral",
            )
            self.assertEqual(_input_inventory(input_root), before)

    def test_full_loopback_http_flow_is_accessible_and_deterministic(self) -> None:
        with PrototypeServerProcess() as server:
            initial = server.get()
            self.assertEqual(initial.status, 200)
            self.assertEqual(initial.content_type, "text/html; charset=utf-8")
            self.assertIn("NOT PRODUCT UI", initial.element("prototype-banner").text)
            self.assertEqual(initial.form("reference-path-form").target, "/action")
            self.assertEqual(initial.form("cube-path-form").target, "/action")
            stale_context_form = initial.form("declare-contexts-form")

            page = server.submit(initial.action_form("load-synthetic"))
            self.assertEqual(
                page.element("reference-metadata").definition("Format"),
                "ppm-p6-rgb8",
            )
            self.assertEqual(
                page.element("transformation-metadata").definition("Interpolation"),
                "trilinear",
            )
            page = server.submit(
                page.form("configure-form"),
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

            page = server.submit(stale_context_form)
            self.assertEqual(
                page.element("command-diagnostic").definition("Code"),
                "COLOR_CONTEXT_REVISION_CONFLICT",
            )
            self.assertEqual(
                page.element("snapshot-revisions").definition("Command status"),
                "rejected",
            )
            page = server.submit(page.form("declare-contexts-form"))
            self.assertEqual(
                page.element("snapshot-revisions").definition("Command status"),
                "committed",
            )
            rendered_contexts = page.element("color-contexts")
            self.assertIn("ProofColorContext", rendered_contexts.definition("Declaration"))
            self.assertIn(
                "ExportColorContext",
                rendered_contexts.definition("Export independent"),
            )
            self.assertIn("interpolation=<Interpolation.TETRAHEDRAL", rendered_contexts.text)

            page = server.submit(page.action_form("request-preview"))
            preview = page.latest_job
            self.assertEqual(preview.purpose, "preview")
            self.assertEqual(preview.state, "queued")
            page = server.submit(
                page.action_form("step-job", {"job-id": str(preview.job_id)})
            )
            stepped_preview = page.job(preview.job_id)
            self.assertEqual(stepped_preview.state, "running")
            self.assertGreater(stepped_preview.completed_units, 0)
            self.assertLess(stepped_preview.completed_units, stepped_preview.total_units)
            page = server.submit(
                page.action_form("run-job", {"job-id": str(preview.job_id)})
            )
            self.assertEqual(page.job(preview.job_id).state, "succeeded")
            self.assertEqual(len(page.elements_with_prefix("surface-")), 2)

            page = server.submit(page.action_form("request-full"))
            published = page.latest_job
            self.assertEqual(published.purpose, "full-resolution-evaluation")
            page = server.submit(
                page.action_form("run-job", {"job-id": str(published.job_id)})
            )
            self.assertEqual(page.job(published.job_id).state, "succeeded")
            valid_full_surface = _full_surface_state(page)
            self.assertEqual(len(valid_full_surface), 1)

            page = server.submit(page.action_form("request-full"))
            cancelled = page.latest_job
            page = server.submit(
                page.action_form("step-job", {"job-id": str(cancelled.job_id)})
            )
            self.assertGreater(page.job(cancelled.job_id).completed_units, 0)
            page = server.submit(
                page.action_form("cancel-job", {"job-id": str(cancelled.job_id)})
            )
            self.assertEqual(page.job(cancelled.job_id).state, "cancelled")
            self.assertEqual(_full_surface_state(page), valid_full_surface)

            page = server.submit(page.action_form("stale-demo"))
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

            page = server.submit(page.action_form("inspect-canonical"))
            canonical_job = page.latest_job
            self.assertEqual(canonical_job.purpose, "canonical-portable-cube-export")
            page = server.submit(
                page.action_form("run-job", {"job-id": str(canonical_job.job_id)})
            )
            canonical = page.element("canonical-artifact")
            self.assertEqual(canonical.definition("Job ID"), str(canonical_job.job_id))
            self.assertTrue(canonical.definition("Canonical bytes"))
            self.assertEqual(
                page.element("ordinary-export-status").text,
                _ORDINARY_EXPORT_BLOCKED,
            )

            before_visible = _last_valid_visible_state(page)
            page = server.submit(page.action_form("malformed-reference"))
            self.assertEqual(
                page.element("command-diagnostic").definition("Code"),
                "REFERENCE_STRUCTURE_INVALID",
            )
            self.assertEqual(_last_valid_visible_state(page), before_visible)


class InternalTestUiMacOsSurfaceAcceptanceTest(unittest.TestCase):
    def test_real_surface_smoke_opt_in_matches_environment(self) -> None:
        smoke = type(self).test_documented_command_opens_and_closes_only_its_real_surface
        enabled = os.environ.get("COLORLUTHIER_RUN_REAL_SURFACE_SMOKE") == "1"

        self.assertEqual(getattr(smoke, "__unittest_skip__", False), not enabled)
        if not enabled:
            self.assertIn(
                "COLORLUTHIER_RUN_REAL_SURFACE_SMOKE=1",
                getattr(smoke, "__unittest_skip_why__", ""),
            )

    def test_opted_in_surface_smoke_remains_fail_closed_off_macos(self) -> None:
        smoke = type(self)(
            "test_documented_command_opens_and_closes_only_its_real_surface"
        )
        surface_test = type(self).test_documented_command_opens_and_closes_only_its_real_surface
        opted_in_body = getattr(surface_test, "__wrapped__", surface_test)
        with (
            mock.patch.object(e2e_support.sys, "platform", "linux"),
            self.assertRaisesRegex(BrowserSurfaceUnavailable, "macOS is required"),
        ):
            opted_in_body(smoke)

    def test_inventory_failures_do_not_expose_unrelated_urls(self) -> None:
        controller = object.__new__(SafariSurfaceController)
        residual_url = "http://127.0.0.1:54321/"
        before = ("https://BEFORE_SECRET.invalid/",)
        current = ("https://CURRENT_SECRET.invalid/", residual_url)

        with mock.patch.object(controller, "inventory", return_value=current):
            with self.assertRaises(BrowserSurfaceUnavailable) as added:
                controller.wait_for_added_document(before, residual_url)
            with self.assertRaises(BrowserSurfaceUnavailable) as restored:
                controller.wait_for_inventory(before, residual_url=residual_url)

        for failure, expected_count in ((added, 2), (restored, 1)):
            message = str(failure.exception)
            self.assertIn(f"residual URL {residual_url}", message)
            self.assertIn(f"expected document count {expected_count}", message)
            self.assertIn("current document count 2", message)
            self.assertIn("target present yes", message)
            self.assertEqual(message.count(residual_url), 1)
            self.assertNotIn("BEFORE_SECRET", message)
            self.assertNotIn("CURRENT_SECRET", message)

    @unittest.skipUnless(
        os.environ.get("COLORLUTHIER_RUN_REAL_SURFACE_SMOKE") == "1",
        "set COLORLUTHIER_RUN_REAL_SURFACE_SMOKE=1 to run the real Safari surface smoke",
    )
    def test_documented_command_opens_and_closes_only_its_real_surface(self) -> None:
        controller = SafariSurfaceController()
        wrapper_path: Path | None = None
        url: str | None = None
        with controller:
            wrapper_path = controller.wrapper_path
            before = controller.inventory()
            process = PrototypeServerProcess(
                open_browser=True,
                extra_environment=controller.browser_environment,
            )
            self.assertEqual(
                process.command,
                (sys.executable, "-m", "internal_test_ui_prototype"),
            )
            cleanup_error: BrowserSurfaceUnavailable | None = None
            try:
                url = process.start()
                opened = controller.wait_for_added_document(before, url)
                self.assertEqual(len(opened), len(before) + 1)
                self.assertEqual(opened.count(url), before.count(url) + 1)
                page = process.get()
                self.assertEqual(page.status, 200)
                self.assertIn("NOT PRODUCT UI", page.element("prototype-banner").text)
            finally:
                try:
                    if url is not None:
                        closed_count = controller.close_exact_url(url)
                        if closed_count != 1:
                            raise BrowserSurfaceUnavailable(
                                f"Safari closed {closed_count} documents; residual URL {url}"
                            )
                        controller.wait_for_inventory(before, residual_url=url)
                except BrowserSurfaceUnavailable as error:
                    cleanup_error = error
                finally:
                    if process.url is not None:
                        process.stop(
                            check=(
                                sys.exc_info()[0] is None
                                and cleanup_error is None
                            )
                        )
                if cleanup_error is not None:
                    raise BrowserSurfaceUnavailable(
                        f"Safari cleanup failed; residual URL {url}"
                    ) from cleanup_error
            if url is None:
                raise AssertionError("prototype did not publish its loopback URL")
            controller.wait_for_inventory(before, residual_url=url)
            self.assertIsNone(process.url)
        self.assertIsNotNone(wrapper_path)
        self.assertFalse(wrapper_path.exists())


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
