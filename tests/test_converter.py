"""End-to-end smoke tests for the convert() function."""

import io
import zipfile

import pytest

from pydocx_pdf import convert
from pydocx_pdf.exceptions import ConversionError


def _minimal_docx() -> bytes:
    """Return a valid minimal .docx with a single paragraph."""
    document_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>Hello, World!</w:t></w:r>
    </w:p>
  </w:body>
</w:document>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def test_convert_bytes_returns_pdf():
    pdf = convert(_minimal_docx())
    assert pdf.startswith(b"%PDF-")


def test_convert_bytesio_input():
    pdf = convert(io.BytesIO(_minimal_docx()))
    assert pdf.startswith(b"%PDF-")


def test_convert_writes_to_file(tmp_path):
    out = tmp_path / "out.pdf"
    convert(_minimal_docx(), out)
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF-")


def test_convert_bad_input_raises():
    with pytest.raises(ConversionError):
        convert(b"not a docx")


def test_convert_nonexistent_file_raises():
    with pytest.raises(FileNotFoundError):
        convert("/tmp/does_not_exist_xyz.docx")
