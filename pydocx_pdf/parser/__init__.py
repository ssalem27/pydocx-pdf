"""
DOCX XML parsing package.

Converts raw XML bytes extracted from a ``.docx`` ZIP archive into the
intermediate data model consumed by the renderer.

Modules
-------
document        -- main parser; walks ``word/document.xml`` and emits Blocks
styles          -- resolves the ``word/styles.xml`` inheritance chain
numbering       -- tracks list counters from ``word/numbering.xml``
relationships   -- maps relationship IDs to targets (``_rels/document.xml.rels``)
theme           -- extracts font and colour scheme from ``word/theme/theme1.xml``
"""
