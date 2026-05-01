"""Custom exceptions for pydocx-pdf."""


class PydocxPdfError(Exception):
    """Base exception for all pydocx-pdf errors."""


class ConversionError(PydocxPdfError):
    """Raised when DOCX → PDF conversion fails."""


class ParseError(PydocxPdfError):
    """Raised when the DOCX XML cannot be parsed."""


class RenderError(PydocxPdfError):
    """Raised when the PDF cannot be rendered."""


class UnsupportedFeatureError(PydocxPdfError):
    """Raised for DOCX features not yet implemented (SmartArt, OLE, etc.)."""
