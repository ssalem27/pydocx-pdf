"""
PDF rendering package.

Converts the intermediate document model into a PDF byte string using
the ``fpdf2`` library.

Modules
-------
pdf_writer      -- top-level orchestrator; registers fonts, iterates blocks
paragraph       -- renders Paragraph objects (text, lists, images)
table           -- renders Table objects (borders, cell layout, nested tables)
"""
