"""
Top-level document model.

The :class:`Document` dataclass is the root of the in-memory representation
produced by :class:`~pydocx_pdf.parser.document.DocumentParser` and consumed
by :class:`~pydocx_pdf.renderer.pdf_writer.PDFWriter`.

A ``Document`` is essentially a flat, ordered sequence of *blocks* -- either
:class:`~pydocx_pdf.models.paragraph.Paragraph` or
:class:`~pydocx_pdf.models.table.Table` objects -- mirroring the linear
structure of ``word/document.xml``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from pydocx_pdf.models.paragraph import Paragraph
from pydocx_pdf.models.table import Table

# Union type representing any top-level content block in a document.
# Used as the element type for Document.blocks.
Block = Union[Paragraph, Table]


@dataclass
class Document:
    """In-memory representation of a parsed DOCX document.

    Produced by :class:`~pydocx_pdf.parser.document.DocumentParser` and
    passed to :class:`~pydocx_pdf.renderer.pdf_writer.PDFWriter` for
    rendering.

    Attributes
    ----------
    blocks:
        Ordered list of top-level content blocks.  Each element is either a
        :class:`~pydocx_pdf.models.paragraph.Paragraph` (text, headings,
        list items) or a :class:`~pydocx_pdf.models.table.Table`.  The order
        matches the document body element order in ``word/document.xml``.
    """

    blocks: list[Block] = field(default_factory=list)
