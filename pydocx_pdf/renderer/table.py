"""
Render a Table model onto an FPDF page.

Features
--------
- Column widths from w:tblGrid; equal split fallback.
- Per-cell background fills (w:shd).
- Individual border lines per edge with colour/width (w:tblBorders / w:tcBorders),
  with a sensible default when the document carries no explicit border info.
- Vertical alignment: top / center / bottom (w:vAlign).
- Vertical cell merges (w:vMerge): restart cells span multiple row heights;
  continuation cells are skipped entirely.
- Horizontal spans (w:gridSpan) carried by TableCell.col_span.
- Nested tables (recursive).
- Temporary margin overrides so ParagraphRenderer sees the correct usable
  width for each cell.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from fpdf import FPDF

from pydocx_pdf.models.paragraph import Paragraph
from pydocx_pdf.models.table import (
    BorderDef, Table, TableCell, TableProps, TableRow,
)
from pydocx_pdf.renderer.paragraph import (
    ParagraphRenderer, _DEFAULT_FONT, _DEFAULT_SIZE_PT, _HEADING_SIZES,
)

_PT_TO_MM   = 1 / 2.8346456692913385
_MIN_LINE_H = _DEFAULT_SIZE_PT * _PT_TO_MM * 1.4
_MIN_PAD_MM = 1.0

# Used when the document has no explicit border info
_DEFAULT_BORDER = BorderDef(style="single", width_pt=0.5, color_hex="000000")


class TableRenderer:
    def __init__(self, pdf: FPDF, para_renderer: ParagraphRenderer) -> None:
        self._pdf  = pdf
        self._para = para_renderer

    # ------------------------------------------------------------------ public

    def render(self, table: Table) -> None:
        if not table.rows:
            return

        pdf        = self._pdf
        usable_w   = pdf.w - pdf.l_margin - pdf.r_margin
        col_widths = self._resolve_col_widths(table, usable_w)
        if not col_widths:
            return

        num_cols     = len(col_widths)
        num_rows     = len(table.rows)
        row_heights  = self._compute_row_heights(table, col_widths)
        vmerge_spans = self._compute_vmerge_spans(table)

        current_y = pdf.get_y()

        for row_idx, row in enumerate(table.rows):
            row_h   = row_heights[row_idx]
            row_y   = current_y
            x       = pdf.l_margin
            col_idx = 0

            for cell in row.cells:
                span   = cell.col_span
                cell_w = sum(col_widths[col_idx : col_idx + span])

                if cell.vmerge == "continue":
                    col_idx += span
                    x       += cell_w
                    continue

                if cell.vmerge == "restart":
                    n_span = vmerge_spans.get((row_idx, col_idx), 1)
                    cell_h = sum(row_heights[row_idx : row_idx + n_span])
                    last_merged = row_idx + n_span - 1
                else:
                    cell_h      = row_h
                    last_merged = row_idx

                is_top    = row_idx == 0
                is_left   = col_idx == 0
                is_right  = (col_idx + span) >= num_cols
                is_bottom = last_merged >= (num_rows - 1)

                self._render_cell(
                    cell=cell,
                    x=x, y=row_y,
                    cell_w=cell_w, cell_h=cell_h,
                    is_top=is_top, is_bottom=is_bottom,
                    is_left=is_left, is_right=is_right,
                    table_props=table.props,
                )

                x       += cell_w
                col_idx += span

            current_y += row_h
            pdf.set_y(current_y)

        pdf.ln(4)

    # ------------------------------------------------------- column resolution

    def _resolve_col_widths(self, table: Table, usable_w: float) -> List[float]:
        if table.col_widths_twips:
            total = sum(table.col_widths_twips)
            if total > 0:
                return [(w / total) * usable_w for w in table.col_widths_twips]
        col_count = (
            max(sum(c.col_span for c in row.cells) for row in table.rows)
            if table.rows else 1
        )
        return [usable_w / col_count] * col_count

    # -------------------------------------------------- row-height precompute

    def _compute_row_heights(
        self, table: Table, col_widths: List[float]
    ) -> List[float]:
        heights: List[float] = []
        for row in table.rows:
            row_h   = _MIN_LINE_H
            col_idx = 0
            for cell in row.cells:
                span   = cell.col_span
                cell_w = sum(col_widths[col_idx : col_idx + span])
                col_idx += span
                if cell.vmerge == "continue":
                    continue
                row_h = max(row_h, self._measure_cell(cell, cell_w))
            heights.append(row_h)
        return heights

    # ---------------------------------------------------- vmerge span mapping

    def _compute_vmerge_spans(
        self, table: Table
    ) -> Dict[Tuple[int, int], int]:
        col_starts_per_row: List[List[int]] = []
        for row in table.rows:
            positions: List[int] = []
            col = 0
            for cell in row.cells:
                positions.append(col)
                col += cell.col_span
            col_starts_per_row.append(positions)

        spans: Dict[Tuple[int, int], int] = {}
        for row_idx, row in enumerate(table.rows):
            for cell_pos, cell in enumerate(row.cells):
                if cell.vmerge != "restart":
                    continue
                col_start   = col_starts_per_row[row_idx][cell_pos]
                span_count  = 1
                for nri in range(row_idx + 1, len(table.rows)):
                    found = False
                    nc = 0
                    for nc_cell in table.rows[nri].cells:
                        if nc == col_start:
                            if nc_cell.vmerge == "continue":
                                span_count += 1
                                found = True
                            break
                        nc += nc_cell.col_span
                    if not found:
                        break
                spans[(row_idx, col_start)] = span_count
        return spans

    # ----------------------------------------------------------- cell drawing

    def _render_cell(
        self,
        cell: TableCell,
        x: float, y: float,
        cell_w: float, cell_h: float,
        is_top: bool, is_bottom: bool,
        is_left: bool, is_right: bool,
        table_props: TableProps,
    ) -> None:
        pdf   = self._pdf
        props = cell.props

        # Background fill
        if props.bg_color_hex:
            try:
                r = int(props.bg_color_hex[0:2], 16)
                g = int(props.bg_color_hex[2:4], 16)
                b = int(props.bg_color_hex[4:6], 16)
                pdf.set_fill_color(r, g, b)
                pdf.rect(x, y, cell_w, cell_h, style="F")
            except (ValueError, IndexError):
                pass

        # Borders
        self._draw_cell_borders(
            cell=cell,
            x=x, y=y, w=cell_w, h=cell_h,
            is_top=is_top, is_bottom=is_bottom,
            is_left=is_left, is_right=is_right,
            table_props=table_props,
        )

        # Content padding: cell-level overrides table-level; enforce minimum
        def _pad(cell_val: float, tbl_val: float) -> float:
            eff = cell_val if cell_val > 0.0 else tbl_val
            return max(eff * _PT_TO_MM, _MIN_PAD_MM)

        pad_left   = _pad(props.pad_left_pt,   table_props.cell_pad_left_pt)
        pad_right  = _pad(props.pad_right_pt,  table_props.cell_pad_right_pt)
        pad_top    = _pad(props.pad_top_pt,    table_props.cell_pad_top_pt)
        pad_bottom = _pad(props.pad_bottom_pt, table_props.cell_pad_bottom_pt)

        content_w = cell_w - pad_left - pad_right
        if content_w <= 0.5:
            return

        content_x = x + pad_left

        # Vertical alignment
        content_h = self._measure_cell_content(cell, content_w)
        inner_h   = cell_h - pad_top - pad_bottom
        if props.v_align == "center":
            y_offset = max(0.0, (inner_h - content_h) / 2.0)
        elif props.v_align == "bottom":
            y_offset = max(0.0, inner_h - content_h)
        else:
            y_offset = 0.0

        content_y = y + pad_top + y_offset

        # Render blocks with overridden margins so ParagraphRenderer uses
        # the cell content width as its baseline.
        old_lm = pdf.l_margin
        old_rm = pdf.r_margin
        pdf.set_left_margin(content_x)
        pdf.set_right_margin(pdf.w - content_x - content_w)
        pdf.set_xy(content_x, content_y)
        try:
            for block in cell.blocks:
                if isinstance(block, Paragraph):
                    self._para.render(block)
                elif isinstance(block, Table):
                    self.render(block)
        finally:
            pdf.set_left_margin(old_lm)
            pdf.set_right_margin(old_rm)

    # ---------------------------------------------------------- border drawing

    def _draw_cell_borders(
        self,
        cell: TableCell,
        x: float, y: float, w: float, h: float,
        is_top: bool, is_bottom: bool,
        is_left: bool, is_right: bool,
        table_props: TableProps,
    ) -> None:
        use_default = not table_props.has_border_info

        def resolve(
            cell_b: Optional[BorderDef],
            outer_b: Optional[BorderDef],
            inner_b: Optional[BorderDef],
            edge_is_outer: bool,
        ) -> Optional[BorderDef]:
            if cell_b is not None:
                return cell_b
            tbl_b = outer_b if edge_is_outer else inner_b
            if tbl_b is not None:
                return tbl_b
            return _DEFAULT_BORDER if use_default else None

        cb = cell.props.borders
        top_b    = resolve(cb.top,    table_props.border_top,    table_props.border_inside_h, is_top)
        bottom_b = resolve(cb.bottom, table_props.border_bottom, table_props.border_inside_h, is_bottom)
        left_b   = resolve(cb.left,   table_props.border_left,   table_props.border_inside_v, is_left)
        right_b  = resolve(cb.right,  table_props.border_right,  table_props.border_inside_v, is_right)

        self._draw_line(x,     y,     x + w, y,     top_b)
        self._draw_line(x,     y + h, x + w, y + h, bottom_b)
        self._draw_line(x,     y,     x,     y + h, left_b)
        self._draw_line(x + w, y,     x + w, y + h, right_b)

    def _draw_line(
        self,
        x1: float, y1: float,
        x2: float, y2: float,
        border: Optional[BorderDef],
    ) -> None:
        if border is None or not border.is_visible:
            return
        pdf = self._pdf
        try:
            r = int(border.color_hex[0:2], 16)
            g = int(border.color_hex[2:4], 16)
            b = int(border.color_hex[4:6], 16)
        except (ValueError, IndexError):
            r, g, b = 0, 0, 0
        pdf.set_draw_color(r, g, b)
        pdf.set_line_width(max(border.width_pt * _PT_TO_MM, 0.1))
        pdf.line(x1, y1, x2, y2)

    # --------------------------------------------------------- height helpers

    def _measure_cell(self, cell: TableCell, cell_w: float) -> float:
        pad_mm   = _MIN_PAD_MM * 2
        inner_w  = max(cell_w - pad_mm * 2, 1.0)
        total_h  = pad_mm * 2
        for block in cell.blocks:
            if isinstance(block, Paragraph):
                total_h += self._measure_paragraph(block, inner_w)
            else:
                total_h += _MIN_LINE_H
        return max(total_h, _MIN_LINE_H + pad_mm * 2)

    def _measure_cell_content(self, cell: TableCell, content_w: float) -> float:
        total_h = 0.0
        for block in cell.blocks:
            if isinstance(block, Paragraph):
                total_h += self._measure_paragraph(block, content_w)
            else:
                total_h += _MIN_LINE_H
        return max(total_h, _MIN_LINE_H)

    def _measure_paragraph(self, para: Paragraph, width_mm: float) -> float:
        pdf = self._pdf

        heading_size = _HEADING_SIZES.get(para.style_id)
        if heading_size is not None:
            size_pt = heading_size
        elif para.runs:
            size_pt = para.runs[0].font_size_pt or _DEFAULT_SIZE_PT
        else:
            size_pt = _DEFAULT_SIZE_PT

        line_h = size_pt * _PT_TO_MM * 1.4
        text   = para.full_text or " "

        if para.is_list_item:
            from pydocx_pdf.utils import twips_to_pt
            hanging_mm = twips_to_pt(para.list_hanging_twips) * _PT_TO_MM
            width_mm   = max(width_mm - hanging_mm, 1.0)

        try:
            pdf.set_font(_DEFAULT_FONT, size=size_pt)
            lines = pdf.multi_cell(
                w=width_mm, h=line_h, text=text,
                dry_run=True, output="LINES",
            )
            return max(1, len(lines)) * line_h
        except Exception:
            return line_h
