"""
Walk ``word/document.xml`` and emit an ordered list of model objects.

:class:`DocumentParser` is the top-level entry point for the parsing phase.
It orchestrates the subsidiary parsers (styles, numbering, relationships),
walks the ``<w:body>`` element, and produces a :class:`~pydocx_pdf.models.document.Document`
containing a flat, ordered sequence of :class:`~pydocx_pdf.models.paragraph.Paragraph`
and :class:`~pydocx_pdf.models.table.Table` objects.

No layout decisions are made here — that is the renderer's responsibility.
The parser's job is solely to extract structured data from the XML.

Parsing strategy
----------------
The body is iterated one child at a time:

- ``<w:p>`` (paragraph) → :meth:`DocumentParser._parse_paragraph`
- ``<w:tbl>`` (table)   → :meth:`DocumentParser._parse_table`
- Everything else is silently skipped (sectPr, bookmarks, etc.)

Within each paragraph, :meth:`_parse_runs` collects ``<w:r>`` runs while
transparently unwrapping ``<w:hyperlink>`` and ``<w:ins>`` (tracked-change
insertion) containers and skipping ``<w:del>`` deletions.
"""

from __future__ import annotations

import contextlib
import xml.etree.ElementTree as ET
from typing import Any

from pydocx_pdf.models.document import Document
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
from pydocx_pdf.parser.numbering import NumberingParser
from pydocx_pdf.parser.relationships import RelationshipsParser
from pydocx_pdf.parser.styles import StylesParser, _parse_ppr, _parse_rpr
from pydocx_pdf.unzipper import DocxParts
from pydocx_pdf.utils import (
    NS,
    parse_xml,
    qn,
)


class DocumentParser:
    """Parse the body of ``word/document.xml`` into the model layer.

    Parameters
    ----------
    parts:
        The :class:`~pydocx_pdf.unzipper.DocxParts` instance produced by
        :func:`~pydocx_pdf.unzipper.unzip_docx`.  All XML parts and media
        are accessed through this object.

    Examples
    --------
    >>> from pydocx_pdf.unzipper import unzip_docx
    >>> parts = unzip_docx(Path("report.docx").read_bytes())
    >>> doc = DocumentParser(parts).parse()
    >>> len(doc.blocks)
    42
    """

    def __init__(self, parts: DocxParts) -> None:
        self._parts     = parts
        self._styles    = StylesParser(parts.styles_xml)
        self._numbering = NumberingParser(parts.numbering_xml)
        self._rels      = RelationshipsParser(parts.relationships_xml)

    def parse(self) -> Document:
        """Parse the document body and return a :class:`~pydocx_pdf.models.document.Document`.

        Iterates over every direct child of ``<w:body>`` and converts
        ``<w:p>`` and ``<w:tbl>`` elements into model objects.  All other
        elements (``<w:sectPr>``, bookmarks, etc.) are silently ignored.

        Returns
        -------
        Document
            An ordered list of :class:`~pydocx_pdf.models.paragraph.Paragraph`
            and :class:`~pydocx_pdf.models.table.Table` objects.

        Raises
        ------
        ValueError
            If ``word/document.xml`` has no ``<w:body>`` element.
        """
        root = parse_xml(self._parts.document_xml)
        body = root.find(f"{{{NS['w']}}}body")
        if body is None:
            raise ValueError("document.xml has no <w:body>")

        blocks: list[Paragraph | Table] = []
        for child in body:
            tag = child.tag
            if tag == qn("w:p"):
                blocks.append(self._parse_paragraph(child))
            elif tag == qn("w:tbl"):
                blocks.append(self._parse_table(child))
            # w:sectPr, mc:AlternateContent, etc. → silently ignored

        return Document(blocks=blocks)

    # ------------------------------------------------------------------
    # Paragraph parsing
    # ------------------------------------------------------------------

    def _parse_paragraph(self, p_el: ET.Element) -> Paragraph:
        """Parse a single ``<w:p>`` element into a :class:`~pydocx_pdf.models.paragraph.Paragraph`.

        Resolution order for style properties:

        1. The named style (from ``<w:pStyle w:val="…"/>``) is resolved
           through the full inheritance chain by :class:`StylesParser`.
        2. Any inline ``<w:pPr>`` overrides on the paragraph element are
           merged on top (higher priority).

        Parameters
        ----------
        p_el:
            The ``<w:p>`` XML element.

        Returns
        -------
        Paragraph
            Fully populated with style props, runs, and list fields.
        """
        style_id = "Normal"
        num_id: str | None = None
        ilvl: int = 0

        ppr = p_el.find(qn("w:pPr"))
        if ppr is not None:
            # Explicit style reference
            ps = ppr.find(qn("w:pStyle"))
            if ps is not None:
                style_id = ps.get(qn("w:val"), "Normal")

            # Numbering / list membership
            num_pr = ppr.find(qn("w:numPr"))
            if num_pr is not None:
                nid_el  = num_pr.find(qn("w:numId"))
                ilvl_el = num_pr.find(qn("w:ilvl"))
                if nid_el is not None:
                    num_id = nid_el.get(qn("w:val"))
                    if num_id == "0":
                        # numId=0 explicitly removes list membership
                        num_id = None
                if ilvl_el is not None:
                    ilvl = int(ilvl_el.get(qn("w:val"), "0"))

        # Resolve the named style, then overlay inline pPr overrides.
        # A paragraph can set its own spacing/alignment/indent without
        # referencing a different style.
        style_props = dict(self._styles.get(style_id))
        if ppr is not None:
            inline_ppr = _parse_ppr(ppr)
            inline_ppr.pop("_basedOn", None)
            style_props.update(inline_ppr)

        runs = self._parse_runs(p_el)

        # ── List fields ──────────────────────────────────────────────────
        list_counter: int | None = None
        list_label:   str | None = None
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
                # Fallback: indent grows with nesting depth
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

    def _parse_runs(self, p_el: ET.Element) -> list[Run]:
        """Collect all :class:`~pydocx_pdf.models.paragraph.Run` objects from a paragraph element.

        Handles the following child element types:

        - ``<w:r>`` — plain run; parsed via :meth:`_parse_single_run`.
        - ``<w:hyperlink>`` — wrapper around one or more runs; the contained
          runs are styled as underlined blue text.
        - ``<w:ins>`` — tracked-change insertion; the contained runs are
          included as if they were plain runs.
        - ``<w:del>`` — tracked-change deletion; silently skipped (deleted
          text is not shown in the output).
        - All other elements (``<w:bookmarkStart>``, ``<w:proofErr>``, etc.)
          are silently skipped.

        Parameters
        ----------
        p_el:
            The ``<w:p>`` element whose children are to be collected.

        Returns
        -------
        list of Run
            Ordered list of runs forming the paragraph content.
        """
        runs: list[Run] = []
        for child in p_el:
            tag = child.tag
            if tag == qn("w:r"):
                runs.extend(self._parse_single_run(child))
            elif tag == qn("w:hyperlink"):
                # Contained runs rendered as underlined blue text (Word default)
                for r_el in child.findall(qn("w:r")):
                    hyp_runs = self._parse_single_run(r_el)
                    for r in hyp_runs:
                        if not r.image:
                            r.props.setdefault("underline", True)
                            r.props.setdefault("color", "2F5496")  # Word link blue
                    runs.extend(hyp_runs)
            elif tag == qn("w:ins"):
                # Accepted (inserted) tracked change — include its text
                for r_el in child.findall(qn("w:r")):
                    runs.extend(self._parse_single_run(r_el))
            # w:del, w:bookmarkStart, w:bookmarkEnd, w:proofErr → skip
        return runs

    def _parse_single_run(self, r_el: ET.Element) -> list[Run]:
        """Parse one ``<w:r>`` element into one or more :class:`~pydocx_pdf.models.paragraph.Run` objects.

        Usually returns a single :class:`Run`, but may return more when the
        element contains a page-break marker (``<w:br w:type="page"/>``) or
        an inline image (``<w:drawing>``), both of which require their own
        separate :class:`Run` objects so the renderer can handle them
        individually.

        Parameters
        ----------
        r_el:
            A ``<w:r>`` element from the document body.

        Returns
        -------
        list of Run
            Typically a single-element list.  Multiple elements are returned
            when a page break or image is interleaved with text content.
        """
        rpr = r_el.find(qn("w:rPr"))
        run_props: dict[str, Any] = _parse_rpr(rpr) if rpr is not None else {}

        result:   list[Run] = []
        text_buf: list[str] = []

        def _flush() -> None:
            """Emit a Run for any accumulated text, then clear the buffer."""
            if text_buf:
                result.append(Run(text="".join(text_buf), props=dict(run_props)))
                text_buf.clear()

        for child in r_el:
            tag = child.tag
            if tag == qn("w:t"):
                # Plain text node (xml:space="preserve" is handled by lxml/ET)
                text_buf.append(child.text or "")
            elif tag == qn("w:tab"):
                # Tab character — renderer converts to spaces
                text_buf.append("\t")
            elif tag == qn("w:br"):
                br_type = child.get(qn("w:type"), "textWrapping")
                if br_type == "page":
                    # Hard page break — flush text first, then emit a
                    # dedicated page-break Run that triggers pdf.add_page()
                    _flush()
                    result.append(Run(text="", props={**run_props, "page_break": True}))
                else:
                    # textWrapping / column break → inline line feed
                    text_buf.append("\n")
            elif tag == qn("w:drawing"):
                # Inline image — flush buffered text, then emit an image Run
                _flush()
                img = self._extract_image(child)
                if img:
                    result.append(Run(text="", props={}, image=img))
            # w:sym, w:fldChar, w:instrText, w:noBreakHyphen, etc. → skip

        _flush()
        return result

    # ------------------------------------------------------------------
    # Table parsing
    # ------------------------------------------------------------------

    def _parse_table(self, tbl_el: ET.Element) -> Table:
        """Parse a ``<w:tbl>`` element into a :class:`~pydocx_pdf.models.table.Table`.

        Parameters
        ----------
        tbl_el:
            The ``<w:tbl>`` XML element.

        Returns
        -------
        Table
            Fully populated with rows, column widths, and table properties.
        """
        # Extract column widths from the grid definition
        col_widths_twips: list[int] = []
        tbl_grid = tbl_el.find(qn("w:tblGrid"))
        if tbl_grid is not None:
            for gc in tbl_grid.findall(qn("w:gridCol")):
                w_val = gc.get(qn("w:w"))
                if w_val is not None:
                    with contextlib.suppress(ValueError):
                        col_widths_twips.append(int(w_val))

        tbl_pr      = tbl_el.find(qn("w:tblPr"))
        table_props = self._parse_table_props(tbl_pr)

        rows: list[TableRow] = [
            self._parse_row(tr_el)
            for tr_el in tbl_el.findall(qn("w:tr"))
        ]
        return Table(rows=rows, col_widths_twips=col_widths_twips, props=table_props)

    def _parse_row(self, tr_el: ET.Element) -> TableRow:
        """Parse a ``<w:tr>`` element into a :class:`~pydocx_pdf.models.table.TableRow`.

        Parameters
        ----------
        tr_el:
            The ``<w:tr>`` XML element.

        Returns
        -------
        TableRow
            Row with all cells parsed and the ``is_header`` flag set.
        """
        is_header = False
        tr_pr = tr_el.find(qn("w:trPr"))
        if tr_pr is not None:
            # <w:tblHeader/> marks this row as a repeating header row
            is_header = tr_pr.find(qn("w:tblHeader")) is not None

        cells = [self._parse_cell(tc_el) for tc_el in tr_el.findall(qn("w:tc"))]
        return TableRow(cells=cells, is_header=is_header)

    def _parse_cell(self, tc_el: ET.Element) -> TableCell:
        """Parse a ``<w:tc>`` element into a :class:`~pydocx_pdf.models.table.TableCell`.

        Parameters
        ----------
        tc_el:
            The ``<w:tc>`` XML element.

        Returns
        -------
        TableCell
            Cell with parsed blocks, span values, vmerge state, and props.
        """
        tc_pr = tc_el.find(qn("w:tcPr"))

        # ── Column span ─────────────────────────────────────────────────
        col_span = 1
        if tc_pr is not None:
            gs = tc_pr.find(qn("w:gridSpan"))
            if gs is not None:
                with contextlib.suppress(ValueError, TypeError):
                    col_span = int(gs.get(qn("w:val"), "1"))

        # ── Vertical merge ──────────────────────────────────────────────
        vmerge = ""
        if tc_pr is not None:
            vm = tc_pr.find(qn("w:vMerge"))
            if vm is not None:
                val = vm.get(qn("w:val"), "")
                # <w:vMerge w:val="restart"/> = first cell of merged group
                # <w:vMerge/>                = continuation (empty val attr)
                vmerge = "restart" if val == "restart" else "continue"

        # ── Cell properties (background, alignment, borders, padding) ───
        props = self._parse_cell_props(tc_pr)

        # ── Cell content (paragraphs and nested tables) ─────────────────
        blocks: list[Paragraph | Table] = []
        for child in tc_el:
            tag = child.tag
            if tag == qn("w:p"):
                blocks.append(self._parse_paragraph(child))
            elif tag == qn("w:tbl"):
                blocks.append(self._parse_table(child))
            # w:tcPr, w:bookmarkStart, etc. → skip

        return TableCell(
            blocks=blocks,
            col_span=col_span,
            row_span=1,
            vmerge=vmerge,
            props=props,
        )

    # ------------------------------------------------------------------
    # Property helpers
    # ------------------------------------------------------------------

    def _parse_cell_props(self, tc_pr: ET.Element | None) -> TableCellProps:
        """Parse a ``<w:tcPr>`` element into :class:`~pydocx_pdf.models.table.TableCellProps`.

        Parameters
        ----------
        tc_pr:
            The ``<w:tcPr>`` element from a ``<w:tc>``, or ``None`` if the
            cell has no explicit properties.

        Returns
        -------
        TableCellProps
            Populated with background colour, vertical alignment, borders,
            and cell-level padding values.
        """
        props = TableCellProps()
        if tc_pr is None:
            return props

        # Background fill
        shd = tc_pr.find(qn("w:shd"))
        if shd is not None:
            fill = shd.get(qn("w:fill"), "")
            if fill and fill.lower() not in ("", "none", "auto"):
                props.bg_color_hex = fill.upper()

        # Vertical alignment
        v_align_el = tc_pr.find(qn("w:vAlign"))
        if v_align_el is not None:
            raw = v_align_el.get(qn("w:val"), "top")
            props.v_align = "center" if raw == "both" else raw

        # Cell borders
        tc_borders = tc_pr.find(qn("w:tcBorders"))
        if tc_borders is not None:
            props.borders = CellBorders(
                top=self._parse_border(tc_borders.find(qn("w:top"))),
                bottom=self._parse_border(tc_borders.find(qn("w:bottom"))),
                left=self._parse_border(tc_borders.find(qn("w:left"))),
                right=self._parse_border(tc_borders.find(qn("w:right"))),
            )

        # Cell-level margin / padding overrides
        tc_mar = tc_pr.find(qn("w:tcMar"))
        if tc_mar is not None:
            for attr, edge in (
                ("w:top",    "pad_top_pt"),
                ("w:bottom", "pad_bottom_pt"),
                ("w:left",   "pad_left_pt"),
                ("w:right",  "pad_right_pt"),
            ):
                el = tc_mar.find(qn(attr))
                if el is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        twips = int(el.get(qn("w:w"), "0"))
                        setattr(props, edge, twips / 20.0)

        return props

    def _parse_table_props(self, tbl_pr: ET.Element | None) -> TableProps:
        """Parse a ``<w:tblPr>`` element into :class:`~pydocx_pdf.models.table.TableProps`.

        Parameters
        ----------
        tbl_pr:
            The ``<w:tblPr>`` element from a ``<w:tbl>``, or ``None`` if the
            table has no explicit properties.

        Returns
        -------
        TableProps
            Table-wide alignment, border, and padding defaults.
        """
        props = TableProps()
        if tbl_pr is None:
            return props

        # Table alignment
        jc = tbl_pr.find(qn("w:jc"))
        if jc is not None:
            props.alignment = jc.get(qn("w:val"), "left")

        # Table-level borders
        tbl_borders = tbl_pr.find(qn("w:tblBorders"))
        if tbl_borders is not None:
            props.has_border_info = True
            props.border_top      = self._parse_border(tbl_borders.find(qn("w:top")))
            props.border_bottom   = self._parse_border(tbl_borders.find(qn("w:bottom")))
            props.border_left     = self._parse_border(tbl_borders.find(qn("w:left")))
            props.border_right    = self._parse_border(tbl_borders.find(qn("w:right")))
            props.border_inside_h = self._parse_border(tbl_borders.find(qn("w:insideH")))
            props.border_inside_v = self._parse_border(tbl_borders.find(qn("w:insideV")))

        # Default cell margins
        tbl_cell_mar = tbl_pr.find(qn("w:tblCellMar"))
        if tbl_cell_mar is not None:
            for attr, edge in (
                ("w:top",    "cell_pad_top_pt"),
                ("w:bottom", "cell_pad_bottom_pt"),
                ("w:left",   "cell_pad_left_pt"),
                ("w:right",  "cell_pad_right_pt"),
            ):
                el = tbl_cell_mar.find(qn(attr))
                if el is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        twips = int(el.get(qn("w:w"), "0"))
                        setattr(props, edge, twips / 20.0)

        return props

    @staticmethod
    def _parse_border(el: ET.Element | None) -> BorderDef | None:
        """Parse a single border element (``<w:top>``, ``<w:left>``, etc.).

        Parameters
        ----------
        el:
            One of the border child elements inside ``<w:tblBorders>`` or
            ``<w:tcBorders>``, or ``None`` if the edge is absent.

        Returns
        -------
        BorderDef or None
            A populated :class:`~pydocx_pdf.models.table.BorderDef`, or
            ``None`` if *el* is ``None``.
        """
        if el is None:
            return None
        style = el.get(qn("w:val"), "single")
        # w:sz is in 1/8th of a point
        sz_raw = el.get(qn("w:sz"), "4")
        try:
            width_pt = max(0.125, int(sz_raw) / 8.0)
        except (ValueError, TypeError):
            width_pt = 0.5
        color = el.get(qn("w:color"), "000000")
        if color.lower() == "auto":
            color = "000000"
        return BorderDef(style=style, width_pt=width_pt, color_hex=color.upper())

    def _extract_image(self, drawing_el: ET.Element) -> Image | None:
        """Extract an inline image from a ``<w:drawing>`` element.

        Resolves the relationship ID to the image filename, fetches the raw
        bytes from :attr:`DocxParts.media`, and reads the display dimensions
        from ``<wp:extent>``.

        Parameters
        ----------
        drawing_el:
            A ``<w:drawing>`` element from within a ``<w:r>`` run.

        Returns
        -------
        Image or None
            An :class:`~pydocx_pdf.models.image.Image` with data and display
            dimensions, or ``None`` if the image cannot be resolved (e.g.
            missing relationship or media file).
        """
        # Namespace shortcuts
        _WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        _A  = "http://schemas.openxmlformats.org/drawingml/2006/main"
        _R  = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

        # Locate the blip element carrying the relationship ID
        # It may be under <wp:inline> or <wp:anchor> → <a:graphic> → <a:graphicData>
        # → <pic:pic> → <pic:blipFill> → <a:blip r:embed="rIdN"/>
        # Use a broad search to be robust against different wrapping structures.
        blip = drawing_el.find(f".//{{{_A}}}blip")
        if blip is None:
            return None

        r_id = blip.get(f"{{{_R}}}embed", "")
        if not r_id:
            return None

        target = self._rels.resolve(r_id)
        if not target:
            return None

        # The target is "media/image1.png" — get the bare filename
        filename = target.split("/")[-1]
        data = self._parts.media.get(filename)
        if not data:
            return None

        # Read display dimensions from <wp:extent cx="..." cy="..."/>
        # Values are in English Metric Units (EMU); 12700 EMU = 1 point
        width_pt:  float | None = None
        height_pt: float | None = None
        extent = drawing_el.find(f"{{{_WP}}}inline/{{{_WP}}}extent")
        if extent is None:
            extent = drawing_el.find(f"{{{_WP}}}anchor/{{{_WP}}}extent")
        if extent is not None:
            with contextlib.suppress(ValueError, TypeError):
                cx = extent.get("cx")
                if cx:
                    width_pt = int(cx) / 12700.0
            with contextlib.suppress(ValueError, TypeError):
                cy = extent.get("cy")
                if cy:
                    height_pt = int(cy) / 12700.0

        return Image(
            filename=filename,
            data=data,
            width_pt=width_pt,
            height_pt=height_pt,
        )

