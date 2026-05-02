"""Top-level PDF renderer."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Set, Tuple, Union

from fpdf import FPDF

from pydocx_pdf.font_map import FontRegistry
from pydocx_pdf.models.document import Document
from pydocx_pdf.models.paragraph import Paragraph
from pydocx_pdf.models.table import Table
from pydocx_pdf.parser.theme import Theme
from pydocx_pdf.renderer.paragraph import ParagraphRenderer
from pydocx_pdf.renderer.table import TableRenderer


# A4 page in mm
PAGE_W_MM = 210.0
PAGE_H_MM = 297.0
MARGIN_MM = 20.0

# Bundled fonts directory
_FONTS_DIR = Path(__file__).parent.parent / "fonts"

# Bundled font configurations
_BUNDLED_FONTS = [
    ("DejaVuSans", "", "DejaVuSans.ttf"),
    ("DejaVuSans", "B", "DejaVuSans-Bold.ttf"),
    ("DejaVuSans", "I", "DejaVuSans-Oblique.ttf"),
    ("DejaVuSans", "BI", "DejaVuSans-BoldOblique.ttf"),
    ("LiberationSans", "", "LiberationSans-Regular.ttf"),
    ("LiberationSans", "B", "LiberationSans-Bold.ttf"),
    ("LiberationSans", "I", "LiberationSans-Italic.ttf"),
    ("LiberationSans", "BI", "LiberationSans-BoldItalic.ttf"),
    ("LiberationSerif", "", "LiberationSerif-Regular.ttf"),
    ("LiberationSerif", "B", "LiberationSerif-Bold.ttf"),
    ("LiberationSerif", "I", "LiberationSerif-Italic.ttf"),
    ("LiberationSerif", "BI", "LiberationSerif-BoldItalic.ttf"),
    ("LiberationMono", "", "LiberationMono-Regular.ttf"),
    ("LiberationMono", "B", "LiberationMono-Bold.ttf"),
    ("LiberationMono", "I", "LiberationMono-Italic.ttf"),
    ("LiberationMono", "BI", "LiberationMono-BoldItalic.ttf"),
]

DEFAULT_FONT = "LiberationSans"


class PDFWriter:
    def __init__(self, font_dir: Union[str, Path, None] = None) -> None:
        self._font_dir = Path(font_dir) if font_dir else None

    def render(
        self,
        doc: Document,
        theme: Optional[Theme] = None,
    ) -> bytes:
        """Render doc to PDF bytes."""
        pdf, registered = self._create_pdf()

        major = theme.major_font if theme else None
        minor = theme.minor_font if theme else None
        font_registry = FontRegistry(
            registered=registered,
            major_font=major,
            minor_font=minor,
        )

        para_renderer = ParagraphRenderer(pdf, font_registry=font_registry)
        table_renderer = TableRenderer(pdf, para_renderer)

        for block in doc.blocks:
            if isinstance(block, Paragraph):
                para_renderer.render(block)
            elif isinstance(block, Table):
                table_renderer.render(block)

        return pdf.output()

    def _create_pdf(self) -> Tuple[FPDF, Set[str]]:
        """Return the initialised FPDF instance and the set of registered font families."""
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_margins(MARGIN_MM, MARGIN_MM, MARGIN_MM)
        pdf.set_auto_page_break(auto=True, margin=MARGIN_MM)
        pdf.add_page()

        registered: Set[str] = set()

        # Register bundled fonts
        for family, style, filename in _BUNDLED_FONTS:
            ttf_path = _FONTS_DIR / filename
            if ttf_path.exists():
                pdf.add_font(family, style=style, fname=str(ttf_path))
                registered.add(family)

        # Register any extra fonts supplied by the caller
        if self._font_dir and self._font_dir.is_dir():
            for ttf in self._font_dir.glob("*.ttf"):
                pdf.add_font(ttf.stem, fname=str(ttf))
                registered.add(ttf.stem)

        pdf.set_font(DEFAULT_FONT, size=11)

        return pdf, registered
