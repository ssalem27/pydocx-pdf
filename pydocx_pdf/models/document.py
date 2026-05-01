from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Union

from pydocx_pdf.models.paragraph import Paragraph
from pydocx_pdf.models.table import Table

Block = Union[Paragraph, Table]


@dataclass
class Document:
    blocks: List[Block] = field(default_factory=list)
