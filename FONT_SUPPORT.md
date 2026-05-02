# Font Support in pydocx-pdf

## Overview

The pydocx-pdf project now includes comprehensive font support with automatic mapping of Microsoft Word fonts to open-source alternatives.

## Supported Fonts

### Built-in Fonts (Bundled)

#### Sans-Serif: LiberationSans
- **Purpose**: Replaces Arial and other sans-serif fonts
- **Styles**: Regular, Bold, Italic, Bold Italic
- **Files**: 4 TTF files in `pydocx_pdf/fonts/`

#### Serif: LiberationSerif  
- **Purpose**: Replaces Times New Roman and other serif fonts
- **Styles**: Regular, Bold, Italic, Bold Italic
- **Files**: 4 TTF files in `pydocx_pdf/fonts/`

#### Monospace: LiberationMono
- **Purpose**: Replaces Courier, Courier New, and other monospace fonts
- **Styles**: Regular, Bold, Italic, Bold Italic
- **Files**: 4 TTF files in `pydocx_pdf/fonts/`

#### Fallback: DejaVuSans
- **Purpose**: Unicode fallback for any unmapped fonts
- **Styles**: Regular, Bold, Italic, Bold Italic
- **Files**: 4 TTF files in `pydocx_pdf/fonts/`

**Total: 16 font files (4 families × 4 styles each)**

## Font Resolution

The `FontRegistry` class in `font_map.py` uses a 4-step resolution strategy:

### 1. Exact Match (Case-Insensitive)
If a DOCX specifies a font that's directly registered in the PDF, it's used.

Example:
```
Arial → LiberationSans (registered)
```

### 2. Genre Lookup
Fonts are categorized into genre sets (sans-serif, serif, monospace). If a font matches a genre, the best available family in that category is selected.

Common mappings:
- Arial, Helvetica, Calibri → **LiberationSans**
- Times New Roman, Georgia, Cambria → **LiberationSerif**
- Courier, Consolas, Monaco → **LiberationMono**

### 3. Substring Heuristics
Fonts are matched by keywords if they don't fit exact categories.

Examples:
- "Courier New Cond" → **LiberationMono** (contains "courier")
- "Times Bold" → **LiberationSerif** (contains "times")

### 4. Fallback to Theme Defaults
If no match is found, the document's theme fonts (major/minor) are used.

## Known Issues & Fixes

### Tab Character Handling
**Issue**: PDF fonts don't have glyphs for tab characters (\t), causing warnings:
```
Font MPDFAA+LiberationSans is missing the following glyphs: '\t'
```

**Solution**: Tabs are automatically replaced with 4 spaces during text rendering (in `paragraph.py`).

## Usage

### Default Behavior
Simply use the `convert()` function - font resolution happens automatically:

```python
from pydocx_pdf import convert

pdf_bytes = convert("document.docx")
```

### Custom Fonts
Provide additional fonts via the `font_dir` parameter:

```python
pdf_bytes = convert("document.docx", font_dir="/path/to/fonts")
```

Custom fonts in the directory will be registered and have priority in resolution.

## Font Files Location

All bundled fonts are stored in:
```
pydocx_pdf/fonts/
├── DejaVuSans.ttf
├── DejaVuSans-Bold.ttf
├── DejaVuSans-Italic.ttf
├── DejaVuSans-BoldItalic.ttf
├── LiberationSans-Regular.ttf
├── LiberationSans-Bold.ttf
├── LiberationSans-Italic.ttf
├── LiberationSans-BoldItalic.ttf
├── LiberationSerif-Regular.ttf
├── LiberationSerif-Bold.ttf
├── LiberationSerif-Italic.ttf
├── LiberationSerif-BoldItalic.ttf
├── LiberationMono-Regular.ttf
├── LiberationMono-Bold.ttf
├── LiberationMono-Italic.ttf
└── LiberationMono-BoldItalic.ttf
```

## Font Licensing

- **Liberation Fonts**: SIL Open Font License (OFL) 1.1
  - Free for commercial and personal use
  - Metric-compatible with Microsoft Office fonts
  
- **DejaVu Fonts**: Bitstream Vera License + Arev License
  - Free for commercial and personal use
  - Unicode support for extended character sets

Both licenses are permissive and suitable for Docker/EKS deployment.

## Testing

Verify font support:

```python
from pydocx_pdf.font_map import FontRegistry

registered = {"LiberationSans", "LiberationSerif", "LiberationMono", "DejaVuSans"}
registry = FontRegistry(registered=registered, major_font="Calibri", minor_font="Calibri")

# Test common fonts
print(registry.resolve("Arial"))              # → LiberationSans
print(registry.resolve("Times New Roman"))    # → LiberationSerif
print(registry.resolve("Courier New"))        # → LiberationMono
```
