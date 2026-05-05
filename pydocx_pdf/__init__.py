"""
pydocx-pdf -- Zero-dependency DOCX to PDF converter for containerised environments.

This package converts Microsoft Word documents (.docx) to PDF entirely in
Python -- no LibreOffice, no Pandoc, no system fonts, no network calls.  It
is designed for use in EKS pods, Docker containers, and other headless
environments where installing native dependencies is impractical or forbidden.

Quick start
-----------
>>> from pydocx_pdf import convert
>>>
>>> # File paths
>>> convert("report.docx", "report.pdf")
>>>
>>> # Raw bytes -> raw bytes (ideal for web handlers / Lambda / FastAPI)
>>> with open("report.docx", "rb") as fh:
...     pdf_bytes = convert(fh.read())
>>>
>>> # Custom font directory (place .ttf files there; no network required)
>>> convert("report.docx", "report.pdf", font_dir="/app/fonts")
>>>
>>> # Async (runs convert() in a thread-pool executor)
>>> import asyncio
>>> asyncio.run(convert_async("report.docx", "report.pdf"))

Exported names
--------------
convert         -- synchronous conversion entry point
convert_async   -- async wrapper around convert()
DocxInput       -- type alias for accepted source types
ConversionError -- raised when the DOCX cannot be parsed or rendered
PydocxPdfError  -- base class for all library exceptions
__version__     -- current package version string
"""

from pydocx_pdf.converter import DocxInput, convert, convert_async
from pydocx_pdf.exceptions import ConversionError, PydocxPdfError

__all__ = [
    "convert",
    "convert_async",
    "DocxInput",
    "ConversionError",
    "PydocxPdfError",
]

__version__ = "0.1.0"
