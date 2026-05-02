"""
Render a Paragraph model object onto an FPDF page.

Handles:
  - Style-driven font selection (bold, italic, underline, size, color)
  - Superscript / subscript (rendered at 65 % of the body size)
  - All-caps / small-caps text transforms
  - Heading sizes inferred from styleId (Heading1..Heading6)
  - Theme font references (w:asciiTheme -> major/minor font via FontRegistry)
  - Alignment (left / center / right / justify)
  - Pre/post spacing and line spacing from style props (w:spacing)
  - Left / right / first-line paragraph indentation (w:ind)
  - Bullet and ordered list markers with correct hanging indent and alignment
  - Mixed-format paragraphs: multiple runs with different styles flow inline
    on the same line (via write()) rather than each breaking to a new line
  - Page-break runs (w:br w:type='page') trigger a new PDF page
  - Inline images
"""

from __future__ import annotations

import io
from typing import Optional

from fpdf import FPDF

from pydocx_pdf.font_map import FontRegistry
from pydocx_pdf.models.paragraph import Paragraph, Run
from pydocx_pdf.models.image import Image
from pydocx_pdf.utils import twips_to_pt

_PT_TO_MM = 1 / 2.8346456692913385

_ALIGN_MAP = {
    "left":    "L",
    "center":  "C",
    "right":   "R",
    "both":    "J",
    "justify": "J",
}

_DEFAULT_FONT    = "DejaVuSans"
_DEFAULT_SIZE_PT = 11.0

_HEADING_SIZES: dict[str, float] = {
    "Heading1": 24.0,
    "Heading2": 18.0,
    "Heading3": 14.0,
    "Heading4": 12.0,
    "Heading5": 11.0,
    "Heading6": 10.0,
    "Title":    28.0,
    "Subtitle": 14.0,
}

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
    def __init__(
        self,
        pdf: FPDF,
        font_registry: Optional[FontRegistry] = None,
        theme_minor_font: Optional[str] = None,
        default_font: Optional[str] = None,
    ) -> None:
        self._pdf = pdf
        if font_registry is not None:
            self._fonts = font_registry
        else:
            body = theme_minor_font or default_font or _DEFAULT_FONT
            self._fonts = FontRegistry(
                registered={body},
                minor_font=body,
                major_font=body,
            )

    def render(self, para: Paragraph) -> None:
        pdf = self._pdf
        style_id = para.style_id

        # Pre-spacing
        space_before_mm = _HEADING_SPACE_BEFORE.get(style_id, 0.0)
        if not space_before_mm:
            twips = para.style_props.get("space_before_twips", 0)
            space_before_mm = twips_to_pt(twips) * _PT_TO_MM if twips else 0.0
        if space_before_mm:
            pdf.ln(space_before_mm)

        heading_size = _HEADING_SIZES.get(style_id)
        is_heading   = heading_size is not None

        align = _ALIGN_MAP.get(para.style_props.get("align", "left"), "L")
        if is_heading:
            align = "L"

        if para.is_list_item:
            self._render_list_item(para, heading_size)
        elif not para.runs:
            pdf.ln(_DEFAULT_SIZE_PT * _PT_TO_MM * 1.2)
        else:
            self._render_runs(para, heading_size, align, is_heading)

        # Post-spacing
        space_after_twips = para.style_props.get("space_after_twips", 0)
        if space_after_twips:
            pdf.ln(twips_to_pt(space_after_twips) * _PT_TO_MM)
        elif not para.is_list_item:
            pdf.ln(1.0)

    # -------------------------------------------------------------------------

    def _render_list_item(self, para: Paragraph, heading_size: Optional[float]) -> None:
        """Render a list item with proper hanging indent and marker alignment.

        All items at the same ilvl share the same list_indent_twips (set at
        parse time from the LevelDef), so their text columns are guaranteed to
        be X-aligned regardless of which numbering instance they belong to.

        Marker alignment:
          Bullets  -> left-aligned in the hanging column (single char).
          Numbered -> right-aligned so the trailing punctuation (. or ))
                      always sits flush against the text column edge, keeping
                      "i." and "viii." visually aligned.
        """
        pdf = self._pdf

        # Indent values from the LevelDef, stored on the paragraph at parse time
        indent_mm  = twips_to_pt(para.list_indent_twips)  * _PT_TO_MM
        hanging_mm = twips_to_pt(para.list_hanging_twips) * _PT_TO_MM

        # Resolved marker string (e.g. "a.", "iii.", "•")
        marker  = para.list_label or "•"
        stripped = marker.strip()
        is_bullet = len(stripped) == 1 and not stripped[0].isalnum()
        marker_align = "L" if is_bullet else "R"

        # Font / line height
        size_pt = heading_size or _DEFAULT_SIZE_PT
        if para.runs:
            first_text = next((r for r in para.runs if r.text), None)
            if first_text:
                size_pt = heading_size or first_text.font_size_pt
        line_h = self._compute_line_h(para, size_pt)

        # Draw marker
        # Marker occupies [l_margin + indent - hanging, l_margin + indent)
        marker_x = pdf.l_margin + indent_mm - hanging_mm
        if marker_x < pdf.l_margin:
            marker_x   = pdf.l_margin
            hanging_mm = indent_mm

        pdf.set_x(marker_x)
        pdf.set_font(self._fonts.minor_family, size=size_pt)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(w=hanging_mm, h=line_h, text=marker, align=marker_align)

        # Draw text runs
        # text_x is the fixed left edge of the text column for this level.
        text_x = pdf.l_margin + indent_mm
        text_w = pdf.w - text_x - pdf.r_margin

        if text_w <= 1.0:
            pdf.ln(line_h)
            return

        text_runs  = [r for r in para.runs if r.text and not r.image]
        image_runs = [r for r in para.runs if r.image]

        if not text_runs:
            pdf.ln(line_h)
        elif self._same_format(text_runs, False, heading_size):
            # All runs share the same format → merge and one multi_cell call.
            ref_run  = text_runs[0]
            combined = "".join(self._apply_text_transforms(r) for r in text_runs)
            self._set_run_font(ref_run, size_override=size_pt)
            pdf.set_x(text_x)
            pdf.multi_cell(
                w=text_w, h=line_h, text=combined,
                align="L", new_x="LMARGIN", new_y="NEXT",
            )
        else:
            # Mixed formatting → write() inline so runs stay on the same line.
            orig_l_margin = pdf.l_margin
            pdf.set_left_margin(text_x)
            pdf.set_x(text_x)
            wrote = False
            lh_last = line_h
            for run in para.runs:
                if run.image:
                    if wrote:
                        pdf.ln(lh_last)
                        wrote = False
                    self._render_image(run.image)  # type: ignore[arg-type]
                elif run.text:
                    sz = heading_size or run.font_size_pt
                    self._set_run_font(run, size_override=sz)
                    lh_last = self._compute_line_h(para, sz)
                    pdf.write(h=lh_last, text=self._apply_text_transforms(run))
                    wrote = True
            if wrote:
                pdf.ln(lh_last)
            pdf.set_left_margin(orig_l_margin)
            pdf.set_x(pdf.l_margin)

        for run in image_runs:
            self._render_image(run.image)  # type: ignore[arg-type]

    # -------------------------------------------------------------------------

    def _render_runs(
        self,
        para: Paragraph,
        heading_size: Optional[float],
        align: str,
        is_heading: bool,
    ) -> None:
        """Render all runs in a paragraph with correct inline text flow.

        Strategy
        --------
        * Page-break run → ``add_page()`` and return immediately.
        * **Single-format** (all text runs share the same visual style):
          merge text into one string and call ``multi_cell`` once.
          This preserves alignment (centre / right / justify) perfectly.
        * **Multi-format** (mixed bold/italic/colour/size within one paragraph):
          call ``write()`` per run so text from successive runs flows on the
          same line.  ``set_left_margin`` is temporarily widened to include any
          left indent so that long wrapped lines also start at the right column.
        * Image runs are rendered inline; any in-progress text line is closed
          with ``ln()`` first.
        """
        pdf  = self._pdf
        runs = para.runs

        # Fast path: page break — don't render any text.
        for run in runs:
            if run.is_page_break:
                pdf.add_page()
                return

        text_runs  = [r for r in runs if r.text and not r.image]
        has_images = any(r.image for r in runs)

        # Dominant font size for line-height calculation.
        first_text = next((r for r in runs if r.text and not r.image), None)
        size_pt    = heading_size or (first_text.font_size_pt if first_text else _DEFAULT_SIZE_PT)

        # Paragraph-level indentation (non-list paragraphs only).
        indent_left_mm  = twips_to_pt(para.style_props.get("indent_left_twips",  0)) * _PT_TO_MM
        indent_right_mm = twips_to_pt(para.style_props.get("indent_right_twips", 0)) * _PT_TO_MM
        indent_first_mm = twips_to_pt(para.style_props.get("indent_first_twips", 0)) * _PT_TO_MM

        # ── Single-format path ──────────────────────────────────────────────
        if (
            not has_images
            and text_runs
            and self._same_format(text_runs, is_heading, heading_size)
        ):
            run0  = text_runs[0]
            size  = heading_size or run0.font_size_pt
            bold  = run0.is_bold or is_heading
            self._set_run_font(run0, size_override=size, bold_override=bold,
                               for_heading=is_heading)
            lh   = self._compute_line_h(para, size)
            text = "".join(self._apply_text_transforms(r) for r in text_runs)

            if indent_left_mm or indent_right_mm or indent_first_mm:
                left_x = pdf.l_margin + indent_left_mm + indent_first_mm
                w      = (pdf.w
                          - pdf.l_margin - indent_left_mm
                          - pdf.r_margin - indent_right_mm)
                pdf.set_x(left_x)
                pdf.multi_cell(w=max(w, 1.0), h=lh, text=text, align=align,
                               new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.multi_cell(w=0, h=lh, text=text, align=align,
                               new_x="LMARGIN", new_y="NEXT")
            return

        # ── Multi-format path ───────────────────────────────────────────────
        orig_l_margin = pdf.l_margin
        if indent_left_mm:
            pdf.set_left_margin(orig_l_margin + indent_left_mm)
            pdf.set_x(orig_l_margin + indent_left_mm + indent_first_mm)

        wrote_text = False
        lh_last    = self._compute_line_h(para, size_pt)

        for run in runs:
            if run.image:
                if wrote_text:
                    pdf.ln(lh_last)
                    wrote_text = False
                self._render_image(run.image)
            elif run.text:
                size = heading_size or run.font_size_pt
                bold = run.is_bold or is_heading
                self._set_run_font(run, size_override=size, bold_override=bold,
                                   for_heading=is_heading)
                lh_last = self._compute_line_h(para, size)
                pdf.write(h=lh_last, text=self._apply_text_transforms(run))
                wrote_text = True

        if wrote_text:
            pdf.ln(lh_last)

        if indent_left_mm:
            pdf.set_left_margin(orig_l_margin)
            pdf.set_x(pdf.l_margin)

    # ── Format-analysis helpers ───────────────────────────────────────────────

    def _same_format(
        self,
        runs: list,
        is_heading: bool,
        heading_size: Optional[float],
    ) -> bool:
        """Return True iff every run in *runs* has identical visual formatting."""
        if len(runs) <= 1:
            return True

        def _key(r: Run) -> tuple:
            size = heading_size if heading_size is not None else r.font_size_pt
            bold = r.is_bold or is_heading
            return (
                bold, r.is_italic, r.is_underline, r.is_strikethrough,
                size, r.font_name, r.font_theme, r.color_hex,
                r.vert_align, r.is_all_caps, r.is_small_caps,
            )

        first = _key(runs[0])
        return all(_key(r) == first for r in runs[1:])

    def _compute_line_h(self, para: Paragraph, size_pt: float) -> float:
        """Compute line height in mm from paragraph spacing properties.

        DOCX ``w:spacing/w:line`` with ``w:lineRule="auto"`` stores the
        spacing as a multiple of 240 (240 = single, 360 = 1.5×, 480 = double).
        For ``exact``/``atLeast`` rules the raw twips value is used directly.
        Falls back to 1.2× the font size when no line-spacing is specified.
        """
        size_mm   = size_pt * _PT_TO_MM
        line_raw  = para.style_props.get("line_twips")
        line_rule = para.style_props.get("line_rule", "auto")
        if line_raw:
            if line_rule in ("exact", "atLeast"):
                return twips_to_pt(int(line_raw)) * _PT_TO_MM
            # "auto": 240 twips = single spacing
            return size_mm * (int(line_raw) / 240.0)
        return size_mm * 1.2

    def _apply_text_transforms(self, run: Run) -> str:
        """Return run text with all-caps / small-caps transforms applied."""
        text = run.text
        # Replace tab characters with spaces (tabs not supported in PDF)
        text = text.replace('\t', '    ')
        if run.is_all_caps or run.is_small_caps:
            text = text.upper()
        return text

    # -------------------------------------------------------------------------

    def _set_run_font(
        self,
        run: Run,
        size_override: Optional[float] = None,
        bold_override: Optional[bool] = None,
        for_heading: bool = False,
    ) -> None:
        pdf  = self._pdf
        size = size_override if size_override is not None else run.font_size_pt
        bold = bold_override if bold_override is not None else run.is_bold

        style_str = ""
        if bold:
            style_str += "B"
        if run.is_italic:
            style_str += "I"
        if run.is_underline:
            style_str += "U"

        # Superscript / subscript: render at ~65 % of the normal size.
        if run.vert_align in ("superscript", "subscript"):
            size = round(size * 0.65, 1)

        if run.font_theme:
            family = (
                self._fonts.resolve_theme_ref(run.font_theme)
                or self._fonts.resolve(None, for_heading=for_heading)
            )
        elif run.font_name:
            family = self._fonts.resolve(run.font_name, for_heading=for_heading)
        else:
            family = self._fonts.resolve(None, for_heading=for_heading)

        try:
            pdf.set_font(family, style=style_str, size=size)
        except Exception:
            try:
                pdf.set_font(self._fonts.minor_family, style=style_str, size=size)
            except Exception:
                pdf.set_font(_DEFAULT_FONT, style=style_str, size=size)

        color = run.color_hex
        if color and color.lower() not in ("auto", "000000"):
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
            w = image.width_pt  * _PT_TO_MM if image.width_pt  else 50.0
            h = image.height_pt * _PT_TO_MM if image.height_pt else None
            pdf.image(io.BytesIO(image.data), w=w, h=h)
            pdf.ln(2)
        except Exception:
            pass
