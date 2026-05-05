"""
Shared utility functions -- XML helpers and unit conversions.

OOXML (Office Open XML) uses a variety of measurement units internally.
This module centralises all conversions so the rest of the codebase can
express values in the unit that is most natural to each context.

Unit reference
--------------
- **EMU** (English Metric Unit): 914400 per inch, 12700 per point.  Used
  for drawing extents (``<wp:extent cx="..." cy="..."/>``).
- **Twips** (twentieth of a point): 20 per point, 1440 per inch.  Used for
  paragraph indentation, spacing, and page margins (``w:ind``, ``w:spacing``).
- **Half-points**: 2 per point.  Used for font size (``w:sz``).
- **Points**: 72 per inch.  Used internally by fpdf2 for most measurements.
- **Millimetres**: fpdf2\'s default coordinate unit for page layout.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# XML namespace map
# ---------------------------------------------------------------------------

NS: dict[str, str] = {
    # WordprocessingML -- the main document namespace
    "w":   "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    # Relationships namespace -- used in .rels files and r:embed attributes
    "r":   "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    # DrawingML -- used for theme colours, fonts, and inline drawing elements
    "a":   "http://schemas.openxmlformats.org/drawingml/2006/main",
    # WordprocessingML Drawing -- used for inline/anchor image extent
    "wp":  "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    # Markup Compatibility -- mc:AlternateContent wrappers
    "mc":  "http://schemas.openxmlformats.org/markup-compatibility/2006",
    # Word 2010 extensions
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    # Word 2010 Processing Shape
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
}


def qn(tag: str) -> str:
    """Expand a prefixed XML tag to Clark notation.

    Converts ``"w:p"`` to ``"{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"``
    so the result can be passed directly to :meth:`xml.etree.ElementTree.Element.find`
    and related methods.

    Parameters
    ----------
    tag:
        A namespace-prefixed tag such as ``"w:pPr"``, ``"a:blip"``, or
        ``"wp:extent"``.  The prefix must be a key in :data:`NS`.

    Returns
    -------
    str
        The Clark-notation equivalent, e.g. ``"{uri}localname"``.

    Raises
    ------
    KeyError
        If the namespace prefix is not registered in :data:`NS`.
    ValueError
        If *tag* does not contain a colon separator.

    Examples
    --------
    >>> qn("w:p")
    \'{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p\'
    """
    prefix, local = tag.split(":", 1)
    return f"{{{NS[prefix]}}}{local}"


def get_attr(el: ET.Element, tag: str, default: str | None = None) -> str | None:
    """Return the value of an attribute on *el*, expanding the namespace prefix.

    A convenience wrapper around :meth:`xml.etree.ElementTree.Element.get`
    that accepts ``"w:val"``-style attribute names and handles the Clark
    notation expansion automatically.

    Parameters
    ----------
    el:
        The XML element to inspect.
    tag:
        Namespace-prefixed attribute name (e.g. ``"w:val"``).
    default:
        Value to return when the attribute is absent.  Defaults to ``None``.

    Returns
    -------
    str or None
        The attribute value, or *default* if not present.
    """
    return el.get(qn(tag), default)


def parse_xml(data: bytes) -> ET.Element:
    """Parse UTF-8 XML bytes and return the root element.

    Parameters
    ----------
    data:
        Raw XML bytes (e.g. the contents of ``word/document.xml``).

    Returns
    -------
    xml.etree.ElementTree.Element
        The root element of the parsed document.

    Raises
    ------
    xml.etree.ElementTree.ParseError
        If *data* is not well-formed XML.
    """
    return ET.fromstring(data)


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------

def emu_to_pt(emu: int) -> float:
    """Convert English Metric Units to points.

    Parameters
    ----------
    emu:
        Value in EMU.  1 point = 12700 EMU.

    Returns
    -------
    float
        Equivalent value in points.

    Examples
    --------
    >>> emu_to_pt(914400)   # 1 inch = 72 pt
    72.0
    >>> emu_to_pt(12700)    # 1 pt
    1.0
    """
    return emu / 12700


def twips_to_pt(twips: int) -> float:
    """Convert twips to points.

    Parameters
    ----------
    twips:
        Value in twips (twentieths of a point).  1 point = 20 twips.

    Returns
    -------
    float
        Equivalent value in points.

    Examples
    --------
    >>> twips_to_pt(720)    # 0.5 inch = 36 pt
    36.0
    >>> twips_to_pt(20)     # 1 pt
    1.0
    """
    return twips / 20


def half_pt_to_pt(hp: int) -> float:
    """Convert half-points to points.

    DOCX stores font sizes in half-points (``w:sz``).  For example,
    a 12pt font is stored as ``w:sz val="24"``.

    Parameters
    ----------
    hp:
        Value in half-points.  1 point = 2 half-points.

    Returns
    -------
    float
        Equivalent value in points.

    Examples
    --------
    >>> half_pt_to_pt(24)   # 12 pt font
    12.0
    >>> half_pt_to_pt(22)   # 11 pt font
    11.0
    """
    return hp / 2


def inches_to_pt(inches: float) -> float:
    """Convert inches to points.

    Parameters
    ----------
    inches:
        Value in inches.  1 inch = 72 points.

    Returns
    -------
    float
        Equivalent value in points.

    Examples
    --------
    >>> inches_to_pt(1.0)   # 1 inch
    72.0
    >>> inches_to_pt(0.5)   # half an inch
    36.0
    """
    return inches * 72


def pt_to_mm(pt: float) -> float:
    """Convert points to millimetres.

    Used when translating point-based DOCX measurements to the mm coordinate
    system used by fpdf2 for page layout.

    Parameters
    ----------
    pt:
        Value in points.  1 mm = 2.8346 pt (approx).

    Returns
    -------
    float
        Equivalent value in millimetres.

    Examples
    --------
    >>> round(pt_to_mm(72), 4)   # 1 inch in mm
    25.4
    """
    return pt / 2.8346456692913385


def mm_to_pt(mm: float) -> float:
    """Convert millimetres to points.

    Parameters
    ----------
    mm:
        Value in millimetres.

    Returns
    -------
    float
        Equivalent value in points.

    Examples
    --------
    >>> round(mm_to_pt(25.4), 4)   # 1 inch in points
    72.0
    """
    return mm * 2.8346456692913385
