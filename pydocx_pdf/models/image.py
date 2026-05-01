from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Image:
    filename: str
    data: bytes
    width_pt: Optional[float] = None
    height_pt: Optional[float] = None
