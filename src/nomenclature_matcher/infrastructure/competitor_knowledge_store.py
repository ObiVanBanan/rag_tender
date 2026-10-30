from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..domain.competitor import CompetitorResolution, ResolvedFact, compact_identity
from ..domain.query_signals import exact_product_identity_anchors


class CompetitorKnowledgeStore:
    """Exact-product KB.

    V2 intentionally uses a new table so family-collapsed v1 rows such as
    marshal:11с67п can never affect exact variant requests.
    """

    TABLE = "competitor_products_v2"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    identity_key TEXT PRIMARY KEY,
                    identity_anchor TEXT NOT NULL,
                    identity_level TEXT NOT NULL,
                    manufacturer TEXT,
                    article TEXT,
                    aliases_json TEXT NOT NULL,
                    facts_json TEXT NOT NULL
                )
                """
            )

    def find(self, query: str) -> CompetitorResolution | None:
        anchors = set(exact_product_identity_anchors(query))
        if not anchors:
            return None

        best_row = None
        best_len = -1
        with sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                f"SELECT identity_key, identity_anchor, identity_level, manufacturer, "
                f"article, aliases_json, facts_json FROM {self.TABLE} "
                "WHERE identity_level = 'EXACT_PRODUCT'"
            ).fetchall()

        for row in rows:
            candidates = {row[1], *json.loads(row[5])}
            for alias in candidates:
                token = compact_identity(alias)
                if token in anchors and len(token) > best_len:
                    best_row = row
                    best_len = len(token)

        if best_row is None:
            return None

        facts_payload = json.loads(best_row[6])
        facts = {
            field: ResolvedFact(
                value=item.get("value"),
                status=item.get("status", "UNKNOWN"),
                sources=item.get("sources", []),
            )
            for field, item in facts_payload.items()
        }
        return CompetitorResolution(
            status="KB_HIT",
            identity_key=best_row[0],
            identity_anchor=best_row[1],
            identity_level=best_row[2],
            manufacturer=best_row[3],
            article=best_row[4],
            aliases=tuple(json.loads(best_row[5])),
            facts=facts,
        )

    def put(self, resolution: CompetitorResolution) -> None:
        if not resolution.resolved:
            return

        payload = {
            field: fact.as_dict()
            for field, fact in sorted((resolution.facts or {}).items())
        }
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                f"""
                INSERT INTO {self.TABLE}(
                    identity_key, identity_anchor, identity_level, manufacturer,
                    article, aliases_json, facts_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identity_key) DO UPDATE SET
                    identity_anchor=excluded.identity_anchor,
                    identity_level=excluded.identity_level,
                    manufacturer=excluded.manufacturer,
                    article=excluded.article,
                    aliases_json=excluded.aliases_json,
                    facts_json=excluded.facts_json
                """,
                (
                    resolution.identity_key,
                    resolution.identity_anchor,
                    resolution.identity_level,
                    resolution.manufacturer,
                    resolution.article,
                    json.dumps(list(resolution.aliases), ensure_ascii=False),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )
