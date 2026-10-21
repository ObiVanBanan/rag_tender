from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LDProduct:
    """A product from the LD catalog, used as the domain matching subject."""

    id: int
    name: str
    article: str | None = None
    price: Any = None
    dn: Any = None
    pn: Any = None
    joining_type: str | None = None
    url: str | None = None
    properties: Any = field(default_factory=dict)
