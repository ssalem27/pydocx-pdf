"""
Parse ``word/theme/theme1.xml`` -- document font and colour scheme.

The DOCX theme defines:

- **Font scheme** (``<a:fontScheme>``): ``majorFont`` (used for headings)
  and ``minorFont`` (used for body text).  In modern Word documents these
  are typically ``"Calibri Light"`` and ``"Calibri"``.
- **Colour scheme** (``<a:clrScheme>``): Named colour slots such as
  ``dk1``/``dk2`` (dark), ``lt1``/``lt2`` (light), and ``accent1``--``accent6``.

These values allow run properties that reference theme slots
(``w:themeColor="dark1"``, ``w:asciiTheme="minorHAnsi"``) to be resolved
to concrete hex colours and font families at render time.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

# DrawingML main namespace (theme XML uses the 'a:' prefix)
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


@dataclass
class Theme:
    """Document-level theme: fonts and colour scheme.

    Produced by :func:`parse_theme` and passed to
    :class:`~pydocx_pdf.renderer.pdf_writer.PDFWriter` which passes the font
    names through to :class:`~pydocx_pdf.font_map.FontRegistry`.

    Attributes
    ----------
    major_font:
        The heading font family name (``<a:majorFont>/<a:latin typeface="..."/>``),
        or ``None`` if absent.  Typically ``"Calibri Light"`` in modern
        Word documents.
    minor_font:
        The body font family name (``<a:minorFont>/<a:latin typeface="..."/>``),
        or ``None`` if absent.  Typically ``"Calibri"`` or ``"Aptos"`` in
        modern Word documents.
    colors:
        Mapping of colour scheme slot name to resolved 6-character RRGGBB
        hex string.  Keys include ``"dk1"``, ``"dk2"``, ``"lt1"``,
        ``"lt2"``, ``"accent1"`` ... ``"accent6"``, ``"hlink"``, etc.
        Only slots present in the XML appear in this dict.
    """

    major_font: str | None = None
    minor_font: str | None = None
    colors: dict[str, str] = field(default_factory=dict)


def parse_theme(xml_bytes: bytes) -> Theme:
    """Parse theme XML and return a :class:`Theme` instance.

    Parameters
    ----------
    xml_bytes:
        Raw bytes of ``word/theme/theme1.xml``.  Pass ``b""`` (or any
        falsy value) for documents with no theme; a :class:`Theme` with
        ``None`` fonts and an empty colour dict is returned in that case.

    Returns
    -------
    Theme
        Populated theme object.  Never raises -- malformed XML results in a
        default :class:`Theme()` rather than an exception, so the conversion
        can continue with fallback fonts.
    """
    if not xml_bytes:
        return Theme()

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        # Silently ignore a broken theme rather than aborting the conversion.
        return Theme()

    theme = Theme()
    _parse_fonts(root, theme)
    _parse_colors(root, theme)
    return theme


def _parse_fonts(root: ET.Element, theme: Theme) -> None:
    """Populate *theme* font fields from ``<a:fontScheme>``."""
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
    """Populate *theme* colour map from ``<a:clrScheme>``."""
    a = _A_NS
    clr_scheme = root.find(f".//{{{a}}}clrScheme")
    if clr_scheme is None:
        return

    for child in clr_scheme:
        # Tag is like ``{uri}dk1``, ``{uri}accent1``, etc.
        name = child.tag.split("}")[-1]

        # Explicit sRGB colour value
        srgb = child.find(f"{{{a}}}srgbClr")
        if srgb is not None:
            val = srgb.get("val")
            if val:
                theme.colors[name] = val
                continue

        # System colour -- use the ``lastClr`` resolved value
        sys_clr = child.find(f"{{{a}}}sysClr")
        if sys_clr is not None:
            val = sys_clr.get("lastClr")
            if val:
                theme.colors[name] = val
