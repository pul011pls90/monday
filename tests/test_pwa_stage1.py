"""Stage 1 PWA tests: Web App Manifest, icons, <head> meta tags across base templates, and CSP."""
from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse

from PIL import Image

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import StudentProfile, User
from test_app import client, login


def test_pwa_manifest_valid_json_content_type_and_icons():
    c = client()
    r = c.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers.get("Content-Type", "").startswith("application/manifest+json")

    data = json.loads(r.data.decode("utf-8"))
    assert data["name"] == "Monday"
    assert data["short_name"] == "Monday"
    assert data["start_url"] == "/"
    assert data["scope"] == "/"
    assert data["display"] == "standalone"
    assert data["background_color"] == "#FFFFFF"
    assert data["theme_color"] == "#F7F8FB"

    icons = data["icons"]
    assert len(icons) == 3
    purposes = {(ic["sizes"], ic["purpose"]): ic for ic in icons}
    assert ("192x192", "any") in purposes
    assert ("512x512", "any") in purposes
    assert ("512x512", "maskable") in purposes

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    img_dir = os.path.join(root, "monday", "static", "img")

    # Every icon in manifest loads 200 and matches declared dimensions on disk
    for (sizes, _purpose), ic in purposes.items():
        parsed = urlparse(ic["src"])
        r_ic = c.get(f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path)
        assert r_ic.status_code == 200
        assert r_ic.headers.get("Content-Type", "").startswith("image/png")

        fname = os.path.basename(parsed.path)
        with Image.open(os.path.join(img_dir, fname)) as im:
            w, h = im.size
            assert f"{w}x{h}" == sizes

    # Apple touch icon (180x180) and full favicon set exist on disk and serve 200
    expected_assets = {
        "apple-touch-icon.png": (180, 180),
        "favicon-32.png": (32, 32),
        "favicon.ico": None,
        "favicon.svg": None,
    }
    for fname, dims in expected_assets.items():
        fpath = os.path.join(img_dir, fname)
        assert os.path.isfile(fpath), f"Missing icon asset: {fname}"
        if dims is not None:
            with Image.open(fpath) as im:
                assert im.size == dims
        r_asset = c.get(f"/static/img/{fname}")
        assert r_asset.status_code == 200


def test_pwa_head_meta_tags_across_all_role_surfaces_and_csp():
    # Auth (login + register), student, teacher, manager/academic, admin all extend base.html
    c_anon = client()
    pages_to_check = [
        (c_anon, "/login"),
        (c_anon, "/register"),
    ]

    for role_email, role_pw, url in [
        ("student@monday.kg", "student123", "/home"),
        ("aibek@monday.kg", "teacher123", "/teacher/"),
        ("admin@monday.kg", "monday2026", "/manager"),
        ("admin@monday.kg", "monday2026", "/admin/"),
    ]:
        c_role = client()
        login(c_role, role_email, role_pw)
        pages_to_check.append((c_role, url))

    for c_obj, url in pages_to_check:
        resp = c_obj.get(url)
        assert resp.status_code == 200, f"{url} returned {resp.status_code}"
        html = resp.data.decode("utf-8")

        assert '<link rel="manifest" href="/manifest.webmanifest">' in html
        assert '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">' in html
        assert '<meta name="apple-mobile-web-app-capable" content="yes">' in html
        assert '<meta name="apple-mobile-web-app-title" content="Monday">' in html
        assert '<meta name="apple-mobile-web-app-status-bar-style" content="default">' in html
        assert re.search(r'<meta name="theme-color" content="#[0-9A-Fa-f]{6}" media="\(prefers-color-scheme: light\)">', html)
        assert re.search(r'<meta name="theme-color" content="#[0-9A-Fa-f]{6}" media="\(prefers-color-scheme: dark\)">', html)
        assert 'rel="apple-touch-icon" sizes="180x180"' in html
        assert "favicon.ico" in html and "favicon.svg" in html and "favicon-32.png" in html

        # Strict CSP preserved alongside manifest-src and worker-src
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "manifest-src 'self'" in csp
        assert "worker-src 'self' blob:" in csp
        assert "object-src 'none'" in csp
        assert "base-uri 'self'" in csp
        assert "frame-ancestors 'self'" in csp
        assert "https://www.desmos.com" in csp
        assert "https://cdn.jsdelivr.net" in csp
        assert "https://www.youtube.com" in csp
        assert "https://www.youtube-nocookie.com" in csp
        assert "https://accounts.google.com" in csp


def test_pwa_manifest_exempt_from_site_lock_and_forced_password_change(tmp_path):
    class LockCfg(Config):
        TESTING = True
        SECRET_KEY = "pwa-lock-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'pwa_lock.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        SEED_DEMO = False
        IMPORT_PACKS = False

    app = create_app(LockCfg, seed_if_empty=False)
    with app.app_context():
        db.create_all()
        adm = User(email="adm@pwa.kg", name="Adm", role="admin", is_approved=True)
        adm.set_password("StrongPass123!")
        stu = User(email="stu@pwa.kg", name="Stu", role="student", is_approved=True, must_change_password=True)
        stu.set_password("StrongPass123!")
        stu.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)
        db.session.add_all([adm, stu])
        db.session.commit()

    c_adm = app.test_client()
    c_adm.post("/login", data={"email": "adm@pwa.kg", "password": "StrongPass123!"})
    c_adm.post("/admin/maintenance", data={"action": "lock", "message": "Lock", "expected_minutes": "10"})

    # Even while locked, browsers can fetch manifest cleanly (200)
    r_locked = app.test_client().get("/manifest.webmanifest")
    assert r_locked.status_code == 200
    assert r_locked.get_json() or json.loads(r_locked.data.decode("utf-8"))["name"] == "Monday"

    # Unlock and verify student forced to change password still gets 200 on manifest
    c_adm.post("/admin/maintenance", data={"action": "unlock"})
    c_stu = app.test_client()
    c_stu.post("/login", data={"email": "stu@pwa.kg", "password": "StrongPass123!"})
    r_pw = c_stu.get("/manifest.webmanifest")
    assert r_pw.status_code == 200
