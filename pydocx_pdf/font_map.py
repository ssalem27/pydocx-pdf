"""
Font name resolution: map DOCX/Word font names to registered PDF font families.

Word documents (especially LLM-generated ones) reference fonts like Calibri,
Arial, Times New Roman, etc. that are not embedded in the PDF.  This module
maps those names to bundled fallback families based on genre heuristics.

Resolution order
----------------
1. Exact match (case-insensitive) against already-registered PDF families.
2. Genre lookup (sans-serif / serif / monospace sets).
3. Substring heuristics (e.g. anything containing "mono" → monospace).
4. Fall back to the theme body or heading family.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Genre sets  (lower-cased font names)
# ---------------------------------------------------------------------------

_SANS_SERIF: FrozenSet[str] = frozenset({
    # Microsoft / Office defaults
    "calibri", "calibri light", "calibri (body)", "calibri (headings)",
    "arial", "arial narrow", "arial black", "arial unicode ms",
    "helvetica", "helvetica neue",
    "tahoma", "verdana", "trebuchet ms",
    "gill sans", "gill sans mt",
    "century gothic", "franklin gothic medium",
    "segoe ui", "segoe ui light", "segoe ui semibold", "segoe ui semilight",
    "aptos", "aptos narrow", "aptos display",   # Office 2024 defaults
    # Web / system
    "myriad pro", "open sans", "lato", "roboto", "source sans pro",
    "noto sans", "inter", "nunito", "poppins", "montserrat", "raleway",
    "ubuntu", "droid sans", "pt sans", "fira sans", "oxygen",
    "system-ui", "ui-sans-serif",
    "liberationsans",  # Bundled font for Arial
    # Generic
    "sans-serif",
})

_SERIF: FrozenSet[str] = frozenset({
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
    "liberationserif",  # Bundled font for Times New Roman
    "ui-serif",
    # Generic
    "serif",
})

_MONO: FrozenSet[str] = frozenset({
    "courier new", "courier",
    "consolas", "monaco", "menlo",
    "inconsolata", "source code pro", "fira code", "fira mono",
    "jetbrains mono", "cascadia code", "cascadia mono",
    "roboto mono", "ubuntu mono", "droid sans mono",
    "lucida console", "lucida sans typewriter",
    "andale mono", "dejavu sans mono",
    "noto mono", "pt mono", "space mono", "ibm plex mono",
    "liberationmono",  # Bundled font for Courier
    "ui-monospace",
    # Generic
    "monospace", "monospaced", "fixed",
})

# ---------------------------------------------------------------------------
# Candidate families tried in priority order (first registered one wins)
# ---------------------------------------------------------------------------

_SANS_CANDIDATES:  Tuple[str, ...] = ("LiberationSans", "DejaVuSans",    "Helvetica", "Arial")
_SERIF_CANDIDATES: Tuple[str, ...] = ("LiberationSerif", "DejaVuSerif",   "NotoSerif", "Times",   "DejaVuSans")
_MONO_CANDIDATES:  Tuple[str, ...] = ("LiberationMono",  "DejaVuSansMono","Courier",              "DejaVuSans")

# ---------------------------------------------------------------------------
# Substring heuristics (checked when exact genre lookup fails)
# ---------------------------------------------------------------------------

_MONO_HINTS  = ("mono", "code", "console", "courier", "typewriter", "fixed")
_SERIF_HINTS = ("serif", "roman", "times", "garamond", "caslon", "bodoni",
                "palatino", "georgia", "cambria", "baskerville")


# ---------------------------------------------------------------------------

class FontRegistry:
    """Resolves DOCX font names to registered PDF font families."""

    def __init__(
        self,
        registered: Set[str],
        major_font: Optional[str] = None,
        minor_font: Optional[str] = None,
    ) -> None:
        # Case-insensitive lookup set + raw-case map for returning correct name
        self._reg_lower: Set[str] = {f.lower() for f in registered}
        self._reg_raw:  Dict[str, str] = {f.lower(): f for f in registered}

        # Resolve theme font names → registered families (or best fallback)
        self.major_family: str = (
            self._resolve_name(major_font) if major_font
            else self._best(_SANS_CANDIDATES)
        )
        self.minor_family: str = (
            self._resolve_name(minor_font) if minor_font
            else self._best(_SANS_CANDIDATES)
        )

        self._cache: Dict[str, str] = {}

    # -- public ----------------------------------------------------------------

    def resolve(self, font_name: Optional[str], *, for_heading: bool = False) -> str:
        """Return the best registered PDF font family for font_name."""
        fallback = self.major_family if for_heading else self.minor_family
        if not font_name:
            return fallback
        key = font_name.strip().lower()
        if key in self._cache:
            return self._cache[key]
        result = self._resolve_name(font_name) or fallback
        self._cache[key] = result
        return result

    def resolve_theme_ref(self, theme_ref: Optional[str]) -> Optional[str]:
        """Resolve w:asciiTheme / w:hAnsiTheme attribute values."""
        if not theme_ref:
            return None
        ref = theme_ref.strip().lower()
        if ref.startswith("major"):
            return self.major_family
        if ref.startswith("minor"):
            return self.minor_family
        return None

    def is_registered(self, family: str) -> bool:
        """Check if a font family is registered in the PDF."""
        return family.lower() in self._reg_lower

    # -- internals -------------------------------------------------------------

    def _resolve_name(self, font_name: str) -> str:
        """Map a DOCX font name to a registered PDF family, or empty string."""
        key = font_name.strip().lower()

        # 1. Exact (case-insensitive) match
        if key in self._reg_lower:
            return self._reg_raw[key]

        # 2. Genre lookup
        if key in _SANS_SERIF:
            return self._best(_SANS_CANDIDATES)
        if key in _SERIF:
            return self._best(_SERIF_CANDIDATES)
        if key in _MONO:
            return self._best(_MONO_CANDIDATES)

        # 3. Substring heuristics
        if any(h in key for h in _MONO_HINTS):
            return self._best(_MONO_CANDIDATES)
        if any(h in key for h in _SERIF_HINTS) and "sans" not in key:
            return self._best(_SERIF_CANDIDATES)

        # 4. No match → caller uses fallback
        return ""

    def _best(self, candidates: Tuple[str, ...]) -> str:
        """Return first registered candidate, else the last entry."""
        for c in candidates:
            if c.lower() in self._reg_lower:
                return self._reg_raw.get(c.lower(), c)
        return candidates[-1]
