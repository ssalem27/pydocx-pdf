"""
Parse word/numbering.xml and resolve abstract/concrete numbering chains.

The DOCX numbering model:
  - abstractNum: defines level formats (bullet char, indent, font, etc.)
  - num: a concrete instance of an abstractNum (may override levels)
  - Paragraphs reference a num via w:numId + w:ilvl (0-based level)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pydocx_pdf.utils import NS, parse_xml, qn


@dataclass
class LevelDef:
    level: int = 0
    num_fmt: str = "bullet"       # bullet | decimal | lowerLetter | …
    level_text: str = "•"        # the format string, e.g. "%1." or "•"
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


class NumberingParser:
    def __init__(self, xml_bytes: bytes) -> None:
        self._abstract: Dict[str, AbstractNum] = {}
        self._concrete: Dict[str, ConcreteNum] = {}
        # Runtime counters: (num_id, ilvl) → current count
        self._counters: Dict[tuple[str, int], int] = {}

        if xml_bytes:
            root = parse_xml(xml_bytes)
            self._parse(root)

    # ── public ────────────────────────────────────────────────────────────────

    def get_level_def(self, num_id: str, ilvl: int) -> Optional[LevelDef]:
        """Return the effective LevelDef for a paragraph with this numId/ilvl."""
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
        """Advance and return the counter for (num_id, ilvl).

        Resets deeper levels when this level is incremented.
        """
        key = (num_id, ilvl)
        self._counters[key] = self._counters.get(key, 0) + 1
        # Reset all deeper levels
        for lvl in range(ilvl + 1, 9):
            self._counters.pop((num_id, lvl), None)
        return self._counters[key]

    # ── internals ─────────────────────────────────────────────────────────────

    def _parse(self, root: ET.Element) -> None:
        w = NS["w"]

        for an_el in root.findall(f"{{{w}}}abstractNum"):
            an_id = an_el.get(qn("w:abstractNumId"), "")
            levels: Dict[int, LevelDef] = {}
            for lvl_el in an_el.findall(f"{{{w}}}lvl"):
                ilvl = int(lvl_el.get(qn("w:ilvl"), "0"))
                levels[ilvl] = _parse_level(lvl_el)
            self._abstract[an_id] = AbstractNum(abstract_num_id=an_id, levels=levels)

        for num_el in root.findall(f"{{{w}}}num"):
            num_id = num_el.get(qn("w:numId"), "")
            an_ref = num_el.find(f"{{{w}}}abstractNumId")
            an_id = an_ref.get(qn("w:val"), "") if an_ref is not None else ""
            overrides: Dict[int, LevelDef] = {}
            for ovr in num_el.findall(f"{{{w}}}lvlOverride"):
                ilvl = int(ovr.get(qn("w:ilvl"), "0"))
                lvl_el = ovr.find(f"{{{w}}}lvl")
                if lvl_el is not None:
                    overrides[ilvl] = _parse_level(lvl_el)
            self._concrete[num_id] = ConcreteNum(
                num_id=num_id, abstract_num_id=an_id, level_overrides=overrides
            )


def _parse_level(lvl_el: ET.Element) -> LevelDef:
    w = NS["w"]
    ilvl = int(lvl_el.get(qn("w:ilvl"), "0"))

    def _text(tag: str) -> Optional[str]:
        el = lvl_el.find(f"{{{w}}}{tag}")
        return el.get(qn("w:val")) if el is not None else None

    num_fmt = _text("numFmt") or "bullet"
    level_text_el = lvl_el.find(f"{{{w}}}lvlText")
    level_text = (
        level_text_el.get(qn("w:val"), "•") if level_text_el is not None else "•"
    )

    start_el = lvl_el.find(f"{{{w}}}start")
    start_val = int(start_el.get(qn("w:val"), "1")) if start_el is not None else 1

    ind_left = 720
    hanging = 360
    ppr = lvl_el.find(f"{{{w}}}pPr")
    if ppr is not None:
        ind = ppr.find(f"{{{w}}}ind")
        if ind is not None:
            ind_left = int(ind.get(qn("w:left"), ind_left))
            hanging = int(ind.get(qn("w:hanging"), hanging))

    return LevelDef(
        level=ilvl,
        num_fmt=num_fmt,
        level_text=level_text,
        indent_left_twips=ind_left,
        hanging_twips=hanging,
        start_value=start_val,
    )
