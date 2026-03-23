"""GraphIQ — Join Graph: BFS pathfinding for SQL join resolution."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from app.core.registry.definitions import JoinEdge
from app.core.exceptions import QueryBuildError


@dataclass
class JoinPath:
    """A resolved join path between two tables."""

    edges: list[JoinEdge]

    @property
    def tables(self) -> list[str]:
        """Ordered list of all tables in the path (including endpoints)."""
        if not self.edges:
            return []
        tables = [self.edges[0].from_table]
        for edge in self.edges:
            tables.append(edge.to_table)
        return tables

    @property
    def depth(self) -> int:
        """Number of joins (edges) in the path."""
        return len(self.edges)


class JoinGraph:
    """Graph of legal table joins with BFS shortest-path resolution.

    Built from the static JoinEdge list in definitions.py.
    """

    MAX_JOIN_DEPTH: int = 5

    def __init__(self, edges: list[JoinEdge]) -> None:
        # Adjacency: table -> list[(neighbor_table, edge)]
        self._adj: dict[str, list[tuple[str, JoinEdge]]] = defaultdict(list)
        for edge in edges:
            self._adj[edge.from_table].append((edge.to_table, edge))
            # Also add reverse direction for undirected pathfinding
            # (creates a synthetic reverse edge for BFS only —
            #  the join_type of the reverse edge stays the same)
            reverse = JoinEdge(
                from_table=edge.to_table,
                from_column=edge.to_column,
                to_table=edge.from_table,
                to_column=edge.from_column,
                join_type=edge.join_type,
                preferred=edge.preferred,
            )
            self._adj[edge.to_table].append((edge.from_table, reverse))

    def find_path(self, from_table: str, to_table: str) -> JoinPath:
        """BFS shortest path between two tables.

        Args:
            from_table: Starting table name.
            to_table: Target table name.

        Returns:
            JoinPath describing the shortest route.

        Raises:
            QueryBuildError: If no path exists or path exceeds MAX_JOIN_DEPTH.
        """
        if from_table == to_table:
            return JoinPath(edges=[])

        # BFS: queue of (current_table, path_so_far)
        queue: deque[tuple[str, list[JoinEdge]]] = deque()
        queue.append((from_table, []))
        visited: set[str] = {from_table}

        while queue:
            current, path = queue.popleft()

            if len(path) > self.MAX_JOIN_DEPTH:
                continue  # Prune deep branches

            neighbors = self._adj.get(current, [])
            # Prefer preferred=True edges first
            neighbors_sorted = sorted(neighbors, key=lambda x: (not x[1].preferred,))

            for neighbor, edge in neighbors_sorted:
                if neighbor in visited:
                    continue
                new_path = path + [edge]
                if neighbor == to_table:
                    if len(new_path) > self.MAX_JOIN_DEPTH:
                        raise QueryBuildError(
                            f"Join path from '{from_table}' to '{to_table}' "
                            f"requires {len(new_path)} joins (max {self.MAX_JOIN_DEPTH}). "
                            "Use Neo4j for multi-hop traversals."
                        )
                    return JoinPath(edges=new_path)
                visited.add(neighbor)
                queue.append((neighbor, new_path))

        raise QueryBuildError(
            f"No join path found between '{from_table}' and '{to_table}'. "
            "These tables may not be directly connected in the schema."
        )

    def hop_count(self, from_table: str, to_table: str) -> int:
        """Return the number of hops between two tables, or -1 if no path."""
        try:
            return self.find_path(from_table, to_table).depth
        except QueryBuildError:
            return -1
