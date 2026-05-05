"""
Font name resolution: map DOCX font names to registered PDF font families.

Word documents reference fonts by name ("Arial", "Calibri",
"Times New Roman", etc.) that are not embedded in the PDF output.
This module maps those names to the bundled Liberation and DejaVu font
families using a multi-tier resolution strategy.

Resolution order
----------------
1. **Exact match** (case-insensitive) against already-registered PDF families.
2. **Genre lookup** -- the font name is looked up in one of three frozen sets:
   ``_SANS_SERIF``, ``_SERIF``, or ``_MONO``.  The first registered candidate
   from the corresponding priority list is returned.
3. **Substring heuristics** -- if the name contains ``"mono"``, ``"code"``,
   ``"courier"``, etc., it is treated as monospace; ``"serif"``, ``"roman"``,
   etc. as serif.
4. **Fallback** -- the registry\'s ``minor_family`` (body font) or
   ``major_family`` (heading font) is used when all other steps fail.

Bundled font families and their DOCX equivalents
-------------------------------------------------
- ``LiberationSans``  -- Arial, Helvetica, Tahoma, Verdana, Calibri, Aptos ...
- ``LiberationSerif`` -- Times New Roman, Georgia, Garamond, Cambria ...
- ``LiberationMono``  -- Courier New, Consolas, Monaco, Inconsolata ...
- ``DejaVuSans``      -- Unicode fallback for all other sans-serif requests
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Genre sets (lower-cased font names -> genre bucket)
# ---------------------------------------------------------------------------

_SANS_SERIF: frozenset[str] = frozenset({
    # Microsoft / Office defaults
    "calibri", "calibri light", "calibri (body)", "calibri (headings)",
    "arial", "arial narrow", "arial black", "arial unicode ms",
    "helvetica", "helvetica neue",
    "tahoma", "verdana", "trebuchet ms",
    "gill sans", "gill sans mt",
    "century gothic", "franklin gothic medium",
    "segoe ui", "segoe ui light", "segoe ui semibold", "segoe ui semilight",
    # Office 2024 defaults
    "aptos", "aptos narrow", "aptos display",
    # Web / system
    "myriad pro", "open sans", "lato", "roboto", "source sans pro",
    "noto sans", "inter", "nunito", "poppins", "montserrat", "raleway",
    "ubuntu", "droid sans", "pt sans", "fira sans", "oxygen",
    "system-ui", "ui-sans-serif",
    # Bundled families (exact-match fallback)
    "liberationsans",
    # Generic CSS name
    "sans-serif",
})

_SERIF: frozenset[str] = frozenset({
    # Classic
    "times new roman", "times", "times roman",
    "georgia", "garamond", "eb garamond",
    "book antiqua", "palatino", "palatino linotype",
    "century", "cambria", "constantia", "cochin",
    "didot", "baskerville", "caslon", "bodoni mt",
    "high tower text", "hoefler text",
    # Web / modern
    "source serif pro", "source serif 4",
    "noto serif", "merriweather", "pt serif", "lora",
    "playfair display", "cormorant garamond", "libre baskerville",
    "charter", "bitstream charter", "computer modern",
    # Bundled families
    "liberationserif",
    # Generic CSS name
    "ui-serif", "serif",
})

_MONO: frozenset[str] = frozenset({
    "courier new", "courier",
    "consolas", "monaco", "menlo",
    "inconsolata", "source code pro", "fira code", "fira mono",
    "jetbrains mono", "cascadia code", "cascadia mono",
    "roboto mono", "ubuntu mono", "droid sans mono",
    "lucida console", "lucida sans typewriter",
    "andale mono", "dejavu sans mono",
    "noto mono", "pt mono", "space mono", "ibm plex mono",
    # Bundled families
    "liberationmono",
    # Generic CSS names
    "ui-monospace", "monospace", "monospaced", "fixed",
})

# ---------------------------------------------------------------------------
# Candidate family lists -- tried in priority order (first registered wins)
# ---------------------------------------------------------------------------

_SANS_CANDIDATES:  tuple[str, ...] = ("LiberationSans",  "DejaVuSans",    "Helvetica", "Arial")
_SERIF_CANDIDATES: tuple[str, ...] = ("LiberationSerif", "DejaVuSerif",   "NotoSerif", "Times", "DejaVuSans")
_MONO_CANDIDATES:  tuple[str, ...] = ("LiberationMono",  "DejaVuSansMono","Courier",            "DejaVuSans")

# ---------------------------------------------------------------------------
# Substring heuristics (used when the exact genre lookup fails)
# ---------------------------------------------------------------------------

_MONO_HINTS  = ("mono", "code", "console", "courier", "typewriter", "fixed")
_SERIF_HINTS = ("serif", "roman", "times", "garamond", "caslon", "bodoni",
                "palatino", "georgia", "cambria", "baskerville")


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class FontRegistry:
    """Resolve DOCX font names to registered PDF font families.

    This class is constructed once per document render and shared between
    :class:`~pydocx_pdf.renderer.paragraph.ParagraphRenderer` and
    :class:`~pydocx_pdf.renderer.table.TableRenderer`.

    Parameters
    ----------
    registered:
        Set of font family names that have been registered with fpdf2 (via
        ``pdf.add_font()``).  Used to select the best available candidate.
    major_font:
        The document theme\'s heading font name (e.g. ``"Calibri Light"``),
        or ``None``.  Resolved to a registered family at construction time.
    minor_font:
        The document theme\'s body font name (e.g. ``"Calibri"``), or
        ``None``.  Resolved to a registered family at construction time.

    Attributes
    ----------
    major_family:
        Resolved registered PDF family name for headings.
    minor_family:
        Resolved registered PDF family name for body text.
    """

    def __init__(
        self,
        registered: set[str],
        major_font: str | None = None,
        minor_font: str | None = None,
    ) -> None:
        self._reg_lower: set[str]       = {f.lower() for f in registered}
        self._reg_raw:   dict[str, str] = {f.lower(): f for f in registered}

        self.major_family: str = (
            self._resolve_name(major_font) if major_font
            else self._best(_SANS_CANDIDATES)
        )
        self.minor_family: str = (
            self._resolve_name(minor_font) if minor_font
            else self._best(_SANS_CANDIDATES)
        )

        self._cache: dict[str, str] = {}

    def resolve(self, font_name: str | None, *, for_heading: bool = False) -> str:
        """Return the best registered PDF font family for *font_name*.

        Parameters
        ----------
        font_name:
            The DOCX font family name to resolve (e.g. ``"Arial"``,
            ``"Times New Roman"``).  Pass ``None`` to get the theme
            body/heading font.
        for_heading:
            When ``True``, use ``major_family`` as the fallback instead of
            ``minor_family``.  Set this for runs inside heading paragraphs.

        Returns
        -------
        str
            A registered PDF font family name (never empty).
        """
        fallback = self.major_family if for_heading else self.minor_family
        if not font_name:
            return fallback
        key = font_name.strip().lower()
        if key in self._cache:
            return self._cache[key]
        result = self._resolve_name(font_name) or fallback
        self._cache[key] = result
        return result

    def resolve_theme_ref(self, theme_ref: str | None) -> str | None:
        """Resolve a ``w:asciiTheme`` / ``w:hAnsiTheme`` attribute value.

        Parameters
        ----------
        theme_ref:
            A theme font reference string such as ``"minorHAnsi"``,
            ``"majorBidi"``, or ``"minorLatin"``.

        Returns
        -------
        str or None
            The resolved font family, or ``None`` if *theme_ref* is not
            recognised as a major/minor reference.
        """
        if not theme_ref:
            return None
        ref = theme_ref.strip().lower()
        if ref.startswith("major"):
            return self.major_family
        if ref.startswith("minor"):
            return self.minor_family
        return None

    def is_registered(self, family: str) -> bool:
        """Return ``True`` if *family* is in the registered font set.

        Parameters
        ----------
        family:
            Font family name to check (case-insensitive).
        """
        return family.lower() in self._reg_lower

    def _resolve_name(self, font_name: str) -> str:
        """Map a DOCX font name to the best registered PDF family.

        Applies the four-tier resolution strategy described in the module
        docstring.

        Returns ``""`` if no match is found (caller applies the fallback).
        """
        key = font_name.strip().lower()

        # Tier 1: exact (case-insensitive) match against registered families
        if key in self._reg_lower:
            return self._reg_raw[key]

        # Tier 2: genre set lookup
        if key in _SANS_SERIF:
            return self._best(_SANS_CANDIDATES)
        if key in _SERIF:
            return self._best(_SERIF_CANDIDATES)
        if key in _MONO:
            return self._best(_MONO_CANDIDATES)

        # Tier 3: substring heuristics
        if any(h in key for h in _MONO_HINTS):
            return self._best(_MONO_CANDIDATES)
        if any(h in key for h in _SERIF_HINTS) and "sans" not in key:
            return self._best(_SERIF_CANDIDATES)

        # Tier 4: no match
        return ""

    def _best(self, candidates: tuple[str, ...]) -> str:
        """Return the first registered candidate in *candidates*.

        Returns the last entry as an absolute fallback if none are registered.
        """
        for c in candidates:
            if c.lower() in self._reg_lower:
                return self._reg_raw.get(c.lower(), c)
        return candidates[-1]
