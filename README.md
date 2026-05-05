# pydocx-pdf

[![PyPI](https://img.shields.io/pypi/v/pydocx-pdf)](https://pypi.org/project/pydocx-pdf/)
[![Python](https://img.shields.io/pypi/pyversions/pydocx-pdf)](https://pypi.org/project/pydocx-pdf/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE.txt)
[![CI](https://github.com/ssalem27/pydocx-pdf/actions/workflows/python-publish.yml/badge.svg)](https://github.com/ssalem27/pydocx-pdf/actions)

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
git clone https://github.com/ssalem27/pydocx-pdf
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
pydocx-pd