"""
Image model for inline images embedded in DOCX documents.

Images are referenced in ``word/document.xml`` via ``<w:drawing>`` elements
and stored as binary files under ``word/media/`` inside the DOCX ZIP.  The
:class:`Image` dataclass carries the raw bytes and the intended display
dimensions extracted from the ``<wp:extent>`` element.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Image:
    """An inline image extracted from a DOCX ``<w:drawing>`` element.

    Attributes
    ----------
    filename:
        The bare filename of the image inside the DOCX archive's
        ``word/media/`` directory (e.g. ``"image1.png"``).  Used for
        identification and debugging; the renderer uses :attr:`data` directly.
    data:
        Raw image bytes as stored in the archive.  The format (PNG, JPEG,
        GIF, etc.) is determined from the bytes themselves by Pillow / fpdf2,
        not from the filename extension.
    width_pt:
        Intended display width in points, converted from the EMU value in
        ``<wp:extent cx="..."/>``.  ``None`` if no extent was specified in the
        XML (the renderer falls back to a default width of 50 mm).
    height_pt:
        Intended display height in points, converted from the EMU value in
        ``<wp:extent cy="..."/>``.  ``None`` if no extent was specified (fpdf2
        will scale the height proportionally to the width).
    """

    filename: str
    data: bytes
    width_pt: float | None = None
    height_pt: float | None = None
