"""
Render a Table model onto an FPDF page.

Column widths are read from w:tblGrid (if available via the model).
Colspan is honoured via w:gridSpan. Rowspan is tracked but rendering
is simplified to repeated cell borders rather than true merged cells.
"""

from __future__ import annotations

from fpdf import FPDF

from pydocx_pdf.models.paragraph import Paragraph
from pydocx_pdf.models.table import Table, TableRow, TableCell
from pydocx_pdf.renderer.paragraph import ParagraphRenderer, _DEFAULT_FONT, _DEFAULT_SIZE_PT

_PT_TO_MM = 1 / 2.8346456692913385
_CELL_PAD_MM = 1.5   # padding inside each cell
_MIN_LINE_H = _DEFAULT_SIZE_PT * _PT_TO_MM * 1.4


class TableRenderer:
    def __init__(
        self,
        pdf: FPDF,
        para_renderer: ParagraphRenderer,
    ) -> None:
        self._pdf = pdf
        self._para = para_renderer

    def render(self, table: Table) -> None:
        if not table.rows:
            return

        pdf = self._pdf
        usable_w = pdf.w - pdf.l_margin - pdf.r_margin

        # Resolve column widths
        col_widths = self._resolve_col_widths(table, usable_w)
        if not col_widths:
            return

        for row in table.rows:
            self._render_row(row, col_widths)

        pdf.ln(4)

    # -------------------------------------------------------------------------

    def _resolve_col_widths(
        self, table: Table, usable_w: float
    ) -> list[float]:
        """Return a list of column widths in mm.

        Prefers explicit grid widths from the model; falls back to equal split.
        """
        # Use explicit widths if the table carries them
        if table.col_widths_twips:
            total_twips = sum(table.col_widths_twips)
            if total_twips > 0:
                return [
                    (w / total_twips) * usable_w
                    for w in table.col_widths_twips
                ]

        # Fall back: count max columns across all rows
        col_count = max(
            sum(c.col_span for c in row.cells)
            for row in table.rows
        ) if table.rows else 1

        return [usable_w / col_count] * col_count

    def _render_row(self, row: TableRow, col_widths: list[float]) -> None:
        pdf = self._pdf
        row_y = pdf.get_y()
        x = pdf.l_margin

        # First pass: measure each cell height
        cell_heights: list[float] = []
        col_idx = 0
        for cell in row.cells:
            span = cell.col_span
            cell_w = sum(col_widths[col_idx : col_idx + span])
            col_idx += span
            cell_heights.append(self._measure_cell(cell, cell_w))

        row_h = max(cell_heights) if cell_heights else _MIN_LINE_H

        # Second pass: draw borders and render content
        col_idx = 0
        for i, cell in enumerate(row.cells):
            span = cell.col_span
            cell_w = sum(col_widths[col_idx : col_idx + span])
            col_idx += span

            # Border
            pdf.rect(x, row_y, cell_w, row_h)

            # Content
            pdf.set_xy(x + _CELL_PAD_MM, row_y + _CELL_PAD_MM)
            for block in cell.blocks:
                if isinstance(block, Paragraph):
                    self._para.render(block)
                elif isinstance(block, Table):
                    # Nested table: recurse (simplified, no nested width calc)
                    self.render(block)

            x += cell_w

        pdf.set_y(row_y + row_h)

    def _measure_cell(self, cell: TableCell, cell_w: float) -> float:
        """Estimate the height needed to render *cell* in *cell_w* mm."""
        pdf = self._pdf
        total_h = _CELL_PAD_MM * 2

        for block in cell.blocks:
            if not isinstance(block, Paragraph):
                total_h += _MIN_LINE_H
                continue

            text = block.full_text or " "
            pdf.set_font(_DEFAULT_FONT, size=_DEFAULT_SIZE_PT)
            line_h = _MIN_LINE_H
            inner_w = cell_w - _CELL_PAD_MM * 2

            try:
                lines = pdf.multi_cell(
                    w=inner_w,
                    h=line_h,
                    text=text,
                    dry_run=True,
                    output="LINES",
                )
                total_h += max(1, len(lines)) * line_h
            except Exception:
                total_h += line_h

        return max(total_h, _MIN_LINE_H + _CELL_PAD_MM * 2)
