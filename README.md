# pydocx-pdf

Zero-dependency DOCX → PDF converter designed for EKS pods and other containerized, headless environments.

- **No LibreOffice, no system fonts, no external calls**
- Unzips `.docx` (a ZIP of XML) and manually renders a PDF using [`fpdf2`](https://py-pdf.github.io/fpdf2/)
- Fully air-gap safe — zero network egress at runtime
- Pure Python, ships as a standard pip package

---

## Installation

```bash
pip install pydocx-pdf
```

Or from source:

```bash
pip install .
```

---

## Usage

```python
from pydocx_pdf import convert

# File paths
convert("input.docx", "output.pdf")

# Bytes in, bytes out
with open("input.docx", "rb") as f:
    pdf_bytes = convert(f.read())

# Async
import asyncio
from pydocx_pdf import convert_async

asyncio.run(convert_async("input.docx", "output.pdf"))
```

### Custom fonts

```python
convert("input.docx", "output.pdf", font_dir="/app/fonts")
```

Place `.ttf` files in `font_dir`. They are registered with fpdf2 at startup — no network calls.

---

## EKS / Docker

```dockerfile
FROM python:3.11-slim
RUN pip install pydocx-pdf
COPY fonts/ /app/fonts/
COPY . /app
WORKDIR /app
```

Zero egress required. Works with read-only root filesystems.

---

## Supported Features

### Text Formatting

| Feature                    | Status | Notes |
|----------------------------|--------|-------|
| Paragraphs                 | ✅     |       |
| Bold / italic / underline  | ✅     |       |
| Font size / color          | ✅     |       |
| Character spacing          | ✅     | Expanded/condensed via `w:spacing` |
| Font width scaling         | ✅     | Via `w:w` (e.g., 80% condensed)   |
| Superscript / subscript    | ✅     |       |
| All caps / small caps      | ✅     |       |
| Strikethrough              | ✅     |       |
| Tab characters             | ✅     | Converted to spaces               |

### Layout & Structure

| Feature           | Status | Notes |
|-------------------|--------|-------|
| Alignment         | ✅     | Left, center, right, justify |
| Bullet lists      | ✅     |       |
| Ordered lists     | ✅     |       |
| Indentation       | ✅     | Paragraph-level only |
| Line spacing      | ✅     | Single, 1.5×, double, exact |
| Page breaks       | ✅     |       |

### Content

| Feature            | Status | Notes |
|--------------------|--------|-------|
| Tables             | ✅     | Basic layout |
| Inline images      | ✅     |       |
| Style inheritance  | ✅     |       |
| Fonts              | ✅     | Arial, Times, Courier via Liberation fonts |

### Not Supported

| Feature            | Status | Reason |
|--------------------|--------|--------|
| Headers / footers  | 🚧     | Partial support |
| Kerning threshold  | ⚠️     | Extracted but font-level feature |
| Baseline offset    | ⚠️     | Extracted but no fpdf2 API |
| Text highlight     | ❌     | fpdf2 limitation |
| SmartArt / WordArt | ❌     | Complex vector graphics |
| Tracked changes    | ❌     |       |
| OLE objects        | ❌     |       |
| BiDi / RTL text    | ❌     |       |

---

## Font Support

**Bundled Fonts** (metric-compatible with Microsoft fonts):
- LiberationSans (Arial replacement)
- LiberationSerif (Times New Roman replacement)
- LiberationMono (Courier replacement)
- DejaVuSans (fallback)

Each font includes Regular, Bold, Italic, and BoldItalic variants.

**Font Resolution** (in order):
1. Exact match (Arial → LiberationSans)
2. Genre lookup (Helvetica → sans-serif)
3. Substring heuristics (contains "courier" → monospace)
4. Theme fallback (document theme fonts)

---

## Character Spacing & Font Scaling

Character-level formatting is fully supported:

```python
from pydocx_pdf import convert

# Character spacing automatically applied from DOCX
# - Positive values expand spacing
# - Negative values condense spacing
# - Proper unit conversion: 1 twentiethpt = 0.01764 mm

# Font width scaling also applied
# - 100% = normal width
# - 80% = condensed
# - 120% = expanded

pdf_bytes = convert("document_with_spacing.docx")
```

**DOCX Properties Extracted**:
- `w:spacing/@w:val` — Character spacing (1/20th point)
- `w:w/@w:val` — Font width percentage
- `w:kern/@w:val` — Kerning threshold (parsed, not applied)
- `w:position/@w:val` — Vertical offset (parsed, not applied)

---

## Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=pydocx_pdf

# Run specific test file
pytest tests/test_character_spacing.py
```

**Test Coverage**:
- Character spacing extraction and application
- Font scaling/width adjustment
- Tab character handling
- All text rendering paths (list items, single-format, multi-format)
- Font resolution and substitution
- Style inheritance

---

## Cleanup

If you need to clean up auto-generated files and update `.gitignore`:

**Windows**:
```cmd
CLEANUP.bat
```

**macOS/Linux**:
```bash
bash CLEANUP.sh
```

This removes:
- Temporary test files
- Pytest caches
- Optional: egg-info and venv directories

---

## Development

```bash
pip install -e ".[dev]"
pytest --cov=pydocx_pdf
```

### Key Implementation Files

- `pydocx_pdf/parser/styles.py` — Extract DOCX properties (including character spacing)
- `pydocx_pdf/models/paragraph.py` — Run model with character formatting properties
- `pydocx_pdf/renderer/paragraph.py` — Apply formatting to PDF

---

## License

MIT
