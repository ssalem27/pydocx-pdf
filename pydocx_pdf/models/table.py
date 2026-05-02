"""
Table model with border, cell-property, and row-span support.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Union

if TYPE_CHECKING:
    from pydocx_pdf.models.paragraph import Paragraph


@dataclass
class BorderDef:
    """One border edge (e.g. from w:tblBorders/w:top or w:tcBorders/w:top)."""
    style: str = "single"     # single | double | dashed | dotted | none | nil
    width_pt: float = 0.5     # w:sz / 8  (sz is eighths of a point)
    color_hex: str = "000000" # RRGGBB; "auto" resolved to "000000"

    @property
    def is_visible(self) -> bool:
        return self.style not in ("none", "nil", "")


@dataclass
class CellBorders:
    """Per-edge borders for one cell (w:tcPr/w:tcBorders)."""
    top:    Optional[BorderDef] = None
    bottom: Optional[BorderDef] = None
    left:   Optional[BorderDef] = None
    right:  Optional[BorderDef] = None


@dataclass
class TableCellProps:
    """Rendering properties for one table cell."""
    bg_color_hex: Optional[str] = None   # hex fill; None = transparent
    v_align: str = "top"                 # top | center | bottom
    borders: CellBorders = field(default_factory=CellBorders)
    pad_top_pt:    float = 0.0
    pad_bottom_pt: float = 0.0
    pad_left_pt:   float = 5.4           # ~Word default 108 twips
    pad_right_pt:  float = 5.4


@dataclass
class TableProps:
    """Rendering properties for the whole table."""
    alignment: str = "left"              # left | center | right

    # Outer edges
    border_top:    Optional[BorderDef] = None
    border_bottom: Optional[BorderDef] = None
    border_left:   Optional[BorderDef] = None
    border_right:  Optional[BorderDef] = None

    # Interior grid lines
    border_inside_h: Optional[BorderDef] = None
    border_inside_v: Optional[BorderDef] = None

    # Default cell padding (overridden per-cell by TableCellProps)
    cell_pad_top_pt:    float = 0.0
    cell_pad_bottom_pt: float = 0.0
    cell_pad_left_pt:   float = 5.4
    cell_pad_right_pt:  float = 5.4

    # True when explicit border info was parsed from the XML.
    # False -> renderer falls back to thin black borders (old behaviour).
    has_border_info: bool = False


@dataclass
class TableCell:
    blocks: List[Union["Paragraph", "Table"]] = field(default_factory=list)
    col_span: int = 1
    row_span: int = 1
    # "restart"  = first cell of a vertical merge group
    # "continue" = subsequent merged cells (skipped during render)
    # ""         = not merged
    vmerge: str = ""
    props: TableCellProps = field(default_factory=TableCellProps)


@dataclass
class TableRow:
    cells: List[TableCell] = field(default_factory=list)
    is_header: bool = False


@dataclass
class Table:
    rows: List[TableRow] = field(default_factory=list)
    col_widths_twips: List[int] = field(default_factory=list)
    props: TableProps = field(default_factory=TableProps)
