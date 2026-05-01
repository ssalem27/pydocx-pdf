"""
Command-line interface for pydocx-pdf.

Usage:
    pydocx-pdf input.docx output.pdf
    pydocx-pdf input.docx               # writes input.pdf next to input.docx
    pydocx-pdf input.docx -o out.pdf
    cat file.docx | pydocx-pdf - out.pdf
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydocx_pdf import convert
from pydocx_pdf.exceptions import ConversionError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pydocx-pdf",
        description="Convert a Word document (.docx) to PDF. No system dependencies.",
    )
    parser.add_argument(
        "input",
        help="Path to input .docx file, or - to read from stdin.",
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="Path to output .pdf file. Defaults to <input>.pdf.",
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_flag",
        metavar="OUTPUT",
        help="Output path (alternative to positional argument).",
    )
    parser.add_argument(
        "--font-dir",
        metavar="DIR",
        help="Directory containing extra .ttf font files.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    args = parser.parse_args(argv)

    # Resolve output path
    output = args.output_flag or args.output
    if args.input == "-":
        source = sys.stdin.buffer.read()
        if output is None:
            output = "output.pdf"
    else:
        source = args.input
        if output is None:
            output = str(Path(args.input).with_suffix(".pdf"))

    try:
        convert(source, output, font_dir=args.font_dir)
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
