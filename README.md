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

## Supported features

| Feature            | Status  |
|--------------------|---------|
| Paragraphs         | ✅      |
| Bold / italic      | ✅      |
| Font size / color  | ✅      |
| Alignment          | ✅      |
| Bullet lists       | ✅      |
| Ordered lists      | ✅      |
| Tables             | ✅ basic |
| Inline images      | ✅      |
| Style inheritance  | ✅      |
| Page breaks        | ✅      |
| Headers / footers  | 🚧      |
| SmartArt / WordArt | ❌      |
| Tracked changes    | ❌      |
| OLE objects        | ❌      |
| BiDi / RTL text    | ❌      |

---

## Development

```bash
pip install -e ".[dev]"
pytest --cov=pydocx_pdf
```

---

## License

MIT
