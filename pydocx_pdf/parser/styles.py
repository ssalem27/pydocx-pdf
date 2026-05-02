"""
Parse word/styles.xml into a flat style map.

Each style entry resolves its full property set by walking the basedOn chain,
so callers always get a single merged dict with no inheritance indirection.

Also parses w:docDefaults for document-level run property defaults (font name,
font size) which are the ultimate base for all styles.
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
        self._doc_defaults: Dict[str, Any] = {}

        if xml_bytes:
            self._root = parse_xml(xml_bytes)
            self._doc_defaults = self._parse_doc_defaults()
            self._parse_raw()

    # -- public ----------------------------------------------------------------

    def get(self, style_id: StyleId) -> Dict[str, Any]:
        """Return the resolved (inheritance-merged) style dict for *style_id*."""
        if style_id not in self._resolved:
            self._resolved[style_id] = self._resolve(style_id, set())
        return self._resolved[style_id]

    def default_paragraph_style(self) -> Dict[str, Any]:
        return self.get("Normal")

    def doc_default_rpr(self) -> Dict[str, Any]:
        """Return run-properties from w:docDefaults/w:rPrDefault/w:rPr."""
        return dict(self._doc_defaults)

    # -- internals -------------------------------------------------------------

    def _parse_doc_defaults(self) -> Dict[str, Any]:
        if self._root is None:
            return {}
        rpr_el = self._root.find(
            f"{{{NS['w']}}}docDefaults"
            f"/{{{NS['w']}}}rPrDefault"
            f"/{{{NS['w']}}}rPr"
        )
        if rpr_el is None:
            return {}
        return _parse_rpr(rpr_el)

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
        ppr = style_el.find(f"{{{NS['w']}}}pPr")
        if ppr is not None:
            props.update(_parse_ppr(ppr))
        rpr = style_el.find(f"{{{NS['w']}}}rPr")
        if rpr is not None:
            props.update(_parse_rpr(rpr))
        return props

    def _resolve(self, sid: StyleId, seen: set) -> Dict[str, Any]:
        if sid in seen:
            return {}
        seen.add(sid)
        raw = self._raw.get(sid, {})
        based_on = raw.get("_basedOn")
        if based_on:
            base = self._resolve(based_on, seen)
        else:
            base = self._doc_defaults
        return {**base, **{k: v for k, v in raw.items() if k != "_basedOn"}}


# -- helpers ------------------------------------------------------------------

def _parse_ppr(ppr: ET.Element) -> Dict[str, Any]:
    """Extract paragraph-level formatting from a w:pPr element."""
    props: Dict[str, Any] = {}

    jc = ppr.find(f"{{{NS['w']}}}jc")
    if jc is not None:
        props["align"] = jc.get(qn("w:val"), "left")

    spacing = ppr.find(f"{{{NS['w']}}}spacing")
    if spacing is not None:
        before = spacing.get(qn("w:before"))
        after = spacing.get(qn("w:after"))
        line = spacing.get(qn("w:line"))
        line_rule = spacing.get(qn("w:lineRule"))
        if before:
            props["space_before_twips"] = int(before)
        if after:
            props["space_after_twips"] = int(after)
        if line:
            props["line_twips"] = int(line)
        if line_rule:
            props["line_rule"] = line_rule

    ind = ppr.find(f"{{{NS['w']}}}ind")
    if ind is not None:
        left = ind.get(qn("w:left"))
        right = ind.get(qn("w:right"))
        hanging = ind.get(qn("w:hanging"))
        first_line = ind.get(qn("w:firstLine"))
        if left:
            props["indent_left_twips"] = int(left)
        if right:
            props["indent_right_twips"] = int(right)
        if hanging:
            props["indent_hanging_twips"] = int(hanging)
        if first_line:
            props["indent_first_twips"] = int(first_line)

    return props


def _parse_rpr(rpr: ET.Element) -> Dict[str, Any]:
    """Extract run-level formatting from a w:rPr element."""
    props: Dict[str, Any] = {}

    # Font size (w:sz stores half-points)
    sz = rpr.find(f"{{{NS['w']}}}sz")
    if sz is not None:
        val = sz.get(qn("w:val"))
        if val:
            props["font_size_half_pt"] = int(val)

    # Basic styles
    bold = rpr.find(f"{{{NS['w']}}}b")
    if bold is not None:
        props["bold"] = bold.get(qn("w:val"), "true") not in ("0", "false")

    italic = rpr.find(f"{{{NS['w']}}}i")
    if italic is not None:
        props["italic"] = italic.get(qn("w:val"), "true") not in ("0", "false")

    # Underline: any w:val other than "none" means underlined
    u = rpr.find(f"{{{NS['w']}}}u")
    if u is not None:
        val = u.get(qn("w:val"), "single")
        props["underline"] = val not in ("none", "0", "false")

    # Strikethrough (single or double — treat identically)
    strike = rpr.find(f"{{{NS['w']}}}strike")
    if strike is not None:
        props["strike"] = strike.get(qn("w:val"), "true") not in ("0", "false")
    if not props.get("strike"):
        dstrike = rpr.find(f"{{{NS['w']}}}dstrike")
        if dstrike is not None:
            props["strike"] = dstrike.get(qn("w:val"), "true") not in ("0", "false")

    # Vertical alignment (superscript / subscript)
    vert = rpr.find(f"{{{NS['w']}}}vertAlign")
    if vert is not None:
        val = vert.get(qn("w:val"), "")
        if val in ("superscript", "subscript"):
            props["vert_align"] = val

    # Caps / small-caps
    caps = rpr.find(f"{{{NS['w']}}}caps")
    if caps is not None:
        props["all_caps"] = caps.get(qn("w:val"), "true") not in ("0", "false")

    small_caps = rpr.find(f"{{{NS['w']}}}smallCaps")
    if small_caps is not None:
        props["small_caps"] = small_caps.get(qn("w:val"), "true") not in ("0", "false")

    # Color: hex value + optional theme slot name
    color = rpr.find(f"{{{NS['w']}}}color")
    if color is not None:
        val = color.get(qn("w:val"))
        if val:
            props["color"] = val
        theme_color = color.get(qn("w:themeColor"))
        if theme_color:
            props["theme_color"] = theme_color

    # Font: explicit name takes priority; theme ref is fallback signal
    fonts = rpr.find(f"{{{NS['w']}}}rFonts")
    if fonts is not None:
        explicit = (
            fonts.get(qn("w:ascii"))
            or fonts.get(qn("w:hAnsi"))
            or fonts.get(qn("w:cs"))
        )
        if explicit:
            props["font_name"] = explicit
        theme_ref = (
            fonts.get(qn("w:asciiTheme"))
            or fonts.get(qn("w:hAnsiTheme"))
        )
        if theme_ref:
            props["font_theme"] = theme_ref

    return props
