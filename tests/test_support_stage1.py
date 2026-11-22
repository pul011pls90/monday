"""Stage 1 tests: support image compression/sanitization pipeline, limits, sender_role snapshot, and auth serving."""
from __future__ import annotations

import io
import os
import random

import pytest
from PIL import Image, ImageDraw

from config import Config
from monday import create_app, storage
from monday.extensions import db
from monday.models import Report, StudentProfile, SupportAttachment, User
from monday.support_images import (
    MAX_IMAGES_PER_MESSAGE,
    MAX_IMAGES_PER_USER_PER_DAY,
    MAX_RAW_IMAGE_BYTES,
    TARGET_WEBP_BYTES,
    SupportImageError,
    process_support_image,
)
from test_app import APP, client, login


def _make_screenshot_png(width: int = 1800, height: int = 1200) -> bytes:
    """Build a realistic screenshot-like RGB PNG with shapes, gradients, and noise so lossless PNG > lossy WebP."""
    img = Image.new("RGB", (width, height), (244, 246, 251))
    draw = ImageDraw.Draw(img)
    rng = random.Random(42)
    for y in range(0, height, 6):
        c = 220 + (y * 25) // height
        draw.line([(0, y), (width, y)], fill=(c - 8, c - 4, min(255, c + 12)), width=4)
    for _ in range(120):
        x0 = rng.randint(20, width - 140)
        y0 = rng.randint(20, height - 100)
        col = (rng.randint(20, 220), rng.randint(40, 210), rng.randint(90, 245))
        draw.rectangle([x0, y0, x0 + rng.randint(40, 130), y0 + rng.randint(20, 90)], fill=col)
    # Add fine noise so lossless PNG doesn't collapse to a few bytes
    px = img.load()
    for _ in range(8000):
        px[rng.randint(0, width - 1), rng.randint(0, height - 1)] = (
            rng.randint(0, 255),
            rng.randint(0, 255),
            rng.randint(0, 255),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_image_bytes(fmt: str, width: int = 1900, height: int = 1000, *, with_gps_exif: bool = False) -> bytes:
    img = Image.new("RGB", (width, height), (36, 98, 220))
    draw = ImageDraw.Draw(img)
    pad = min(60, width // 6, height // 6)
    draw.rectangle([pad, pad, width - pad, height - pad], fill=(250, 250, 252), outline=(10, 26, 92), width=max(1, min(6, pad // 4)))
    buf = io.BytesIO()
    if fmt.upper() == "JPEG" and with_gps_exif:
        exif = Image.Exif()
        exif[0x0112] = 6  # Rotated 90 deg -> oriented output flips W/H
        exif[0x010F] = "Apple"
        exif[0x8825] = {1: "N", 2: (42.0, 52.0, 12.0), 3: "E", 4: (74.0, 35.0, 20.0)}
        img.save(buf, format="JPEG", quality=92, exif=exif.tobytes())
    else:
        img.save(buf, format=fmt.upper(), quality=90)
    return buf.getvalue()


def test_support_images_compress_jpeg_png_webp_strip_exif_and_make_thumb():
    # PNG screenshot compresses smaller than original and respects target + max edge + thumb 320px
    shot_png = _make_screenshot_png(1900, 1100)
    res_png = process_support_image(shot_png)
    assert res_png["mime"] == "image/webp"
    assert res_png["bytes_stored"] <= TARGET_WEBP_BYTES
    assert res_png["bytes_stored"] < res_png["bytes_original"]
    assert max(res_png["width"], res_png["height"]) == 1600
    assert res_png["data"] != shot_png

    with Image.open(io.BytesIO(res_png["thumb_data"])) as th:
        assert th.format == "WEBP"
        assert max(th.size) == 320

    # JPEG with EXIF orientation=6 + GPS metadata: oriented properly & ALL metadata stripped
    jpeg_gps = _make_image_bytes("JPEG", 800, 400, with_gps_exif=True)
    res_jpg = process_support_image(jpeg_gps)
    assert res_jpg["bytes_stored"] <= TARGET_WEBP_BYTES
    with Image.open(io.BytesIO(res_jpg["data"])) as out_im:
        assert out_im.format == "WEBP"
        assert out_im.size == (400, 800)  # EXIF orientation 6 applied
        assert len(out_im.getexif()) == 0
        assert len(out_im.getexif().get_ifd(0x8825)) == 0
        assert not out_im.info.get("exif")
    assert b"Apple" not in res_jpg["data"]

    # Valid WebP input re-encoded cleanly
    webp_raw = _make_image_bytes("WEBP", 1000, 700)
    res_webp = process_support_image(webp_raw)
    assert res_webp["mime"] == "image/webp"
    assert res_webp["bytes_stored"] <= TARGET_WEBP_BYTES
    assert res_webp["width"] == 1000 and res_webp["height"] == 700


def test_support_images_reject_fake_svg_gif_polyglot_and_bomb():
    # 1. Fake image (plain text renamed .png)
    with pytest.raises(SupportImageError):
        process_support_image(b"this is definitely not a png image")

    # 2. SVG payload
    with pytest.raises(SupportImageError):
        process_support_image(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>')

    # 3. GIF payload (even though Pillow normally knows GIF)
    gif_buf = io.BytesIO()
    Image.new("RGB", (32, 32), (255, 0, 0)).save(gif_buf, format="GIF")
    with pytest.raises(SupportImageError):
        process_support_image(gif_buf.getvalue())

    # 4. Polyglot (PNG with appended script/HTML payload)
    png_buf = io.BytesIO()
    Image.new("RGB", (32, 32), (0, 128, 0)).save(png_buf, format="PNG")
    polyglot = png_buf.getvalue() + b"<script>alert('xss')</script>"
    with pytest.raises(SupportImageError):
        process_support_image(polyglot)

    # 5. Oversized-pixel decompression bomb
    bomb_buf = io.BytesIO()
    Image.new("1", (6000, 5000), 1).save(bomb_buf, format="PNG")  # 30,000,000 px > 25 MP
    with pytest.raises(SupportImageError):
        process_support_image(bomb_buf.getvalue())

    # 6. Raw size > 10 MB
    with pytest.raises(SupportImageError):
        process_support_image(b"\x89PNG\r\n\x1a\n" + b"0" * (MAX_RAW_IMAGE_BYTES + 1))


def test_support_route_limits_authorization_and_server_role(tmp_path):
    class SupCfg(Config):
        TESTING = True
        SECRET_KEY = "sup-stage1-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'sup.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        SEED_DEMO = False
        IMPORT_PACKS = False

    app = create_app(SupCfg, seed_if_empty=False)
    with app.app_context():
        db.create_all()
        s1 = User(email="s1@sup.kg", name="Student One", role="student", is_approved=True)
        s1.set_password("Pass1234!")
        s1.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)

        s2 = User(email="s2@sup.kg", name="Student Two", role="student", is_approved=True)
        s2.set_password("Pass1234!")
        s2.profile = StudentProfile(exam="SAT", grade="11", onboarded=True)

        adm = User(email="adm@sup.kg", name="Admin Sup", role="admin", is_approved=True)
        adm.set_password("StrongAdmin123!")

        db.session.add_all([s1, s2, adm])
        db.session.commit()
        s1_id, s2_id = s1.id, s2.id

    c_anon = app.test_client()
    c_s1 = app.test_client()
    c_s2 = app.test_client()
    c_adm = app.test_client()
    c_s1.post("/login", data={"email": "s1@sup.kg", "password": "Pass1234!"})
    c_s2.post("/login", data={"email": "s2@sup.kg", "password": "Pass1234!"})
    c_adm.post("/login", data={"email": "adm@sup.kg", "password": "StrongAdmin123!"})

    # Image-only support message + forged sender_role field in POST ignored
    shot = _make_screenshot_png(1400, 900)
    r_ok = c_s1.post(
        "/support",
        data={
            "subject": "Техническая проблема",
            "message": "",
            "sender_role": "admin",
            "images": (io.BytesIO(shot), "../../evil<script>.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert r_ok.status_code == 302

    with app.app_context():
        rep = Report.query.filter_by(author_id=s1_id).one()
        assert rep.sender_role == "student"  # forged "admin" ignored
        assert len(rep.attachments) == 1
        att = rep.attachments[0]
        att_id = att.id
        assert att.mime == "image/webp"
        assert att.bytes_stored < att.bytes_original
        assert "evil" not in att.storage_key and "<" not in att.storage_key
        assert os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], att.full_object_name()))
        assert os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], att.thumb_object_name()))
        att_obj = att.full_object_name()

    # Unauthenticated -> 401
    assert c_anon.get(f"/support/attachments/{att_id}").status_code == 401

    # Another student -> 403
    assert c_s2.get(f"/support/attachments/{att_id}").status_code == 403

    # Direct /uploads/support/... -> 403 for any authenticated student
    assert c_s2.get(f"/uploads/{att_obj}").status_code == 403
    assert c_s1.get(f"/uploads/{att_obj}").status_code == 403

    # Sender & Admin -> 200 with image/webp, nosniff, Cache-Control: private
    for cli in (c_s1, c_adm):
        for suffix in ("", "?size=thumb"):
            resp = cli.get(f"/support/attachments/{att_id}{suffix}")
            assert resp.status_code == 200
            assert resp.headers.get("Content-Type") == "image/webp"
            assert resp.headers.get("X-Content-Type-Options") == "nosniff"
            assert "private" in (resp.headers.get("Cache-Control") or "")
            assert not resp.headers.get("Content-Disposition")

    # Enforce per-message limit (> 3 images -> 400)
    tiny_png = _make_image_bytes("PNG", 64, 64)
    r_4imgs = c_s1.post(
        "/support",
        data={
            "subject": "Техническая проблема",
            "message": "too many",
            "images": [(io.BytesIO(tiny_png), f"{i}.png") for i in range(MAX_IMAGES_PER_MESSAGE + 1)],
        },
        content_type="multipart/form-data",
    )
    assert r_4imgs.status_code == 400

    # Enforce > 5 MB total request body -> 413
    big_chunk = b"x" * (5 * 1024 * 1024 + 256)
    r_5mb = c_s1.post(
        "/support",
        data={"subject": "Техническая проблема", "message": "big", "images": (io.BytesIO(big_chunk), "big.png")},
        content_type="multipart/form-data",
    )
    assert r_5mb.status_code == 413

    # Enforce fake image rejection -> 400
    r_fake = c_s1.post(
        "/support",
        data={"subject": "Техническая проблема", "message": "fake", "images": (io.BytesIO(b"not an img"), "bad.png")},
        content_type="multipart/form-data",
    )
    assert r_fake.status_code == 400

    # Enforce daily limit (20 images per user per 24h)
    with app.app_context():
        s2_rep = Report(author_id=s2_id, sender_role="student", kind="other", message="seed")
        db.session.add(s2_rep)
        db.session.flush()
        for idx in range(MAX_IMAGES_PER_USER_PER_DAY):
            db.session.add(
                SupportAttachment(
                    message_id=s2_rep.id,
                    storage_key=f"seed-quota-{idx}",
                    mime="image/webp",
                    width=100,
                    height=100,
                    bytes_original=500,
                    bytes_stored=200,
                    sha256="0" * 64,
                )
            )
        db.session.commit()

    r_quota = c_s2.post(
        "/support",
        data={"subject": "Техническая проблема", "message": "over quota", "images": (io.BytesIO(tiny_png), "q.png")},
        content_type="multipart/form-data",
    )
    assert r_quota.status_code == 400
    assert "20" in r_quota.data.decode("utf-8")
