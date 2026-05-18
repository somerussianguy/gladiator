// Gladiator dashboard client.
// Polls /api/nodes every 60s and updates each node card in place,
// so we don't reload the whole page (and the user doesn't lose scroll).

const POLL_INTERVAL_MS = 60_000;

function formatPrice(v) {
    if (v === null || v === undefined) return "—";
    return "$" + Number(v).toFixed(2);
}

function updateNodeCard(node) {
    const card = document.querySelector(`[data-global-id="${node.global_id}"]`);
    if (!card) return;

    card.querySelector(".node-value").textContent = formatPrice(node.current_value);

    const meta = card.querySelector(".node-meta");
    if (node.last_status === "error") {
        card.classList.add("node-error");
        meta.innerHTML = `<span class="status status-error">error: ${node.last_error || "unknown"}</span>`;
    } else {
        card.classList.remove("node-error");
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
}

// Don't fire on page load — the server-rendered values are already fresh.
setInterval(refresh, POLL_INTERVAL_MS);
console.log(`Gladiator: polling /api/nodes every ${POLL_INTERVAL_MS/1000}s`);
