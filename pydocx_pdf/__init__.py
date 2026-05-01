"""
pydocx-pdf — Zero-dependency DOCX → PDF converter for containerized environments.

Usage:
    from pydocx_pdf import convert

    # File paths
    convert("input.docx", "output.pdf")

    # Bytes in, bytes out
    pdf_bytes = convert(docx_bytes)

    # Async
    await convert_async("input.docx", "output.pdf")
"""

from pydocx_pdf.converter import convert, convert_async

__all__ = ["convert", "convert_async"]
__version__ = "0.1.0"
