"""
Paragraph and Run data models.

A DOCX paragraph (``<w:p>``) is composed of one or more *runs* (``<w:r>``),
each carrying a fragment of text with a uniform set of character-level
formatting properties.  This module defines the two dataclasses that
represent these objects after parsing.

The flow from XML to model is::

    <w:p>                      ->  Paragraph
      <w:pPr> ... </w:pPr>     ->  Paragraph.style_props  (merged from styles)
      <w:r>                    ->  Run
        <w:rPr> ... </w:rPr>   ->  Run.props
        <w:t>Hello</w:t>       ->  Run.text = "Hello"
      </w:r>
    </w:p>
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydocx_pdf.models.image import Image


@dataclass
class Run:
    """A single formatting run within a paragraph.

    A run is the smallest unit of text in DOCX -- a contiguous sequence of
    characters that share identical character-level formatting.  One paragraph
    may contain many runs (e.g. normal text -> bold word -> normal text).

    Attributes
    ----------
    text:
        The plain text content of the run.  May be empty ("") for
        special runs such as page-break markers or image carriers.
    props:
        Raw dictionary of character formatting properties extracted from
        ``<w:rPr>``.  Use the typed properties (``is_bold``, ``font_size_pt``,
        etc.) instead of accessing this dict directly.
    image:
        When the run carries an inline ``<w:drawing>`` element rather than
        text, this holds the extracted :class:`~pydocx_pdf.models.image.Image`
        object.  ``None`` for plain text runs.

    Properties
    ----------
    is_bold, is_italic, is_underline, is_strikethrough:
        Boolean character style flags from ``<w:b>``, ``<w:i>``, ``<w:u>``,
        ``<w:strike>`` / ``<w:dstrike>``.
    vert_align:
        ``"superscript"``, ``"subscript"``, or ``None`` (from ``<w:vertAlign>``).
    is_all_caps:
        ``True`` when ``<w:caps/>`` is present (renders text in full capitals).
    is_small_caps:
        ``True`` when ``<w:smallCaps/>`` is present (renders text in small
        capitals -- implemented as uppercase at ~80% size).
    is_page_break:
        ``True`` when this run contains a ``<w:br w:type="page"/>`` marker.
        The renderer triggers ``pdf.add_page()`` and discards any text.
    font_size_pt:
        Font size in points.  ``w:sz`` stores half-points, so this divides
        by 2.  Defaults to 11 pt when absent.
    font_name:
        Explicit font family name from ``<w:rFonts w:ascii="..."/>`` or
        ``<w:rFonts w:hAnsi="..."/>``.  May differ from what is ultimately
        rendered (the :class:`~pydocx_pdf.font_map.FontRegistry` maps it to
        a bundled equivalent).
    font_theme:
        Theme font reference such as ``"minorHAnsi"`` or ``"majorBidi"``
        from ``<w:rFonts w:asciiTheme="..."/>``.  Resolved via the document
        theme to a concrete font family at render time.
    theme_color:
        Theme colour slot name from ``<w:color w:themeColor="..."/>``
        (e.g. ``"dark1"``, ``"accent1"``).
    color_hex:
        Explicit RRGGBB hex colour from ``<w:color w:val="..."/>``.
        ``"auto"`` and ``"000000"`` render as black.
    char_spacing_twentiethpt:
        Character spacing in 1/20th-point units from ``<w:spacing w:val="..."/>``
        inside ``<w:rPr>``.  Positive = expanded, negative = condensed.
        Converted to points and passed to ``fpdf2.set_char_spacing()``.
    kern_half_pt:
        Minimum font size (in half-points) at which pair kerning is applied
        (``<w:kern w:val="..."/>``).  Stored for completeness; fpdf2 does not
        expose sub-glyph kerning APIs.
    scale_percent:
        Horizontal glyph width scaling as a percentage from
        ``<w:w w:val="..."/>`` (100 = normal, 80 = condensed, 120 = expanded).
        Passed to ``fpdf2.set_stretching()``.
    position_half_pt:
        Vertical position offset in half-points from ``<w:position w:val="..."/>``.
        Positive = raised, negative = lowered.  Stored for completeness;
        fpdf2 has no direct baseline-shift API.
    """

    text: str
    props: dict[str, Any] = field(default_factory=dict)
    image: Image | None = None

    @property
    def is_bold(self) -> bool:
        """``True`` when ``<w:b/>`` is set in the run\'s ``<w:rPr>``."""
        return bool(self.props.get("bold", False))

    @property
    def is_italic(self) -> bool:
        """``True`` when ``<w:i/>`` is set in the run\'s ``<w:rPr>``."""
        return bool(self.props.get("italic", False))

    @property
    def is_underline(self) -> bool:
        """``True`` when any non-"none" underline style is set (``<w:u>``)."""
        return bool(self.props.get("underline", False))

    @property
    def is_strikethrough(self) -> bool:
        """``True`` for single (``<w:strike>``) or double (``<w:dstrike>``) strikethrough."""
        return bool(self.props.get("strike", False))

    @property
    def vert_align(self) -> str | None:
        """Return ``"superscript"``, ``"subscript"``, or ``None``."""
        return self.props.get("vert_align")

    @property
    def is_all_caps(self) -> bool:
        """``True`` when ``<w:caps/>`` forces full uppercase rendering."""
        return bool(self.props.get("all_caps", False))

    @property
    def is_small_caps(self) -> bool:
        """``True`` when ``<w:smallCaps/>`` forces small-capitals rendering."""
        return bool(self.props.get("small_caps", False))

    @property
    def is_page_break(self) -> bool:
        """``True`` when this run carries a ``<w:br w:type="page"/>`` marker."""
        return bool(self.props.get("page_break", False))

    @property
    def font_size_pt(self) -> float:
        """Font size in points (``w:sz`` / 2).  Defaults to 11.0 pt."""
        hp = self.props.get("font_size_half_pt")
        return hp / 2 if hp else 11.0

    @property
    def font_name(self) -> str | None:
        """Explicit font family name, or ``None`` if not set."""
        return self.props.get("font_name")

    @property
    def font_theme(self) -> str | None:
        """Theme font reference (e.g. ``"minorHAnsi"``), or ``None``."""
        return self.props.get("font_theme")

    @property
    def theme_color(self) -> str | None:
        """Theme colour slot name (e.g. ``"dark1"``), or ``None``."""
        return self.props.get("theme_color")

    @property
    def color_hex(self) -> str | None:
        """Explicit RRGGBB hex colour string (e.g. ``"1F3864"``), or ``None``."""
        return self.props.get("color")

    @property
    def char_spacing_twentiethpt(self) -> int:
        """Character spacing in 1/20th-point units.  0 = normal spacing."""
        return int(self.props.get("char_spacing_twentiethpt", 0))

    @property
    def kern_half_pt(self) -> int | None:
        """Kerning threshold in half-points, or ``None`` if not specified."""
        return self.props.get("kern_half_pt")

    @property
    def scale_percent(self) -> int:
        """Horizontal glyph width scaling percentage.  100 = normal width."""
        return int(self.props.get("scale_percent", 100))

    @property
    def position_half_pt(self) -> int:
        """Vertical position offset in half-points.  0 = baseline."""
        return int(self.props.get("position_half_pt", 0))


@dataclass
class Paragraph:
    """A parsed DOCX paragraph, ready for rendering.

    Combines the paragraph\'s resolved style properties with its ordered list
    of :class:`Run` objects.  List items carry additional pre-computed fields
    (``list_label``, ``list_indent_twips``, ``list_hanging_twips``) so the
    renderer never needs to access the numbering definitions directly.

    Attributes
    ----------
    style_id:
        The style name referenced by ``<w:pStyle w:val="..."/>``.  Defaults to
        ``"Normal"``.  Used to look up heading sizes, spacing, etc.
    style_props:
        Merged dictionary of paragraph-level formatting properties resolved
        from the named style and any inline ``<w:pPr>`` overrides.  Keys
        include ``"align"``, ``"space_before_twips"``, ``"space_after_twips"``,
        ``"line_twips"``, ``"line_rule"``, ``"indent_left_twips"``, etc.
    runs:
        Ordered list of :class:`Run` objects forming the paragraph content.
        An empty list represents a blank paragraph (vertical gap).
    num_id:
        Numbering definition ID from ``<w:numId w:val="..."/>``.  ``None``
        for non-list paragraphs.
    ilvl:
        Zero-based list nesting level from ``<w:ilvl w:val="..."/>``.  Only
        meaningful when :attr:`num_id` is set.
    list_counter:
        Current counter value for ordered lists, advanced by
        :meth:`~pydocx_pdf.parser.numbering.NumberingParser.next_count` at
        parse time.  ``None`` for bullet lists and non-list paragraphs.
    list_label:
        Pre-formatted marker string, e.g. ``"1."``, ``"a."``, ``"*"``,
        ``"iii."``.  ``None`` for non-list paragraphs.
    list_indent_twips:
        Distance in twips from the page left margin to the start of the list
        item text (= ``w:ind/@w:left`` from the list level definition).
        Defaults to 720 twips (0.5 inch).
    list_hanging_twips:
        Width of the marker column in twips (= ``w:ind/@w:hanging``).  The
        marker is right-aligned within this column; text begins at
        ``list_indent_twips``.  Defaults to 360 twips (0.25 inch).
    """

    style_id: str = "Normal"
    style_props: dict[str, Any] = field(default_factory=dict)
    runs: list[Run] = field(default_factory=list)
    num_id: str | None = None
    ilvl: int = 0
    list_counter: int | None = None

    list_label: str | None = None
    list_indent_twips: int = 720
    list_hanging_twips: int = 360

    @property
    def is_list_item(self) -> bool:
        """``True`` when this paragraph belongs to a numbered or bullet list."""
        return self.num_id is not None

    @property
    def full_text(self) -> str:
        """Concatenation of all run texts (no formatting, no transforms)."""
        return "".join(r.text for r in self.runs)
