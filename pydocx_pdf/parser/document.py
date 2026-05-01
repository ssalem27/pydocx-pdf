"""
Walk word/document.xml and emit a list of model objects.

The parser produces a flat list of Block objects (paragraphs, tables, images)
that the renderer consumes sequentially -- no layout decisions here.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List, Optional

from pydocx_pdf.models.document import Document
from pydocx_pdf.models.paragraph import Paragraph, Run
from pydocx_pdf.models.table import Table, TableRow, TableCell
from pydocx_pdf.models.image import Image
from pydocx_pdf.parser.numbering import NumberingParser
from pydocx_pdf.parser.relationships import RelationshipsParser
from pydocx_pdf.parser.styles import StylesParser, _parse_rpr
from pydocx_pdf.unzipper import DocxParts
from pydocx_pdf.utils import NS, get_attr, parse_xml, qn, half_pt_to_pt, twips_to_pt, emu_to_pt


class DocumentParser:
    def __init__(self, parts: DocxParts) -> None:
        self._parts = parts
        self._styles = StylesParser(parts.styles_xml)
        self._numbering = NumberingParser(parts.numbering_xml)
        self._rels = RelationshipsParser(parts.relationships_xml)

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
            # w:sectPr (section properties) -- skip for now

        return Document(blocks=blocks)

    # -- paragraph -------------------------------------------------------------

    def _parse_paragraph(self, p_el: ET.Element) -> Paragraph:
        # Style reference
        style_id = "Normal"
        ppr = p_el.find(qn("w:pPr"))
        num_id: Optional[str] = None
        ilvl: int = 0

        if ppr is not None:
            ps = ppr.find(qn("w:pStyle"))
            if ps is not None:
                style_id = ps.get(qn("w:val"), "Normal")

            # List membership
            num_pr = ppr.find(qn("w:numPr"))
            if num_pr is not None:
                nid_el = num_pr.find(qn("w:numId"))
                ilvl_el = num_pr.find(qn("w:ilvl"))
                if nid_el is not None:
                    num_id = nid_el.get(qn("w:val"))
                if ilvl_el is not None:
                    ilvl = int(ilvl_el.get(qn("w:val"), "0"))

        style_props = self._styles.get(style_id)
        runs = self._parse_runs(p_el)

        list_counter: Optional[int] = None
        if num_id:
            list_counter = self._numbering.next_count(num_id, ilvl)

        return Paragraph(
            style_id=style_id,
            style_props=style_props,
            runs=runs,
            num_id=num_id,
            ilvl=ilvl,
            list_counter=list_counter,
        )

    def _parse_runs(self, p_el: ET.Element) -> List[Run]:
        runs = []
        for r_el in p_el.findall(qn("w:r")):
            text = "".join(
                t.text or "" for t in r_el.findall(qn("w:t"))
            )
            rpr = r_el.find(qn("w:rPr"))
            run_props = {}
            if rpr is not None:
                run_props = _parse_rpr(rpr)

            runs.append(Run(text=text, props=run_props))

            # Check for inline image (w:drawing inside w:r)
            for drawing in r_el.findall(qn("w:drawing")):
                img = self._extract_image(drawing)
                if img:
                    runs.append(Run(text="", props={}, image=img))

        return runs

    # -- table -----------------------------------------------------------------

    def _parse_table(self, tbl_el: ET.Element) -> Table:
        # Extract column widths from w:tblGrid
        col_widths_twips: List[int] = []
        tbl_grid = tbl_el.find(qn("w:tblGrid"))
        if tbl_grid is not None:
            for grid_col in tbl_grid.findall(qn("w:gridCol")):
                w_val = grid_col.get(qn("w:w"))
                if w_val is not None:
                    try:
                        col_widths_twips.append(int(w_val))
                    except ValueError:
                        pass

        rows = []
        for tr_el in tbl_el.findall(qn("w:tr")):
            cells = []
            for tc_el in tr_el.findall(qn("w:tc")):
                # Extract col_span from w:tcPr/w:gridSpan
                col_span = 1
                tc_pr = tc_el.find(qn("w:tcPr"))
                if tc_pr is not None:
                    grid_span = tc_pr.find(qn("w:gridSpan"))
                    if grid_span is not None:
                        try:
                            col_span = int(grid_span.get(qn("w:val"), "1"))
                        except ValueError:
                            pass

                cell_blocks = []
                for child in tc_el:
                    if child.tag == qn("w:p"):
                        cell_blocks.append(self._parse_paragraph(child))
                    elif child.tag == qn("w:tbl"):
                        cell_blocks.append(self._parse_table(child))
                cells.append(TableCell(blocks=cell_blocks, col_span=col_span))
            rows.append(TableRow(cells=cells))
        return Table(rows=rows, col_widths_twips=col_widths_twips)

    # -- image -----------------------------------------------------------------

    def _extract_image(self, drawing_el: ET.Element) -> Optional[Image]:
        # Look for a:blip with r:embed attribute
        blip = drawing_el.find(f".//{{{NS['a']}}}blip")
        if blip is None:
            return None
        r_id = blip.get(f"{{{NS['r']}}}embed")
        if not r_id:
            return None
        target = self._rels.resolve(r_id)
        if not target:
            return None
        # Strip the "media/" prefix to match the key in DocxParts.media
        fname = target.split("/")[-1]
        data = self._parts.media.get(fname)
        if data is None:
            return None

        # Try to get dimensions from wp:extent
        width_emu = height_emu = 0
        extent = drawing_el.find(f".//{{{NS['wp']}}}extent")
        if extent is not None:
            cx = extent.get("cx")
            cy = extent.get("cy")
            if cx:
                width_emu = int(cx)
            if cy:
                height_emu = int(cy)

        return Image(
            filename=fname,
            data=data,
            width_pt=emu_to_pt(width_emu) if width_emu else None,
            height_pt=emu_to_pt(height_emu) if height_emu else None,
        )
