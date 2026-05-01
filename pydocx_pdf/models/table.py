from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Union

if TYPE_CHECKING:
    from pydocx_pdf.models.paragraph import Paragraph


@dataclass
class TableCell:
    blocks: List[Union["Paragraph", "Table"]] = field(default_factory=list)
    col_span: int = 1
    row_span: int = 1


@dataclass
class TableRow:
    cells: List[TableCell] = field(default_factory=list)


@dataclass
class Table:
    rows: List[TableRow] = field(default_factory=list)
    col_widths_twips: List[int] = field(default_factory=list)
