"""
Table data models.

Represents the full table structure extracted from ``<w:tbl>`` elements in
``word/document.xml``, including per-cell borders, background fills, padding,
vertical alignment, vertical merges (row-spans), and horizontal spans.

Class hierarchy::

    Table
    -- rows: List[TableRow]
       -- cells: List[TableCell]
          -- blocks: List[Paragraph | Table]  (nested content)
          -- props: TableCellProps
             -- borders: CellBorders
                -- top/bottom/left/right: Optional[BorderDef]

TableProps captures table-wide defaults (alignment, outer borders,
interior grid lines, default cell padding) that individual cells may
override via their own :class:`TableCellProps`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydocx_pdf.models.paragraph import Paragraph


@dataclass
class BorderDef:
    """Definition of a single border edge.

    Parsed from ``<w:tblBorders>`` (table-level) or ``<w:tcBorders>``
    (cell-level) child elements such as ``<w:top>``, ``<w:bottom>``, etc.

    Attributes
    ----------
    style:
        Border style keyword from ``w:val``.  Common values: ``"single"``,
        ``"double"``, ``"dashed"``, ``"dotted"``, ``"none"``, ``"nil"``.
    width_pt:
        Border line width in points.  DOCX stores this as ``w:sz`` in
        eighths of a point; this field stores the converted value.
        Enforced to a minimum of 0.125 pt at parse time.
    color_hex:
        Border colour as a 6-character RRGGBB hex string (e.g. ``"000000"``
        for black).  ``"auto"`` is resolved to ``"000000"`` at parse time.
    """

    style: str = "single"
    width_pt: float = 0.5
    color_hex: str = "000000"

    @property
    def is_visible(self) -> bool:
        """``True`` unless the style is ``"none"`` or ``"nil"``."""
        return self.style not in ("none", "nil", "")


@dataclass
class CellBorders:
    """Per-edge border definitions for one table cell.

    Parsed from ``<w:tcPr>/<w:tcBorders>``.  Any edge that is absent in
    the XML is ``None``; the renderer falls back to the table-level border
    or a default thin black border for that edge.

    Attributes
    ----------
    top, bottom, left, right:
        :class:`BorderDef` for the respective edge, or ``None`` if not
        explicitly set for this cell.
    """

    top:    BorderDef | None = None
    bottom: BorderDef | None = None
    left:   BorderDef | None = None
    right:  BorderDef | None = None


@dataclass
class TableCellProps:
    """Rendering properties for a single table cell.

    Parsed from the ``<w:tcPr>`` element inside each ``<w:tc>``.

    Attributes
    ----------
    bg_color_hex:
        Cell background fill colour as a 6-character RRGGBB hex string, or
        ``None`` for a transparent (white) background.  Parsed from
        ``<w:shd w:fill="..."/>``.
    v_align:
        Vertical content alignment within the cell: ``"top"``, ``"center"``,
        or ``"bottom"``.  Parsed from ``<w:vAlign w:val="..."/>``; Word\'s
        ``"both"`` value is mapped to ``"center"``.
    borders:
        Per-edge border overrides for this cell (``<w:tcBorders>``).
    pad_top_pt, pad_bottom_pt, pad_left_pt, pad_right_pt:
        Cell-level padding in points (from ``<w:tcMar>``).  A value of
        ``0.0`` means "use the table-level default".  The renderer enforces
        a minimum of 1 mm regardless.
    """

    bg_color_hex: str | None = None
    v_align: str = "top"
    borders: CellBorders = field(default_factory=CellBorders)
    pad_top_pt:    float = 0.0
    pad_bottom_pt: float = 0.0
    pad_left_pt:   float = 5.4
    pad_right_pt:  float = 5.4


@dataclass
class TableProps:
    """Table-wide rendering properties.

    Parsed from ``<w:tblPr>`` at the top of each ``<w:tbl>`` element.
    These values act as defaults that individual cells may override via
    their own :class:`TableCellProps`.

    Attributes
    ----------
    alignment:
        Horizontal alignment of the table on the page: ``"left"``,
        ``"center"``, or ``"right"``.  Parsed from ``<w:jc w:val="..."/>``.
    border_top, border_bottom, border_left, border_right:
        Outer table border edges (``<w:tblBorders>/<w:top>`` etc.), or
        ``None`` if not specified.
    border_inside_h:
        Horizontal interior grid lines (``<w:insideH>``), drawn between
        adjacent rows.
    border_inside_v:
        Vertical interior grid lines (``<w:insideV>``), drawn between
        adjacent columns.
    cell_pad_top_pt, cell_pad_bottom_pt, cell_pad_left_pt, cell_pad_right_pt:
        Default cell padding in points from ``<w:tblCellMar>``.  Overridden
        per-cell by :class:`TableCellProps`.
    has_border_info:
        ``True`` when explicit border information was found in the XML.
        ``False`` causes the renderer to apply thin black borders everywhere
        (the legacy behaviour for documents with no explicit border info).
    """

    alignment: str = "left"

    border_top:    BorderDef | None = None
    border_bottom: BorderDef | None = None
    border_left:   BorderDef | None = None
    border_right:  BorderDef | None = None

    border_inside_h: BorderDef | None = None
    border_inside_v: BorderDef | None = None

    cell_pad_top_pt:    float = 0.0
    cell_pad_bottom_pt: float = 0.0
    cell_pad_left_pt:   float = 5.4
    cell_pad_right_pt:  float = 5.4

    has_border_info: bool = False


@dataclass
class TableCell:
    """A single cell within a table row.

    Attributes
    ----------
    blocks:
        Ordered content of the cell.  Each element is a
        :class:`~pydocx_pdf.models.paragraph.Paragraph` or a nested
        :class:`Table`.  The renderer recurses into nested tables.
    col_span:
        Number of grid columns this cell spans (``<w:gridSpan w:val="..."/>``).
        Defaults to 1.
    row_span:
        Number of rows this cell spans.  Set to 1 by the parser; the actual
        row-span count is computed by the renderer from the ``vmerge`` chain.
    vmerge:
        Vertical merge participation: ``"restart"`` (first cell), ``"continue"``
        (subsequent cells), or ``""`` (not merged).
    props:
        Cell-level formatting (background, padding, borders, alignment).
    """

    blocks: list[Paragraph | Table] = field(default_factory=list)
    col_span: int = 1
    row_span: int = 1
    vmerge: str = ""
    props: TableCellProps = field(default_factory=TableCellProps)


@dataclass
class TableRow:
    """A single row within a table.

    Attributes
    ----------
    cells:
        Ordered list of :class:`TableCell` objects in this row.
    is_header:
        ``True`` when the row is marked as a header row via
        ``<w:tblHeader/>`` in ``<w:trPr>``.
    """

    cells: list[TableCell] = field(default_factory=list)
    is_header: bool = False


@dataclass
class Table:
    """A parsed DOCX table (``<w:tbl>``).

    Attributes
    ----------
    rows:
        Ordered list of :class:`TableRow` objects.
    col_widths_twips:
        List of column widths in twips, parsed from ``<w:tblGrid>``.
        When empty the renderer distributes available width equally.
    props:
        Table-wide properties (alignment, borders, padding defaults).
    """

    rows: list[TableRow] = field(default_factory=list)
    col_widths_twips: list[int] = field(default_factory=list)
    props: TableProps = field(default_factory=TableProps)
