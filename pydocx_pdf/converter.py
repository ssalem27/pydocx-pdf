"""
Top-level conversion entry points for pydocx-pdf.

This module provides two public functions:

- :func:`convert` -- synchronous, suitable for scripts, CLI tools, and
  synchronous web frameworks (Flask, Django, etc.).
- :func:`convert_async` -- async wrapper that offloads the blocking I/O and
  CPU work to a thread-pool executor, suitable for FastAPI, aiohttp, etc.

Both functions accept the same flexible *source* argument (file path, raw
bytes, or a ``BytesIO`` buffer) and write an optional output file while
always returning the PDF bytes directly.

Example usage
-------------
>>> from pydocx_pdf import convert
>>> # Convert a file on disk
>>> convert("report.docx", "report.pdf")

>>> # Convert from bytes (e.g. from a database blob or HTTP upload)
>>> pdf_bytes = convert(docx_bytes)

>>> # Supply a custom font directory bundled with your Docker image
>>> convert("report.docx", "report.pdf", font_dir="/app/fonts")

>>> # Async usage (FastAPI / aiohttp)
>>> import asyncio
>>> asyncio.run(convert_async("report.docx", "report.pdf"))
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Union

from pydocx_pdf.exceptions import ConversionError
from pydocx_pdf.parser.document import DocumentParser
from pydocx_pdf.parser.theme import parse_theme
from pydocx_pdf.renderer.pdf_writer import PDFWriter
from pydocx_pdf.unzipper import unzip_docx

# ---------------------------------------------------------------------------
# Public type alias -- re-exported from __init__.py
# ---------------------------------------------------------------------------

DocxInput = Union[str, Path, bytes, io.BytesIO]
"""Accepted types for the *source* argument of :func:`convert`.

- ``str`` / ``pathlib.Path`` -- path to a ``.docx`` file on disk.
- ``bytes`` -- raw DOCX file contents already loaded into memory.
- ``io.BytesIO`` -- seekable byte-stream wrapping DOCX data.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert(
    source: DocxInput,
    dest: str | Path | None = None,
    *,
    font_dir: str | Path | None = None,
) -> bytes:
    """Convert a ``.docx`` document to PDF.

    The conversion is fully in-process: no subprocesses, no network calls,
    no system font dependencies.  All bundled fonts (Liberation + DejaVu)
    are loaded from inside the package wheel.

    Parameters
    ----------
    source:
        The DOCX to convert.  Accepts:

        - A ``str`` or :class:`pathlib.Path` file path -- the file is read
          from disk.
        - ``bytes`` -- raw DOCX data already in memory (e.g. from a database
          or HTTP upload).
        - :class:`io.BytesIO` -- a seekable byte-stream containing DOCX data.

    dest:
        Optional output path (``str`` or :class:`pathlib.Path`).  When
        provided the PDF bytes are written to this file **and** returned.
        When omitted only the bytes are returned and nothing is written to
        disk.

    font_dir:
        Optional path to a directory containing extra ``.ttf`` font files.
        Every ``.ttf`` in the directory is registered with fpdf2 under the
        font's stem name (e.g. ``MyFont-Bold.ttf`` -> family ``"MyFont-Bold"``).
        Use this to ship proprietary or specialised fonts alongside your
        application without modifying the package.

    Returns
    -------
    bytes
        The rendered PDF as a byte string.  Always starts with ``b"%PDF-"``.

    Raises
    ------
    FileNotFoundError
        If *source* is a path and the file does not exist.
    TypeError
        If *source* is not a ``str``, ``Path``, ``bytes``, or ``BytesIO``.
    ConversionError
        If the DOCX cannot be parsed or the PDF cannot be rendered.  The
        original exception is chained as ``__cause__``.

    Examples
    --------
    >>> convert("report.docx", "report.pdf")
    b'%PDF-...'

    >>> with open("report.docx", "rb") as fh:
    ...     pdf = convert(fh.read())
    >>> pdf[:5]
    b'%PDF-'
    """
    # FileNotFoundError and TypeError are caller errors -- let them propagate
    # unmodified so callers can distinguish them from conversion failures.
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
    dest: str | Path | None = None,
    *,
    font_dir: str | Path | None = None,
) -> bytes:
    """Async wrapper around :func:`convert` -- runs in a thread-pool executor.

    Because :func:`convert` does CPU-bound XML parsing and PDF rendering it
    would block an async event loop if awaited directly.  This wrapper
    offloads the work to :func:`asyncio.get_running_loop`'s default executor
    (a :class:`~concurrent.futures.ThreadPoolExecutor`) so the event loop
    remains responsive.

    Parameters
    ----------
    source:
        Same as :func:`convert`.
    dest:
        Same as :func:`convert`.
    font_dir:
        Same as :func:`convert`.

    Returns
    -------
    bytes
        The rendered PDF bytes -- same semantics as :func:`convert`.

    Raises
    ------
    FileNotFoundError
        If *source* is a path that does not exist.
    TypeError
        If *source* is an unsupported type.
    ConversionError
        If the conversion fails.

    Examples
    --------
    >>> import asyncio
    >>> asyncio.run(convert_async("report.docx", "report.pdf"))
    b'%PDF-...'
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: convert(source, dest, font_dir=font_dir),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_source(source: DocxInput) -> bytes:
    """Normalise *source* to raw ``bytes``.

    Parameters
    ----------
    source:
        A file path (``str`` / ``Path``), raw ``bytes``, or ``BytesIO``.

    Returns
    -------
    bytes
        The raw DOCX data.

    Raises
    ------
    FileNotFoundError
        If *source* is a path that does not exist on disk.
    TypeError
        If *source* is none of the accepted types.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"No such file: {path}")
        return path.read_bytes()
    if isinstance(source, io.BytesIO):
        return source.getvalue()
    if isinstance(source, bytes):
        return source
    raise TypeError(
        f"source must be a str, Path, bytes, or BytesIO; got {type(source).__name__}"
    )
