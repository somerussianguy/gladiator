// Gladiator dashboard client.
// Polls /api/nodes every 60s and updates each node card in place,
// so we don't reload the whole page (and the user doesn't lose scroll).
// The prompt <details> element is never replaced — it stays open/closed
// as the user left it.

const POLL_INTERVAL_MS = 60_000;
const SVG_NS = "http://www.w3.org/2000/svg";

function formatValue(node) {
    const v = node.current_value;
    if (v === null || v === undefined) return "—";
    const isCurrency = node.data_source && node.data_source.type === "yfinance";
    return (isCurrency ? "$" : "") + Number(v).toFixed(2);
}

function updateNodeCard(node) {
    const card = document.querySelector(`[data-global-id="${node.global_id}"]`);
    if (!card) return;

    card.querySelector(".node-value").textContent = formatValue(node);

    const meta = card.querySelector(".node-meta");
    card.classList.remove("node-error");
    if (node.last_status === "error") {
        card.classList.add("node-error");
        meta.innerHTML = `<span class="status status-error">error: ${node.last_error || "unknown"}</span>`;
    } else if (node.last_status === "no_source") {
        meta.innerHTML = `<span class="status status-faint">no data source</span>`;
    } else {
        meta.innerHTML = `<span class="status status-ok">updated ${node.last_updated}</span>`;
    }
}

async function refresh() {
    try {
        const res = await fetch("/api/nodes", { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        data.nodes.forEach(updateNodeCard);
        document.getElementById("refresh-state").textContent = "on";
        document.getElementById("refresh-state").style.color = "var(--ok)";
    } catch (err) {
        console.error("Refresh failed:", err);
        document.getElementById("refresh-state").textContent = "error";
        document.getElementById("refresh-state").style.color = "var(--error)";
    }
    scheduleRedraw();
}

// ---------- edge rendering ----------------------------------------------
//
// Each card has data-inputs: a JSON list of {from, polarity, weight}
// describing edges that flow FROM an upstream card INTO this card.
// We draw a cubic Bezier with an arrowhead landing on the consumer card.
//
// Geometry: an input card (upstream) sits in a deeper layer (lower on
// screen since layers stack top-to-bottom). The arrow exits the top of
// the input card and lands on the bottom of the consumer card.

function ensureArrowMarkers(svg) {
    // Create one <defs> with two markers (power = green, depower = red).
    // The marker uses fill via context-stroke so it picks up the path color.
    if (svg.querySelector("defs")) return;
    const defs = document.createElementNS(SVG_NS, "defs");
    for (const polarity of ["power", "depower"]) {
        const marker = document.createElementNS(SVG_NS, "marker");
        marker.setAttribute("id", `arrow-${polarity}`);
        marker.setAttribute("viewBox", "0 0 10 10");
        marker.setAttribute("refX", "9");
        marker.setAttribute("refY", "5");
        marker.setAttribute("markerWidth", "7");
        marker.setAttribute("markerHeight", "7");
        marker.setAttribute("orient", "auto-start-reverse");
        const path = document.createElementNS(SVG_NS, "path");
        path.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
        path.setAttribute(
            "fill",
            polarity === "power" ? "var(--edge-power)" : "var(--edge-depower)"
        );
        marker.appendChild(path);
        defs.appendChild(marker);
    }
    svg.appendChild(defs);
}

function drawEdges() {
    const svg = document.getElementById("edge-overlay");
    if (!svg) return;

    const container = svg.parentElement;
    const containerRect = container.getBoundingClientRect();

    // Resize SVG to match its container's rendered size, so SVG user
    // coordinates match CSS pixels for the overlay.
    svg.setAttribute("width", containerRect.width);
    svg.setAttribute("height", containerRect.height);
    svg.setAttribute("viewBox", `0 0 ${containerRect.width} ${containerRect.height}`);

    // Clear previous edges (but keep <defs>).
    [...svg.querySelectorAll(".edge")].forEach(e => e.remove());
    ensureArrowMarkers(svg);

    const cards = document.querySelectorAll(".node[data-global-id]");
    const cardById = {};
    cards.forEach(c => cardById[c.dataset.globalId] = c);

    for (const consumer of cards) {
        let inputs;
        try {
            inputs = JSON.parse(consumer.dataset.inputs || "[]");
        } catch {
            continue;
        }
        if (!inputs.length) continue;

        const consumerRect = consumer.getBoundingClientRect();
        // Landing point: bottom-center of consumer card (in container coords).
        const endX = consumerRect.left + consumerRect.width / 2 - containerRect.left;
        const endY = consumerRect.bottom - containerRect.top;

        for (const inp of inputs) {
            const source = cardById[inp.from];
            if (!source) continue;
            const sourceRect = source.getBoundingClientRect();
            // Exit point: top-center of source (upstream, deeper) card.
            const startX = sourceRect.left + sourceRect.width / 2 - containerRect.left;
            const startY = sourceRect.top - containerRect.top;

            // Cubic Bezier with control points pulled vertically for a soft S.
            const dy = endY - startY;
            const c1x = startX;
            const c1y = startY + dy * 0.4;
            const c2x = endX;
            const c2y = endY - dy * 0.4;

            const path = document.createElementNS(SVG_NS, "path");
            path.setAttribute(
                "d",
                `M ${startX} ${startY} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${endX} ${endY}`
            );
            path.setAttribute(
                "class",
                `edge edge-${inp.polarity === "depower" ? "depower" : "power"}`
            );
            path.setAttribute(
                "marker-end",
                `url(#arrow-${inp.polarity === "depower" ? "depower" : "power"})`
            );
            svg.appendChild(path);
        }
    }
}

// Redraw edges after initial layout, on window resize, and after
// data refreshes (in case a card's class/size changed).
function scheduleRedraw() {
    // requestAnimationFrame ensures layout has settled.
    requestAnimationFrame(drawEdges);
}

window.addEventListener("load", () => {
    scheduleRedraw();
    // Card height changes when a prompt expands or collapses — redraw.
    document.querySelectorAll("details.node-prompt").forEach(d => {
        d.addEventListener("toggle", scheduleRedraw);
    });
});
window.addEventListener("resize", scheduleRedraw);

setInterval(refresh, POLL_INTERVAL_MS);
console.log(`Gladiator: polling /api/nodes every ${POLL_INTERVAL_MS/1000}s`);
