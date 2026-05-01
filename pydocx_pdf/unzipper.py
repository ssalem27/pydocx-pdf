"""
Unzip a .docx (ZIP) archive and return its parts as raw bytes.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class DocxParts:
    """Raw byte contents of the relevant files inside a .docx archive."""

    document_xml: bytes = b""
    styles_xml: bytes = b""
    numbering_xml: bytes = b""
    relationships_xml: bytes = b""
    theme_xml: bytes = b""
    # filename → bytes for all images in word/media/
    media: Dict[str, bytes] = field(default_factory=dict)


def unzip_docx(data: bytes) -> DocxParts:
    """Unzip *data* and return a :class:`DocxParts` instance.

    Raises:
        zipfile.BadZipFile: If *data* is not a valid ZIP archive.
        KeyError: If ``word/document.xml`` is missing.
    """
    parts = DocxParts()

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())

        def _read(path: str) -> bytes:
            return zf.read(path) if path in names else b""

        parts.document_xml = zf.read("word/document.xml")  # required
        parts.styles_xml = _read("word/styles.xml")
        parts.numbering_xml = _read("word/numbering.xml")
        parts.relationships_xml = _read("word/_rels/document.xml.rels")
        parts.theme_xml = _read("word/theme/theme1.xml")

        # Extract all media files (images)
        for name in names:
            if name.startswith("word/media/"):
                fname = name.split("/")[-1]
                parts.media[fname] = zf.read(name)

    return parts
