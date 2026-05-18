# Gladiator

A localhost HTML dashboard built with Flask.

## Stack

- **Python 3.9+**
- **Flask** — web framework
- **HTML / CSS / vanilla JS** — frontend (no build step)

## Project structure

```
gladiator/
├── app.py              # Flask app: routes, fetch orchestration
├── graph.py            # Node + Graph classes, layer computation, cycle check
├── fetchers.py         # Data source functions (yfinance, manual, ...)
├── nodes.json          # Graph definition — edit this to add/modify nodes
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html      # Dashboard page (renders nodes by layer)
├── static/
│   ├── css/style.css
│   └── js/main.js      # Polls /api/nodes every 60s
├── .gitignore
└── README.md
```

## How the graph works

Each node represents a quantity (a price, an indicator, etc.) and lives in `nodes.json`. A node has:

- `id` — unique within its layer
- `name` — display label
- `inputs` — list of `{node_id, node_layer, weight}` pointing to upstream nodes
- `data_source` — `{type, config}` matching a fetcher in `fetchers.py`
- `wishlist` — notes for future work on this node

**Layers are auto-computed** from graph structure (max parent layer + 1). A node with no inputs is layer 1. The graph is a DAG — cycles are rejected at load time.

To add a new node, edit `nodes.json` and (if needed) add a fetcher in `fetchers.py`. The server reloads the file on every request, so no restart needed.

## Setup (Windows)

### 1. Install Python

1. Go to <https://www.python.org/downloads/windows/> and download the latest stable Python 3 installer (64-bit).
2. **Run the installer.** On the very first screen, check the box **"Add python.exe to PATH"** before clicking Install. This is the single most important step — without it, the `python` command won't work in a new terminal.
3. Click **Install Now** and let it finish.
4. Open a **new** PowerShell or Command Prompt window (existing windows won't see the updated PATH) and verify:
   ```powershell
   python --version
   pip --version
   ```
   Both should print version numbers. If `python` opens the Microsoft Store instead, the PATH checkbox was missed — re-run the installer and choose **Modify**, then re-tick the box.

### 2. Install Git (skip if you already have it)

1. Download from <https://git-scm.com/download/win> and run the installer.
2. The default options are fine. Click Next through everything.
3. Open a new terminal and verify:
   ```powershell
   git --version
   ```

### 3. Clone the repo and run the app

Open PowerShell, then:

```powershell
# Clone the repo (run this once, in whatever folder you want the project to live)
git clone https://github.com/somerussianguy/gladiator.git
cd gladiator

# Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# If PowerShell blocks the activation script with an "execution policy" error,
# run this once (in the same window) and then re-run the Activate line:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# Install dependencies
pip install -r requirements.txt

# Run the dashboard
python app.py
```

Then open <http://localhost:5000> in your browser.

To stop the server: `Ctrl+C` in the terminal. To restart it later, `cd` back into the `gladiator` folder, run `.\venv\Scripts\Activate.ps1`, then `python app.py`.

## Development

The app runs in debug mode by default, so changes to Python files auto-reload. For template and static file changes, just refresh the browser.

## License

TBD
