from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydocx_pdf.models.image import Image


@dataclass
class Run:
    text: str
    props: Dict[str, Any] = field(default_factory=dict)
    image: Optional[Image] = None

    @property
    def is_bold(self) -> bool:
        return bool(self.props.get("bold", False))

    @property
    def is_italic(self) -> bool:
        return bool(self.props.get("italic", False))

    @property
    def font_size_pt(self) -> float:
        hp = self.props.get("font_size_half_pt")
        return hp / 2 if hp else 11.0  # default 11pt

    @property
    def font_name(self) -> Optional[str]:
        return self.props.get("font_name")

    @property
    def color_hex(self) -> Optional[str]:
        return self.props.get("color")  # e.g. "1F3864"


@dataclass
class Paragraph:
    style_id: str = "Normal"
    style_props: Dict[str, Any] = field(default_factory=dict)
    runs: List[Run] = field(default_factory=list)
    num_id: Optional[str] = None
    ilvl: int = 0
    list_counter: Optional[int] = None

    @property
    def is_list_item(self) -> bool:
        return self.num_id is not None

    @property
    def full_text(self) -> str:
        return "".join(r.text for r in self.runs)
