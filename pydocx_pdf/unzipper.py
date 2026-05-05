"""
DOCX archive extraction.

A ``.docx`` file is a ZIP archive that follows the Office Open XML (OOXML)
specification.  This module opens the archive, reads the well-known XML
parts that the converter needs, and collects any embedded media (images)
into a flat filename -> bytes dictionary.

The :func:`unzip_docx` function is the single entry point used by
:class:`~pydocx_pdf.parser.document.DocumentParser`.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field


@dataclass
class DocxParts:
    """Raw byte contents extracted from a ``.docx`` ZIP archive.

    Each attribute holds the UTF-8 encoded XML for the corresponding
    OOXML part, or ``b""`` if the part is absent (all parts except
    ``document_xml`` are optional).

    Attributes
    ----------
    document_xml:
        ``word/document.xml`` -- the main document body (required).  Contains
        all paragraphs, tables, and inline drawing references.
    styles_xml:
        ``word/styles.xml`` -- named paragraph/character styles and document
        defaults.  Absent in minimal documents generated programmatically.
    numbering_xml:
        ``word/numbering.xml`` -- list definitions (abstract and concrete
        numbering).  Absent when the document has no lists.
    relationships_xml:
        ``word/_rels/document.xml.rels`` -- maps relationship IDs (rId) to
        targets such as image files.  Absent when there are no relationships.
    theme_xml:
        ``word/theme/theme1.xml`` -- colour and font scheme.  Used to resolve
        theme-font references (e.g. ``w:asciiTheme="minorHAnsi"``).
    media:
        A mapping of bare filename -> raw bytes for every file found under
        ``word/media/``.  Keyed by filename only (e.g. ``"image1.png"``),
        not by the full ZIP path.
    """

    document_xml: bytes = b""
    styles_xml: bytes = b""
    numbering_xml: bytes = b""
    relationships_xml: bytes = b""
    theme_xml: bytes = b""
    # filename (basename only) -> raw image bytes
    media: dict[str, bytes] = field(default_factory=dict)


def unzip_docx(data: bytes) -> DocxParts:
    """Open a DOCX byte string and return its constituent XML parts.

    Parameters
    ----------
    data:
        The raw bytes of a ``.docx`` file.  This is the content you would
        get from ``Path("file.docx").read_bytes()``.

    Returns
    -------
    DocxParts
        Populated dataclass with the extracted XML and media bytes.

    Raises
    ------
    zipfile.BadZipFile
        If *data* is not a valid ZIP archive (i.e. not a real DOCX file).
    KeyError
        If ``word/document.xml`` is missing from the archive.  A valid DOCX
        file must always contain this part.

    Notes
    -----
    All optional parts (styles, numbering, relationships, theme) are read
    silently as empty bytes when absent -- the parser and renderer handle
    the missing-data case gracefully with sensible defaults.

    Image files under ``word/media/`` are collected regardless of extension
    (.png, .jpg, .gif, .emf, etc.) and stored by basename.  The renderer
    passes them to Pillow / fpdf2 which determines the format from the
    raw bytes, not the extension.
    """
    parts = DocxParts()

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())

        def _read(path: str) -> bytes:
            """Read *path* from the archive, returning b"" if absent."""
            return zf.read(path) if path in names else b""

        # word/document.xml is mandatory; missing -> KeyError propagates.
        parts.document_xml = zf.read("word/document.xml")

        # Optional parts -- missing is normal for minimal / generated documents.
        parts.styles_xml = _read("word/styles.xml")
        parts.numbering_xml = _read("word/numbering.xml")
        parts.relationships_xml = _read("word/_rels/document.xml.rels")
        parts.theme_xml = _read("word/theme/theme1.xml")

        # Collect all embedded media (images, EMFs, etc.).
        for name in names:
            if name.startswith("word/media/"):
                fname = name.split("/")[-1]
                parts.media[fname] = zf.read(name)

    return parts
