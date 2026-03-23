"""GraphIQ — PostgreSQL async storage via asyncpg."""
from __future__ import annotations

from typing import Any

import asyncpg  # type: ignore[import]

from app.core.exceptions import StoreError


class PostgresStore:
    """Async PostgreSQL connection pool and query executor.

    Created at startup, shared across all handlers.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def create(cls, dsn: str) -> "PostgresStore":
        """Create a PostgresStore with a connection pool.

        Args:
            dsn: asyncpg-compatible PostgreSQL DSN.

        Returns:
            Initialized PostgresStore instance.
        """
        pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        return cls(pool)

    async def fetch(self, query: str, *params: Any) -> list[asyncpg.Record]:
        """Execute a SELECT query and return all rows.

        Args:
            query: Parameterized SQL string.
            *params: Query parameters.

        Returns:
            List of asyncpg.Record objects.

        Raises:
            StoreError: On PostgreSQL error or timeout.
        """
        try:
            async with self._pool.acquire() as conn:
                return await conn.fetch(query, *params)
        except asyncpg.PostgresError as e:
            raise StoreError(f"PostgreSQL query failed: {e}", detail=query) from e

    async def fetch_one(self, query: str, *params: Any) -> asyncpg.Record | None:
        """Execute a SELECT query and return the first row or None."""
        try:
            async with self._pool.acquire() as conn:
                return await conn.fetchrow(query, *params)
        except asyncpg.PostgresError as e:
            raise StoreError(f"PostgreSQL query failed: {e}") from e

    async def execute(self, query: str, *params: Any) -> str:
        """Execute a non-SELECT query (INSERT, UPDATE, DELETE)."""
        try:
            async with self._pool.acquire() as conn:
                return await conn.execute(query, *params)
        except asyncpg.PostgresError as e:
            raise StoreError(f"PostgreSQL execute failed: {e}") from e

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        """Bulk execute a query with multiple parameter tuples."""
        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(query, args)
        except asyncpg.PostgresError as e:
            raise StoreError(f"PostgreSQL bulk execute failed: {e}") from e

    async def health_check(self) -> bool:
        """Check PostgreSQL connectivity."""
        try:
            async with self._pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the connection pool."""
        await self._pool.close()
