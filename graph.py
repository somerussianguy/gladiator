"""Graph model for the dashboard.

A Graph is a DAG of Nodes. Each node has:
  - an id unique within its layer (layers are auto-computed from graph structure)
  - a name, a list of weighted input references, a data source spec, a wishlist
  - runtime fields populated by the fetcher: current_value, last_updated, last_status

Layer assignment rule: a node's layer = max(parent layers) + 1.
A node with no inputs is layer 1 (a "leaf" in influence terms, or the root metric).
Cycles are rejected at load time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InputRef:
    """A reference from one node to another node that feeds into it, with a weight."""
    node_id: int          # id of the upstream node (unique within its layer)
    node_layer: int       # layer of the upstream node — needed because id is layer-scoped
    weight: float = 1.0   # relative weight; normalized within parent at compute time


ALLOWED_NODE_TYPES: set[str] = {"influence", "composition"}


@dataclass
class Node:
    """A single node in the influence graph."""
    id: int
    name: str
    inputs: list[InputRef] = field(default_factory=list)
    data_source: dict[str, Any] = field(default_factory=dict)
    wishlist: list[str] = field(default_factory=list)
    # Node role in the model. Blank/None is allowed for genesis nodes
    # where the distinction doesn't apply yet.
    node_type: str | None = None

    # Derived / runtime fields — not persisted to JSON
    layer: int = 0
    current_value: float | None = None
    last_updated: str | None = None       # ISO timestamp string
    last_status: str = "never_fetched"    # "ok" | "error" | "never_fetched"
    last_error: str | None = None

    @property
    def global_id(self) -> str:
        """Stable identifier across the whole graph, e.g. 'L1-N1'."""
        return f"L{self.layer}-N{self.id}"

    def normalized_input_weights(self) -> list[tuple[InputRef, float]]:
        """Return inputs paired with weights normalized to sum to 1.0."""
        total = sum(i.weight for i in self.inputs)
        if total <= 0:
            return [(i, 0.0) for i in self.inputs]
        return [(i, i.weight / total) for i in self.inputs]


class GraphError(Exception):
    """Raised when the graph structure is invalid (cycle, dangling reference, etc.)."""


class Graph:
    """The full DAG. Loaded from JSON; layers are computed on load."""

    def __init__(self, nodes: list[Node]):
        self.nodes: list[Node] = nodes
        self._compute_layers()

    # ---- loading & saving -------------------------------------------------

    @classmethod
    def from_json_file(cls, path: str | Path) -> "Graph":
        data = json.loads(Path(path).read_text())
        nodes: list[Node] = []
        for n in data.get("nodes", []):
            nt = n.get("node_type")
            if nt is not None and nt not in ALLOWED_NODE_TYPES:
                raise GraphError(
                    f"Node id={n.get('id')} ('{n.get('name')}') has invalid "
                    f"node_type={nt!r}. Allowed: {sorted(ALLOWED_NODE_TYPES)} or null."
                )
            nodes.append(Node(
                id=n["id"],
                name=n["name"],
                inputs=[InputRef(**ref) for ref in n.get("inputs", [])],
                data_source=n.get("data_source", {}),
                wishlist=list(n.get("wishlist", [])),
                node_type=nt,
            ))
        return cls(nodes)

    # ---- lookup -----------------------------------------------------------

    def find(self, layer: int, node_id: int) -> Node | None:
        for n in self.nodes:
            if n.layer == layer and n.id == node_id:
                return n
        return None

    def root_nodes(self) -> list[Node]:
        """Nodes with no inputs — the 'sources' of the DAG."""
        return [n for n in self.nodes if not n.inputs]

    def nodes_by_layer(self) -> dict[int, list[Node]]:
        out: dict[int, list[Node]] = {}
        for n in self.nodes:
            out.setdefault(n.layer, []).append(n)
        return out

    # ---- layer computation ------------------------------------------------

    def _compute_layers(self) -> None:
        """Assign each node a layer = max(input layers) + 1.

        Validates:
          - every input reference points to an existing node
          - the graph has no cycles
        """
        # Resolve inputs to actual Node objects via (id_only) lookup pre-layer.
        # Since layer is what we're computing, inputs reference nodes by (id, layer)
        # but at this point layer hasn't been set. We instead use id alone *plus*
        # the node_layer hint stored on the InputRef. The hint is treated as a
        # disambiguator only when needed — but ids must still be globally
        # unique enough to resolve here. To keep it simple, we require:
        # node ids are unique per layer AND each InputRef carries node_layer.
        # We resolve by matching (id == ref.node_id) and tracking via memoization.

        # Build an index by raw id for initial resolution; the node_layer field
        # on InputRef is checked once layers are assigned.
        by_id: dict[int, list[Node]] = {}
        for n in self.nodes:
            by_id.setdefault(n.id, []).append(n)

        # DFS to compute layer of each node, detecting cycles.
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[int, int] = {id(n): WHITE for n in self.nodes}

        def visit(node: Node) -> int:
            if color[id(node)] == GRAY:
                raise GraphError(f"Cycle detected involving node '{node.name}' (id={node.id})")
            if color[id(node)] == BLACK:
                return node.layer

            color[id(node)] = GRAY

            if not node.inputs:
                node.layer = 1
            else:
                parent_layers = []
                for ref in node.inputs:
                    parents = by_id.get(ref.node_id, [])
                    if not parents:
                        raise GraphError(
                            f"Node '{node.name}' references missing input id={ref.node_id}"
                        )
                    # Prefer a match where node_layer hint also matches (post-resolution),
                    # but since hint is forward-looking, we resolve by recursing into
                    # every candidate and pick the one whose computed layer matches the hint.
                    chosen: Node | None = None
                    for cand in parents:
                        cand_layer = visit(cand)
                        if cand_layer == ref.node_layer:
                            chosen = cand
                            break
                    if chosen is None:
                        # Hint didn't match; if there's only one candidate, take it.
                        if len(parents) == 1:
                            chosen = parents[0]
                        else:
                            raise GraphError(
                                f"Ambiguous input reference from '{node.name}': "
                                f"id={ref.node_id} matches multiple nodes and "
                                f"node_layer={ref.node_layer} matched none of them"
                            )
                    parent_layers.append(chosen.layer)
                node.layer = max(parent_layers) + 1

            color[id(node)] = BLACK
            return node.layer

        for n in self.nodes:
            if color[id(n)] == WHITE:
                visit(n)

        # Sanity check: ids unique within layer
        seen: dict[tuple[int, int], Node] = {}
        for n in self.nodes:
            key = (n.layer, n.id)
            if key in seen:
                other = seen[key]
                raise GraphError(
                    f"Duplicate node id={n.id} in layer={n.layer} "
                    f"('{n.name}' and '{other.name}')"
                )
            seen[key] = n
