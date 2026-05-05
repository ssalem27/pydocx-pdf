# Changelog

All notable changes to **pydocx-pdf** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.1.0] — 2026-05-04

### Added

**Core conversion**
- `convert(source, dest, *, font_dir)` — synchronous DOCX → PDF entry point.
  Accepts file paths (`str` / `pathlib.Path`), raw `bytes`, or `io.BytesIO`.
- `convert_async(source, dest, *, font_dir)` — async wrapper that offloads
  work to a thread-pool executor (suitable for FastAPI / aiohttp).
- `pydocx-pdf` CLI script with stdin support (`-` input), `-o / --output`
  flag, `--font-dir` option, and `--version`.

**Text formatting**
- Bold, italic, underline, strikethrough (single and double).
- Font size from `w:sz` (half-points → points).
- Font colour (explicit RRGGBB hex + theme colour slot resolution).
- Superscript / subscript at 65 % of the enclosing body size.
- All-caps and small-caps text transforms.
- Character spacing (`w:spacing` inside `w:rPr`, 1/20-pt units) via
  `fpdf2.set_char_spacing()`.
- Horizontal glyph width scaling (`w:w` percentage) via
  `fpdf2.set_stretching()`.
- Kerning threshold (`w:kern`) and vertical position offset (`w:position`)
  extracted and stored (not yet applied — fpdf2 limitation).

**Paragraph layout**
- Alignment: left, center, right, justify (`w:jc`).
- Space before / after paragraphs (`w:spacing/@w:before`, `@w:after`).
- Line spacing: auto multiplier, exact, atLeast (`w:spacing/@w:line`,
  `@w:lineRule`).  Auto spacing uses font ascent/descent metrics.
- Left, right, and first-line indentation (`w:ind`).
- Hard page breaks (`w:br w:type="page"`).
- Inline line breaks and tab characters (rendered as 4 spaces).

**Headings**
- `Heading1`–`Heading6`, `Title`, `Subtitle` detected from style ID.
- Hard-coded sizes (28, 24, 18, 14, 12, 11, 10 pt) and pre-paragraph spacing.

**Lists**
- Bullet lists (character markers).
- Ordered lists: decimal, lowerLetter, upperLetter, lowerRoman, upperRoman.
- Nested lists (up to 9 levels via `w:ilvl`).
- Multi-level counter placeholders (`%1.%2.` templates in `w:lvlText`).
- Correct hanging-indent layout (marker column + body text column).
- Counter reset when a higher level advances.

**Tables**
- `<w:tblGrid>` proportional column widths; equal-split fallback.
- Per-cell background fill (`w:shd`).
- Per-edge borders with colour and width (`w:tblBorders`, `w:tcBorders`).
- Interior grid lines (`w:insideH`, `w:insideV`).
- Vertical alignment: top, center, bottom (`w:vAlign`).
- Horizontal spans (`w:gridSpan`).
- Vertical merges (`w:vMerge restart/continue`).
- Nested tables (recursive rendering).
- Table-level and cell-level padding (`w:tblCellMar`, `w:tcMar`).

**Images**
- Inline images via `<w:drawing>` / `<a:blip>`.
- Display dimensions from `<wp:extent cx cy>` (EMU → points → mm).
- Relationship resolution (`word/_rels/document.xml.rels`).

**Style system**
- Full `word/styles.xml` inheritance chain resolution (basedOn chain,
  `w:docDefaults` as ultimate base).
- Inline `<w:pPr>` overrides merged on top of named style.

**Font system**
- Bundled TrueType fonts: Liberation Sans/Serif/Mono + DejaVu Sans
  (Regular, Bold, Italic, BoldItalic each).
- Four-tier font resolution: exact match → genre set → substring heuristic
  → theme fallback.
- Theme font resolution (`w:asciiTheme` major/minor references).
- Custom font directory support (`font_dir` argument / `--font-dir` CLI flag).

**Theme**
- `word/theme/theme1.xml` parsing for font scheme and colour scheme.
- Theme colour slot resolution (`w:themeColor` → RRGGBB hex).

**Exceptions**
- `PydocxPdfError` (base), `ConversionError`, `ParseError`, `RenderError`,
  `UnsupportedFeatureError`.

**Package**
- `py.typed` marker (PEP 561 — inline type stubs).
- `pydocx_pdf.models` public package with explicit `__all__`.
- GitHub Actions workflow: test matrix (Python 3.9 / 3.11 / 3.12),
  ruff linting, mypy strict type-checking, PyPI OIDC trusted publishing.

### Known limitations

- No header / footer support.
- No SmartArt, WordArt, or OLE object rendering.
- No tracked-change deletion rendering (deletions are skipped).
- No bidirectional (RTL) text.
- No text highlight colour (fpdf2 limitation).
- Kerning and baseline offset are parsed but not applied.
- Output is always A4 portrait; page size is not read from the DOCX.

---

[Unreleased]: https://github.com/ssalem27/pydocx-pdf/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ssalem27/pydocx-pdf/releases/tag/v0.1.0
