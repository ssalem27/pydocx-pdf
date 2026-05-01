"""
Shared utility functions — unit conversions and XML helpers.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

# ── XML namespaces ────────────────────────────────────────────────────────────

NS: dict[str, str] = {
    "w":   "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r":   "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "a":   "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp":  "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "mc":  "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
}


def qn(tag: str) -> str:
    """Expand a prefixed tag like ``w:p`` to its Clark notation ``{uri}p``."""
    prefix, local = tag.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def get_attr(el: ET.Element, tag: str, default: Optional[str] = None) -> Optional[str]:
    """Return the value of *tag* attribute on *el*, expanding namespace prefix."""
    return el.get(qn(tag), default)


def parse_xml(data: bytes) -> ET.Element:
    """Parse XML bytes and return the root element."""
    return ET.fromstring(data)


# ── Unit conversions ──────────────────────────────────────────────────────────

def emu_to_pt(emu: int) -> float:
    """English Metric Units → points (1 pt = 12700 EMU)."""
    return emu / 12700


def twips_to_pt(twips: int) -> float:
    """Twips → points (1 pt = 20 twips)."""
    return twips / 20


def half_pt_to_pt(hp: int) -> float:
    """Half-points → points."""
    return hp / 2


def inches_to_pt(inches: float) -> float:
    """Inches → points (1 inch = 72 pt)."""
    return inches * 72


def pt_to_mm(pt: float) -> float:
    """Points → millimetres (1 mm ≈ 2.835 pt)."""
    return pt / 2.8346456692913385


def mm_to_pt(mm: float) -> float:
    """Millimetres → points."""
    return mm * 2.8346456692913385
