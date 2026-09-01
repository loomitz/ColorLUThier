# SPDX-FileCopyrightText: 2026 ColorLUThier contributors <https://github.com/loomitz/ColorLUThier>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import ast
import struct
import threading
import unittest
import zlib
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from colorluthier_engine import (
    CommandStatus,
    Interpolation,
    JobPurpose,
    JobState,
    ProvisionalImageFormat,
)
from internal_test_ui_prototype import (
    PrototypeApplication,
    create_server,
    render_page,
    server_url,
)
from internal_test_ui_prototype._synthetic import (
    SYNTHETIC_IDENTITY_CUBE,
    SYNTHETIC_REFERENCE_PPM,
)


def expected_basis_fields(application: PrototypeApplication) -> dict[str, str]:
    basis = application.current.snapshot.color_contexts.revision_basis
    return {
        "expected-interpretation": str(basis.interpretation.value),
        "expected-viewing": str(basis.viewing.value),
        "expected-export": str(basis.export.value),
    }


def job_by_id(application: PrototypeApplication, job_id: int):
    return next(
        job
        for job in application.current.snapshot.jobs
        if job.job_id.value == job_id
    )


def synthetic_rgba_png() -> bytes:
    def chunk(chunk_type: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        return (
            struct.pack(">I", len(payload))
            + chunk_type
            + payload
            + struct.pack(">I", checksum)
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    scanline = b"\x00\x12\x34\x56\x78"
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanline))
        + chunk(b"IEND", b"")
    )


class ReferenceFormatOptionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_reference_format = False
        self.values: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        values = dict(attributes)
        if tag == "select" and values.get("name") == "image-format":
            self._inside_reference_format = True
        elif tag == "option" and self._inside_reference_format:
            value = values.get("value")
            if value is not None:
                self.values.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "select" and self._inside_reference_format:
            self._inside_reference_format = False


class CountingRenderApplication:
    def __init__(self, application: PrototypeApplication) -> None:
        self._application = application
        self.current_reads = 0

    @property
    def current(self):
        self.current_reads += 1
        return self._application.current

    @property
    def pending_job_ids(self):
        return self._application.pending_job_ids

    @property
    def notice(self):
        return self._application.notice


class InternalTestUiPrototypeTest(unittest.TestCase):
    def test_every_reference_format_option_is_public_and_loads_rgba_png(self) -> None:
        option_parser = ReferenceFormatOptionParser()
        option_parser.feed(render_page(PrototypeApplication()).decode("utf-8"))
        public_values = tuple(image_format.value for image_format in ProvisionalImageFormat)
        failures = []

        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            inputs = {
                ProvisionalImageFormat.PPM_P6_RGB8.value: SYNTHETIC_REFERENCE_PPM,
                ProvisionalImageFormat.PNG_RGB8.value: synthetic_rgba_png(),
            }
            for option_value in option_parser.values:
                try:
                    ProvisionalImageFormat(option_value)
                except ValueError:
                    failures.append(f"{option_value}:not-public")
                    encoded = synthetic_rgba_png()
                else:
                    encoded = inputs[option_value]
                input_path = root / f"input-{len(failures)}.bin"
                input_path.write_bytes(encoded)
                application = PrototypeApplication()
                application.dispatch_action(
                    "open-reference-path",
                    {
                        "reference-path": str(input_path),
                        "image-format": option_value,
                    },
                )
                if application.notice is not None:
                    failures.append(
                        f"{option_value}:{application.notice.code}"
                    )
                if application.current.snapshot.reference is None:
                    failures.append(f"{option_value}:not-loaded")

        self.assertEqual(failures, [])
        self.assertEqual(tuple(option_parser.values), public_values)

    def test_actions_map_through_adapter_and_declare_independent_export(self) -> None:
        application = PrototypeApplication()
        application.dispatch_action("load-synthetic", {})
        snapshot = application.current.snapshot
        self.assertIsNotNone(snapshot.reference)
        self.assertIsNotNone(snapshot.transformation)

        application.dispatch_action(
            "configure-transformation",
            {
                "interpolation": "tetrahedral",
                "bypass": "on",
                "mix": "0.5",
            },
        )
        transformation = application.current.snapshot.transformation
        self.assertEqual(transformation.interpolation, Interpolation.TETRAHEDRAL)
        self.assertTrue(transformation.bypass)
        self.assertEqual(transformation.mix, 0.5)

        application.dispatch_action(
            "declare-contexts",
            expected_basis_fields(application),
        )
        contexts = application.current.snapshot.color_contexts
        self.assertIsNotNone(contexts.proof)
        self.assertIsNotNone(contexts.display)
        self.assertIsNotNone(contexts.export_context)
        self.assertEqual(
            contexts.export_context.interpolation,
            Interpolation.TETRAHEDRAL,
        )
        self.assertIsNot(
            contexts.export_context.input_context,
            contexts.export_context.output_context,
        )

        for action, purpose in (
            ("request-preview", JobPurpose.PREVIEW),
            ("request-full", JobPurpose.FULL_RESOLUTION_EVALUATION),
            ("inspect-canonical", JobPurpose.CANONICAL_PORTABLE_CUBE_EXPORT),
        ):
            application.dispatch_action(action, {})
            state = application.current
            self.assertEqual(state.command_status, CommandStatus.ACCEPTED)
            self.assertEqual(
                job_by_id(application, state.submitted_job_id.value).purpose,
                purpose,
            )

    def test_path_actions_read_inputs_without_writing_artifacts(self) -> None:
        application = PrototypeApplication()
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            reference = root / "synthetic.ppm"
            cube = root / "identity.cube"
            reference.write_bytes(SYNTHETIC_REFERENCE_PPM)
            cube.write_bytes(SYNTHETIC_IDENTITY_CUBE)
            before = tuple(root.iterdir())

            application.dispatch_action(
                "open-reference-path",
                {
                    "reference-path": str(reference),
                    "image-format": "ppm-p6-rgb8",
                },
            )
            application.dispatch_action(
                "load-cube-path",
                {
                    "cube-path": str(cube),
                    "interpolation": "trilinear",
                    "mix": "1.0",
                },
            )

            self.assertIsNotNone(application.current.snapshot.reference)
            self.assertIsNotNone(application.current.snapshot.transformation)
            self.assertEqual(tuple(root.iterdir()), before)

    def test_manual_progress_cancel_and_newest_before_oldest_are_deterministic(
        self,
    ) -> None:
        application = PrototypeApplication()
        application.dispatch_action("load-synthetic", {})
        application.dispatch_action("request-full", {})
        cancelled_id = application.current.submitted_job_id.value
        self.assertEqual(job_by_id(application, cancelled_id).progress.completed_units, 0)

        application.dispatch_action("step-job", {"job-id": str(cancelled_id)})
        self.assertEqual(job_by_id(application, cancelled_id).progress.completed_units, 1)
        application.dispatch_action("cancel-job", {"job-id": str(cancelled_id)})
        self.assertEqual(job_by_id(application, cancelled_id).state, JobState.CANCELLED)
        self.assertNotIn(cancelled_id, application.pending_job_ids)
        self.assertIsNone(application.current.snapshot.full_resolution)

        application.dispatch_action("stale-demo", {})
        full_jobs = tuple(
            job
            for job in application.current.snapshot.jobs
            if job.purpose is JobPurpose.FULL_RESOLUTION_EVALUATION
        )
        older, newer = full_jobs[-2:]
        self.assertLess(older.job_id.value, newer.job_id.value)
        self.assertEqual(older.state, JobState.STALE)
        self.assertEqual(newer.state, JobState.SUCCEEDED)
        self.assertEqual(
            application.current.snapshot.full_resolution.job_id,
            newer.job_id,
        )
        self.assertEqual(application.pending_job_ids, ())

    def test_malformed_reference_preserves_last_valid_rendered_values(self) -> None:
        application = PrototypeApplication()
        application.dispatch_action("load-synthetic", {})
        application.dispatch_action("request-preview", {})
        preview_id = application.current.submitted_job_id.value
        application.dispatch_action("run-job", {"job-id": str(preview_id)})
        before = application.current.snapshot

        application.dispatch_action("malformed-reference", {})
        after = application.current

        self.assertEqual(after.command_status, CommandStatus.REJECTED)
        self.assertEqual(after.diagnostic_code, "REFERENCE_STRUCTURE_INVALID")
        self.assertIs(after.snapshot.reference, before.reference)
        self.assertIs(after.snapshot.transformation, before.transformation)
        self.assertIs(after.snapshot.preview, before.preview)

    def test_full_render_reads_current_once_and_exposes_accessible_state(self) -> None:
        application = PrototypeApplication()
        application.dispatch_action("load-synthetic", {})
        application.dispatch_action(
            "declare-contexts",
            expected_basis_fields(application),
        )
        application.dispatch_action("request-preview", {})
        preview_id = application.current.submitted_job_id.value
        application.dispatch_action("run-job", {"job-id": str(preview_id)})
        application.dispatch_action("inspect-canonical", {})
        canonical_id = application.current.submitted_job_id.value
        application.dispatch_action("run-job", {"job-id": str(canonical_id)})
        application.dispatch_action("malformed-reference", {})
        probe = CountingRenderApplication(application)

        rendered = render_page(probe).decode("utf-8")

        self.assertEqual(probe.current_reads, 1)
        self.assertIn("DISPOSABLE INTERNAL TEST UI — NOT PRODUCT UI", rendered)
        self.assertIn('data-testid="snapshot-revisions"', rendered)
        self.assertIn('data-testid="color-contexts"', rendered)
        self.assertIn('data-testid="command-diagnostic"', rendered)
        self.assertIn("REFERENCE_STRUCTURE_INVALID", rendered)
        self.assertIn("diagnostic visualization", rendered)
        self.assertIn("provisional-unmanaged", rendered)
        self.assertIn('data-testid="canonical-artifact"', rendered)
        self.assertIn("blocked-pending-explicit-color-contexts", rendered)
        self.assertIn("Pixel byte count", rendered)
        self.assertIn("Bounded byte prefix", rendered)

    def test_loopback_server_serves_forms_and_shuts_down_without_sleeps(self) -> None:
        application = PrototypeApplication()
        server = create_server(application, port=0)
        barrier = threading.Barrier(2)

        def serve() -> None:
            barrier.wait()
            server.serve_forever(poll_interval=0.01)

        server_thread = threading.Thread(target=serve)
        server_thread.start()
        barrier.wait()
        try:
            with urlopen(server_url(server), timeout=5) as response:
                initial = response.read()
                self.assertEqual(response.status, 200)
                self.assertIsNone(response.headers.get("Set-Cookie"))
            self.assertIn(b"DISPOSABLE INTERNAL TEST UI", initial)

            request = Request(
                server_url(server) + "action",
                data=urlencode({"action": "load-synthetic"}).encode("ascii"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                rendered = response.read()
                self.assertEqual(response.status, 200)
            self.assertIn(b'data-testid="reference-metadata"', rendered)
            self.assertIn(b'data-testid="transformation-metadata"', rendered)
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=5)
        self.assertFalse(server_thread.is_alive())

    def test_prototype_imports_no_private_engine_harness_testing_or_toolkit(
        self,
    ) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        package_root = repository_root / "internal_test_ui_prototype"
        sources = tuple(sorted(package_root.glob("*.py")))
        self.assertEqual(
            tuple(source.name for source in sources),
            (
                "__init__.py",
                "__main__.py",
                "_application.py",
                "_executor.py",
                "_http.py",
                "_synthetic.py",
            ),
        )
        forbidden_import_roots = {
            "AppKit",
            "PyQt5",
            "PyQt6",
            "PySide2",
            "PySide6",
            "objc",
            "portable_cube_harness",
            "tkinter",
        }

        for source_path in sources:
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
            self.assertTrue(forbidden_import_roots.isdisjoint(imported_roots))
            self.assertNotIn("ControlledExecutor", source)
            self.assertNotIn("colorluthier_engine.testing", source)


if __name__ == "__main__":
    unittest.main()
