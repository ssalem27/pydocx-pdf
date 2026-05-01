"""
Top-level PDF renderer.

Owns the fpdf2 FPDF instance and delegates to sub-renderers for paragraphs,
tables, and images.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Optional, Union

from fpdf import FPDF

from pydocx_pdf.models.document import Block, Document
from pydocx_pdf.models.paragraph import Paragraph
from pydocx_pdf.models.table import Table
from pydocx_pdf.renderer.paragraph import ParagraphRenderer
from pydocx_pdf.renderer.table import TableRenderer


# A4 page in mm
PAGE_W_MM = 210.0
PAGE_H_MM = 297.0
MARGIN_MM = 20.0


class PDFWriter:
    def __init__(self, font_dir: Union[str, Path, None] = None) -> None:
        self._font_dir = Path(font_dir) if font_dir else None

    def render(self, doc: Document) -> bytes:
        pdf = self._create_pdf()
        para_renderer = ParagraphRenderer(pdf)
        table_renderer = TableRenderer(pdf, para_renderer)

        for block in doc.blocks:
            if isinstance(block, Paragraph):
                para_renderer.render(block)
            elif isinstance(block, Table):
                table_renderer.render(block)

        return pdf.output()

    def _create_pdf(self) -> FPDF:
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
        pdf.set_auto_page_break(auto=True, margin=MARGIN_MM)
        pdf.add_page()

        # Register fonts if font_dir was provided
        if self._font_dir and self._font_dir.is_dir():
            for ttf in self._font_dir.glob("*.ttf"):
                pdf.add_font(ttf.stem, fname=str(ttf))

        # Fall back to built-in Helvetica
        pdf.set_font("Helvetica", size=11)

        return pdf
