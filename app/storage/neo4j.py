"""GraphIQ — Neo4j async storage via neo4j.AsyncDriver."""
from __future__ import annotations

import time
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase  # type: ignore[import]
from neo4j.exceptions import Neo4jError  # type: ignore[import]

from app.core.exceptions import StoreError


class Neo4jStore:
    """Async Neo4j driver wrapper with query execution and sync utilities."""

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver
        self._last_sync_ts: float = 0.0

    @classmethod
    async def create(cls, url: str, user: str, password: str) -> "Neo4jStore":
        """Create a Neo4jStore with an async driver.

        Args:
            url: Bolt URL, e.g. bolt://localhost:7687
            user: Neo4j username.
            password: Neo4j password.

        Returns:
            Initialized Neo4jStore instance.
        """
        driver = AsyncGraphDatabase.driver(url, auth=(user, password))
        return cls(driver)

    async def run_query(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts.

        Args:
            cypher: Parameterized Cypher string.
            params: Parameter dict.

        Returns:
            List of result dicts.

        Raises:
            StoreError: On Neo4j execution error.
        """
        try:
            async with self._driver.session() as session:
                result = await session.run(cypher, params)
                records = await result.data()
                return records
        except Neo4jError as e:
            raise StoreError(f"Neo4j query failed: {e}", detail=cypher) from e

    async def run_write(self, cypher: str, params: dict[str, Any]) -> None:
        """Execute a write Cypher (MERGE, CREATE) within a write transaction."""
        try:
            async with self._driver.session() as session:
                await session.execute_write(
                    lambda tx: tx.run(cypher, params)
                )
        except Neo4jError as e:
            raise StoreError(f"Neo4j write failed: {e}") from e

    async def run_batch_write(self, cypher: str, batch: list[dict[str, Any]]) -> None:
        """Run a Cypher with UNWIND for batch writes.

        Args:
            cypher: Cypher with UNWIND $rows AS row ...
            batch: List of row dicts to unwind.
        """
        try:
            async with self._driver.session() as session:
                await session.execute_write(
                    lambda tx: tx.run(cypher, {"rows": batch})
                )
        except Neo4jError as e:
            raise StoreError(f"Neo4j batch write failed: {e}") from e

    async def health_check(self) -> bool:
        """Check Neo4j connectivity."""
        try:
            async with self._driver.session() as session:
                await session.run("RETURN 1")
            return True
        except Exception:
            return False

    def sync_lag_seconds(self) -> float:
        """Return seconds since the last successful neo4j sync."""
        if self._last_sync_ts == 0.0:
            return -1.0
        return time.time() - self._last_sync_ts

    def record_sync(self) -> None:
        """Mark the current time as last successful sync."""
        self._last_sync_ts = time.time()

    async def close(self) -> None:
        """Close the driver."""
        await self._driver.close()
