"""
Top-level conversion entry points.
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Union

from pydocx_pdf.exceptions import ConversionError
from pydocx_pdf.parser.document import DocumentParser
from pydocx_pdf.parser.theme import parse_theme
from pydocx_pdf.renderer.pdf_writer import PDFWriter
from pydocx_pdf.unzipper import unzip_docx


DocxInput = Union[str, Path, bytes, io.BytesIO]


def convert(
    source: DocxInput,
    dest: Union[str, Path, None] = None,
    *,
    font_dir: Union[str, Path, None] = None,
) -> bytes:
    """Convert a .docx file or bytes to PDF.

    FileNotFoundError and TypeError propagate as-is (caller errors).
    ConversionError is raised for parse/render failures.
    """
    # Let FileNotFoundError and TypeError propagate -- they are caller errors.
    docx_bytes = _load_source(source)

    try:
        parts = unzip_docx(docx_bytes)
        theme = parse_theme(parts.theme_xml)
        doc = DocumentParser(parts).parse()
        writer = PDFWriter(font_dir=font_dir)
        pdf_bytes = writer.render(doc, theme=theme)
    except Exception as exc:
        raise ConversionError(str(exc)) from exc

    if dest is not None:
        Path(dest).write_bytes(pdf_bytes)

    return pdf_bytes


async def convert_async(
    source: DocxInput,
    dest: Union[str, Path, None] = None,
    *,
    font_dir: Union[str, Path, None] = None,
) -> bytes:
    """Async wrapper around :func:`convert` -- runs in a thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: convert(source, dest, font_dir=font_dir),
    )


# helpers

def _load_source(source: DocxInput) -> bytes:
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"No such file: {path}")
        return path.read_bytes()
    if isinstance(source, io.BytesIO):
        return source.getvalue()
    if isinstance(source, bytes):
        return source
    raise TypeError(f"Unsupported source type: {type(source)}")
