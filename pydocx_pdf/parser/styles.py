"""
Parse ``word/styles.xml`` into a resolved, flat style-property map.

DOCX styles form an inheritance chain via ``<w:basedOn>``.  Rather than
walking the chain at render time, :class:`StylesParser` resolves each
style\'s full set of properties once (lazily on first access) and caches the
result.  Callers always receive a single merged ``dict`` with no further
inheritance to apply.

The resolution order from lowest to highest priority is:

1. ``w:docDefaults`` -- document-wide run-property defaults (font, size).
2. The ``basedOn`` style chain, from the root style down.
3. The style\'s own ``<w:pPr>`` and ``<w:rPr>`` overrides.
4. Inline ``<w:pPr>`` overrides on the paragraph element itself
   (applied by :class:`~pydocx_pdf.parser.document.DocumentParser`,
   not here).

Module-level helpers :func:`_parse_ppr` and :func:`_parse_rpr` are also
used directly by :class:`~pydocx_pdf.parser.document.DocumentParser` to
parse inline overrides.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from pydocx_pdf.utils import NS, parse_xml, qn

StyleId  = str
StyleMap = dict[StyleId, dict[str, Any]]


class StylesParser:
    """Parse ``word/styles.xml`` and resolve the full DOCX style hierarchy.

    Instantiate once per document; subsequent calls to :meth:`get` are
    served from an in-memory cache.

    Parameters
    ----------
    xml_bytes:
        Raw bytes of ``word/styles.xml``.  Pass ``b""`` for documents that
        have no styles part (all calls to :meth:`get` will return an empty
        dict in that case).
    """

    def __init__(self, xml_bytes: bytes) -> None:
        self._root: ET.Element | None = None
        self._raw: dict[StyleId, dict[str, Any]] = {}
        self._resolved: StyleMap = {}
        self._doc_defaults: dict[str, Any] = {}

        if xml_bytes:
            self._root = parse_xml(xml_bytes)
            self._doc_defaults = self._parse_doc_defaults()
            self._parse_raw()

    def get(self, style_id: StyleId) -> dict[str, Any]:
        """Return the fully resolved property dict for *style_id*.

        Resolution walks the ``basedOn`` chain and merges properties from
        ``w:docDefaults`` upward, so the returned dict is a single flat
        mapping with no further inheritance indirection.

        Parameters
        ----------
        style_id:
            The ``w:styleId`` value to look up (e.g. ``"Normal"``,
            ``"Heading1"``, ``"ListParagraph"``).

        Returns
        -------
        dict
            Merged property dict.  Returns ``{}`` for unknown styles.
        """
        if style_id not in self._resolved:
            self._resolved[style_id] = self._resolve(style_id, set())
        return self._resolved[style_id]

    def default_paragraph_style(self) -> dict[str, Any]:
        """Return the resolved properties for the ``"Normal"`` style."""
        return self.get("Normal")

    def doc_default_rpr(self) -> dict[str, Any]:
        """Return the run-property defaults from ``<w:docDefaults>``."""
        return dict(self._doc_defaults)

    def _parse_doc_defaults(self) -> dict[str, Any]:
        """Extract run-property defaults from ``<w:docDefaults/w:rPrDefault/w:rPr>``."""
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
        """Populate ``_raw`` with unresolved properties for every ``<w:style>``."""
        assert self._root is not None
        for style_el in self._root.findall(f"{{{NS['w']}}}style"):
            sid = style_el.get(qn("w:styleId"), "")
            if not sid:
                continue
            self._raw[sid] = self._extract_props(style_el)

    def _extract_props(self, style_el: ET.Element) -> dict[str, Any]:
        """Return the raw (unresolved) property dict for one ``<w:style>``."""
        props: dict[str, Any] = {}

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

    def _resolve(self, sid: StyleId, seen: set[str]) -> dict[str, Any]:
        """Recursively resolve *sid* by walking its basedOn chain."""
        if sid in seen:
            return {}
        seen.add(sid)

        raw = self._raw.get(sid, {})
        based_on = raw.get("_basedOn")

        base = self._resolve(based_on, seen) if based_on else self._doc_defaults

        return {**base, **{k: v for k, v in raw.items() if k != "_basedOn"}}


def _parse_ppr(ppr: ET.Element) -> dict[str, Any]:
    """Extract paragraph-level formatting properties from a ``<w:pPr>`` element.

    Parameters
    ----------
    ppr:
        A ``<w:pPr>`` XML element from either a style definition or a
        paragraph\'s inline property block.

    Returns
    -------
    dict
        Subset of keys: ``"align"``, ``"space_before_twips"``,
        ``"space_after_twips"``, ``"line_twips"``, ``"line_rule"``,
        ``"indent_left_twips"``, ``"indent_right_twips"``,
        ``"indent_hanging_twips"``, ``"indent_first_twips"``.
    """
    props: dict[str, Any] = {}

    jc = ppr.find(f"{{{NS['w']}}}jc")
    if jc is not None:
        props["align"] = jc.get(qn("w:val"), "left")

    spacing = ppr.find(f"{{{NS['w']}}}spacing")
    if spacing is not None:
        before     = spacing.get(qn("w:before"))
        after      = spacing.get(qn("w:after"))
        line       = spacing.get(qn("w:line"))
        line_rule  = spacing.get(qn("w:lineRule"))
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
        left       = ind.get(qn("w:left"))
        right      = ind.get(qn("w:right"))
        hanging    = ind.get(qn("w:hanging"))
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


def _parse_rpr(rpr: ET.Element) -> dict[str, Any]:
    """Extract character-level (run) formatting properties from a ``<w:rPr>`` element.

    Parameters
    ----------
    rpr:
        A ``<w:rPr>`` element from a run, a style definition, or
        ``<w:docDefaults/w:rPrDefault>``.

    Returns
    -------
    dict
        Keys: ``"font_size_half_pt"``, ``"bold"``, ``"italic"``,
        ``"underline"``, ``"strike"``, ``"vert_align"``, ``"all_caps"``,
        ``"small_caps"``, ``"color"``, ``"theme_color"``, ``"font_name"``,
        ``"font_theme"``, ``"char_spacing_twentiethpt"``, ``"kern_half_pt"``,
        ``"scale_percent"``, ``"position_half_pt"``.
    """
    props: dict[str, Any] = {}

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

    u = rpr.find(f"{{{NS['w']}}}u")
    if u is not None:
        val = u.get(qn("w:val"), "single")
        props["underline"] = val not in ("none", "0", "false")

    strike = rpr.find(f"{{{NS['w']}}}strike")
    if strike is not None:
        props["strike"] = strike.get(qn("w:val"), "true") not in ("0", "false")
    if not props.get("strike"):
        dstrike = rpr.find(f"{{{NS['w']}}}dstrike")
        if dstrike is not None:
            props["strike"] = dstrike.get(qn("w:val"), "true") not in ("0", "false")

    vert = rpr.find(f"{{{NS['w']}}}vertAlign")
    if vert is not None:
        val = vert.get(qn("w:val"), "")
        if val in ("superscript", "subscript"):
            props["vert_align"] = val

    caps = rpr.find(f"{{{NS['w']}}}caps")
    if caps is not None:
        props["all_caps"] = caps.get(qn("w:val"), "true") not in ("0", "false")

    small_caps = rpr.find(f"{{{NS['w']}}}smallCaps")
    if small_caps is not None:
        props["small_caps"] = small_caps.get(qn("w:val"), "true") not in ("0", "false")

    color = rpr.find(f"{{{NS['w']}}}color")
    if color is not None:
        val = color.get(qn("w:val"))
        if val:
            props["color"] = val
        theme_color = color.get(qn("w:themeColor"))
        if theme_color:
            props["theme_color"] = theme_color

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

    spacing = rpr.find(f"{{{NS['w']}}}spacing")
    if spacing is not None:
        val = spacing.get(qn("w:val"))
        if val:
            props["char_spacing_twentiethpt"] = int(val)

    kern = rpr.find(f"{{{NS['w']}}}kern")
    if kern is not None:
        val = kern.get(qn("w:val"))
        if val:
            props["kern_half_pt"] = int(val)

    scale = rpr.find(f"{{{NS['w']}}}w")
    if scale is not None:
        val = scale.get(qn("w:val"))
        if val:
            props["scale_percent"] = int(val)

    position = rpr.find(f"{{{NS['w']}}}position")
    if position is not None:
        val = position.get(qn("w:val"))
        if val:
            props["position_half_pt"] = int(val)

    return props
