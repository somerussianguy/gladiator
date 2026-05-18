"""Gladiator — Flask app entry point.

Loads the influence graph from nodes.json, fetches current values for each node
on each request, and renders them grouped by layer.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template

from fetchers import fetch
from graph import Graph, GraphError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gladiator")

BASE_DIR = Path(__file__).parent
NODES_FILE = BASE_DIR / "nodes.json"

app = Flask(__name__)


def load_graph() -> Graph:
    """Load the graph fresh from disk every time — cheap, and lets you edit
    nodes.json without restarting the server."""
    try:
        return Graph.from_json_file(NODES_FILE)
    except GraphError as e:
        log.error("Invalid graph: %s", e)
        raise


def refresh_node_values(graph: Graph) -> None:
    """Fetch current values for every node. Errors are captured on the node,
    not raised, so one bad source doesn't blank the whole dashboard."""
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for node in graph.nodes:
        try:
            node.current_value = fetch(node.data_source)
            node.last_status = "ok"
            node.last_error = None
            node.last_updated = now_iso
        except Exception as e:  # noqa: BLE001
            log.warning("Fetch failed for %s (%s): %s", node.name, node.global_id, e)
            node.last_status = "error"
            node.last_error = str(e)
            node.last_updated = now_iso


@app.route("/")
def index():
    graph = load_graph()
    refresh_node_values(graph)
    layers = sorted(graph.nodes_by_layer().items())
    return render_template("index.html", layers=layers)


@app.route("/api/nodes")
def api_nodes():
    """JSON endpoint for the front-end to poll without a full page reload."""
    graph = load_graph()
    refresh_node_values(graph)
    return jsonify({
        "nodes": [
            {
                "global_id": n.global_id,
                "id": n.id,
                "layer": n.layer,
                "name": n.name,
                "current_value": n.current_value,
                "last_updated": n.last_updated,
                "last_status": n.last_status,
                "last_error": n.last_error,
                "wishlist": n.wishlist,
            }
            for n in graph.nodes
        ]
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
