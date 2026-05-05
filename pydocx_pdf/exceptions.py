"""
Custom exception hierarchy for pydocx-pdf.

All exceptions raised by this library derive from :class:`PydocxPdfError`,
making it easy for callers to catch library-specific errors without
accidentally swallowing unrelated exceptions::

    from pydocx_pdf.exceptions import PydocxPdfError

    try:
        convert("file.docx", "file.pdf")
    except PydocxPdfError as exc:
        log.error("conversion failed: %s", exc)

Hierarchy::

    PydocxPdfError
    +-- ConversionError       general parse/render failure (top-level wrapper)
    +-- ParseError            DOCX XML could not be parsed
    +-- RenderError           PDF could not be rendered from the parsed model
    +-- UnsupportedFeatureError  DOCX feature not yet implemented
"""


class PydocxPdfError(Exception):
    """Base exception for all pydocx-pdf errors.

    Catch this class to intercept any error raised by the library::

        try:
            convert(source, dest)
        except PydocxPdfError as exc:
            handle(exc)
    """


class ConversionError(PydocxPdfError):
    """Raised when the end-to-end DOCX -> PDF conversion fails.

    This is the primary exception raised by :func:`~pydocx_pdf.convert`.  It
    wraps lower-level :class:`ParseError` and :class:`RenderError` instances
    so callers only need to handle one exception type at the top level.

    The original cause is always chained (``__cause__``) and can be inspected
    if finer-grained error handling is needed::

        try:
            convert(source, dest)
        except ConversionError as exc:
            if isinstance(exc.__cause__, ParseError):
                ...  # malformed DOCX
    """


class ParseError(PydocxPdfError):
    """Raised when the DOCX ZIP or its XML content cannot be parsed.

    Typical causes:

    - The input is not a valid ZIP archive.
    - ``word/document.xml`` is missing or malformed.
    - A required XML namespace is absent.
    """


class RenderError(PydocxPdfError):
    """Raised when the in-memory document model cannot be rendered to PDF.

    Typical causes:

    - A required font file is missing or unreadable.
    - An fpdf2 API call fails unexpectedly.
    """


class UnsupportedFeatureError(PydocxPdfError):
    """Raised for DOCX features that are not yet implemented.

    Examples: SmartArt, WordArt, OLE objects, bidirectional text.

    Note: most unsupported features are silently skipped rather than raising
    this exception.  It is reserved for cases where the feature is so central
    that producing a result without it would be meaningless.
    """
