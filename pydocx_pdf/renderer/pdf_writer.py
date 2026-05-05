"""
Top-level PDF renderer.

:class:`PDFWriter` is the orchestrator for the rendering phase.  It:

1. Creates an :class:`fpdf.FPDF` instance sized for A4.
2. Registers all bundled TrueType fonts (Liberation + DejaVu families).
3. Optionally registers any extra fonts from a caller-supplied directory.
4. Builds a :class:`~pydocx_pdf.font_map.FontRegistry` that maps DOCX font
   names to the registered PDF families.
5. Iterates over each :class:`~pydocx_pdf.models.document.Block` in the
   document and delegates to :class:`~pydocx_pdf.renderer.paragraph.ParagraphRenderer`
   or :class:`~pydocx_pdf.renderer.table.TableRenderer`.
6. Returns the finished PDF as a ``bytes`` object.

Page format
-----------
All output is A4 portrait (210 x 297 mm) with 20 mm margins on all sides.
Page-break handling is automatic (fpdf2 ``auto_page_break``).
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from pydocx_pdf.font_map import FontRegistry
from pydocx_pdf.models.document import Document
from pydocx_pdf.models.paragraph import Paragraph
from pydocx_pdf.models.table import Table
from pydocx_pdf.parser.theme import Theme
from pydocx_pdf.renderer.paragraph import ParagraphRenderer
from pydocx_pdf.renderer.table import TableRenderer

# ---------------------------------------------------------------------------
# Page constants
# ---------------------------------------------------------------------------

PAGE_W_MM: float = 210.0
"""A4 page width in millimetres."""

PAGE_H_MM: float = 297.0
"""A4 page height in millimetres."""

MARGIN_MM: float = 20.0
"""Uniform page margin (top, bottom, left, right) in millimetres."""

# ---------------------------------------------------------------------------
# Bundled font directory (inside the wheel)
# ---------------------------------------------------------------------------

#: Absolute path to the ``pydocx_pdf/fonts/`` directory bundled in the wheel.
_FONTS_DIR: Path = Path(__file__).parent.parent / "fonts"

# Each tuple is (family_name, style_flag, filename_in_fonts_dir).
# Style flags: "" = Regular, "B" = Bold, "I" = Italic, "BI" = BoldItalic.
_BUNDLED_FONTS = [
    # DejaVu Sans -- Unicode fallback family
    ("DejaVuSans",      "",   "DejaVuSans.ttf"),
    ("DejaVuSans",      "B",  "DejaVuSans-Bold.ttf"),
    ("DejaVuSans",      "I",  "DejaVuSans-Oblique.ttf"),
    ("DejaVuSans",      "BI", "DejaVuSans-BoldOblique.ttf"),
    # Liberation Sans -- metric-compatible Arial replacement
    ("LiberationSans",  "",   "LiberationSans-Regular.ttf"),
    ("LiberationSans",  "B",  "LiberationSans-Bold.ttf"),
    ("LiberationSans",  "I",  "LiberationSans-Italic.ttf"),
    ("LiberationSans",  "BI", "LiberationSans-BoldItalic.ttf"),
    # Liberation Serif -- metric-compatible Times New Roman replacement
    ("LiberationSerif", "",   "LiberationSerif-Regular.ttf"),
    ("LiberationSerif", "B",  "LiberationSerif-Bold.ttf"),
    ("LiberationSerif", "I",  "LiberationSerif-Italic.ttf"),
    ("LiberationSerif", "BI", "LiberationSerif-BoldItalic.ttf"),
    # Liberation Mono -- metric-compatible Courier New replacement
    ("LiberationMono",  "",   "LiberationMono-Regular.ttf"),
    ("LiberationMono",  "B",  "LiberationMono-Bold.ttf"),
    ("LiberationMono",  "I",  "LiberationMono-Italic.ttf"),
    ("LiberationMono",  "BI", "LiberationMono-BoldItalic.ttf"),
]

#: Default font family used for the initial ``set_font`` call.
DEFAULT_FONT: str = "LiberationSans"


class PDFWriter:
    """Render a :class:`~pydocx_pdf.models.document.Document` to PDF bytes.

    Parameters
    ----------
    font_dir:
        Optional path to a directory containing extra ``.ttf`` font files.
        Every ``.ttf`` in the directory is registered under the font\'s stem
        name (e.g. ``MyFont-Bold.ttf`` -> family ``"MyFont-Bold"``).  These
        fonts are available to the :class:`~pydocx_pdf.font_map.FontRegistry`
        for resolution alongside the bundled families.

    Examples
    --------
    >>> writer = PDFWriter()
    >>> pdf_bytes = writer.render(doc, theme=theme)

    >>> writer = PDFWriter(font_dir="/app/fonts")
    >>> pdf_bytes = writer.render(doc)
    """

    def __init__(self, font_dir: str | Path | None = None) -> None:
        self._font_dir = Path(font_dir) if font_dir else None

    def render(
        self,
        doc: Document,
        theme: Theme | None = None,
    ) -> bytes:
        """Render *doc* to a PDF byte string.

        Parameters
        ----------
        doc:
            The parsed document model produced by
            :class:`~pydocx_pdf.parser.document.DocumentParser`.
        theme:
            Optional :class:`~pydocx_pdf.parser.theme.Theme` extracted from
            ``word/theme/theme1.xml``.  When provided the theme\'s
            ``major_font`` and ``minor_font`` are used to seed the
            :class:`~pydocx_pdf.font_map.FontRegistry`; otherwise the
            bundled Liberation Sans is used for both heading and body text.

        Returns
        -------
        bytes
            Complete PDF file contents starting with ``b"%PDF-"``.
        """
        pdf, registered = self._create_pdf()

        # Resolve theme font names (Calibri, Aptos, etc.) to registered families
        major = theme.major_font if theme else None
        minor = theme.minor_font if theme else None
        font_registry = FontRegistry(
            registered=registered,
            major_font=major,
            minor_font=minor,
        )

        para_renderer  = ParagraphRenderer(pdf, font_registry=font_registry)
        table_renderer = TableRenderer(pdf, para_renderer)

        for block in doc.blocks:
            if isinstance(block, Paragraph):
                para_renderer.render(block)
            elif isinstance(block, Table):
                table_renderer.render(block)

        return bytes(pdf.output())

    def _create_pdf(self) -> tuple[FPDF, set[str]]:
        """Initialise the FPDF instance and register all fonts.

        Returns
        -------
        tuple[FPDF, set[str]]
            The configured FPDF instance and the set of registered font
            family names (used to seed :class:`~pydocx_pdf.font_map.FontRegistry`).
        """
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
        pdf.set_auto_page_break(auto=True, margin=MARGIN_MM)
        pdf.add_page()

        registered: set[str] = set()

        # Register all bundled fonts (skip any whose .ttf file is missing --
        # this can happen in unusual packaging scenarios but should never
        # occur with a properly installed wheel)
        for family, style, filename in _BUNDLED_FONTS:
            ttf_path = _FONTS_DIR / filename
            if ttf_path.exists():
                pdf.add_font(family, style=style, fname=str(ttf_path))
                registered.add(family)

        # Register any caller-supplied extra fonts
        if self._font_dir and self._font_dir.is_dir():
            for ttf in self._font_dir.glob("*.ttf"):
                # Register under the stem name (without extension).
                # The FontRegistry maps DOCX font names to these stems.
                pdf.add_font(ttf.stem, fname=str(ttf))
                registered.add(ttf.stem)

        # Set a default font so the PDF is in a valid state before any
        # content is rendered
        pdf.set_font(DEFAULT_FONT, size=11)

        return pdf, registered
