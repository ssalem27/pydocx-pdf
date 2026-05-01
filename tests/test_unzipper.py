"""Tests for the DOCX unzipper."""

import io
import zipfile

import pytest

from pydocx_pdf.unzipper import DocxParts, unzip_docx


def _make_docx(files: dict[str, bytes]) -> bytes:
    """Build a minimal in-memory .docx ZIP for testing."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_unzip_extracts_document_xml():
    xml = b"<root/>"
    docx = _make_docx({"word/document.xml": xml})
    parts = unzip_docx(docx)
    assert parts.document_xml == xml


def test_unzip_extracts_media():
    img = b"\x89PNG\r\n"
    docx = _make_docx({
        "word/document.xml": b"<root/>",
        "word/media/image1.png": img,
    })
    parts = unzip_docx(docx)
    assert parts.media["image1.png"] == img


def test_unzip_missing_optional_parts_are_empty():
    docx = _make_docx({"word/document.xml": b"<root/>"})
    parts = unzip_docx(docx)
    assert parts.styles_xml == b""
    assert parts.numbering_xml == b""


def test_unzip_bad_zip_raises():
    with pytest.raises(zipfile.BadZipFile):
        unzip_docx(b"not a zip")


def test_unzip_missing_document_xml_raises():
    docx = _make_docx({"word/styles.xml": b"<root/>"})
    with pytest.raises(KeyError):
        unzip_docx(docx)
