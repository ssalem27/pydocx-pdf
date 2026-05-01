"""
Parse word/_rels/document.xml.rels — maps relationship IDs to targets.

Used to resolve image references: <a:blip r:embed="rId5"/> → word/media/image1.png
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, Optional

from pydocx_pdf.utils import parse_xml

_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class RelationshipsParser:
    def __init__(self, xml_bytes: bytes) -> None:
        # rId → target path (relative to the word/ directory)
        self._map: Dict[str, str] = {}
        if xml_bytes:
            self._parse(parse_xml(xml_bytes))

    def resolve(self, r_id: str) -> Optional[str]:
        """Return the target path for relationship *r_id*, or None."""
        return self._map.get(r_id)

    def _parse(self, root: ET.Element) -> None:
        for rel in root.findall(f"{{{_REL_NS}}}Relationship"):
            rid = rel.get("Id", "")
            target = rel.get("Target", "")
            if rid and target:
                # Normalize to just the filename (images are in word/media/)
                self._map[rid] = target.lstrip("/").replace("../", "")
