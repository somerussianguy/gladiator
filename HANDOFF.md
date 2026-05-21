# Gladiator — Handoff Context

This file is the bridge between sessions. A new Claude instance reading this should be able to pick up where the previous one left off without re-asking the user questions that were already settled, and without losing the *reasoning* behind decisions that the code alone wouldn't reveal.

**For future-Claude:** Read this whole file before doing anything. The user is `somerussianguy` on GitHub, Windows machine, repo at <https://github.com/somerussianguy/gladiator>. The user is technical, asks pointed questions, and prefers honest pushback over agreeable execution. When you'd otherwise smooth over a contradiction or guess at intent, stop and ask.

---

## 1. What the project is

**Goal:** A localhost HTML dashboard that models the price of an asset (currently WTI crude oil) as a graph of influences and compositions. Each node represents a quantity or a qualitative driver; edges represent how upstream nodes contribute to downstream ones. The user calls this "paper oil price."

**Bigger context:** A previous session attempted this with a draw.io diagram and got tangled in node-relationship confusion. The current strategy is **build one node at a time, start at the root, expand outward.** Resist the temptation to scaffold a big tree up front.

**Stack:**
- Python 3 + Flask (chosen by Claude; user delegated the language choice "because you'll be doing all the coding")
- Vanilla HTML/CSS/JS frontend, no build step
- SVG overlay for edge rendering
- `yfinance` for free market data
- Repo on GitHub, user runs the server on their Windows machine

---

## 2. How collaboration works in this project

### The workflow
1. User has a Windows machine, Python installed, repo cloned at `~/gladiator` (or wherever).
2. Claude works in a fresh Linux container (ephemeral, resets per session).
3. Container has GitHub access via a fine-grained personal access token scoped to this one repo with read+write on contents.
4. Claude clones the repo, makes edits, commits, pushes. User runs `git pull` locally and tests.
5. Token gets revoked at end of session; user generates a fresh one next time.

### Network constraints in Claude's container
- GitHub access works.
- Yahoo Finance is **blocked** (`HTTP 403: Host not in allowlist`). This means *Claude cannot test the yfinance fetchers in the container* — they'll always fail here. They work on the user's machine. Don't be alarmed by yfinance errors during smoke tests; check graph loading and Flask import success instead.

### Commit/push pattern Claude has been using
1. Stage everything: `git add -A`
2. Commit with a detailed message.
3. `git remote set-url origin https://<user>:<token>@github.com/...` (briefly, just for the push)
4. `git push`
5. `git remote set-url origin https://github.com/...` (scrub token from config immediately)

The token was always temporarily inlined into the remote URL, then immediately removed. This keeps the token out of any persisted git config in the working copy.

### Tone and norms the user appreciates
- Push back when something doesn't make sense, with a clear alternative.
- Surface contradictions rather than silently picking one path.
- Flag when something is harder than it looks (e.g., "real-time order book data is paywalled").
- Don't ask questions whose answers are obvious from prior context.
- When the user's stated rule contradicts their stated example, **the example is the truth.** (Learned the hard way during the edge-style-by-consumer-vs-upstream confusion. See section 5.)
- Honest debriefs at the end of complex changes — what got built, what didn't, what was traded off.

### Tone and norms the user is allergic to
- Excessive caveats and apologies.
- Doing work without confirming when there's ambiguity in the spec.
- Pretending a deeper problem isn't there (e.g., the layer-direction inversion bug).
- Quietly switching decisions and hoping nobody notices.

---

## 3. The mental model: nodes, layers, types, edges

### Layer convention (this took some pain to settle — don't change without asking)

- **Layer 1 = root metric.** The central thing being modeled. Currently the oil price (`L1-N1`). One node.
- **Layer 2 = direct inputs into the root.**
- **Layer K+1 = direct inputs into layer K nodes.**
- **Every edge goes from layer K+1 → K.** Always one layer deeper to one layer shallower. Never sideways, never skipping, never the same layer.

This makes the graph a **DAG by construction** — no cycle detection needed. The validator just checks the K+1 rule.

**Historical note for future-Claude:** The original auto-compute approach (`layer = max(parent layers) + 1`) was wrong: it produced the inverse convention (root metric ends up at the *deepest* layer) and got tangled when ids were reused across layers. After multiple failed attempts to fix it, we **switched to user-declared layers in JSON, with validation**. Auto-computation is *not* in the current code. If a future you wants to bring it back, fine, but the validation-only approach has been clean and the user prefers it.

### Node `id` uniqueness
- **Unique within layer, not globally.** Every node so far is `id: 1` because each layer currently has one node. When layer 2 gets a second node, it'll be `id: 2` in layer 2; that doesn't conflict with `id: 2` existing elsewhere in some other layer.
- `global_id` = `L{layer}-N{id}` is the unique handle. Used in HTML `data-global-id`, in the API, in commit messages, and in conversation with the user.

### Three node types (all explicit, no nulls in practice)
- **`genesis`** — root metric. Light purple tint. Will never be an input to anything else. Right now only `L1-N1` (oil) is genesis.
- **`influence`** — a node that exerts indirect, qualitative pressure on its consumer. Light blue tint. Typically aggregators with prompts that ask an LLM to assess "how strong is this force right now?"
- **`composition`** — a node that is a *part of* its consumer. Light yellow tint. Composition relationships are structural — the consumer is literally built from these parts.

The semantic distinction is the user's model, not Claude's: the user is encoding a worldview about which drivers are direct (composition) vs. indirect (influence). Don't try to compute it; just respect the labels.

### Edge model

Each input ref in JSON: `{node_id, node_layer, weight, polarity}`.

- **`polarity`**: `"power"` or `"depower"`. Power = upstream pushes consumer in the same direction; depower = opposite direction.
- **`weight`**: relative magnitude, normalized within parent at compute time. Defaults to 1.0. Not yet used for any actual computation — placeholder for when aggregation logic lands.

### Visual conventions on the dashboard

These are the rules in effect, and they took multiple rounds to settle. **Don't change them without re-asking.**

| Attribute | Source | Values |
|---|---|---|
| Card tint | Node's own `node_type` | genesis = purple, influence = blue, composition = yellow |
| Edge color | Polarity (overridden by composition upstream) | power = green, depower = red, composition upstream → neutral gray regardless of polarity |
| Edge line style | **Upstream** node's `node_type` | influence upstream = dashed, composition upstream = solid |
| Arrow direction | Always into the consumer (downstream node) | Bottom of consumer card, exiting top of upstream card |

**Why upstream determines line style:** The line describes the upstream's *role in the relationship*. An influence node *influences* its consumer (loose, indirect → dashed). A composition node *composes* its consumer (tight, direct → solid). When the user said "consumer determines style" once during clarification, Claude took it literally and got it wrong; the user's *example* (current edge should be dashed) revealed the right rule. Lesson: trust the example over the verbal rule when they conflict.

---

## 4. The current graph (as of this handoff)

Six nodes in a linear chain, layer 1 → layer 6:

```
L1-N1  WTI Crude Oil                                       (genesis,    yfinance CL=F)
  ↑  dashed red (depower, influence upstream)
L2-N1  US government attempt to lower paper oil price      (influence,  no source, has prompt)
  ↑  solid gray (composition upstream)
L3-N1  Market Manipulation intended to rescue stock market (composition, no source, has prompt)
  ↑  solid gray
L4-N1  Treasury Shorting Paper Oil                         (composition, no source, has prompt)
  ↑  dashed red (depower, influence upstream)
L5-N1  Difficulty for treasury to sustain shorting op      (influence,  no source, has prompt)
  ↑  solid gray (composition upstream)
L6-N1  Expense of the operation                            (composition, yfinance_activity CL=F, has prompt)
```

**Open at handoff:**
- L5-N1's wishlist mentions a *second* composition sub-node — the user said this would come "next" but we hadn't started it when the handoff was requested. Whatever it is, it'll be L6-N2 (second node in layer 6).
- The "media manipulation" branch is foreshadowed in L6-N1's prompt but not yet a node.

**The narrative the graph currently encodes:**
The treasury can short paper oil to suppress price. The cost (L6-N1) creates a headwind (L5-N1) on the treasury's ability to do this (L4-N1), which is part of broader market manipulation (L3-N1), which is part of the government's broader effort to lower paper oil price (L2-N1), which depowers actual paper oil price (L1-N1).

---

## 5. Decisions made along the way, with reasoning

Numbered roughly in chronological order. Reading these will make future decisions faster.

### 5.1 Why Python/Flask
User left the choice to Claude. Flask was picked because (a) dashboards often grow into data wrangling and Python's ecosystem there is unmatched, (b) Flask is minimal — one file can serve real content, (c) the user's eventual needs (LLM calls, scheduled fetches, possibly a database) are all Python-native.

### 5.2 Why the user runs Flask, not Claude's container
Claude's container is ephemeral and network-restricted. `localhost:5000` from the user's browser refers to *their* machine, not the container. The container is for *code authorship* (write, commit, push); the user's machine is for *execution*. This is the right separation of concerns and worth keeping clear.

### 5.3 GitHub workflow with a fine-grained PAT
After explaining several workflow options (copy-paste, zip downloads, GitHub with token), the user picked the GitHub path. Token was scoped to one repo with `contents: read+write`. Worked cleanly. The pattern of "embed token in remote URL → push → strip" was Claude's approach — it works, but is unsatisfying. If a future session wants to use SSH keys or a credential helper, that's also fine.

### 5.4 Node schema decisions
- **Layer declared, not auto-computed** (see §3 historical note). Validation enforces consistency.
- **Polarity on edges, not nodes.** A node can power one consumer and depower another; the property belongs to the edge.
- **`prompt` is a top-level field on the node, not nested in `data_source`.** Reason: prompts are first-class content the user wants to read; data_source is internal plumbing. The eventual LLM execution will likely read `node.prompt` directly.
- **`data_source: null` is allowed.** Means "this node doesn't fetch its own value — it'll be computed from its children later (via LLM or aggregation)." Refresh skips it and marks status `no_source`.

### 5.5 The genesis node type
Added late, after influence and composition. Reason: the genesis (root) node felt awkward as a "typeless" special case, and the user wanted a distinct visual treatment. With three explicit types, every node has a type and the visual rules need no fallbacks.

### 5.6 Why the current edge from aggregator → oil is dashed red
- Dashed because the upstream (aggregator, L2-N1) is `influence`. Influence upstreams = dashed edges (loose association).
- Red because the polarity is `depower`. Higher gov effort → lower oil price.

### 5.7 Why composition edges are gray, not green/red
Composition is *structural*, not *directional*. "X is a part of Y" doesn't push Y up or down — it constitutes Y. So polarity-driven colors don't fit. Gray (not pure black, which gets lost on the dark theme) signals neutrality. The `polarity` field is still required on the input — it's just ignored visually when the upstream is composition.

### 5.8 The buying-pressure data discussion (most important market-research moment)
The user wanted "real time data about paper oil order volumes" for L6-N1.

Reality check Claude gave:
- True order flow / order-book depth / trade direction tagging = **institutional pricing only.** CME L2 data is not free.
- Free APIs (Yahoo, Alpha Vantage, EIA) give **OHLCV only.** From OHLCV you can derive proxies but not real order flow.
- The strongest free signals for "how much capital is chasing oil right now":
  1. **Total volume** (yfinance) — what we used.
  2. **Open interest** changes (CME/CFTC, daily) — strong signal of new money entering, but daily resolution and not in yfinance directly.
  3. **CFTC Commitments of Traders report** — weekly, free, shows hedge fund net positioning. Released Fridays for prior Tuesday.
  4. **Term-structure spread** (front-month vs next-month) — backwardation signals tight near-term demand.
  5. **DXY** (dollar index) — weak dollar = oil priced higher = more apparent buying pressure.

We picked the simplest workable option: `price × volume` today divided by 30-day rolling average → a single dimensionless **activity multiplier**. Not buying pressure literally; it's *trading intensity*. Honest about the limitation. Renders as `1.42×` on the card.

**If future-user wants more rigor here:**
- Add CME open interest as a second data source (would require a schema change: `data_source` becomes a list, or a node gets multiple fields, or we add a "supplementary signals" mechanism). The user's option 3 from that conversation was a multi-source schema; we deferred it.
- Or add separate nodes for OI, term-structure, and DXY as inputs to this node, and let aggregation compose them.

### 5.9 Node reuse / DAG limitation (NOT YET RESOLVED — important)
The current "every edge K+1 → K" rule means **a node can only feed one branch of the tree at one depth.** Real influence graphs need shared nodes — e.g., "oil spot price" affects costs in multiple places, and "DXY" affects everything in oil markets. Our model can't reuse a node.

Workarounds when this bites:
- (a) Duplicate the node at multiple layers (ugly, drift risk).
- (b) Relax the K+1 rule to "K+N for any N ≥ 1" (more flexible, but layer assignment becomes ambiguous when a node feeds multiple consumers at different depths).
- (c) Add a "shared facts" concept — nodes can reference other nodes without it being a graph edge (cleanest, biggest schema change).

The user hasn't asked for this yet but the issue is real. Flag it if it comes up.

---

## 6. The architecture in one diagram

```
nodes.json                     ←  source of truth for the graph
   │
   ▼
graph.py (Graph, Node, InputRef)
   │  - load + validate (layer rule, polarity, type, ids unique per layer)
   │  - no auto-compute; declared layers are authoritative
   │
   ▼
fetchers.py (registry)
   │  - @register("yfinance")        → fetch_yfinance(config)
   │  - @register("yfinance_activity") → activity multiplier
   │  - @register("manual")          → fixed value (placeholder)
   │
   ▼
app.py (Flask)
   │  - GET /          renders index.html with graph + fetched values
   │  - GET /api/nodes JSON of all nodes for client polling
   │  - load_graph()   re-reads nodes.json on every request (no restart needed)
   │  - refresh_node_values()  skips null sources (status: no_source)
   │
   ▼
templates/index.html
   │  - layers rendered top-down (L1 at top)
   │  - each card has data-global-id, data-node-type, data-inputs
   │  - SVG#edge-overlay anchored absolutely inside .container
   │  - <details class="node-prompt"> collapsed by default
   │
   ▼
static/js/main.js
   │  - polls /api/nodes every 60s
   │  - updates value + meta in place (preserves prompt expanded/collapsed)
   │  - drawEdges(): measures card rects, draws cubic Béziers
   │  - redraws on load, resize, prompt-toggle, and after each refresh
   │
   ▼
static/css/style.css
      - dark theme
      - three node tint variants
      - three edge color variants + two line styles
      - markers for each color variant
```

---

## 7. Things that are NOT yet built (and why each was deferred)

- **LLM execution of prompts.** Prompts are stored and displayed, not run. Wiring this up means: a new fetcher `"prompt"` that calls the Anthropic API with the node's prompt + context about children, parses a number out, returns it as `current_value`. Deferred because we don't yet have the deeper nodes the prompts are meant to scout, and API-key plumbing deserves its own focused step. The user said "wire up the LLM later."
- **Aggregation from children to parents.** Each parent currently has a `current_value` from its own data source (or null). Nothing combines children's values into a parent's value. The weight field is parked. This will likely come hand-in-hand with LLM execution — the LLM is the aggregator for influence nodes; composition nodes might use a different rule (sum? weighted average?).
- **Multi-data-source per node.** Discussed in §5.8. Would let one node read multiple market signals (price + OI + DXY) in one fetch. Deferred.
- **Node reuse / DAG with shared nodes.** §5.9. Will eventually be needed.
- **The "second composition sub-node" feeding L5-N1.** User said it was coming next when they asked for this handoff. Whatever it is, it'll be `L6-N2`.
- **The media-manipulation branch.** Referenced in L6-N1's prompt but no nodes yet.
- **Sparkline / history.** Each node has only `current_value`. No time series. Wishlist on L1-N1.
- **Lower-latency oil price.** Yahoo is 15-min delayed. Wishlist on L1-N1.

---

## 8. Files in the repo (current state)

```
gladiator/
├── HANDOFF.md          ← this file
├── README.md           ← user-facing; install + setup + visual conventions
├── app.py              ← Flask app, routes, refresh logic
├── graph.py            ← Node, InputRef, Graph; loading + validation
├── fetchers.py         ← registry of data-source functions
├── nodes.json          ← the graph itself
├── requirements.txt    ← Flask, yfinance
├── templates/
│   └── index.html      ← server-side render of cards by layer
├── static/
│   ├── css/style.css   ← dark theme, tints, edge styles, marker defs
│   └── js/main.js      ← polling + edge drawing + redraw triggers
└── .gitignore
```

---

## 9. Gotchas a future-Claude will hit and waste time on

1. **yfinance is blocked in the container.** Don't try to test it; it'll always 403. Test graph loading and Flask `import app` instead.
2. **`view` output shows line numbers as `    N\t` — those are display-only.** Don't include them in `str_replace`'s `old_str`. (Standard tool quirk.)
3. **str_replace can show "string not found" on a file you just edited.** It means the file is already in the desired state (your previous edit landed correctly, but your in-context view is stale). Re-view the file rather than retrying with variations of the string. Lost time to this multiple times this session.
4. **Don't `create_file` over an existing file.** It errors. Use `str_replace`, or `rm` first.
5. **The repo's `main.js` was accidentally deleted at one point and silently restored from `git checkout HEAD`.** If something looks missing, check `git status`. Be more careful with file state than I was.
6. **JSON in HTML data attributes gets entity-escaped** (`&#34;` for `"`). The browser decodes it on attribute access, so `JSON.parse(element.dataset.inputs)` works. But if you eyeball the HTML and think the JSON is malformed, it's not.
7. **The activity multiplier is sensitive to weekends and market holidays.** Yahoo's daily bars skip non-trading days. The `lookback_days` config is *trading days*, not calendar days. 30 trading days ≈ 6 weeks of wall-clock time.
8. **`current_value` is a single scalar.** Schema doesn't yet support multi-field nodes. Don't try to return a dict from a fetcher; it'll break the JSON encoder and the template.
9. **The 60-second poll interval is hardcoded in `main.js`.** Easy to forget when debugging "why isn't it updating."
10. **The genesis node currently has `wishlist` items but no `prompt`.** The user said "some nodes will just not have a prompt because they are very straightforward." Don't add a prompt to the genesis node uninvited.

---

## 10. Token / credentials handling (security note)

The user has been pasting fine-grained PATs scoped to this repo only, with short expiration. The token was visible in commands during this session; treat any token that has touched a conversation as **burned after use** — the user should revoke it via <https://github.com/settings/personal-access-tokens> at the end of the session and generate fresh next time.

If a future session starts and the user pastes a token: it should be scoped narrowly to `gladiator` with only `contents: read+write`, expiration ≤ 30 days. Use the temporary-inline-in-remote-URL pattern, scrub immediately after the push.

---

## 11. How to start a new session well

If you are a future-Claude:

1. **Read this file first.** Don't ask questions whose answers are here.
2. **Pull the repo.** If you have a token, clone or `git pull`. The graph state in `nodes.json` is the truth — if it disagrees with the descriptions here, the JSON wins.
3. **Don't ask the user to re-introduce the project.** You already know what it is.
4. **Confirm what the user wants in this session before coding.** New node? Wire up the LLM? Fix something? Just ask.
5. **Use the established commit/push pattern.** Detailed messages, scrub tokens, share the repo URL when you push.
6. **Surface contradictions.** When the user says X and previous decisions say Y, name the conflict.

---

*Last updated by the Claude instance that built nodes L1 through L6, including the activity multiplier fetcher.*
