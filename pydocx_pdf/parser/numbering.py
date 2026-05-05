"""
Parse ``word/numbering.xml`` and resolve DOCX list definitions.

DOCX numbering model
---------------------
``word/numbering.xml`` contains two groups of elements:

``<w:abstractNum>``
    Template definitions.  Each one defines up to 9 list levels (``<w:lvl>``),
    specifying the number format, marker text, indentation, and starting value.
    These are *blueprints*, not tied to any specific list in the document.

``<w:num>``
    Concrete instances.  Each one references an ``abstractNum`` by ID and
    may override individual levels.  Paragraphs reference a ``<w:num>`` via
    ``<w:numId w:val="..."/>`` in their ``<w:pPr>``.

Resolution order
----------------
For a paragraph with ``numId="3"`` and ``ilvl="1"``:

1. Look up ``<w:num numId="3">`` -> its ``abstractNumId`` reference.
2. Check if that ``<w:num>`` has a ``<w:lvlOverride ilvl="1">`` -> use it.
3. Otherwise fall back to the referenced ``<w:abstractNum>`` -> level 1.

Counter management
------------------
:class:`NumberingParser` maintains per-(numId, ilvl) counters that are
advanced by :meth:`next_count` in document order.  Advancing level N
automatically resets all deeper levels (N+1 ... 8), matching Word behaviour.
"""

from __future__ import annotations

import re as _re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from pydocx_pdf.utils import NS, parse_xml, qn


def _to_alpha(n: int, upper: bool = False) -> str:
    """Convert a 1-based counter to an alphabetic string.

    Follows the same pattern as Excel columns: 1->a, 26->z, 27->aa, etc.

    Parameters
    ----------
    n:
        Positive integer to convert (1-based).
    upper:
        When ``True``, return uppercase letters.

    Returns
    -------
    str
        The alphabetic representation (e.g. ``"a"``, ``"z"``, ``"aa"``).
    """
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(ord("A" if upper else "a") + rem) + result
    return result


def _to_roman(n: int, upper: bool = True) -> str:
    """Convert a positive integer to a Roman numeral string.

    Parameters
    ----------
    n:
        Positive integer to convert.
    upper:
        When ``True`` (the default), return uppercase numerals (I, V, X ...).

    Returns
    -------
    str
        Roman numeral string, e.g. ``"XIV"`` or ``"xiv"``.
    """
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
    """Format *count* according to a DOCX ``numFmt`` value.

    Parameters
    ----------
    count:
        Current counter value (1-based).
    num_fmt:
        DOCX number-format string.  Handled values: ``"decimal"``,
        ``"lowerLetter"``, ``"upperLetter"``, ``"lowerRoman"``,
        ``"upperRoman"``.  All other values fall back to decimal.

    Returns
    -------
    str
        Formatted counter string (e.g. ``"1"``, ``"a"``, ``"iii"``).
    """
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
        return str(count)


@dataclass
class LevelDef:
    """Definition of one list level within an ``<w:abstractNum>``.

    Attributes
    ----------
    level:
        Zero-based nesting level index (0 = outermost).
    num_fmt:
        DOCX number-format string: ``"bullet"``, ``"decimal"``,
        ``"lowerLetter"``, ``"upperRoman"``, etc.
    level_text:
        The marker template string.  For bullets this is the literal
        character (``"*"``, ``"-"``).  For numbered lists it is a pattern
        such as ``"%1."`` where ``%N`` is a placeholder for the counter at
        level N-1 (1-based).
    indent_left_twips:
        Left indent in twips for text in this list item (``w:ind/@w:left``).
    hanging_twips:
        Hanging indent in twips (``w:ind/@w:hanging``).
    start_value:
        The initial counter value for this level (``w:start/@w:val``),
        typically 1.
    """

    level: int = 0
    num_fmt: str = "bullet"
    level_text: str = "*"
    indent_left_twips: int = 720
    hanging_twips: int = 360
    start_value: int = 1


@dataclass
class AbstractNum:
    """A DOCX ``<w:abstractNum>`` -- a template list definition.

    Attributes
    ----------
    abstract_num_id:
        The ``w:abstractNumId`` attribute value.
    levels:
        Mapping of level index (0-8) to :class:`LevelDef`.
    """

    abstract_num_id: str = ""
    levels: dict[int, LevelDef] = field(default_factory=dict)


@dataclass
class ConcreteNum:
    """A DOCX ``<w:num>`` -- a concrete list instance.

    Attributes
    ----------
    num_id:
        The ``w:numId`` attribute value referenced by paragraph ``<w:numPr>``.
    abstract_num_id:
        The ``<w:abstractNumId w:val="..."/>`` reference.
    level_overrides:
        Level definitions that override the abstract template for specific
        levels (``<w:lvlOverride>``).  Keyed by level index.
    """

    num_id: str = ""
    abstract_num_id: str = ""
    level_overrides: dict[int, LevelDef] = field(default_factory=dict)


class NumberingParser:
    """Parse ``word/numbering.xml`` and track per-list counters.

    Maintains stateful counters that advance as paragraphs are parsed in
    document order, so that ordered list markers (``"1."``, ``"2."``, ...) are
    always correct even across nested levels.

    Parameters
    ----------
    xml_bytes:
        Raw bytes of ``word/numbering.xml``.  Pass ``b""`` for documents
        with no lists; all public methods return safe defaults in that case.
    """

    def __init__(self, xml_bytes: bytes) -> None:
        self._abstract: dict[str, AbstractNum] = {}
        self._concrete: dict[str, ConcreteNum] = {}
        self._counters: dict[tuple[str, int], int] = {}

        if xml_bytes:
            root = parse_xml(xml_bytes)
            self._parse(root)

    def get_level_def(self, num_id: str, ilvl: int) -> LevelDef | None:
        """Return the effective :class:`LevelDef` for *num_id* / *ilvl*.

        Checks level overrides on the concrete ``<w:num>`` first, then
        falls back to the referenced ``<w:abstractNum>``.

        Parameters
        ----------
        num_id:
            Concrete numbering ID referenced by the paragraph.
        ilvl:
            Zero-based list nesting level.

        Returns
        -------
        LevelDef or None
            ``None`` when *num_id* is not registered.
        """
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
        """Advance the counter for *(num_id, ilvl)* and return the new value.

        Also resets all deeper levels (``ilvl + 1`` ... 8).

        Parameters
        ----------
        num_id:
            Concrete numbering ID.
        ilvl:
            Zero-based list level being advanced.

        Returns
        -------
        int
            The new counter value (1-based).
        """
        key = (num_id, ilvl)
        self._counters[key] = self._counters.get(key, 0) + 1
        for lvl in range(ilvl + 1, 9):
            self._counters.pop((num_id, lvl), None)
        return self._counters[key]

    def get_current_counters(self, num_id: str) -> dict[int, int]:
        """Return a snapshot of all current counter values for *num_id*.

        Parameters
        ----------
        num_id:
            Concrete numbering ID.

        Returns
        -------
        dict
            Mapping of level index -> current counter value.
        """
        return {
            ilvl: count
            for (nid, ilvl), count in self._counters.items()
            if nid == num_id
        }

    def format_marker(self, num_id: str, ilvl: int) -> str:
        """Return the fully formatted list marker for the current state.

        Parameters
        ----------
        num_id:
            Concrete numbering ID.
        ilvl:
            Zero-based level index (must have been advanced by
            :meth:`next_count` before calling this).

        Returns
        -------
        str
            Formatted marker string (e.g. ``"1."``, ``"a."``, ``"*"``).
        """
        level_def = self.get_level_def(num_id, ilvl)
        if level_def is None:
            return "*"

        if level_def.num_fmt == "bullet":
            return level_def.level_text or "*"

        counters   = self.get_current_counters(num_id)
        level_text = level_def.level_text

        if not level_text:
            return _format_counter(counters.get(ilvl, 1), level_def.num_fmt) + "."

        def _replace(m: _re.Match) -> str:  # type: ignore[type-arg]
            lvl_0 = int(m.group(1)) - 1
            count = counters.get(lvl_0, 1)
            ldef  = self.get_level_def(num_id, lvl_0)
            fmt   = ldef.num_fmt if ldef else "decimal"
            return _format_counter(count, fmt)

        return _re.sub(r"%(\d+)", _replace, level_text)

    def _parse(self, root: ET.Element) -> None:
        """Populate ``_abstract`` and ``_concrete`` from the numbering XML root."""
        w = NS["w"]

        for an_el in root.findall(f"{{{w}}}abstractNum"):
            an_id = an_el.get(qn("w:abstractNumId"), "")
            levels: dict[int, LevelDef] = {}
            for lvl_el in an_el.findall(f"{{{w}}}lvl"):
                ilvl = int(lvl_el.get(qn("w:ilvl"), "0"))
                levels[ilvl] = _parse_level(lvl_el)
            self._abstract[an_id] = AbstractNum(abstract_num_id=an_id, levels=levels)

        for num_el in root.findall(f"{{{w}}}num"):
            num_id = num_el.get(qn("w:numId"), "")
            an_ref = num_el.find(f"{{{w}}}abstractNumId")
            an_id  = an_ref.get(qn("w:val"), "") if an_ref is not None else ""
            overrides: dict[int, LevelDef] = {}
            for ovr in num_el.findall(f"{{{w}}}lvlOverride"):
                ilvl   = int(ovr.get(qn("w:ilvl"), "0"))
                ovr_lvl: ET.Element | None = ovr.find(f"{{{w}}}lvl")
                if ovr_lvl is not None:
                    overrides[ilvl] = _parse_level(ovr_lvl)
            self._concrete[num_id] = ConcreteNum(
                num_id=num_id,
                abstract_num_id=an_id,
                level_overrides=overrides,
            )


def _parse_level(lvl_el: ET.Element) -> LevelDef:
    """Parse one ``<w:lvl>`` element into a :class:`LevelDef`.

    Parameters
    ----------
    lvl_el:
        A ``<w:lvl>`` element from either an ``<w:abstractNum>`` or a
        ``<w:lvlOverride>`` within a ``<w:num>``.

    Returns
    -------
    LevelDef
        Populated level definition with sensible defaults.
    """
    w    = NS["w"]
    ilvl = int(lvl_el.get(qn("w:ilvl"), "0"))

    def _text(tag: str) -> str | None:
        el = lvl_el.find(f"{{{w}}}{tag}")
        return el.get(qn("w:val")) if el is not None else None

    num_fmt = _text("numFmt") or "bullet"

    level_text_el = lvl_el.find(f"{{{w}}}lvlText")
    level_text    = (
        level_text_el.get(qn("w:val"), "*")
        if level_text_el is not None else "*"
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
