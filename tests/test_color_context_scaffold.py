from __future__ import annotations

import hashlib
import io
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, asdict, fields
from typing import get_args

import colorluthier_engine as engine
from colorluthier_engine import (
    CancelJob,
    ColorContextUnknownReason,
    ColorContextsSnapshot,
    ColorDocument,
    ColorManagementLane,
    ConfigureColorTransformation,
    ContentIdentity,
    DeclareColorContexts,
    DisplayColorContext,
    DocumentCommand,
    EncodingIdentity,
    ExportColorContext,
    HostFormatProfileIdentity,
    IccColorContextIdentity,
    Interpolation,
    KnownColorContext,
    LoadPortableCube,
    OpenReferenceImage,
    OcioAcesColorContextIdentity,
    ProofColorContext,
    ProvisionalImageFormat,
    ReferenceImageSnapshot,
    RequestCanonicalPortableCubeExport,
    RequestPreview,
    RgbBounds,
    SourceColorContext,
    UnknownColorContext,
    WorkingColorContext,
)
from colorluthier_engine.__main__ import _emit


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
    return ContentIdentity(sha256=digit * 64)


def encoding_identity(identifier: str, digit: str) -> EncodingIdentity:
    return EncodingIdentity(
        identifier=identifier,
        specification=content_identity(digit),
    )


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
        encoding=encoding_identity("rgb-values-v1", encoding_digit),
    )


class ColorContextScaffoldTest(unittest.TestCase):
    def test_initial_snapshot_is_inspection_first(self) -> None:
        snapshot = ColorDocument().snapshot()

        self.assertIsNone(snapshot.color_contexts.selected_lane)
        self.assertTrue(snapshot.color_contexts.inspection_only)
        self.assertEqual(
            snapshot.color_contexts.working,
            WorkingColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_DECLARED)
            ),
        )
        self.assertIsNone(snapshot.color_contexts.proof)
        self.assertIsNone(snapshot.color_contexts.display)

    def test_open_reference_publishes_explicit_unknown_source_context(self) -> None:
        document = ColorDocument()

        result = document.apply(
            OpenReferenceImage(
                encoded=b"P6\n1 1\n255\n" + bytes((64, 128, 192)),
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )

        reference = result.snapshot.reference
        self.assertIsNotNone(reference)
        self.assertEqual(
            reference.source_color_context,
            SourceColorContext(
                UnknownColorContext(
                    ColorContextUnknownReason.SOURCE_METADATA_MISSING
                )
            ),
        )
        self.assertEqual(reference.source_color_context_status, "unknown")
        self.assertEqual(
            reference.interpretation_status,
            "provisional-inspection-only",
        )

    def test_reference_legacy_fields_remain_constructible_and_serializable(
        self,
    ) -> None:
        reference = ReferenceImageSnapshot(
            revision=engine.DocumentRevision(1),
            encoded_sha256="a" * 64,
            width=1,
            height=1,
            image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            source_color_context_status="unknown",
            interpretation_status="provisional-inspection-only",
        )

        serialized = asdict(reference)
        self.assertEqual(serialized["source_color_context_status"], "unknown")
        self.assertEqual(
            serialized["interpretation_status"],
            "provisional-inspection-only",
        )
        self.assertIn("source_color_context", serialized)

        with self.assertRaises(ValueError):
            ReferenceImageSnapshot(
                revision=engine.DocumentRevision(1),
                encoded_sha256="a" * 64,
                width=1,
                height=1,
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
                source_color_context_status="known",
            )

    def test_public_color_context_value_objects_are_frozen(self) -> None:
        profile = content_identity("a")
        encoding = encoding_identity("rgb-values-v1", "b")
        unknown = UnknownColorContext(ColorContextUnknownReason.NOT_AVAILABLE)
        known = KnownColorContext(
            ColorManagementLane.ICC,
            IccColorContextIdentity(profile),
            encoding,
        )
        bounds = RgbBounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        host_profile = HostFormatProfileIdentity(
            "portable-cube",
            "1",
            content_identity("c"),
        )
        export = ExportColorContext(
            input_context=known,
            output_context=known,
            numeric_domain=bounds,
            numeric_range=bounds,
            interpolation=Interpolation.TETRAHEDRAL,
            profile=host_profile,
        )
        instances = (
            profile,
            encoding,
            unknown,
            known,
            SourceColorContext(unknown),
            WorkingColorContext(unknown),
            ProofColorContext(known),
            DisplayColorContext(known, content_identity("d")),
            bounds,
            host_profile,
            export,
            ColorDocument().snapshot().color_contexts,
        )

        for instance in instances:
            with self.subTest(type=type(instance).__name__):
                field = fields(instance)[0]
                with self.assertRaises(FrozenInstanceError):
                    setattr(instance, field.name, getattr(instance, field.name))

    def test_identity_encoding_host_profile_and_bounds_validate(self) -> None:
        specification = content_identity("d")
        self.assertEqual(
            EncodingIdentity("rgb-values-v1", specification).specification,
            specification,
        )
        self.assertEqual(
            HostFormatProfileIdentity(
                "portable-cube",
                "1",
                specification,
            ).specification,
            specification,
        )
        self.assertEqual(
            RgbBounds((0.0, -0.5, 0.25), (1.0, 1.5, 2.0)).maximum,
            (1.0, 1.5, 2.0),
        )

        invalid_digests = ("", "a" * 63, "g" * 64, "A" * 64)
        for digest in invalid_digests:
            with self.subTest(digest=digest):
                with self.assertRaises(ValueError):
                    ContentIdentity(digest)

        with self.assertRaises(ValueError):
            EncodingIdentity("", specification)
        with self.assertRaises(ValueError):
            HostFormatProfileIdentity("", "1", specification)
        with self.assertRaises(ValueError):
            HostFormatProfileIdentity("portable-cube", "", specification)

        invalid_bounds = (
            ((0.0, 0.0), (1.0, 1.0, 1.0)),
            ((0.0, 0.0, 0.0), (1.0, 1.0)),
            ((0.0, 0.0, 0.0), (0.0, 1.0, 1.0)),
            ((0.0, math.nan, 0.0), (1.0, 1.0, 1.0)),
            ((0.0, 0.0, 0.0), (1.0, math.inf, 1.0)),
        )
        for minimum, maximum in invalid_bounds:
            with self.subTest(minimum=minimum, maximum=maximum):
                with self.assertRaises(ValueError):
                    RgbBounds(minimum, maximum)

    def test_lane_specific_identity_and_display_interpretation_are_required(
        self,
    ) -> None:
        encoding = encoding_identity("rgb-values-v1", "a")
        icc_identity = IccColorContextIdentity(content_identity("b"))
        ocio_identity = OcioAcesColorContextIdentity(
            content_identity("c"),
            "ACEScg",
        )
        icc = KnownColorContext(
            ColorManagementLane.ICC,
            icc_identity,
            encoding,
        )

        self.assertEqual(
            KnownColorContext(
                ColorManagementLane.OCIO_ACES,
                ocio_identity,
                encoding,
            ).identity.exact_color_space,
            "ACEScg",
        )
        with self.assertRaises(ValueError):
            KnownColorContext(
                ColorManagementLane.ICC,
                ocio_identity,
                encoding,
            )
        with self.assertRaises(ValueError):
            KnownColorContext(
                ColorManagementLane.OCIO_ACES,
                icc_identity,
                encoding,
            )
        with self.assertRaises(ValueError):
            OcioAcesColorContextIdentity(content_identity("d"), "")

        viewing = content_identity("e")
        self.assertEqual(
            DisplayColorContext(icc, viewing).viewing_interpretation,
            viewing,
        )
        with self.assertRaises(ValueError):
            DisplayColorContext(icc)
        with self.assertRaises(ValueError):
            DisplayColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_AVAILABLE),
                viewing,
            )

    def test_export_color_context_is_valid_for_one_lane_only(self) -> None:
        source = known_context(
            ColorManagementLane.ICC,
            identity_digit="1",
            encoding_digit="2",
        )
        output = known_context(
            ColorManagementLane.ICC,
            identity_digit="3",
            encoding_digit="4",
        )
        bounds = RgbBounds((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        profile = HostFormatProfileIdentity(
            "portable-cube",
            "1",
            content_identity("5"),
        )

        export = ExportColorContext(
            input_context=source,
            output_context=output,
            numeric_domain=bounds,
            numeric_range=bounds,
            interpolation=Interpolation.TRILINEAR,
            profile=profile,
        )

        self.assertEqual(export.input_context.lane, ColorManagementLane.ICC)
        self.assertEqual(export.output_context.lane, ColorManagementLane.ICC)
        self.assertEqual(
            tuple(field.name for field in fields(ExportColorContext)),
            (
                "input_context",
                "output_context",
                "numeric_domain",
                "numeric_range",
                "interpolation",
                "profile",
            ),
        )
        self.assertFalse(hasattr(export, "proof"))
        self.assertFalse(hasattr(export, "display"))

        ocio_output = known_context(
            ColorManagementLane.OCIO_ACES,
            identity_digit="6",
            encoding_digit="7",
        )
        with self.assertRaises(ValueError):
            ExportColorContext(
                input_context=source,
                output_context=ocio_output,
                numeric_domain=bounds,
                numeric_range=bounds,
                interpolation=Interpolation.TRILINEAR,
                profile=profile,
            )

    def test_color_context_snapshot_rejects_incoherent_lane(self) -> None:
        legacy_unknown = ColorContextsSnapshot(
            selected_lane=None,
            working=WorkingColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_AVAILABLE)
            ),
            proof=ProofColorContext(
                UnknownColorContext(ColorContextUnknownReason.NOT_AVAILABLE)
            ),
            display=None,
        )
        self.assertIsNone(legacy_unknown.selected_lane)

        ocio_working = WorkingColorContext(
            known_context(
                ColorManagementLane.OCIO_ACES,
                identity_digit="8",
                encoding_digit="9",
            )
        )

        with self.assertRaises(ValueError):
            ColorContextsSnapshot(
                selected_lane=ColorManagementLane.ICC,
                working=ocio_working,
                proof=None,
                display=None,
            )

        with self.assertRaises(ValueError):
            ColorContextsSnapshot(
                selected_lane=None,
                working=ocio_working,
                proof=None,
                display=None,
            )

        coherent = ColorContextsSnapshot(
            selected_lane=ColorManagementLane.OCIO_ACES,
            working=ocio_working,
            proof=None,
            display=None,
        )
        self.assertTrue(coherent.inspection_only)
        self.assertNotIn(
            "inspection_only",
            tuple(field.name for field in fields(ColorContextsSnapshot)),
        )

    def test_gate4b_adds_only_declaration_and_canonical_flow_remains_blocked(
        self,
    ) -> None:
        self.assertIs(engine.DeclareColorContexts, DeclareColorContexts)
        self.assertFalse(hasattr(engine, "ConfigureColorContexts"))
        self.assertEqual(
            {command.__name__ for command in get_args(DocumentCommand)},
            {
                OpenReferenceImage.__name__,
                LoadPortableCube.__name__,
                ConfigureColorTransformation.__name__,
                DeclareColorContexts.__name__,
                RequestPreview.__name__,
                RequestCanonicalPortableCubeExport.__name__,
                CancelJob.__name__,
            },
        )

        document = ColorDocument()
        document.apply(
            LoadPortableCube(
                encoded=IDENTITY_CUBE,
                interpolation=Interpolation.TETRAHEDRAL,
            )
        )
        document.apply(RequestCanonicalPortableCubeExport())

        artifact = document.snapshot().canonical_cube_export
        self.assertIsNotNone(artifact)
        self.assertEqual(
            artifact.ordinary_export_status,
            "blocked-pending-explicit-color-contexts",
        )

    def test_cli_emit_bypasses_windows_newline_translation(self) -> None:
        encoded = io.BytesIO()
        stream = io.TextIOWrapper(
            encoded,
            encoding="ascii",
            newline="\r\n",
            write_through=True,
        )

        _emit({"ok": True}, stream=stream)

        self.assertEqual(encoded.getvalue(), b'{"ok":true}\n')

        text_only_stream = io.StringIO()
        _emit({"ok": True}, stream=text_only_stream)
        self.assertEqual(text_only_stream.getvalue(), '{"ok":true}\n')

    def test_legacy_headless_smoke_remains_byte_identical(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            reference = temporary_root / "reference.ppm"
            artifact = temporary_root / "canonical.cube"
            reference.write_bytes(
                b"P6\n1 1\n255\n" + bytes((64, 128, 192))
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "colorluthier_engine",
                    "--reference",
                    str(reference),
                    "--cube",
                    "tests/fixtures/identity-2/input.cube",
                    "--interpolation",
                    "tetrahedral",
                    "--export-output",
                    str(artifact),
                ],
                cwd=repository_root,
                env=environment,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            self.assertEqual(len(result.stdout), 837)
            self.assertEqual(
                hashlib.sha256(result.stdout).hexdigest(),
                "bbe13ab9256575ba6c2cb2759a3710225ac2d20e91eb6f95ea003fc7ec04f0a2",
            )
            artifact_bytes = artifact.read_bytes()
            self.assertEqual(len(artifact_bytes), 62)
            self.assertEqual(
                hashlib.sha256(artifact_bytes).hexdigest(),
                "c8bce4299c8606d5ca59a4724f46e484e430c42d506cfc2a3f30bbe84d5199cc",
            )


if __name__ == "__main__":
    unittest.main()
