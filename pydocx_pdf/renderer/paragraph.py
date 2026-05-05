"""
Render a :class:`~pydocx_pdf.models.paragraph.Paragraph` onto an FPDF page.

Handles the full range of paragraph and run-level formatting extracted by
the parser:

- **Font selection**: bold, italic, underline, size, colour, super/subscript,
  all-caps, small-caps, strikethrough.
- **Style-driven headings**: ``Heading1`` through ``Heading6``, ``Title``,
  ``Subtitle`` -- font size and spacing determined from style ID.
- **Theme font resolution**: ``w:asciiTheme`` references (``"minorHAnsi"``,
  ``"majorBidi"``, etc.) resolved via :class:`~pydocx_pdf.font_map.FontRegistry`.
- **Paragraph layout**: alignment (L/C/R/J), pre/post spacing, left/right/
  first-line indentation.
- **Character spacing**: ``w:spacing`` inside ``w:rPr`` -- expanded/condensed
  via ``fpdf2.set_char_spacing()``.
- **Horizontal glyph scaling**: ``w:w`` percentage via ``fpdf2.set_stretching()``.
- **Lists**: bullet and ordered markers with correct hanging indent and
  right-aligned counter column.
- **Mixed-format paragraphs**: multiple runs with differing styles flow on
  the same line using fpdf2\'s ``write()`` method.
- **Page breaks**: ``w:br w:type="page"`` -> ``pdf.add_page()``.
- **Inline images**: ``<w:drawing>`` content rendered via fpdf2\'s ``image()``.
"""

from __future__ import annotations

import io

from fpdf import FPDF

from pydocx_pdf.font_map import FontRegistry
from pydocx_pdf.models.image import Image
from pydocx_pdf.models.paragraph import Paragraph, Run
from pydocx_pdf.utils import twips_to_pt

_PT_TO_MM: float = 1 / 2.8346456692913385

_ALIGN_MAP = {
    "left":    "L",
    "center":  "C",
    "right":   "R",
    "both":    "J",
    "justify": "J",
}

_DEFAULT_FONT:    str   = "DejaVuSans"
_DEFAULT_SIZE_PT: float = 11.0

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
    """Render :class:`~pydocx_pdf.models.paragraph.Paragraph` objects onto an FPDF page.

    Parameters
    ----------
    pdf:
        The :class:`fpdf.FPDF` instance to draw onto.  Must already have at
        least one page added and fonts registered.
    font_registry:
        A :class:`~pydocx_pdf.font_map.FontRegistry` that resolves DOCX
        font names to registered PDF font family names.
    theme_minor_font:
        Deprecated -- pass a :class:`~pydocx_pdf.font_map.FontRegistry`
        instead.  Kept for backwards compatibility.
    default_font:
        Fallback family when no registry is provided.  Defaults to
        ``"DejaVuSans"``.
    """

    def __init__(
        self,
        pdf: FPDF,
        font_registry: FontRegistry | None = None,
        theme_minor_font: str | None = None,
        default_font: str | None = None,
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
        self._current_char_spacing_pt: float = 0.0
        self._current_scale_percent:   int   = 100

    def render(self, para: Paragraph) -> None:
        """Render *para* onto the current FPDF page.

        Applies pre-paragraph spacing, dispatches to the appropriate
        render path (list item, empty paragraph, or normal), then applies
        post-paragraph spacing.

        Parameters
        ----------
        para:
            The paragraph to render.
        """
        pdf      = self._pdf
        style_id = para.style_id

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
            pdf.set_font(self._fonts.minor_family, size=_DEFAULT_SIZE_PT)
            pdf.ln(self._natural_line_h_mm(_DEFAULT_SIZE_PT))
        else:
            self._render_runs(para, heading_size, align, is_heading)

        space_after_twips = para.style_props.get("space_after_twips", 0)
        if space_after_twips:
            pdf.ln(twips_to_pt(space_after_twips) * _PT_TO_MM)

    def _render_list_item(self, para: Paragraph, heading_size: float | None) -> None:
        """Render a list item with correct hanging-indent marker layout.

        Parameters
        ----------
        para:
            The list-item paragraph to render.
        heading_size:
            Override font size for heading-style list items, or ``None``.
        """
        pdf = self._pdf

        indent_mm  = twips_to_pt(para.list_indent_twips)  * _PT_TO_MM
        hanging_mm = twips_to_pt(para.list_hanging_twips) * _PT_TO_MM

        marker   = para.list_label or "*"
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
                    self._render_image(run.image)
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

    def _render_runs(
        self,
        para: Paragraph,
        heading_size: float | None,
        align: str,
        is_heading: bool,
    ) -> None:
        """Render all runs in a non-list paragraph with correct inline flow.

        Parameters
        ----------
        para:
            The paragraph whose runs are to be rendered.
        heading_size:
            Font-size override for heading styles, or ``None``.
        align:
            fpdf2 alignment code (``"L"``, ``"C"``, ``"R"``, ``"J"``).
        is_heading:
            ``True`` for Heading1 through Heading6, Title, Subtitle styles.
        """
        pdf  = self._pdf
        runs = para.runs

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

    def _same_format(
        self,
        runs: list[Run],
        is_heading: bool,
        heading_size: float | None,
    ) -> bool:
        """Return ``True`` iff every run in *runs* has identical visual formatting.

        Parameters
        ----------
        runs:
            List of :class:`~pydocx_pdf.models.paragraph.Run` objects.
        is_heading:
            Whether the paragraph is a heading (forces bold).
        heading_size:
            Font size override for headings, or ``None``.

        Returns
        -------
        bool
            ``True`` when all runs can be merged into a single draw call.
        """
        if len(runs) <= 1:
            return True

        def _key(r: Run) -> tuple[object, ...]:
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
        """Return the font\'s natural line height in millimetres.

        Reads ascent/descent metrics from the current fpdf2 font descriptor
        and derives the typographic line height ratio.

        Parameters
        ----------
        size_pt:
            Font size in points for the current line.

        Returns
        -------
        float
            Line height in millimetres.
        """
        try:
            font = self._pdf.current_font
            if not hasattr(font, "desc"):
                raise AttributeError
            desc  = font.desc  # type: ignore[union-attr]
            asc   = desc.ascent
            dsc   = desc.descent
            ratio: float = float((asc - dsc) / 1000.0)
            ratio = max(1.0, min(ratio, 2.0))
        except Exception:
            ratio = 1.15
        return size_pt * ratio * _PT_TO_MM

    def _compute_line_h(self, para: Paragraph, size_pt: float) -> float:
        """Compute line height in mm from paragraph spacing properties.

        Parameters
        ----------
        para:
            Paragraph whose ``style_props`` contain the line-spacing info.
        size_pt:
            Font size in points for this line.

        Returns
        -------
        float
            Line height in millimetres.
        """
        line_raw  = para.style_props.get("line_twips")
        line_rule = para.style_props.get("line_rule", "auto")
        if line_raw:
            if line_rule in ("exact", "atLeast"):
                return twips_to_pt(int(line_raw)) * _PT_TO_MM
            return self._natural_line_h_mm(size_pt) * (int(line_raw) / 240.0)
        return self._natural_line_h_mm(size_pt)

    def _apply_text_transforms(self, run: Run) -> str:
        """Return run text with all-caps and small-caps transforms applied.

        Also converts tab characters to four spaces.

        Parameters
        ----------
        run:
            The run whose text is to be transformed.

        Returns
        -------
        str
            Transformed text ready to pass to fpdf2.
        """
        text = run.text.replace("\t", "    ")
        if run.is_all_caps or run.is_small_caps:
            text = text.upper()
        return text

    def _apply_character_spacing(self, run: Run) -> None:
        """Apply character spacing and horizontal glyph scaling to the PDF state.

        Both values are always explicitly set to reset any prior non-default
        value left by the preceding run.

        Parameters
        ----------
        run:
            The run whose spacing and scale properties are to be applied.
        """
        spacing_mm = run.char_spacing_twentiethpt / 20.0 * _PT_TO_MM
        self._pdf.set_char_spacing(spacing_mm)
        self._pdf.set_stretching(run.scale_percent)

    def _set_run_font(
        self,
        run: Run,
        size_override: float | None = None,
        bold_override: bool | None = None,
        for_heading: bool = False,
    ) -> None:
        """Set the PDF font and text colour for *run*.

        Parameters
        ----------
        run:
            The run whose formatting is to be applied.
        size_override:
            Override font size in points (e.g. heading size).
        bold_override:
            Override bold flag (e.g. force bold for headings).
        for_heading:
            When ``True``, use the major (heading) font family.
        """
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
        """Render an inline image onto the current page.

        Failures are silently swallowed so a single bad image does not abort
        the entire conversion.

        Parameters
        ----------
        image:
            The :class:`~pydocx_pdf.models.image.Image` model to render.
        """
        pdf = self._pdf
        try:
            w = image.width_pt  * _PT_TO_MM if image.width_pt  else 50.0
            h = image.height_pt * _PT_TO_MM if image.height_pt else 0.0
            pdf.image(io.BytesIO(image.data), w=w, h=h)
            pdf.ln(2)
        except Exception:
            pass
