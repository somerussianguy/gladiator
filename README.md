# Gladiator

A localhost HTML dashboard built with Flask.

## Stack

- **Python 3.9+**
- **Flask** — web framework
- **HTML / CSS / vanilla JS** — frontend (no build step)

## Project structure

```
gladiator/
├── app.py              # Flask app entry point
├── requirements.txt    # Python dependencies
├── templates/          # Jinja2 HTML templates
│   └── index.html
├── static/             # CSS, JS, images
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── main.js
├── .gitignore
└── README.md
```

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # on Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the dashboard
python app.py
```

Then open <http://localhost:5000> in your browser.

## Development

The app runs in debug mode by default, so changes to Python files auto-reload. For template and static file changes, just refresh the browser.

## License

TBD
