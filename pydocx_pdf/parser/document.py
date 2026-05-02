"""
Walk word/document.xml and emit a list of model objects.

Produces a flat list of Block objects (paragraphs, tables) that the renderer
consumes sequentially -- no layout decisions here.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from pydocx_pdf.models.document import Document
from pydocx_pdf.models.paragraph import Paragraph, Run
from pydocx_pdf.models.table import (
    BorderDef, CellBorders, Table, TableCell, TableCellProps,
    TableProps, TableRow,
)
from pydocx_pdf.models.image import Image
from pydocx_pdf.parser.numbering import NumberingParser
from pydocx_pdf.parser.relationships import RelationshipsParser
from pydocx_pdf.parser.styles import StylesParser, _parse_ppr, _parse_rpr
from pydocx_pdf.unzipper import DocxParts
from pydocx_pdf.utils import (
    NS, get_attr, parse_xml, qn,
    half_pt_to_pt, twips_to_pt, emu_to_pt,
)


class DocumentParser:
    def __init__(self, parts: DocxParts) -> None:
        self._parts    = parts
        self._styles   = StylesParser(parts.styles_xml)
        self._numbering = NumberingParser(parts.numbering_xml)
        self._rels     = RelationshipsParser(parts.relationships_xml)

    def parse(self) -> Document:
        root = parse_xml(self._parts.document_xml)
        body = root.find(f"{{{NS['w']}}}body")
        if body is None:
            raise ValueError("document.xml has no <w:body>")

        blocks = []
        for child in body:
            tag = child.tag
            if tag == qn("w:p"):
                blocks.append(self._parse_paragraph(child))
            elif tag == qn("w:tbl"):
                blocks.append(self._parse_table(child))

        return Document(blocks=blocks)

    # ---------------------------------------------------------------- paragraph

    def _parse_paragraph(self, p_el: ET.Element) -> Paragraph:
        style_id = "Normal"
        num_id: Optional[str] = None
        ilvl: int = 0

        ppr = p_el.find(qn("w:pPr"))
        if ppr is not None:
            ps = ppr.find(qn("w:pStyle"))
            if ps is not None:
                style_id = ps.get(qn("w:val"), "Normal")

            num_pr = ppr.find(qn("w:numPr"))
            if num_pr is not None:
                nid_el  = num_pr.find(qn("w:numId"))
                ilvl_el = num_pr.find(qn("w:ilvl"))
                if nid_el is not None:
                    num_id = nid_el.get(qn("w:val"))
                    if num_id == "0":      # numId=0 means "remove numbering"
                        num_id = None
                if ilvl_el is not None:
                    ilvl = int(ilvl_el.get(qn("w:val"), "0"))

        # Start from the named style, then overlay any inline paragraph overrides.
        # (A paragraph can directly set spacing, alignment, indent, etc. without
        # referencing a different style — those values live in its own w:pPr.)
        style_props = dict(self._styles.get(style_id))
        if ppr is not None:
            inline_ppr = _parse_ppr(ppr)
            inline_ppr.pop("_basedOn", None)
            style_props.update(inline_ppr)

        runs = self._parse_runs(p_el)

        # List fields
        list_counter: Optional[int] = None
        list_label:   Optional[str] = None
        list_indent_twips:  int = 720
        list_hanging_twips: int = 360

        if num_id:
            list_counter = self._numbering.next_count(num_id, ilvl)
            list_label   = self._numbering.format_marker(num_id, ilvl)
            level_def    = self._numbering.get_level_def(num_id, ilvl)
            if level_def is not None:
                list_indent_twips  = level_def.indent_left_twips
                list_hanging_twips = level_def.hanging_twips
            else:
                list_indent_twips  = 720 * (ilvl + 1)
                list_hanging_twips = 360

        return Paragraph(
            style_id=style_id,
            style_props=style_props,
            runs=runs,
            num_id=num_id,
            ilvl=ilvl,
            list_counter=list_counter,
            list_label=list_label,
            list_indent_twips=list_indent_twips,
            list_hanging_twips=list_hanging_twips,
        )

    def _parse_runs(self, p_el: ET.Element) -> List[Run]:
        """Collect all Run objects from a paragraph element.

        Handles plain ``w:r`` runs, hyperlink wrappers (``w:hyperlink``),
        tracked-change insertions (``w:ins``), and silently skips deletions
        (``w:del``) and bookmarks.
        """
        runs: List[Run] = []
        for child in p_el:
            tag = child.tag
            if tag == qn("w:r"):
                runs.extend(self._parse_single_run(child))
            elif tag == qn("w:hyperlink"):
                # Runs inside a hyperlink render as underlined blue text.
                for r_el in child.findall(qn("w:r")):
                    hyp_runs = self._parse_single_run(r_el)
                    for r in hyp_runs:
                        if not r.image:
                            r.props.setdefault("underline", True)
                            r.props.setdefault("color", "2F5496")
                    runs.extend(hyp_runs)
            elif tag == qn("w:ins"):
                # Tracked insertion — include the text.
                for r_el in child.findall(qn("w:r")):
                    runs.extend(self._parse_single_run(r_el))
            # w:del, w:bookmarkStart, w:bookmarkEnd, w:proofErr → skip
        return runs

    def _parse_single_run(self, r_el: ET.Element) -> List[Run]:
        """Parse one ``w:r`` element into a list of Run objects.

        Usually returns a single Run, but may return more when the element
        contains a page-break marker (``w:br w:type='page'``) or an inline
        image (``w:drawing``), which need to be separate objects.
        """
        rpr = r_el.find(qn("w:rPr"))
        run_props: Dict = _parse_rpr(rpr) if rpr is not None else {}

        result: List[Run] = []
        text_buf: List[str] = []

        def _flush() -> None:
            if text_buf:
                result.append(Run(text="".join(text_buf), props=dict(run_props)))
                text_buf.clear()

        for child in r_el:
            tag = child.tag
            if tag == qn("w:t"):
                text_buf.append(child.text or "")
            elif tag == qn("w:tab"):
                text_buf.append("\t")
            elif tag == qn("w:br"):
                br_type = child.get(qn("w:type"), "textWrapping")
                if br_type == "page":
                    _flush()
                    result.append(Run(text="", props={**run_props, "page_break": True}))
                else:
                    # Column break, text-wrapping line break → inline newline.
                    text_buf.append("\n")
            elif tag == qn("w:drawing"):
                _flush()
                img = self._extract_image(child)
                if img:
                    result.append(Run(text="", props={}, image=img))
            # w:sym, w:fldChar, w:instrText, etc. → skip

        _flush()
        return result

    # ------------------------------------------------------------------- table

    def _parse_table(self, tbl_el: ET.Element) -> Table:
        col_widths_twips: List[int] = []
        tbl_grid = tbl_el.find(qn("w:tblGrid"))
        if tbl_grid is not None:
            for gc in tbl_grid.findall(qn("w:gridCol")):
                w_val = gc.get(qn("w:w"))
                if w_val is not None:
                    try:
                        col_widths_twips.append(int(w_val))
                    except ValueError:
                        pass

        tbl_pr      = tbl_el.find(qn("w:tblPr"))
        table_props = self._parse_table_props(tbl_pr)

        rows: List[TableRow] = [
            self._parse_row(tr_el)
            for tr_el in tbl_el.findall(qn("w:tr"))
        ]
        return Table(rows=rows, col_widths_twips=col_widths_twips, props=table_props)

    def _parse_row(self, tr_el: ET.Element) -> TableRow:
        is_header = False
        tr_pr = tr_el.find(qn("w:trPr"))
        if tr_pr is not None:
            is_header = tr_pr.find(qn("w:tblHeader")) is not None

        cells = [self._parse_cell(tc_el) for tc_el in tr_el.findall(qn("w:tc"))]
        return TableRow(cells=cells, is_header=is_header)

    def _parse_cell(self, tc_el: ET.Element) -> TableCell:
        col_span = 1
        vmerge   = ""
        tc_pr    = tc_el.find(qn("w:tcPr"))
        cell_props = TableCellProps()

        if tc_pr is not None:
            gs = tc_pr.find(qn("w:gridSpan"))
            if gs is not None:
                try:
                    col_span = int(gs.get(qn("w:val"), "1"))
                except ValueError:
                    pass

            vm = tc_pr.find(qn("w:vMerge"))
            if vm is not None:
                vmerge = "restart" if vm.get(qn("w:val"), "") == "restart" else "continue"

            cell_props = self._parse_cell_props(tc_pr)

        blocks = []
        for child in tc_el:
            if child.tag == qn("w:p"):
                blocks.append(self._parse_paragraph(child))
            elif child.tag == qn("w:tbl"):
                blocks.append(self._parse_table(child))

        return TableCell(blocks=blocks, col_span=col_span, vmerge=vmerge, props=cell_props)

    # --------------------------------------------------------- property parsers

    def _parse_table_props(self, tbl_pr: Optional[ET.Element]) -> TableProps:
        props = TableProps()
        if tbl_pr is None:
            return props

        jc = tbl_pr.find(qn("w:jc"))
        if jc is not None:
            props.alignment = jc.get(qn("w:val"), "left")

        borders_el = tbl_pr.find(qn("w:tblBorders"))
        if borders_el is not None:
            props.has_border_info  = True
            props.border_top       = _parse_border_el(borders_el.find(qn("w:top")))
            props.border_bottom    = _parse_border_el(borders_el.find(qn("w:bottom")))
            props.border_left      = _parse_border_el(borders_el.find(qn("w:left")))
            props.border_right     = _parse_border_el(borders_el.find(qn("w:right")))
            props.border_inside_h  = _parse_border_el(borders_el.find(qn("w:insideH")))
            props.border_inside_v  = _parse_border_el(borders_el.find(qn("w:insideV")))

        mar_el = tbl_pr.find(qn("w:tblCellMar"))
        if mar_el is not None:
            props.cell_pad_top_pt    = _parse_margin_pt(mar_el, "top")
            props.cell_pad_bottom_pt = _parse_margin_pt(mar_el, "bottom")
            props.cell_pad_left_pt   = _parse_margin_pt(mar_el, "left")
            props.cell_pad_right_pt  = _parse_margin_pt(mar_el, "right")

        return props

    def _parse_cell_props(self, tc_pr: ET.Element) -> TableCellProps:
        props = TableCellProps()

        shd = tc_pr.find(qn("w:shd"))
        if shd is not None:
            fill = shd.get(qn("w:fill"), "")
            if fill and fill.lower() not in ("auto", ""):
                props.bg_color_hex = fill.upper()

        va = tc_pr.find(qn("w:vAlign"))
        if va is not None:
            val = va.get(qn("w:val"), "top")
            props.v_align = "center" if val == "both" else val

        borders_el = tc_pr.find(qn("w:tcBorders"))
        if borders_el is not None:
            props.borders = CellBorders(
                top    = _parse_border_el(borders_el.find(qn("w:top"))),
                bottom = _parse_border_el(borders_el.find(qn("w:bottom"))),
                left   = _parse_border_el(borders_el.find(qn("w:left"))),
                right  = _parse_border_el(borders_el.find(qn("w:right"))),
            )

        mar_el = tc_pr.find(qn("w:tcMar"))
        if mar_el is not None:
            props.pad_top_pt    = _parse_margin_pt(mar_el, "top")
            props.pad_bottom_pt = _parse_margin_pt(mar_el, "bottom")
            props.pad_left_pt   = _parse_margin_pt(mar_el, "left")
            props.pad_right_pt  = _parse_margin_pt(mar_el, "right")

        return props

    # ------------------------------------------------------------------- image

    def _extract_image(self, drawing_el: ET.Element) -> Optional[Image]:
        blip = drawing_el.find(f".//{{{NS['a']}}}blip")
        if blip is None:
            return None
        r_id = blip.get(f"{{{NS['r']}}}embed")
        if not r_id:
            return None
        target = self._rels.resolve(r_id)
        if not target:
            return None
        fname = target.split("/")[-1]
        data  = self._parts.media.get(fname)
        if data is None:
            return None

        width_emu = height_emu = 0
        extent = drawing_el.find(f".//{{{NS['wp']}}}extent")
        if extent is not None:
            cx = extent.get("cx"); cy = extent.get("cy")
            if cx: width_emu  = int(cx)
            if cy: height_emu = int(cy)

        return Image(
            filename=fname,
            data=data,
            width_pt=emu_to_pt(width_emu)  if width_emu  else None,
            height_pt=emu_to_pt(height_emu) if height_emu else None,
        )


# ---------------------------------------------------------------------------
# Module-level XML helpers (also used by tests)
# ---------------------------------------------------------------------------

def _parse_border_el(el: Optional[ET.Element]) -> Optional[BorderDef]:
    """Parse one border element (e.g. w:top) into a BorderDef, or None."""
    if el is None:
        return None
    style = el.get(qn("w:val"), "single")
    if style in ("none", "nil"):
        return BorderDef(style=style, width_pt=0.0, color_hex="000000")
    try:
        sz = int(el.get(qn("w:sz"), "4"))
    except ValueError:
        sz = 4
    width_pt = max(sz / 8.0, 0.125)
    color    = el.get(qn("w:color"), "000000")
    if color.lower() in ("auto", ""):
        color = "000000"
    return BorderDef(style=style, width_pt=width_pt, color_hex=color.upper())


def _parse_margin_pt(mar_el: ET.Element, side: str) -> float:
    """Return the margin for *side* in points (from a tblCellMar/tcMar element)."""
    el = mar_el.find(qn(f"w:{side}"))
    if el is None:
        return 0.0
    w_type = el.get(qn("w:type"), "dxa")
    try:
        val = int(el.get(qn("w:w"), "0"))
    except ValueError:
        return 0.0
    if w_type in ("dxa", ""):
        return twips_to_pt(val)
    return 0.0
