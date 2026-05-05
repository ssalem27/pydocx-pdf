"""
Command-line interface for pydocx-pdf.

Provides a ``pydocx-pdf`` script that converts a Word document to PDF
without requiring LibreOffice, Pandoc, or any other system dependency.

Usage
-----
::

    pydocx-pdf input.docx                    # writes input.pdf alongside input.docx
    pydocx-pdf input.docx output.pdf         # explicit output path (positional)
    pydocx-pdf input.docx -o output.pdf      # explicit output path (flag)
    pydocx-pdf input.docx --font-dir /fonts  # custom font directory
    cat file.docx | pydocx-pdf - output.pdf  # read DOCX from stdin
    pydocx-pdf --version                     # print version and exit

Exit codes
----------
0   Conversion succeeded.
1   File not found, unsupported input, or conversion error (details on stderr).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydocx_pdf import __version__, convert
from pydocx_pdf.exceptions import ConversionError


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``pydocx-pdf`` command-line tool.

    Parses *argv* (defaults to ``sys.argv[1:]`` when ``None``), invokes
    :func:`~pydocx_pdf.convert`, and prints a success or error message to
    the appropriate stream.

    Parameters
    ----------
    argv:
        Argument list to parse.  Pass an explicit list to call this
        programmatically without touching ``sys.argv``::

            rc = main(["input.docx", "output.pdf"])

        When ``None`` (the default) :mod:`argparse` reads ``sys.argv[1:]``.

    Returns
    -------
    int
        ``0`` on success, ``1`` on any error (message printed to stderr).
    """
    parser = argparse.ArgumentParser(
        prog="pydocx-pdf",
        description=(
            "Convert a Word document (.docx) to PDF.\n"
            "No LibreOffice, no Pandoc, no system dependencies."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  pydocx-pdf report.docx                    # writes report.pdf\n"
            "  pydocx-pdf report.docx output.pdf         # explicit output\n"
            "  pydocx-pdf report.docx -o output.pdf      # flag form\n"
            "  pydocx-pdf report.docx --font-dir /fonts  # custom fonts\n"
            "  cat report.docx | pydocx-pdf - output.pdf # stdin\n"
        ),
    )

    parser.add_argument(
        "input",
        help="Path to the input .docx file, or '-' to read from stdin.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help=(
            "Path to the output .pdf file.  "
            "Defaults to <input>.pdf in the same directory as the input."
        ),
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_flag",
        metavar="OUTPUT",
        help="Output path (alternative to the positional argument).",
    )
    parser.add_argument(
        "--font-dir",
        metavar="DIR",
        help=(
            "Directory containing extra .ttf font files to register.  "
            "Useful in containers where custom fonts are bundled at a known path."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args(argv)

    # Resolve the output path and the source (file path or stdin bytes).
    output: str = args.output_flag or args.output or ""

    if args.input == "-":
        # Read raw DOCX bytes from stdin (binary mode).
        source: object = sys.stdin.buffer.read()
        if not output:
            output = "output.pdf"
    else:
        source = args.input
        if not output:
            # Default: same directory as the input, .pdf extension.
            output = str(Path(args.input).with_suffix(".pdf"))

    # Run the conversion.
    try:
        convert(source, output, font_dir=args.font_dir)  # type: ignore[arg-type]
    except FileNotFoundError as exc:
        print(f"pydocx-pdf: error: {exc}", file=sys.stderr)
        return 1
    except ConversionError as exc:
        print(f"pydocx-pdf: conversion failed: {exc}", file=sys.stderr)
        return 1

    print(f"pydocx-pdf: wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
