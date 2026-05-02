"""
Parse word/numbering.xml and resolve abstract/concrete numbering chains.

DOCX numbering model:
  abstractNum  - defines level formats (bullet char, indent, num_fmt, etc.)
  num          - a concrete instance of an abstractNum (may override levels)
  Paragraphs reference a num via w:numId + w:ilvl (0-based level index)
"""

from __future__ import annotations

import re as _re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from pydocx_pdf.utils import NS, parse_xml, qn


# ---------------------------------------------------------------------------
# Counter-formatting helpers (module-level so tests can import them directly)
# ---------------------------------------------------------------------------

def _to_alpha(n: int, upper: bool = False) -> str:
    """1-based counter to letter string: 1->a, 26->z, 27->aa …"""
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord("A" if upper else "a") + rem) + result
    return result


def _to_roman(n: int, upper: bool = True) -> str:
    """Positive integer to Roman numeral string."""
    if n <= 0:
        return str(n)
    vals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100,  "C"), (90,  "XC"), (50,  "L"), (40,  "XL"),
        (10,   "X"), (9,   "IX"), (5,   "V"), (4,   "IV"), (1, "I"),
    ]
    result = ""
    for val, numeral in vals:
        while n >= val:
            result += numeral
            n -= val
    return result if upper else result.lower()


def _format_counter(count: int, num_fmt: str) -> str:
    """Format *count* per DOCX num_fmt value."""
    if num_fmt == "decimal":
        return str(count)
    elif num_fmt == "lowerLetter":
        return _to_alpha(count, upper=False)
    elif num_fmt == "upperLetter":
        return _to_alpha(count, upper=True)
    elif num_fmt == "lowerRoman":
        return _to_roman(count, upper=False)
    elif num_fmt == "upperRoman":
        return _to_roman(count, upper=True)
    else:
        return str(count)   # ordinal, chicago, etc. -> decimal fallback


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class LevelDef:
    level: int = 0
    num_fmt: str = "bullet"
    level_text: str = "•"
    indent_left_twips: int = 720
    hanging_twips: int = 360
    start_value: int = 1


@dataclass
class AbstractNum:
    abstract_num_id: str = ""
    levels: Dict[int, LevelDef] = field(default_factory=dict)


@dataclass
class ConcreteNum:
    num_id: str = ""
    abstract_num_id: str = ""
    level_overrides: Dict[int, LevelDef] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class NumberingParser:
    def __init__(self, xml_bytes: bytes) -> None:
        self._abstract: Dict[str, AbstractNum] = {}
        self._concrete: Dict[str, ConcreteNum] = {}
        self._counters: Dict[Tuple[str, int], int] = {}

        if xml_bytes:
            root = parse_xml(xml_bytes)
            self._parse(root)

    # ----------------------------------------------------------------- public

    def get_level_def(self, num_id: str, ilvl: int) -> Optional[LevelDef]:
        """Effective LevelDef for a paragraph with this numId/ilvl."""
        concrete = self._concrete.get(num_id)
        if concrete is None:
            return None
        if ilvl in concrete.level_overrides:
            return concrete.level_overrides[ilvl]
        abstract = self._abstract.get(concrete.abstract_num_id)
        if abstract is None:
            return None
        return abstract.levels.get(ilvl)

    def next_count(self, num_id: str, ilvl: int) -> int:
        """Advance counter for (num_id, ilvl) and reset all deeper levels."""
        key = (num_id, ilvl)
        self._counters[key] = self._counters.get(key, 0) + 1
        for lvl in range(ilvl + 1, 9):
            self._counters.pop((num_id, lvl), None)
        return self._counters[key]

    def get_current_counters(self, num_id: str) -> Dict[int, int]:
        """Snapshot of all current counter values for *num_id*."""
        return {
            ilvl: count
            for (nid, ilvl), count in self._counters.items()
            if nid == num_id
        }

    def format_marker(self, num_id: str, ilvl: int) -> str:
        """Formatted list marker for the current state of (num_id, ilvl).

        Resolves %N placeholders in level_text, formatting each placeholder
        with that level's own num_fmt.  Bullet markers are returned as-is.
        """
        level_def = self.get_level_def(num_id, ilvl)
        if level_def is None:
            return "•"

        if level_def.num_fmt == "bullet":
            return level_def.level_text or "•"

        counters   = self.get_current_counters(num_id)
        level_text = level_def.level_text

        if not level_text:
            return _format_counter(counters.get(ilvl, 1), level_def.num_fmt) + "."

        def _replace(m: _re.Match) -> str:  # type: ignore[type-arg]
            lvl_0 = int(m.group(1)) - 1     # %N is 1-based
            count = counters.get(lvl_0, 1)
            ldef  = self.get_level_def(num_id, lvl_0)
            fmt   = ldef.num_fmt if ldef else "decimal"
            return _format_counter(count, fmt)

        return _re.sub(r"%(\d+)", _replace, level_text)

    # --------------------------------------------------------------- internal

    def _parse(self, root: ET.Element) -> None:
        w = NS["w"]

        for an_el in root.findall(f"{{{w}}}abstractNum"):
            an_id  = an_el.get(qn("w:abstractNumId"), "")
            levels: Dict[int, LevelDef] = {}
            for lvl_el in an_el.findall(f"{{{w}}}lvl"):
                ilvl = int(lvl_el.get(qn("w:ilvl"), "0"))
                levels[ilvl] = _parse_level(lvl_el)
            self._abstract[an_id] = AbstractNum(abstract_num_id=an_id, levels=levels)

        for num_el in root.findall(f"{{{w}}}num"):
            num_id = num_el.get(qn("w:numId"), "")
            an_ref = num_el.find(f"{{{w}}}abstractNumId")
            an_id  = an_ref.get(qn("w:val"), "") if an_ref is not None else ""
            overrides: Dict[int, LevelDef] = {}
            for ovr in num_el.findall(f"{{{w}}}lvlOverride"):
                ilvl   = int(ovr.get(qn("w:ilvl"), "0"))
                lvl_el = ovr.find(f"{{{w}}}lvl")
                if lvl_el is not None:
                    overrides[ilvl] = _parse_level(lvl_el)
            self._concrete[num_id] = ConcreteNum(
                num_id=num_id,
                abstract_num_id=an_id,
                level_overrides=overrides,
            )


# ---------------------------------------------------------------------------
# Level parsing helper
# ---------------------------------------------------------------------------

def _parse_level(lvl_el: ET.Element) -> LevelDef:
    w    = NS["w"]
    ilvl = int(lvl_el.get(qn("w:ilvl"), "0"))

    def _text(tag: str) -> Optional[str]:
        el = lvl_el.find(f"{{{w}}}{tag}")
        return el.get(qn("w:val")) if el is not None else None

    num_fmt      = _text("numFmt") or "bullet"
    level_text_el = lvl_el.find(f"{{{w}}}lvlText")
    level_text   = (
        level_text_el.get(qn("w:val"), "•")
        if level_text_el is not None else "•"
    )

    start_el  = lvl_el.find(f"{{{w}}}start")
    start_val = int(start_el.get(qn("w:val"), "1")) if start_el is not None else 1

    ind_left = 720
    hanging  = 360
    ppr = lvl_el.find(f"{{{w}}}pPr")
    if ppr is not None:
        ind = ppr.find(f"{{{w}}}ind")
        if ind is not None:
            ind_left = int(ind.get(qn("w:left"),    ind_left))
            hanging  = int(ind.get(qn("w:hanging"), hanging))

    return LevelDef(
        level=ilvl,
        num_fmt=num_fmt,
        level_text=level_text,
        indent_left_twips=ind_left,
        hanging_twips=hanging,
        start_value=start_val,
    )
