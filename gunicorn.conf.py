"""Gunicorn settings (Render runs: gunicorn app:app -c gunicorn.conf.py).

preload_app: the app (tables, packs, one-time fixes) is set up once in the master process, so two workers
never import the same pack at the same time. Each worker then opens its own database connections.
"""
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60
preload_app = True


def post_fork(server, worker):
    from monday.extensions import db
    from app import app
    with app.app_context():
        db.engine.dispose(close=False)  # don't reuse the master's connections in the worker
