"""
Parse ``word/_rels/document.xml.rels`` -- relationship ID to target mapping.

DOCX uses an Open Packaging Conventions (OPC) relationship model.  Each
embedded resource (image, hyperlink, etc.) is referenced from the document
body via an opaque relationship ID (``rId1``, ``rId2``, ...) rather than a
direct file path.  The ``.rels`` file maps those IDs to actual targets.

For example, an inline image is referenced as::

    <a:blip r:embed="rId5"/>

The relationships file resolves ``rId5`` to its target::

    <Relationship Id="rId5"
                  Type="..."
                  Target="media/image1.png"/>

:class:`RelationshipsParser` builds this ID -> target map so the document
parser can locate media files when it encounters ``<w:drawing>`` elements.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from pydocx_pdf.utils import parse_xml

# The OPC package relationships namespace (not a WordprocessingML namespace)
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class RelationshipsParser:
    """Parse a ``.rels`` file and resolve relationship IDs to target paths.

    Parameters
    ----------
    xml_bytes:
        Raw bytes of ``word/_rels/document.xml.rels``.  Pass ``b""`` for
        documents with no embedded media; :meth:`resolve` will return
        ``None`` for all IDs in that case.
    """

    def __init__(self, xml_bytes: bytes) -> None:
        # rId -> target path string (normalised to word/-relative basename)
        self._map: dict[str, str] = {}
        if xml_bytes:
            self._parse(parse_xml(xml_bytes))

    def resolve(self, r_id: str) -> str | None:
        """Return the target path for relationship *r_id*.

        Parameters
        ----------
        r_id:
            The relationship ID to look up (e.g. ``"rId5"``).

        Returns
        -------
        str or None
            The normalised target string as stored in the relationships XML
            (e.g. ``"media/image1.png"``), or ``None`` if *r_id* is not
            registered.

        Notes
        -----
        The caller (typically
        :meth:`~pydocx_pdf.parser.document.DocumentParser._extract_image`)
        splits the returned path on ``"/"`` and takes the last component to
        get the bare filename, which it then uses as a key in
        :attr:`~pydocx_pdf.unzipper.DocxParts.media`.
        """
        return self._map.get(r_id)

    def _parse(self, root: ET.Element) -> None:
        """Populate ``_map`` from all ``<Relationship>`` elements."""
        for rel in root.findall(f"{{{_REL_NS}}}Relationship"):
            rid    = rel.get("Id", "")
            target = rel.get("Target", "")
            if rid and target:
                # Normalise: strip leading slash and collapse "../" so
                # "media/image1.png", "/media/image1.png", and
                # "../media/image1.png" all map to "media/image1.png".
                self._map[rid] = target.lstrip("/").replace("../", "")
