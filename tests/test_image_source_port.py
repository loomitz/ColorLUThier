from __future__ import annotations

import hashlib
import unittest

from colorluthier_engine import (
    ColorDocument,
    CommandStatus,
    OpenReferenceImage,
    ProvisionalImageFormat,
)
from colorluthier_engine._image_source import DecodedImage


class _FailAfterFirstImageSource:
    def __init__(self) -> None:
        self.calls: list[tuple[bytes, ProvisionalImageFormat]] = []

    def decode(
        self,
        encoded: bytes,
        image_format: ProvisionalImageFormat,
        /,
    ) -> DecodedImage:
        self.calls.append((encoded, image_format))
        if len(self.calls) > 1:
            raise RuntimeError("adapter-private failure detail")
        return DecodedImage(width=1, height=1, pixels_rgb8=b"\x0c\x22\x38")


class ImageSourcePortTest(unittest.TestCase):
    def test_injected_source_is_transactional(self) -> None:
        source = _FailAfterFirstImageSource()
        document = ColorDocument(image_source=source)
        first_payload = b"opaque synthetic payload one"

        opened = document.apply(
            OpenReferenceImage(
                encoded=first_payload,
                image_format=ProvisionalImageFormat.PPM_P6_RGB8,
            )
        )

        self.assertEqual(opened.status, CommandStatus.COMMITTED)
        self.assertEqual(
            opened.snapshot.reference.encoded_sha256,
            hashlib.sha256(first_payload).hexdigest(),
        )
        self.assertEqual(
            source.calls,
            [(first_payload, ProvisionalImageFormat.PPM_P6_RGB8)],
        )

        last_valid = document.snapshot()
        rejected = document.apply(
            OpenReferenceImage(
                encoded=b"opaque synthetic payload two",
                image_format=ProvisionalImageFormat.PNG_RGB8,
            )
        )

        self.assertEqual(rejected.status, CommandStatus.REJECTED)
        self.assertEqual(rejected.diagnostic.code, "IMAGE_SOURCE_FAILED")
        self.assertNotIn("adapter-private", rejected.diagnostic.message)
        self.assertEqual(rejected.snapshot, last_valid)
        self.assertEqual(document.snapshot(), last_valid)


if __name__ == "__main__":
    unittest.main()
