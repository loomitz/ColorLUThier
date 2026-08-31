"""Narrow image-source port and provisional stdlib adapter.

The port is intentionally internal to the functional vertical.  It separates
``ColorDocument`` from concrete image codecs without defining the stable image
source and color-management contract tracked outside issue #49.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ._limits import REFERENCE_MAX_DIMENSION, REFERENCE_MAX_PIXELS
from ._reference import ReferenceImageError, decode_reference_image
from .model import ProvisionalImageFormat


DiagnosticValue = int | str
DiagnosticContext = tuple[tuple[str, DiagnosticValue], ...]


@dataclass(frozen=True, slots=True)
class DecodedImage:
    """Immutable RGB8 pixels returned across the internal image-source port."""

    width: int
    height: int
    pixels_rgb8: bytes

    def __post_init__(self) -> None:
        if (
            type(self.width) is not int
            or not 1 <= self.width <= REFERENCE_MAX_DIMENSION
        ):
            raise ValueError("Decoded image width is outside the accepted range.")
        if (
            type(self.height) is not int
            or not 1 <= self.height <= REFERENCE_MAX_DIMENSION
        ):
            raise ValueError("Decoded image height is outside the accepted range.")
        pixel_count = self.width * self.height
        if pixel_count > REFERENCE_MAX_PIXELS:
            raise ValueError("Decoded image pixel count exceeds the accepted limit.")
        if type(self.pixels_rgb8) is not bytes:
            raise TypeError("Decoded image pixels must be immutable bytes.")
        if len(self.pixels_rgb8) != pixel_count * 3:
            raise ValueError("Decoded image pixels do not match its dimensions.")


class ImageSourceError(ValueError):
    """Stable diagnostic raised by an image-source adapter."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        reason: str,
        context: DiagnosticContext = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.reason = reason
        self.context = context


class ImageSource(Protocol):
    """Decode one immutable payload in its explicitly declared format.

    Implementations must be deterministic and must use ``ImageSourceError``
    only for bounded, payload-free diagnostics.
    """

    def decode(
        self,
        encoded: bytes,
        image_format: ProvisionalImageFormat,
        /,
    ) -> DecodedImage:
        """Return bounded RGB8 pixels or raise ``ImageSourceError``."""


class StdlibImageSource:
    """Provisional bounded PPM/PNG adapter implemented with the stdlib."""

    def decode(
        self,
        encoded: bytes,
        image_format: ProvisionalImageFormat,
        /,
    ) -> DecodedImage:
        try:
            decoded = decode_reference_image(encoded, image_format.value)
        except ReferenceImageError as error:
            raise ImageSourceError(
                str(error),
                code=error.code,
                reason=error.reason,
                context=error.context,
            ) from None
        return DecodedImage(
            width=decoded.width,
            height=decoded.height,
            pixels_rgb8=decoded.pixels_rgb8,
        )
