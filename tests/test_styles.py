"""Tests for the styles parser."""


from pydocx_pdf.parser.styles import StylesParser

_STYLES_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:styleId="Normal" w:type="paragraph">
    <w:rPr>
      <w:sz w:val="22"/>
    </w:rPr>
  </w:style>
  <w:style w:styleId="Heading1" w:type="paragraph">
    <w:basedOn w:val="Normal"/>
    <w:rPr>
      <w:b/>
      <w:sz w:val="32"/>
    </w:rPr>
  </w:style>
</w:styles>"""


def test_get_normal_style():
    parser = StylesParser(_STYLES_XML)
    props = parser.get("Normal")
    assert props["font_size_half_pt"] == 22


def test_heading_inherits_from_normal():
    parser = StylesParser(_STYLES_XML)
    props = parser.get("Heading1")
    # Should have bold from Heading1 and size overriding Normal
    assert props["bold"] is True
    assert props["font_size_half_pt"] == 32


def test_unknown_style_returns_empty():
    parser = StylesParser(_STYLES_XML)
    props = parser.get("NonExistent")
    assert props == {}


def test_empty_xml_is_safe():
    parser = StylesParser(b"")
    assert parser.get("Normal") == {}
