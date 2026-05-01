"""
Render a Paragraph model object onto an FPDF page.

Handles:
  - Style-driven font selection (bold, italic, size, color)
  - Heading sizes inferred from styleId (Heading1..Heading6)
  - Alignment (left / center / right / justify)
  - Pre/post spacing from style props
  - Bullet and ordered list markers with hanging indent
  - Inline images
"""

from __future__ import annotations

import io
from typing import Optional

from fpdf import FPDF

from pydocx_pdf.models.paragraph import Paragraph, Run
from pydocx_pdf.models.image import Image
from pydocx_pdf.utils import twips_to_pt

_PT_TO_MM = 1 / 2.8346456692913385

# Map DOCX alignment values -> fpdf2 align strings
_ALIGN_MAP = {
    "left":    "L",
    "center":  "C",
    "right":   "R",
    "both":    "J",
    "justify": "J",
}

_DEFAULT_FONT = "Helvetica"
_DEFAULT_SIZE_PT = 11.0

# Heading style -> font size in pt
_HEADING_SIZES: dict[str, float] = {
    "Heading1": 24.0,
    "Heading2": 18.0,
    "Heading3": 14.0,
    "Heading4": 12.0,
    "Heading5": 11.0,
    "Heading6": 10.0,
    # Title / Subtitle
    "Title":    28.0,
    "Subtitle": 14.0,
}

# Spacing above headings (mm)
_HEADING_SPACE_BEFORE: dict[str, float] = {
    "Heading1": 8.0,
    "Heading2": 6.0,
    "Heading3": 4.0,
    "Heading4": 3.0,
    "Heading5": 2.0,
    "Heading6": 2.0,
    "Title":    0.0,
    "Subtitle": 2.0,
}


class ParagraphRenderer:
    def __init__(self, pdf: FPDF, theme_minor_font: Optional[str] = None) -> None:
        self._pdf = pdf
        self._body_font = theme_minor_font or _DEFAULT_FONT

    def render(self, para: Paragraph) -> None:
        pdf = self._pdf
        style_id = para.style_id

        # -- Pre-spacing
        space_before_mm = _HEADING_SPACE_BEFORE.get(style_id, 0.0)
        if not space_before_mm:
            twips = para.style_props.get("space_before_twips", 0)
            space_before_mm = twips_to_pt(twips) * _PT_TO_MM if twips else 0.0
        if space_before_mm:
            pdf.ln(space_before_mm)

        # -- Compute effective font size for headings
        heading_size = _HEADING_SIZES.get(style_id)
        is_heading = heading_size is not None

        align = _ALIGN_MAP.get(para.style_props.get("align", "left"), "L")
        if is_heading:
            align = "L"  # headings are always left-aligned in most docs

        # -- List item: print marker then render text inline
        if para.is_list_item:
            self._render_list_item(para, heading_size)
        elif not para.runs:
            # Empty paragraph = blank line
            line_h = _DEFAULT_SIZE_PT * _PT_TO_MM * 1.2
            pdf.ln(line_h)
        else:
            # Regular paragraph: render run by run
            for run in para.runs:
                if run.image:
                    self._render_image(run.image)
                elif run.text:
                    size = heading_size or run.font_size_pt
                    bold = run.is_bold or is_heading
                    self._set_run_font(run, size_override=size, bold_override=bold)
                    line_h = size * _PT_TO_MM * 1.4
                    pdf.multi_cell(
                        w=0,
                        h=line_h,
                        text=run.text,
                        align=align,
                        new_x="LMARGIN",
                        new_y="NEXT",
                    )

        # -- Post-spacing
        space_after_twips = para.style_props.get("space_after_twips", 0)
        if space_after_twips:
            pdf.ln(twips_to_pt(space_after_twips) * _PT_TO_MM)
        elif not para.is_list_item:
            pdf.ln(1.0)

    # -------------------------------------------------------------------------

    def _render_list_item(self, para: Paragraph, heading_size: Optional[float]) -> None:
        pdf = self._pdf

        indent_twips = para.style_props.get("indent_left_twips", 720)
        hanging_twips = para.style_props.get("indent_hanging_twips", 360)
        indent_mm = twips_to_pt(indent_twips) * _PT_TO_MM
        hanging_mm = twips_to_pt(hanging_twips) * _PT_TO_MM

        # Determine marker
        marker = self._list_marker(para)

        text = para.full_text
        if not text and not marker:
            return

        # Choose font size from first run or heading override
        size_pt = heading_size or _DEFAULT_SIZE_PT
        if para.runs:
            size_pt = heading_size or para.runs[0].font_size_pt

        line_h = size_pt * _PT_TO_MM * 1.4
        marker_w = hanging_mm

        # Print marker
        pdf.set_x(pdf.l_margin + indent_mm - hanging_mm)
        pdf.set_font(_DEFAULT_FONT, size=size_pt)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(w=marker_w, h=line_h, text=marker)

        # Print text (indented past the marker)
        text_x = pdf.l_margin + indent_mm
        pdf.set_x(text_x)
        text_w = pdf.w - text_x - pdf.r_margin

        for run in para.runs:
            if run.image:
                self._render_image(run.image)
            elif run.text:
                self._set_run_font(run, size_override=size_pt)
                pdf.multi_cell(
                    w=text_w,
                    h=line_h,
                    text=run.text,
                    align="L",
                    new_x="LMARGIN",
                    new_y="NEXT",
                )

    def _list_marker(self, para: Paragraph) -> str:
        """Return the marker string for a list paragraph."""
        # For now return bullet; ordered lists need the numbering counter
        # which will be plumbed through in a future step
        if para.list_counter is not None:
            return f"{para.list_counter}."
        return "\u2022"   # bullet

    def _set_run_font(
        self,
        run: Run,
        size_override: Optional[float] = None,
        bold_override: Optional[bool] = None,
    ) -> None:
        pdf = self._pdf
        size = size_override if size_override is not None else run.font_size_pt
        bold = bold_override if bold_override is not None else run.is_bold

        style_str = ""
        if bold:
            style_str += "B"
        if run.is_italic:
            style_str += "I"

        font = run.font_name or self._body_font
        try:
            pdf.set_font(font, style=style_str, size=size)
        except Exception:
            pdf.set_font(_DEFAULT_FONT, style=style_str, size=size)

        color = run.color_hex
        if color and color not in ("auto", "000000", None):
            try:
                r = int(color[0:2], 16)
                g = int(color[2:4], 16)
                b = int(color[4:6], 16)
                pdf.set_text_color(r, g, b)
            except (ValueError, IndexError):
                pdf.set_text_color(0, 0, 0)
        else:
            pdf.set_text_color(0, 0, 0)

    def _render_image(self, image: Image) -> None:
        pdf = self._pdf
        try:
            w = image.width_pt * _PT_TO_MM if image.width_pt else 50.0
            h = image.height_pt * _PT_TO_MM if image.height_pt else None
            pdf.image(io.BytesIO(image.data), w=w, h=h)
            pdf.ln(2)
        except Exception:
            pass
