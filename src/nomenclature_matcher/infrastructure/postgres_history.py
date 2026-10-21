from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..settings import Settings


class PostgresRequestHistory:
    def __init__(self, settings: Settings):
        self.open_timeout = settings.db_connect_timeout_seconds
        self.pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            timeout=settings.db_connect_timeout_seconds,
            kwargs={"autocommit": True},
            open=False,
        )

    def open(self) -> None:
        self.pool.open(wait=True, timeout=self.open_timeout)
        try:
            with self.pool.connection() as conn:
                migration_table = conn.execute(
                    "SELECT to_regclass('public.rag_schema_migrations')"
                ).fetchone()
                if not migration_table or migration_table[0] is None:
                    raise RuntimeError(
                        "Request-history schema is not migrated; run the database migration service"
                    )
                migrated = conn.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM rag_schema_migrations
                        WHERE version = '0001_request_history'
                    )
                    """
                ).fetchone()
            if not migrated or not migrated[0]:
                raise RuntimeError(
                    "Request-history schema is not migrated; run the database migration service"
                )
        except Exception:
            self.pool.close()
            raise

    def record(
        self,
        *,
        request_id: str,
        created_at: datetime,
        completed_at: datetime,
        status: str,
        http_status: int,
        product_count: int,
        matched_count: int,
        latency_ms: float,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        error: str | None = None,
    ) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO rag_match_requests (
                    request_id, created_at, completed_at, status, http_status,
                    product_count, matched_count, latency_ms,
                    request_json, response_json, error
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                """,
                (
                    request_id,
                    created_at,
                    completed_at,
                    status,
                    http_status,
                    product_count,
                    matched_count,
                    latency_ms,
                    Jsonb(request_payload),
                    Jsonb(response_payload),
                    error,
                ),
            )

    def ping(self) -> bool:
        try:
            with self.pool.connection() as conn:
                row = conn.execute("SELECT 1").fetchone()
            return bool(row and row[0] == 1)
        except Exception:
            return False

    def close(self) -> None:
        self.pool.close()
