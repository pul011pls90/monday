"""Copy Monday's data into a new, empty Supabase database, and uploaded files into Supabase Storage.

    venv/bin/python tools/move_to_supabase.py --from "<current DATABASE_URL>" --to "<Supabase session pooler URL>"
    venv/bin/python tools/move_to_supabase.py --uploads instance/uploads      # files only (needs SUPABASE_URL/_SERVICE_KEY)

The first form copies every table row by row (in an order that respects the links between tables), then moves each
id counter past the copied rows and prints both row counts per table. It stops if the target already holds data, so
it can't mix two databases. The source is only read. Columns the source doesn't have yet are left empty or default.
Run it when nobody is using the site (e.g. late evening), then point DATABASE_URL on Render at Supabase.
"""
import argparse
import mimetypes
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlalchemy as sa  # noqa: E402

from config import _database_url, _engine_options  # noqa: E402
from monday.extensions import db  # noqa: E402
import monday.models  # noqa: E402,F401  (registers the tables)

BATCH = 1000


def engine(url):
    os.environ["DATABASE_URL"] = url
    url = _database_url()
    return sa.create_engine(url, **_engine_options(url))


def copy_database(src_url, dst_url):
    src, dst = engine(src_url), engine(dst_url)
    have = sa.inspect(src)
    db.metadata.create_all(dst)
    tables = db.metadata.sorted_tables
    with dst.connect() as conn:
        busy = [t.name for t in tables if conn.execute(sa.select(sa.func.count()).select_from(t)).scalar()]
    if busy:
        sys.exit(f"The target already has data ({', '.join(busy[:5])}…). Use an empty database.")
    with src.connect() as s, dst.begin() as d:
        if dst.dialect.name == "postgresql":   # no link checks while copying: rows may point at rows copied later
            try:
                with d.begin_nested():
                    d.execute(sa.text("SET LOCAL session_replication_role = replica"))
            except sa.exc.DBAPIError:
                print("(could not defer link checks; copying in id order)")
        for t in tables:
            if not have.has_table(t.name):
                print(f"{t.name:28} not in the source, left empty")
                continue
            cols = [c for c in t.columns if c.name in {x["name"] for x in have.get_columns(t.name)}]
            rows = s.execute(sa.select(*cols).order_by(*t.primary_key.columns)).mappings()
            n = 0
            while chunk := rows.fetchmany(BATCH):
                d.execute(t.insert(), [dict(r) for r in chunk])
                n += len(chunk)
            if dst.dialect.name == "postgresql" and "id" in t.c and isinstance(t.c.id.type, sa.Integer):
                d.execute(sa.text(f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', 'id'), "
                                  f"COALESCE((SELECT MAX(id) FROM \"{t.name}\"), 0) + 1, false)"))
            print(f"{t.name:28} {n} rows")
    with src.connect() as s, dst.connect() as d:
        wrong = [t.name for t in tables if have.has_table(t.name) and
                 s.execute(sa.select(sa.func.count()).select_from(t)).scalar() != d.execute(sa.select(sa.func.count()).select_from(t)).scalar()]
    print("All row counts match." if not wrong else f"Row counts differ: {wrong}")


def copy_uploads(folder):
    from flask import Flask
    from config import Config
    from monday import storage
    app = Flask(__name__)
    app.config.from_object(Config)
    with app.app_context():
        if not storage.using_supabase():
            sys.exit("Set SUPABASE_URL and SUPABASE_SERVICE_KEY first.")
        storage.ensure_bucket()
        n = 0
        for root, _dirs, files in os.walk(folder):
            for f in files:
                path = os.path.join(root, f)
                name = os.path.relpath(path, folder).replace(os.sep, "/")
                if name.startswith("packs/") or f.startswith("."):
                    continue  # pack figures are served from the repository
                with open(path, "rb") as fh:
                    storage.save(name, fh.read(), mimetypes.guess_type(f)[0] or "application/octet-stream")
                n += 1
        print(f"{n} files uploaded to bucket {app.config['SUPABASE_BUCKET']}.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from", dest="src")
    p.add_argument("--to", dest="dst")
    p.add_argument("--uploads", help="a local uploads folder to copy into Supabase Storage")
    a = p.parse_args()
    if a.src and a.dst:
        copy_database(a.src, a.dst)
    if a.uploads:
        copy_uploads(a.uploads)
    if not (a.src and a.dst) and not a.uploads:
        p.print_help()
