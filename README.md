# pydocx-pdf

[![PyPI](https://img.shields.io/pypi/v/pydocx-pdf)](https://pypi.org/project/pydocx-pdf/)
[![Python](https://img.shields.io/pypi/pyversions/pydocx-pdf)](https://pypi.org/project/pydocx-pdf/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.txt)
[![CI](https://github.com/safialhasi/pydocx-pdf/actions/workflows/python-publish.yml/badge.svg)](https://github.com/safialhasi/pydocx-pdf/actions)

Zero-dependency DOCX → PDF converter designed for **EKS pods**, Docker containers, and other **headless, containerised** environments.

- **No LibreOffice, no Pandoc, no system fonts, no external API calls**
- Unzips `.docx` (a ZIP of XML) and renders a PDF directly using [`fpdf2`](https://py-pdf.github.io/fpdf2/)
- Fully air-gap safe — zero network egress at runtime
- Ships as a standard pip package; works on read-only root filesystems
- PEP 561 compliant (`py.typed` marker included)

---

## Installation

```bash
pip install pydocx-pdf
```

From source:

```bash
git clone https://github.com/safialhasi/pydocx-pdf
cd pydocx-pdf
pip install -e ".[dev]"
```

---

## Quick start

### Python API

```python
from pydocx_pdf import convert

# File path → file path
convert("report.docx", "report.pdf")

# Raw bytes → raw bytes (perfect for web handlers, Lambda, FastAPI)
with open("report.docx", "rb") as fh:
    pdf_bytes = convert(fh.read())

# BytesIO → bytes
import io
convert(io.BytesIO(docx_bytes), "report.pdf")

# Async (FastAPI / aiohttp)
import asyncio
from pydocx_pdf import convert_async

asyncio.run(convert_async("report.docx", "report.pdf"))

# Custom font directory
convert("report.docx", "report.pdf", font_dir="/app/fonts")
```

### CLI

```bash
pydocx-pdf report.docx                    # writes report.pdf
pydocx-pdf report.docx output.pdf         # explicit output path
pydocx-pdf report.docx -o output.pdf      # flag form
pydocx-pdf report.docx --font-dir /fonts  # custom fonts
cat report.docx | pydocx-pdf - output.pdf # read from stdin
pydocx-pdf --version
```

---

## API reference

### `convert(source, dest=None, *, font_dir=None) → bytes`

Convert a `.docx` document to PDF.

| Parameter | Type | Description |
|-----------|------|-------------|
| `source` | `str \| Path \| bytes \| BytesIO` | Input DOCX — file path, raw bytes, or a byte-stream |
| `dest` | `str \| Path \| None` | Optional output path; PDF bytes are always returned |
| `font_dir` | `str \| Path \| None` | Directory of extra `.ttf` files to register |

**Returns** `bytes` — the rendered PDF starting with `b"%PDF-"`.

**Raises**:
- `FileNotFoundError` — when `source` is a path and the file does not exist
- `TypeError` — when `source` is an unsupported type
- `ConversionError` — when the DOCX cannot be parsed or the PDF cannot be rendered

### `convert_async(source, dest=None, *, font_dir=None) → Awaitable[bytes]`

Async wrapper around `convert()`.  Runs in a thread-pool executor so the event loop stays responsive.  Same parameters, same return type.

### `DocxInput`

Type alias for accepted source types: `Union[str, Path, bytes, io.BytesIO]`.

### Exceptions

```python
from pydocx_pdf.exceptions import (
    PydocxPdfError,          # base class — catch this to handle any library error
    ConversionError,         # parse or render failure (wraps the original cause)
    ParseError,              # DOCX XML could not be parsed
    RenderError,             # PDF could not be rendered
    UnsupportedFeatureError, # DOCX feature not yet implemented
)
```

---

## Docker / EKS

```dockerfile
FROM python:3.12-slim
RUN pip install pydocx-pdf
# Optional: bundle extra fonts
COPY fonts/ /app/fonts/
WORKDIR /app
```

Zero egress required at runtime. Works with read-only root filesystems (`/tmp` is used for nothing — all rendering is in-memory).

---

## Supported features

### Text formatting

| Feature | Status | Notes |
|---|---|---|
| Bold / italic / underline | ✅ | |
| Strikethrough (single + double) | ✅ | |
| Font size | ✅ | `w:sz` half-points |
| Font colour | ✅ | Explicit hex + theme colour resolution |
| Superscript / subscript | ✅ | Rendered at 65% of enclosing size |
| All caps / small caps | ✅ | Text uppercased |
| Character spacing | ✅ | `w:spacing` in 1/20-pt units → `set_char_spacing()` |
| Font width scaling | ✅ | `w:w` percentage → `set_stretching()` |
| Tab characters | ✅ | Converted to 4 spaces |
| Kerning threshold | ⚠️ | Parsed, not applied (fpdf2 limitation) |
| Baseline offset | ⚠️ | Parsed, not applied |
| Text highlight | ❌ | fpdf2 limitation |

### Paragraph layout

| Feature | Status | Notes |
|---|---|---|
| Alignment (L/C/R/J) | ✅ | |
| Space before / after | ✅ | |
| Line spacing (auto/exact/atLeast) | ✅ | Auto uses font ascent/descent metrics |
| Left / right / first-line indent | ✅ | |
| Hard page breaks | ✅ | `w:br type="page"` |

### Structure

| Feature | Status | Notes |
|---|---|---|
| Headings (H1–H6, Title, Subtitle) | ✅ | Size + spacing from style ID |
| Bullet lists | ✅ | |
| Ordered lists (decimal/alpha/roman) | ✅ | |
| Nested lists (up to 9 levels) | ✅ | |
| Multi-level counter templates | ✅ | `%1.%2.` placeholders |
| Style inheritance chain | ✅ | Full `basedOn` resolution |

### Tables

| Feature | Status | Notes |
|---|---|---|
| Proportional column widths | ✅ | From `w:tblGrid` |
| Cell background fill | ✅ | `w:shd` |
| Borders (colour + width) | ✅ | Table-level and per-cell |
| Interior grid lines | ✅ | `insideH` / `insideV` |
| Vertical alignment | ✅ | top / center / bottom |
| Horizontal span (`gridSpan`) | ✅ | |
| Vertical merge (`vMerge`) | ✅ | |
| Nested tables | ✅ | Recursive |
| Cell padding | ✅ | Table-level + per-cell overrides |

### Images & other

| Feature | Status | Notes |
|---|---|---|
| Inline images | ✅ | PNG, JPEG, GIF via `<w:drawing>` |
| Hyperlinks | ✅ | Rendered as underlined blue text |
| Tracked change insertions | ✅ | Text included |
| Tracked change deletions | ✅ | Text excluded |
| Headers / footers | 🚧 | Partial support |
| SmartArt / WordArt | ❌ | Complex vector graphics |
| OLE objects | ❌ | |
| BiDi / RTL text | ❌ | |

---

## Font support

### Bundled fonts (always available)

| Family | Replaces | Variants |
|--------|----------|----------|
| LiberationSans | Arial, Calibri, Tahoma, Aptos, … | Regular, Bold, Italic, BoldItalic |
| LiberationSerif | Times New Roman, Georgia, Cambria, … | Regular, Bold, Italic, BoldItalic |
| LiberationMono | Courier New, Consolas, Monaco, … | Regular, Bold, Italic, BoldItalic |
| DejaVuSans | Unicode fallback | Regular, Bold, Oblique, BoldOblique |

### Font resolution order

1. Exact name match (case-insensitive) against registered families
2. Genre lookup (Arial → sans-serif → LiberationSans)
3. Substring heuristics (contains "mono" → LiberationMono)
4. Theme font fallback (document's majorFont / minorFont)

### Custom fonts

Place `.ttf` files in any directory and pass it as `font_dir`:

```python
convert("doc.docx", "doc.pdf", font_dir="/app/fonts")
```

Each file is registered under its stem name (`MyFont-Bold.ttf` → `"MyFont-Bold"`).
No network access required.

---

## Character spacing & font scaling

These DOCX run properties are fully supported:

| DOCX property | Meaning | fpdf2 API used |
|---|---|---|
| `w:spacing/@w:val` | Character spacing in 1/20 pt | `set_char_spacing()` |
| `w:w/@w:val` | Horizontal glyph width % | `set_stretching()` |
| `w:kern/@w:val` | Kerning threshold (half-pt) | Parsed, stored |
| `w:position/@w:val` | Baseline offset (half-pt) | Parsed, stored |

---

## Development

```bash
# Install with dev extras
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=pydocx_pdf --cov-report=term-missing

# Lint
ruff check pydocx_pdf tests

# Type-check (strict)
mypy pydocx_pdf
```

### Project structure

```
pydocx_pdf/
  __init__.py          # Public API: convert, convert_async, exceptions
  converter.py         # Top-level conversion entry points
  cli.py               # Command-line interface
  exceptions.py        # Exception hierarchy
  font_map.py          # DOCX font name → PDF family resolution
  unzipper.py          # DOCX ZIP extraction → DocxParts
  utils.py             # XML helpers + unit conversions
  fonts/               # Bundled TrueType fonts (Liberation + DejaVu)
  models/
    document.py        # Document, Block
    paragraph.py       # Paragraph, Run
    table.py           # Table, TableRow, TableCell, …
    image.py           # Image
  parser/
    document.py        # DocumentParser — walks word/document.xml
    styles.py          # StylesParser — resolves basedOn inheritance chain
    numbering.py       # NumberingParser — list counters
    relationships.py   # RelationshipsParser — rId → target mapping
    theme.py           # parse_theme — font/colour scheme
  renderer/
    pdf_writer.py      # PDFWriter — orchestrates fpdf2
    paragraph.py       # ParagraphRenderer
    table.py           # TableRenderer
tests/
  test_converter.py
  test_character_spacing.py
  test_styles.py
  test_unzipper.py
```

---

## License

[MIT](LICENSE.txt) © Safiuddeen Salem
