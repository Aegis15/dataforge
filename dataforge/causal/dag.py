"""Column-level causal DAG utilities for root-cause analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx  # type: ignore[import-untyped]

__all__ = ["CausalDAG", "CausalEdge"]


@dataclass(frozen=True)
class CausalEdge:
    """Metadata for a directed causal edge.

    Args:
        source: Source column name.
        target: Target column name.
        confidence: Confidence in the directed influence, from 0.0 to 1.0.
        provenance: Human-readable source of the edge.
    """

    source: str
    target: str
    confidence: float
    provenance: str


class CausalDAG:
    """Acyclic directed graph whose nodes are dataset columns.

    Args:
        nodes: Optional initial column names.

    Example:
        >>> dag = CausalDAG(["discount_pct", "order_total"])
        >>> dag.add_edge("discount_pct", "order_total", confidence=0.9, provenance="fd")
        >>> dag.is_reachable("discount_pct", "order_total")
        True
    """

    def __init__(self, nodes: list[str] | tuple[str, ...] = ()) -> None:
        self._graph: nx.DiGraph[Any] = nx.DiGraph()
        self._graph.add_nodes_from(nodes)

    @property
    def nodes(self) -> tuple[str, ...]:
        """Return graph nodes in insertion order."""
        return tuple(str(node) for node in self._graph.nodes)

    @property
    def edges(self) -> tuple[CausalEdge, ...]:
        """Return directed edges with metadata."""
        result: list[CausalEdge] = []
        for source, target, attrs in self._graph.edges(data=True):
            result.append(
                CausalEdge(
                    source=str(source),
                    target=str(target),
                    confidence=float(attrs.get("confidence", 0.0)),
                    provenance=str(attrs.get("provenance", "unknown")),
                )
            )
        return tuple(result)

    def add_node(self, column: str) -> None:
        """Add a column node if it is not already present.

        Args:
            column: Column name.
        """
        self._graph.add_node(column)

    def add_edge(
        self,
        source: str,
        target: str,
        *,
        confidence: float,
        provenance: str,
    ) -> None:
        """Add a directed causal edge while preserving acyclicity.

        Args:
            source: Source column name.
            target: Target column name.
            confidence: Confidence score from 0.0 to 1.0.
            provenance: Source of the edge.

        Raises:
            ValueError: If the edge is self-referential or creates a cycle.
        """
        if source == target:
            raise ValueError("Causal DAG does not allow self-edges")
        self._graph.add_node(source)
        self._graph.add_node(target)
        if nx.has_path(self._graph, target, source):
            raise ValueError(f"Adding {source!r} -> {target!r} would create a cycle")
        bounded = max(0.0, min(1.0, confidence))
        self._graph.add_edge(source, target, confidence=bounded, provenance=provenance)

    def successors(self, column: str) -> tuple[str, ...]:
        """Return direct downstream columns for a node.

        Args:
            column: Column name.

        Returns:
            A tuple of direct successor column names.
        """
        if column not in self._graph:
            return ()
        return tuple(str(node) for node in self._graph.successors(column))

    def is_reachable(self, source: str, target: str) -> bool:
        """Return whether target is reachable from source.

        Args:
            source: Source column name.
            target: Target column name.

        Returns:
            True if source equals target or a directed path exists.
        """
        if source == target:
            return True
        if source not in self._graph or target not in self._graph:
            return False
        return bool(nx.has_path(self._graph, source, target))

    def path_confidence(self, source: str, target: str) -> float:
        """Return the weakest-edge confidence on the shortest path.

        Args:
            source: Source column name.
            target: Target column name.

        Returns:
            Confidence in [0.0, 1.0], or 0.0 when no path exists.
        """
        if source == target:
            return 1.0
        if not self.is_reachable(source, target):
            return 0.0
        path = nx.shortest_path(self._graph, source, target)
        confidences = [
            float(self._graph.edges[path[i], path[i + 1]].get("confidence", 0.0))
            for i in range(len(path) - 1)
        ]
        return min(confidences, default=0.0)

    def minimal_root_columns(self, columns: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        """Return selected columns that are not downstream of another selection.

        Args:
            columns: Selected error columns.

        Returns:
            Minimal root columns in first-seen order.
        """
        unique: list[str] = []
        for column in columns:
            if column not in unique:
                unique.append(column)

        roots: list[str] = []
        for column in unique:
            has_upstream = any(
                other != column and self.is_reachable(other, column) for other in unique
            )
            if not has_upstream:
                roots.append(column)
        return tuple(roots)
