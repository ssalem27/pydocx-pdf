"""
Parse word/styles.xml into a flat style map.

Each style entry resolves its full property set by walking the basedOn chain,
so callers always get a single merged dict with no inheritance indirection.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional

from pydocx_pdf.utils import NS, parse_xml, qn


StyleId = str
StyleMap = Dict[StyleId, Dict[str, Any]]


class StylesParser:
    def __init__(self, xml_bytes: bytes) -> None:
        self._root: Optional[ET.Element] = None
        self._raw: Dict[StyleId, Dict[str, Any]] = {}
        self._resolved: StyleMap = {}

        if xml_bytes:
            self._root = parse_xml(xml_bytes)
            self._parse_raw()

    # ── public ────────────────────────────────────────────────────────────────

    def get(self, style_id: StyleId) -> Dict[str, Any]:
        """Return the resolved (inheritance-merged) style dict for *style_id*."""
        if style_id not in self._resolved:
            self._resolved[style_id] = self._resolve(style_id, set())
        return self._resolved[style_id]

    def default_paragraph_style(self) -> Dict[str, Any]:
        return self.get("Normal")

    # ── internals ─────────────────────────────────────────────────────────────

    def _parse_raw(self) -> None:
        assert self._root is not None
        for style_el in self._root.findall(f"{{{NS['w']}}}style"):
            sid = style_el.get(qn("w:styleId"), "")
            if not sid:
                continue
            self._raw[sid] = self._extract_props(style_el)

    def _extract_props(self, style_el: ET.Element) -> Dict[str, Any]:
        props: Dict[str, Any] = {}

        based_on_el = style_el.find(f"{{{NS['w']}}}basedOn")
        if based_on_el is not None:
            props["_basedOn"] = based_on_el.get(qn("w:val"), "")

        # Paragraph properties (w:pPr)
        ppr = style_el.find(f"{{{NS['w']}}}pPr")
        if ppr is not None:
            props.update(_parse_ppr(ppr))

        # Run properties (w:rPr)
        rpr = style_el.find(f"{{{NS['w']}}}rPr")
        if rpr is not None:
            props.update(_parse_rpr(rpr))

        return props

    def _resolve(self, sid: StyleId, seen: set[StyleId]) -> Dict[str, Any]:
        if sid in seen:
            return {}
        seen.add(sid)
        raw = self._raw.get(sid, {})
        based_on = raw.get("_basedOn")
        if based_on:
            base = self._resolve(based_on, seen)
            return {**base, **{k: v for k, v in raw.items() if k != "_basedOn"}}
        return {k: v for k, v in raw.items() if k != "_basedOn"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_ppr(ppr: ET.Element) -> Dict[str, Any]:
    """Extract paragraph-level formatting from a w:pPr element."""
    props: Dict[str, Any] = {}

    # Alignment: w:jc
    jc = ppr.find(f"{{{NS['w']}}}jc")
    if jc is not None:
        props["align"] = jc.get(qn("w:val"), "left")

    # Spacing: w:spacing
    spacing = ppr.find(f"{{{NS['w']}}}spacing")
    if spacing is not None:
        before = spacing.get(qn("w:before"))
        after = spacing.get(qn("w:after"))
        line = spacing.get(qn("w:line"))
        if before:
            props["space_before_twips"] = int(before)
        if after:
            props["space_after_twips"] = int(after)
        if line:
            props["line_twips"] = int(line)

    # Indentation: w:ind
    ind = ppr.find(f"{{{NS['w']}}}ind")
    if ind is not None:
        left = ind.get(qn("w:left"))
        hanging = ind.get(qn("w:hanging"))
        if left:
            props["indent_left_twips"] = int(left)
        if hanging:
            props["indent_hanging_twips"] = int(hanging)

    return props


def _parse_rpr(rpr: ET.Element) -> Dict[str, Any]:
    """Extract run-level formatting from a w:rPr element."""
    props: Dict[str, Any] = {}

    sz = rpr.find(f"{{{NS['w']}}}sz")
    if sz is not None:
        val = sz.get(qn("w:val"))
        if val:
            props["font_size_half_pt"] = int(val)

    bold = rpr.find(f"{{{NS['w']}}}b")
    if bold is not None:
        props["bold"] = bold.get(qn("w:val"), "true") not in ("0", "false")

    italic = rpr.find(f"{{{NS['w']}}}i")
    if italic is not None:
        props["italic"] = italic.get(qn("w:val"), "true") not in ("0", "false")

    color = rpr.find(f"{{{NS['w']}}}color")
    if color is not None:
        props["color"] = color.get(qn("w:val"))

    fonts = rpr.find(f"{{{NS['w']}}}rFonts")
    if fonts is not None:
        props["font_name"] = (
            fonts.get(qn("w:ascii"))
            or fonts.get(qn("w:hAnsi"))
            or fonts.get(qn("w:cs"))
        )

    return props
