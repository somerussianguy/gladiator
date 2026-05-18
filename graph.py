"""Graph model for the dashboard.

A Graph is a DAG of Nodes. Each node has:
  - id    : unique within its layer
  - layer : declared in JSON; validated at load time
  - name, inputs, data_source, wishlist, node_type

Layer convention:
  Layer 1 = root node(s) — the central metric you care about.
  Layer 2 = direct inputs into a layer-1 node.
  Layer N+1 = direct inputs into a layer-N node.

Input refs identify their parent by (node_id, node_layer), which is unique
since ids are layer-scoped.

Validation at load time:
  - Each input's (node_id, node_layer) resolves to exactly one existing node.
  - For a node at layer K, every input must be at layer K+1.
  - No cycles (would imply a node references itself transitively).
  - At least one root exists (a node at layer 1 not referenced by anyone).
  - Input polarity, node type, ids-unique-per-layer all enforced.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class InputRef:
    """A reference from one node to another node that feeds into it.

    polarity: "power" = upstream value pushes in the same direction;
              "depower" = upstream value pushes in the opposite direction.
    weight:   relative magnitude; normalized within the parent at compute time.
    """
    node_id: int
    node_layer: int
    weight: float = 1.0
    polarity: str = "power"


ALLOWED_NODE_TYPES: set[str] = {"influence", "composition"}
ALLOWED_POLARITIES: set[str] = {"power", "depower"}


@dataclass
class Node:
    id: int
    name: str
    layer: int                                          # declared in JSON
    inputs: list[InputRef] = field(default_factory=list)
    data_source: dict[str, Any] | None = field(default_factory=dict)
    wishlist: list[str] = field(default_factory=list)
    node_type: str | None = None
    # Optional instruction for an LLM to compute this node's value by scouting
    # its child nodes. Not all nodes need one (raw price nodes typically don't).
    prompt: str | None = None

    # Runtime fields — populated by the fetcher, not persisted.
    current_value: float | None = None
    last_updated: str | None = None
    last_status: str = "never_fetched"   # ok | error | no_source | never_fetched
    last_error: str | None = None

    @property
    def global_id(self) -> str:
        return f"L{self.layer}-N{self.id}"


class GraphError(Exception):
    """Raised when the graph structure is invalid."""


class Graph:
    def __init__(self, nodes: list[Node]):
        self.nodes: list[Node] = nodes
        self._validate()

    # ---- loading ----------------------------------------------------------

    @classmethod
    def from_json_file(cls, path: str | Path) -> "Graph":
        data = json.loads(Path(path).read_text())
        nodes: list[Node] = []
        for n in data.get("nodes", []):
            if "layer" not in n:
                raise GraphError(
                    f"Node id={n.get('id')} ('{n.get('name')}') is missing "
                    f"required 'layer' field."
                )

            nt = n.get("node_type")
            if nt is not None and nt not in ALLOWED_NODE_TYPES:
                raise GraphError(
                    f"Node id={n.get('id')} ('{n.get('name')}') has invalid "
                    f"node_type={nt!r}. Allowed: {sorted(ALLOWED_NODE_TYPES)} or null."
                )

            inputs: list[InputRef] = []
            for ref in n.get("inputs", []):
                pol = ref.get("polarity", "power")
                if pol not in ALLOWED_POLARITIES:
                    raise GraphError(
                        f"Node id={n.get('id')} ('{n.get('name')}') has input with "
                        f"invalid polarity={pol!r}. Allowed: {sorted(ALLOWED_POLARITIES)}."
                    )
                inputs.append(InputRef(
                    node_id=ref["node_id"],
                    node_layer=ref["node_layer"],
                    weight=ref.get("weight", 1.0),
                    polarity=pol,
                ))

            nodes.append(Node(
                id=n["id"],
                name=n["name"],
                layer=n["layer"],
                inputs=inputs,
                data_source=n.get("data_source") or {},
                wishlist=list(n.get("wishlist", [])),
                node_type=nt,
                prompt=n.get("prompt"),
            ))
        return cls(nodes)

    # ---- lookup -----------------------------------------------------------

    def find(self, layer: int, node_id: int) -> Node | None:
        for n in self.nodes:
            if n.layer == layer and n.id == node_id:
                return n
        return None

    def nodes_by_layer(self) -> dict[int, list[Node]]:
        out: dict[int, list[Node]] = {}
        for n in self.nodes:
            out.setdefault(n.layer, []).append(n)
        return out

    # ---- validation -------------------------------------------------------

    def _validate(self) -> None:
        # 1. ids unique within each layer.
        by_key: dict[tuple[int, int], Node] = {}
        for n in self.nodes:
            key = (n.layer, n.id)
            if key in by_key:
                raise GraphError(
                    f"Duplicate node: layer={n.layer}, id={n.id} "
                    f"('{n.name}' and '{by_key[key].name}')"
                )
            by_key[key] = n

        # 2. Every input ref resolves to an existing node.
        # 3. For a node at layer K, every input must be at layer K+1.
        for child in self.nodes:
            for ref in child.inputs:
                key = (ref.node_layer, ref.node_id)
                if key not in by_key:
                    raise GraphError(
                        f"Node '{child.name}' (L{child.layer}-N{child.id}) "
                        f"references missing input L{ref.node_layer}-N{ref.node_id}."
                    )
                expected = child.layer + 1
                if ref.node_layer != expected:
                    raise GraphError(
                        f"Node '{child.name}' (L{child.layer}-N{child.id}) "
                        f"has an input at layer {ref.node_layer}, but inputs "
                        f"to a layer-{child.layer} node must be at layer "
                        f"{expected}."
                    )

        # 4. At least one root exists at layer 1.
        layer1 = [n for n in self.nodes if n.layer == 1]
        if not layer1:
            raise GraphError(
                "Graph has no layer-1 root node. There must be at least one "
                "node at layer 1."
            )

        # 5. No cycles. Since edges only go from layer K to layer K+1, the
        # graph is automatically a DAG — no cycle check needed. The
        # layer-mismatch check above already enforces this.