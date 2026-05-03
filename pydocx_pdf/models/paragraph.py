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
    def is_underline(self) -> bool:
        return bool(self.props.get("underline", False))

    @property
    def is_strikethrough(self) -> bool:
        return bool(self.props.get("strike", False))

    @property
    def vert_align(self) -> Optional[str]:
        """Return 'superscript', 'subscript', or None."""
        return self.props.get("vert_align")

    @property
    def is_all_caps(self) -> bool:
        return bool(self.props.get("all_caps", False))

    @property
    def is_small_caps(self) -> bool:
        return bool(self.props.get("small_caps", False))

    @property
    def is_page_break(self) -> bool:
        """True when this run carries a w:br w:type='page' marker."""
        return bool(self.props.get("page_break", False))

    @property
    def font_size_pt(self) -> float:
        hp = self.props.get("font_size_half_pt")
        return hp / 2 if hp else 11.0  # default 11pt

    @property
    def font_name(self) -> Optional[str]:
        return self.props.get("font_name")

    @property
    def font_theme(self) -> Optional[str]:
        """Theme font reference from w:asciiTheme/w:hAnsiTheme (e.g. 'minorHAnsi')."""
        return self.props.get("font_theme")

    @property
    def theme_color(self) -> Optional[str]:
        """Theme color slot name from w:themeColor (e.g. 'dark1', 'accent1')."""
        return self.props.get("theme_color")

    @property
    def color_hex(self) -> Optional[str]:
        return self.props.get("color")  # e.g. "1F3864"

    @property
    def char_spacing_twentiethpt(self) -> int:
        """Character spacing in 1/20th of a point. Positive=expanded, negative=condensed."""
        return self.props.get("char_spacing_twentiethpt", 0)

    @property
    def kern_half_pt(self) -> Optional[int]:
        """Minimum font size for kerning in half-points."""
        return self.props.get("kern_half_pt")

    @property
    def scale_percent(self) -> int:
        """Character width scaling as percentage (100 = normal)."""
        return self.props.get("scale_percent", 100)

    @property
    def position_half_pt(self) -> int:
        """Vertical position offset in half-points. Positive=raise, negative=lower."""
        return self.props.get("position_half_pt", 0)


@dataclass
class Paragraph:
    style_id: str = "Normal"
    style_props: Dict[str, Any] = field(default_factory=dict)
    runs: List[Run] = field(default_factory=list)
    num_id: Optional[str] = None
    ilvl: int = 0
    list_counter: Optional[int] = None

    # Pre-computed at parse time from the LevelDef for this list item.
    # The renderer reads these directly — no access to NumberingParser needed.
    list_label: Optional[str] = None        # resolved marker, e.g. "a.", "iii.", "•"
    list_indent_twips: int = 720            # distance (twips) from page left-margin to
                                            # the start of the text (= w:ind/@w:left)
    list_hanging_twips: int = 360           # width of the marker column
                                            # (= w:ind/@w:hanging)

    @property
    def is_list_item(self) -> bool:
        return self.num_id is not None

    @property
    def full_text(self) -> str:
        return "".join(r.text for r in self.runs)
