"""Where uploaded files live: the uploads folder (local runs, tests), or a private Supabase Storage bucket.

Supabase is used when SUPABASE_URL and SUPABASE_SERVICE_KEY are set. Files keep the same names as on disk
(e.g. "solutions/a12_3_ab12cd.jpg"), so the database doesn't change. The /uploads/<name> address stays the only
way to open a file: it checks the login and then sends the browser to a short-lived signed link.
Pack figures ("packs/<pack>/<file>") are not uploads: they are served straight from monday/data/packs.
The Storage REST API is called with urllib, so no new package is needed.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

SIGNED_SECONDS = 2 * 3600   # a signed link works this long; the /uploads redirect is cached for less (see __init__)
_signed = {}                # name -> (url, expires at): one signing request per file per hour, not per page view


def using_supabase():
    c = current_app.config
    return bool(c.get("SUPABASE_URL") and c.get("SUPABASE_SERVICE_KEY"))


def _api(path, data=None, headers=None, timeout=20):
    c = current_app.config
    req = urllib.request.Request(c["SUPABASE_URL"].rstrip("/") + "/storage/v1/" + path, data=data,
                                 method="POST" if data is not None else "GET")
    key = c["SUPABASE_SERVICE_KEY"]
    auth = {"apikey": key} if key.startswith("sb_") else {"apikey": key, "Authorization": "Bearer " + key}   # new secret keys go in apikey only
    for k, v in {**auth, "Content-Type": "application/json", **(headers or {})}.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _object(name):
    return f"{current_app.config['SUPABASE_BUCKET']}/{urllib.parse.quote(name)}"


def save(name, data, content_type="application/octet-stream"):
    """Store bytes under name (overwrites a file of the same name)."""
    if using_supabase():
        _api("object/" + _object(name), data, {"Content-Type": content_type, "x-upsert": "true",
                                               "Cache-Control": "max-age=86400"}, timeout=30)
        _signed.pop(name, None)
        return name
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return name


def signed_url(name):
    """A link to the file that works for SIGNED_SECONDS, or None when the bucket doesn't have it."""
    hit = _signed.get(name)
    if hit and hit[1] > time.time() + 60:
        return hit[0]
    try:
        body = _api("object/sign/" + _object(name), json.dumps({"expiresIn": SIGNED_SECONDS}).encode())
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):   # Supabase answers 400 "Object not found" for a missing file
            return None
        raise
    reply = json.loads(body)
    link = reply.get("signedURL") or reply.get("signedUrl")
    if not link:
        return None
    url = current_app.config["SUPABASE_URL"].rstrip("/") + "/storage/v1" + link
    if len(_signed) > 5000:
        _signed.clear()
    _signed[name] = (url, time.time() + SIGNED_SECONDS)
    return url


def ensure_bucket():
    """Create the private bucket if it's missing (once at start-up; harmless when it exists)."""
    if not using_supabase():
        return
    bucket = current_app.config["SUPABASE_BUCKET"]
    try:
        _api("bucket", json.dumps({"id": bucket, "name": bucket, "public": False}).encode())
    except urllib.error.HTTPError as e:
        if e.code not in (400, 409):   # already there
            current_app.logger.warning("Supabase bucket %s: HTTP %s", bucket, e.code)
    except (OSError, ValueError) as e:   # unreachable, or a malformed key: the site still starts (the key is not logged)
        current_app.logger.warning("Supabase Storage not usable: %s", type(e).__name__)
