"""
Parse word/theme/theme1.xml to extract the document's default font and color scheme.

The theme defines:
  - dk1/dk2 (dark1/dark2) text colors
  - lt1/lt2 (light1/light2) background colors
  - accent1..6 colors
  - majorFont / minorFont (heading / body font families)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Optional

_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


@dataclass
class Theme:
    major_font: Optional[str] = None   # heading font, e.g. "Calibri Light"
    minor_font: Optional[str] = None   # body font, e.g. "Calibri"
    colors: Dict[str, str] = field(default_factory=dict)  # scheme name -> hex


def parse_theme(xml_bytes: bytes) -> Theme:
    """Parse theme XML and return a :class:`Theme` instance."""
    if not xml_bytes:
        return Theme()

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return Theme()

    theme = Theme()
    _parse_fonts(root, theme)
    _parse_colors(root, theme)
    return theme


def _parse_fonts(root: ET.Element, theme: Theme) -> None:
    a = _A_NS
    font_scheme = root.find(f".//{{{a}}}fontScheme")
    if font_scheme is None:
        return

    major = font_scheme.find(f"{{{a}}}majorFont/{{{a}}}latin")
    if major is not None:
        theme.major_font = major.get("typeface")

    minor = font_scheme.find(f"{{{a}}}minorFont/{{{a}}}latin")
    if minor is not None:
        theme.minor_font = minor.get("typeface")


def _parse_colors(root: ET.Element, theme: Theme) -> None:
    a = _A_NS
    clr_scheme = root.find(f".//{{{a}}}clrScheme")
    if clr_scheme is None:
        return

    for child in clr_scheme:
        # tag is like {uri}dk1, {uri}accent1, etc.
        name = child.tag.split("}")[-1]
        # color can be srgbClr or sysClr
        srgb = child.find(f"{{{a}}}srgbClr")
        if srgb is not None:
            val = srgb.get("val")
            if val:
                theme.colors[name] = val
                continue
        sys_clr = child.find(f"{{{a}}}sysClr")
        if sys_clr is not None:
            # lastClr is the resolved system color
            val = sys_clr.get("lastClr")
            if val:
                theme.colors[name] = val
