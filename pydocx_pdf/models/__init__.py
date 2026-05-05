"""
Data model classes produced by the parser and consumed by the renderer.

These classes form the intermediate representation between the DOCX XML
parsing phase and the PDF rendering phase.  They are pure dataclasses with
no dependency on fpdf2 or any XML library -- making them straightforward
to inspect, test, or extend.

Public classes
--------------
Document        -- root container, holds an ordered list of Block objects
Paragraph       -- a single paragraph with merged style props and Run list
Run             -- a formatting run (text fragment + character properties)
Image           -- an inline image with display dimensions
Table           -- a parsed <w:tbl> element
TableRow        -- a single row within a table
TableCell       -- a single cell with content, span, and style props
TableProps      -- table-wide border, padding, and alignment defaults
TableCellProps  -- per-cell border, padding, background, and alignment
BorderDef       -- a single border edge (style, width, colour)
CellBorders     -- the four edge borders for one cell
"""

from pydocx_pdf.models.document import Block, Document
from pydocx_pdf.models.image import Image
from pydocx_pdf.models.paragraph import Paragraph, Run
from pydocx_pdf.models.table import (
    BorderDef,
    CellBorders,
    Table,
    TableCell,
    TableCellProps,
    TableProps,
    TableRow,
)

__all__ = [
    "Document",
    "Block",
    "Image",
    "Paragraph",
    "Run",
    "Table",
    "TableRow",
    "TableCell",
    "TableProps",
    "TableCellProps",
    "BorderDef",
    "CellBorders",
]
