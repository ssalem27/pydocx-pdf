"""Tests for character spacing and font scaling preservation in PDF output.

Verifies the full pipeline:
  w:spacing in w:rPr  -> parser -> Run.char_spacing_twentiethpt
                      -> renderer -> fpdf2.set_char_spacing -> PDF Tc operator

  w:w in w:rPr        -> parser -> Run.scale_percent
                      -> renderer -> fpdf2.set_stretching  -> PDF Tz operator
"""

import io
import zipfile
import zlib
import re

from pydocx_pdf import convert


# ---------------------------------------------------------------------------
# DOCX fixtures
# ---------------------------------------------------------------------------

def _make_docx(document_xml: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _docx_with_character_spacing() -> bytes:
    return _make_docx(b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:rPr><w:spacing w:val="80"/></w:rPr>
        <w:t>Expanded 4pt spacing</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:rPr><w:spacing w:val="-20"/></w:rPr>
        <w:t>Condensed 1pt spacing</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Normal spacing resets to zero</w:t></w:r>
    </w:p>
  </w:body>
</w:document>""")


def _docx_with_font_scaling() -> bytes:
    return _make_docx(b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:rPr><w:w w:val="80"/></w:rPr>
        <w:t>Condensed 80 percent</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:rPr><w:w w:val="120"/></w:rPr>
        <w:t>Expanded 120 percent</w:t></w:r>
    </w:p>
    <w:p>
      <w:r><w:t>Normal width resets to 100</w:t></w:r>
    </w:p>
  </w:body>
</w:document>""")


def _docx_with_combined_formatting() -> bytes:
    return _make_docx(b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:rPr>
          <w:b/><w:i/>
          <w:color w:val="1F3864"/>
          <w:spacing w:val="10"/>
          <w:w w:val="90"/>
        </w:rPr>
        <w:t>Combined formatting</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>""")


def _docx_safiuddeen_heading() -> bytes:
    """Regression: exact heading from the real-world docx (4pt / val=80 spacing)."""
    return _make_docx(b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:spacing w:after="60"/><w:jc w:val="center"/></w:pPr>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/>
          <w:b/><w:bCs/>
          <w:color w:val="1A1A1A"/>
          <w:spacing w:val="80"/>
          <w:sz w:val="40"/><w:szCs w:val="40"/>
        </w:rPr>
        <w:t>SAFIUDDEEN SALEM</w:t>
      </w:r>
    </w:p>
  </w:body>
</w:document>""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pdf_tc_values(pdf: bytes) -> list:
    """Return all Tc values (mm) from decompressed PDF content streams."""
    values = []
    for stream in re.findall(b"stream\r?\n(.*?)\r?\nendstream", pdf, re.DOTALL):
        try:
            data = zlib.decompress(stream)
            for m in re.finditer(rb"([-\d.]+) Tc", data):
                values.append(round(float(m.group(1)), 4))
        except Exception:
            pass
    return values


def _pdf_tz_values(pdf: bytes) -> list:
    """Return all Tz values (%) from decompressed PDF content streams."""
    values = []
    for stream in re.findall(b"stream\r?\n(.*?)\r?\nendstream", pdf, re.DOTALL):
        try:
            data = zlib.decompress(stream)
            for m in re.finditer(rb"([\d.]+) Tz", data):
                values.append(round(float(m.group(1)), 2))
        except Exception:
            pass
    return values


# ---------------------------------------------------------------------------
# PDF validity
# ---------------------------------------------------------------------------

def test_convert_with_character_spacing_returns_pdf():
    pdf = convert(_docx_with_character_spacing())
    assert pdf.startswith(b"%PDF-")
    assert b"stream" in pdf


def test_convert_with_font_scaling_returns_pdf():
    pdf = convert(_docx_with_font_scaling())
    assert pdf.startswith(b"%PDF-")
    assert b"stream" in pdf


def test_convert_with_combined_formatting_returns_pdf():
    pdf = convert(_docx_with_combined_formatting())
    assert pdf.startswith(b"%PDF-")
    assert b"stream" in pdf


# ---------------------------------------------------------------------------
# Character spacing: Tc operator
# ---------------------------------------------------------------------------

def test_character_spacing_expanded_tc_in_pdf():
    """w:spacing val=80 (4pt expanded) -> Tc ~1.41 mm in PDF."""
    pdf = convert(_docx_with_character_spacing())
    tc_vals = _pdf_tc_values(pdf)
    assert tc_vals, "No Tc operator found — character spacing not rendered"
    # 80 * 25.4 / (72 * 20) = 1.4111... mm
    assert any(abs(v - 1.4111) < 0.01 for v in tc_vals), (
        f"Expected Tc ~1.41 mm for 4pt spacing, got: {tc_vals}"
    )


def test_character_spacing_condensed_tc_in_pdf():
    """w:spacing val=-20 (condensed) -> negative Tc in PDF."""
    pdf = convert(_docx_with_character_spacing())
    tc_vals = _pdf_tc_values(pdf)
    assert any(v < 0 for v in tc_vals), (
        f"Expected a negative Tc for condensed spacing, got: {tc_vals}"
    )


def test_character_spacing_reset_to_zero():
    """Normal paragraph (no w:spacing) -> Tc 0.0 reset in PDF."""
    pdf = convert(_docx_with_character_spacing())
    tc_vals = _pdf_tc_values(pdf)
    assert 0.0 in tc_vals, (
        f"Expected Tc=0.0 reset for normal paragraph, got: {tc_vals}"
    )


def test_safiuddeen_heading_4pt_spacing():
    """Regression: SAFIUDDEEN SALEM heading with w:spacing val=80 (4pt)."""
    pdf = convert(_docx_safiuddeen_heading())
    tc_vals = _pdf_tc_values(pdf)
    assert tc_vals, "No Tc operator — 4pt heading spacing was not preserved"
    assert any(abs(v - 1.4111) < 0.01 for v in tc_vals), (
        f"Expected Tc ~1.41 mm for 4pt heading, got: {tc_vals}"
    )


# ---------------------------------------------------------------------------
# Font scaling: Tz operator
# ---------------------------------------------------------------------------

def test_font_scaling_tz_in_pdf():
    """w:w val=80 -> 80% width -> Tz 80.0 in PDF."""
    pdf = convert(_docx_with_font_scaling())
    tz_vals = _pdf_tz_values(pdf)
    assert tz_vals, "No Tz operator found — font scaling not rendered"
    assert 80.0 in tz_vals, f"Expected Tz=80.0, got: {tz_vals}"


def test_font_scaling_reset_to_100():
    """Normal paragraph (no w:w) -> Tz 100.0 reset in PDF."""
    pdf = convert(_docx_with_font_scaling())
    tz_vals = _pdf_tz_values(pdf)
    assert 100.0 in tz_vals, f"Expected Tz=100.0 reset, got: {tz_vals}"


# ---------------------------------------------------------------------------
# Combined
# ---------------------------------------------------------------------------

def test_combined_formatting_both_operators():
    """w:spacing + w:w -> both Tc and Tz operators in PDF."""
    pdf = convert(_docx_with_combined_formatting())
    assert _pdf_tc_values(pdf), "No Tc — char spacing missing from combined run"
    assert _pdf_tz_values(pdf), "No Tz — font scaling missing from combined run"
