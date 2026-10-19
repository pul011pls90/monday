"""Monday — entry point.

Run locally:
    source venv/bin/activate
    python3 app.py

The first run creates the database and fills it with demo data.
"""
import os

from monday import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("MONDAY_DEBUG", "1") == "1")
