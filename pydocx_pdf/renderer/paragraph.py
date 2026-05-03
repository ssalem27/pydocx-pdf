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
  - Character spacing (w:spacing in w:rPr) and horizontal scaling (w:w)
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
        # Character spacing and scale properties (set during font rendering)
        self._current_char_spacing_pt: float = 0.0
        self._current_scale_percent: int = 100

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
            # Empty paragraph: use the font's natural line height as the gap.
            # Set a font first so current_font metrics are available.
            pdf.set_font(self._fonts.minor_family, size=_DEFAULT_SIZE_PT)
            pdf.ln(self._natural_line_h_mm(_DEFAULT_SIZE_PT))
        else:
            self._render_runs(para, heading_size, align, is_heading)

        # Post-spacing
        # Only emit explicit space_after when the style specifies it.
        # The old 1mm fallback (≈ 2.83pt) was adding unintended inter-paragraph
        # gaps for every paragraph that lacked a space_after value.
        space_after_twips = para.style_props.get("space_after_twips", 0)
        if space_after_twips:
            pdf.ln(twips_to_pt(space_after_twips) * _PT_TO_MM)

    # -------------------------------------------------------------------------

    def _render_list_item(self, para: Paragraph, heading_size: Optional[float]) -> None:
        """Render a list item with proper hanging indent and marker alignment."""
        pdf = self._pdf

        indent_mm  = twips_to_pt(para.list_indent_twips)  * _PT_TO_MM
        hanging_mm = twips_to_pt(para.list_hanging_twips) * _PT_TO_MM

        marker   = para.list_label or "•"
        stripped = marker.strip()
        is_bullet    = len(stripped) == 1 and not stripped[0].isalnum()
        marker_align = "L" if is_bullet else "R"

        size_pt = heading_size or _DEFAULT_SIZE_PT
        if para.runs:
            first_text = next((r for r in para.runs if r.text), None)
            if first_text:
                size_pt = heading_size or first_text.font_size_pt
        line_h = self._compute_line_h(para, size_pt)

        marker_x = pdf.l_margin + indent_mm - hanging_mm
        if marker_x < pdf.l_margin:
            marker_x   = pdf.l_margin
            hanging_mm = indent_mm

        pdf.set_x(marker_x)
        pdf.set_font(self._fonts.minor_family, size=size_pt)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(w=hanging_mm, h=line_h, text=marker, align=marker_align)

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
            ref_run  = text_runs[0]
            combined = "".join(self._apply_text_transforms(r) for r in text_runs)
            self._set_run_font(ref_run, size_override=size_pt)
            self._apply_character_spacing(ref_run)
            pdf.set_x(text_x)
            pdf.multi_cell(
                w=text_w, h=line_h, text=combined,
                align="L", new_x="LMARGIN", new_y="NEXT",
            )
        else:
            orig_l_margin = pdf.l_margin
            pdf.set_left_margin(text_x)
            pdf.set_x(text_x)
            wrote   = False
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
                    self._apply_character_spacing(run)
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

        # Fast path: page break
        for run in runs:
            if run.is_page_break:
                pdf.add_page()
                return

        text_runs  = [r for r in runs if r.text and not r.image]
        has_images = any(r.image for r in runs)

        first_text = next((r for r in runs if r.text and not r.image), None)
        size_pt    = heading_size or (first_text.font_size_pt if first_text else _DEFAULT_SIZE_PT)

        indent_left_mm  = twips_to_pt(para.style_props.get("indent_left_twips",  0)) * _PT_TO_MM
        indent_right_mm = twips_to_pt(para.style_props.get("indent_right_twips", 0)) * _PT_TO_MM
        indent_first_mm = twips_to_pt(para.style_props.get("indent_first_twips", 0)) * _PT_TO_MM

        # ── Single-format path ──────────────────────────────────────────────
        if (
            not has_images
            and text_runs
            and self._same_format(text_runs, is_heading, heading_size)
        ):
            run0 = text_runs[0]
            size = heading_size or run0.font_size_pt
            bold = run0.is_bold or is_heading
            self._set_run_font(run0, size_override=size, bold_override=bold,
                               for_heading=is_heading)
            self._apply_character_spacing(run0)
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
                self._apply_character_spacing(run)
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
                r.char_spacing_twentiethpt, r.scale_percent,
            )

        first = _key(runs[0])
        return all(_key(r) == first for r in runs[1:])

    def _natural_line_h_mm(self, size_pt: float) -> float:
        """Compute the font's natural line height in mm.

        Reads ascent/descent from the current fpdf2 font descriptor (units of
        1/1000 of the em square) and derives the typographic line height ratio.
        This matches DOCX "auto" line spacing where line=240 means 1× single
        spacing based on the font's own metrics — NOT simply 1.0× the point size.

        LiberationSans example: ascent=905, descent=-212 → ratio=1.117,
        so 11pt single-spaced → 12.29pt line height (not 13.2pt from ×1.2).
        """
        try:
            desc  = self._pdf.current_font.desc
            asc   = desc.ascent         # e.g. 905
            dsc   = desc.descent        # e.g. -212  (negative)
            ratio = (asc - dsc) / 1000.0
            ratio = max(1.0, min(ratio, 2.0))
        except Exception:
            ratio = 1.15  # safe fallback (better than 1.2)
        return size_pt * ratio * _PT_TO_MM

    def _compute_line_h(self, para: Paragraph, size_pt: float) -> float:
        """Compute line height in mm from paragraph spacing properties.

        DOCX w:spacing/w:line with w:lineRule="auto" stores spacing as a
        multiple of 240 (240 = single, 360 = 1.5x, 480 = double), where the
        base is the font's *natural* line height (ascent − descent), not its
        point size.  For exact/atLeast rules the raw twips value is used directly.
        Falls back to the natural line height when no line-spacing is specified.
        """
        line_raw  = para.style_props.get("line_twips")
        line_rule = para.style_props.get("line_rule", "auto")
        if line_raw:
            if line_rule in ("exact", "atLeast"):
                return twips_to_pt(int(line_raw)) * _PT_TO_MM
            # auto: multiplier is line_raw/240; base is the natural line height
            return self._natural_line_h_mm(size_pt) * (int(line_raw) / 240.0)
        return self._natural_line_h_mm(size_pt)

    def _apply_text_transforms(self, run: Run) -> str:
        """Return run text with all-caps / small-caps transforms applied."""
        text = run.text.replace('\t', '    ')
        if run.is_all_caps or run.is_small_caps:
            text = text.upper()
        return text

    def _apply_character_spacing(self, run: Run) -> None:
        """Apply character spacing and horizontal scaling from DOCX run props.

        w:spacing in w:rPr is in 1/20th of a point (twentieths-of-a-point).
        Positive = expanded, negative = condensed.

        fpdf2's set_char_spacing() outputs the value directly into the PDF
        content stream as a Tc operator WITHOUT applying the k-factor unit
        conversion that fpdf2 applies to all other coordinates.  The PDF Tc
        operator is specified in "unscaled text space units" which, in fpdf2's
        coordinate system, are points — the same unit as the font size in Tf.
        Therefore we must pass the value in **points**, not in mm.

        Conversion: 1 twentiethpt = 1/20 pt  (simple divide-by-20, no mm step).

        w:w stores horizontal glyph scaling as a percentage (100 = normal).
        fpdf2 set_stretching() accepts the percentage integer directly.

        Both values are always explicitly set — even to their defaults of 0 pt
        and 100% — so a run with default formatting resets any value left active
        by the preceding run and spacing never bleeds across run boundaries.
        """
        # 1/20 pt -> pt: divide by 20.
        # Do NOT convert to mm here — fpdf2 emits set_char_spacing values
        # verbatim as Tc (no k-factor applied), so the unit must be points.
        spacing_pt = run.char_spacing_twentiethpt / 20.0
        self._pdf.set_char_spacing(spacing_pt)
        self._pdf.set_stretching(run.scale_percent)

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
