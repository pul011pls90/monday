"""Support image validation, sanitization, EXIF stripping, WebP compression, and quota enforcement."""
from __future__ import annotations

import hashlib
import io
import uuid
import warnings
from datetime import timedelta

from flask import current_app
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func

from . import storage
from .audit import write_audit_log
from .extensions import db
from .models import Report, SupportAttachment, utcnow

ALLOWED_PIL_FORMATS = ("JPEG", "PNG", "WEBP")
MAX_RAW_IMAGE_BYTES = 10 * 1024 * 1024       # 10 MB raw upload ceiling per image
MAX_SUPPORT_REQUEST_BYTES = 5 * 1024 * 1024  # 5 MB total request body for support submissions
MAX_IMAGES_PER_MESSAGE = 3
MAX_IMAGES_PER_USER_PER_DAY = 20
MAX_IMAGE_PIXELS = 25_000_000                # Decompression bomb guard (~25 MP)
MAX_IMAGE_DIMENSION = 12_000
LONG_EDGE_MAX = 1600
THUMB_LONG_EDGE = 320
TARGET_WEBP_BYTES = 250 * 1024               # ~250 KB target per stored image
QUALITY_STEPS = (80, 74, 68, 62, 55)
RESIZE_STEP_FACTOR = 0.85

_BAD_HEAD_MARKERS = (
    b"<svg",
    b"<?xml",
    b"<!doctype",
    b"<html",
    b"<script",
    b"<iframe",
    b"gif87a",
    b"gif89a",
)
_POLYGLOT_MARKERS = (b"<script", b"<!doctype html", b"<html", b"<?php", b"<svg")


class SupportImageError(ValueError):
    """Raised when an uploaded image fails format, size, bomb, or quota validation."""


def _encode_webp(pil_img: Image.Image, quality: int) -> bytes:
    """Encode a clean Pillow image to WebP without any metadata chunks."""
    buf = io.BytesIO()
    pil_img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()


def _check_magic_and_polyglot(raw_bytes: bytes) -> None:
    if not raw_bytes:
        raise SupportImageError("Файл изображения пуст.")
    if len(raw_bytes) > MAX_RAW_IMAGE_BYTES:
        raise SupportImageError("Файл слишком большой (максимум 10 МБ).")

    head = raw_bytes[:128].lstrip().lower()
    if any(head.startswith(m) for m in _BAD_HEAD_MARKERS):
        raise SupportImageError("Поддерживаются только изображения JPEG, PNG и WebP (SVG и GIF не поддерживаются).")

    # Reject ISO BMFF / HEIC containers explicitly even before decoding
    if len(raw_bytes) >= 12 and raw_bytes[4:8] == b"ftyp":
        raise SupportImageError("Формат HEIC/HEIF не поддерживается. Сохраните изображение в JPEG, PNG или WebP.")

    lowered = raw_bytes.lower()
    if any(marker in lowered for marker in _POLYGLOT_MARKERS):
        raise SupportImageError("Файл содержит недопустимое содержимое или повреждён.")

    # Guard against PNG polyglots carrying trailing data after IEND
    if raw_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        iend_pos = raw_bytes.rfind(b"IEND")
        if iend_pos == -1 or (len(raw_bytes) - (iend_pos + 8)) > 16:
            raise SupportImageError("Файл PNG повреждён или содержит посторонние данные.")


def process_support_image(raw_bytes: bytes) -> dict:
    """Decode, verify, orient, strip ALL metadata, resize, and re-encode an image to <= ~250 KB WebP + 320px thumb.

    Original bytes are NEVER stored. Only valid JPEG, PNG, and WebP decoded cleanly by Pillow are accepted.
    """
    _check_magic_and_polyglot(raw_bytes)

    prev_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            # Pass 1: header & structural verification with strict decoder allowlist
            with Image.open(io.BytesIO(raw_bytes), formats=ALLOWED_PIL_FORMATS) as probe:
                fmt = (probe.format or "").upper()
                if fmt not in ALLOWED_PIL_FORMATS:
                    raise SupportImageError("Поддерживаются только изображения JPEG, PNG и WebP.")
                w0, h0 = probe.size
                if w0 <= 0 or h0 <= 0 or w0 * h0 > MAX_IMAGE_PIXELS or max(w0, h0) > MAX_IMAGE_DIMENSION:
                    raise SupportImageError("Разрешение изображения слишком большое (максимум 25 МП).")
                probe.verify()

            # Pass 2: full pixel decode + EXIF orientation + metadata-free pixel buffer copy
            with Image.open(io.BytesIO(raw_bytes), formats=ALLOWED_PIL_FORMATS) as opened:
                opened.load()
                oriented = ImageOps.exif_transpose(opened)
                if getattr(oriented, "is_animated", False):
                    oriented.seek(0)
                has_alpha = (
                    oriented.mode in ("RGBA", "LA")
                    or (oriented.mode == "P" and "transparency" in oriented.info)
                )
                converted = oriented.convert("RGBA" if has_alpha else "RGB")
                # Creating from raw pixel bytes removes EXIF, GPS, XMP, IPTC, and ICC profiles completely.
                clean = Image.frombytes(converted.mode, converted.size, converted.tobytes())
    except SupportImageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, MemoryError) as exc:
        raise SupportImageError("Изображение слишком большого разрешения или повреждено.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, EOFError) as exc:
        raise SupportImageError("Не удалось распознать изображение. Допустимы только JPEG, PNG и WebP.") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = prev_max_pixels

    if max(clean.size) > LONG_EDGE_MAX:
        clean.thumbnail((LONG_EDGE_MAX, LONG_EDGE_MAX), Image.Resampling.LANCZOS)

    cur = clean
    best_bytes = b""
    best_size = cur.size

    while True:
        for q in QUALITY_STEPS:
            encoded = _encode_webp(cur, q)
            best_bytes = encoded
            best_size = cur.size
            if len(encoded) <= TARGET_WEBP_BYTES:
                break
        if len(best_bytes) <= TARGET_WEBP_BYTES:
            break
        cur_w, cur_h = cur.size
        if max(cur_w, cur_h) <= THUMB_LONG_EDGE:
            break
        next_w = max(1, int(round(cur_w * RESIZE_STEP_FACTOR)))
        next_h = max(1, int(round(cur_h * RESIZE_STEP_FACTOR)))
        if next_w == cur_w and next_h == cur_h:
            break
        cur = clean.resize((next_w, next_h), Image.Resampling.LANCZOS)

    thumb = clean.copy()
    if max(thumb.size) > THUMB_LONG_EDGE:
        thumb.thumbnail((THUMB_LONG_EDGE, THUMB_LONG_EDGE), Image.Resampling.LANCZOS)
    thumb_bytes = _encode_webp(thumb, 75)

    return {
        "data": best_bytes,
        "thumb_data": thumb_bytes,
        "mime": "image/webp",
        "width": best_size[0],
        "height": best_size[1],
        "bytes_original": len(raw_bytes),
        "bytes_stored": len(best_bytes),
        "sha256": hashlib.sha256(best_bytes).hexdigest(),
    }


def user_daily_attachment_count(user_id: int) -> int:
    """Count attachments uploaded by `user_id` within the trailing 24 hours."""
    since = utcnow() - timedelta(hours=24)
    return (
        db.session.query(SupportAttachment.id)
        .join(Report, Report.id == SupportAttachment.message_id)
        .filter(Report.author_id == user_id, SupportAttachment.created_at >= since)
        .count()
    )


def prepare_and_store_attachments(report: Report, uploaded_files: list, user_id: int) -> list[SupportAttachment]:
    """Validate quotas, sanitize/compress every image before writing any files, then store WebP + thumbs."""
    non_empty = [f for f in uploaded_files if f and ((getattr(f, "filename", "") or "").strip() or _peek_non_empty(f))]
    if not non_empty:
        return []
    if len(non_empty) > MAX_IMAGES_PER_MESSAGE:
        raise SupportImageError(f"Можно прикрепить не более {MAX_IMAGES_PER_MESSAGE} изображений к одному сообщению.")

    used_today = user_daily_attachment_count(user_id)
    if used_today + len(non_empty) > MAX_IMAGES_PER_USER_PER_DAY:
        raise SupportImageError(f"Превышен дневной лимит: не более {MAX_IMAGES_PER_USER_PER_DAY} изображений в сутки.")

    raw_items = []
    total_raw = 0
    for f in non_empty:
        f.stream.seek(0)
        raw = f.stream.read(MAX_RAW_IMAGE_BYTES + 1)
        total_raw += len(raw)
        if len(raw) > MAX_RAW_IMAGE_BYTES:
            raise SupportImageError("Файл слишком большой (максимум 10 МБ).")
        if total_raw > MAX_SUPPORT_REQUEST_BYTES:
            raise SupportImageError("Общий размер вложений превышает 5 МБ.")
        raw_items.append(raw)

    # Process all images before saving anything to storage or database
    processed = [process_support_image(raw) for raw in raw_items]

    rows = []
    saved_objects = []
    try:
        for item in processed:
            key = uuid.uuid4().hex
            att = SupportAttachment(
                message=report,
                storage_key=key,
                mime="image/webp",
                width=item["width"],
                height=item["height"],
                bytes_original=item["bytes_original"],
                bytes_stored=item["bytes_stored"],
                sha256=item["sha256"],
            )
            full_name = att.full_object_name()
            thumb_name = att.thumb_object_name()
            storage.save(full_name, item["data"], "image/webp")
            saved_objects.append(full_name)
            storage.save(thumb_name, item["thumb_data"], "image/webp")
            saved_objects.append(thumb_name)
            db.session.add(att)
            rows.append(att)
    except Exception:
        for name in saved_objects:
            storage.delete(name)
        raise

    return rows


def _peek_non_empty(file_storage) -> bool:
    try:
        pos = file_storage.stream.tell()
        chunk = file_storage.stream.read(1)
        file_storage.stream.seek(pos)
        return bool(chunk)
    except Exception:
        return False


def purge_closed_support_images(days: int = 90, *, dry_run: bool = False) -> dict:
    """Delete attachment files and DB rows for support threads closed more than `days` ago.

    Idempotent: re-running after cleanup finds 0 matching attachments. Logs counts only, never content.
    """
    age_days = max(0, int(days))
    cutoff = utcnow() - timedelta(days=age_days)
    closed_at = func.coalesce(Report.handled_at, Report.created_at)
    rows = (
        SupportAttachment.query.join(Report, Report.id == SupportAttachment.message_id)
        .filter(Report.status != "open", closed_at < cutoff)
        .all()
    )
    count = len(rows)
    total_bytes = sum(int(r.bytes_stored or 0) for r in rows)

    if not dry_run and rows:
        for att in rows:
            storage.delete(att.full_object_name())
            storage.delete(att.thumb_object_name())
            db.session.delete(att)
        db.session.commit()

    current_app.logger.info(
        "support_purge_images dry_run=%s days=%s attachments=%s bytes=%s",
        bool(dry_run),
        age_days,
        count,
        total_bytes,
    )
    return {"attachments": count, "bytes_freed": total_bytes, "dry_run": bool(dry_run), "days": age_days}


def delete_user_support_attachments(user_id: int) -> int:
    """Delete all stored files and DB rows for support attachments authored by `user_id`."""
    rows = (
        SupportAttachment.query.join(Report, Report.id == SupportAttachment.message_id)
        .filter(Report.author_id == user_id)
        .all()
    )
    for att in rows:
        storage.delete(att.full_object_name())
        storage.delete(att.thumb_object_name())
        db.session.delete(att)
    return len(rows)


def soft_delete_support_attachment(att: SupportAttachment, *, actor_id: int) -> bool:
    """Admin-initiated removal of one support attachment: deletes object bytes, marks deleted_at, writes AuditLog."""
    if att.deleted_at is not None:
        return False
    storage.delete(att.full_object_name())
    storage.delete(att.thumb_object_name())
    att.deleted_at = utcnow()
    write_audit_log(
        actor_id=actor_id,
        action="support.attachment.delete",
        entity_type="support_attachment",
        entity_id=att.id,
        old_value={"message_id": att.message_id, "bytes_stored": int(att.bytes_stored or 0)},
        new_value={"deleted_at": att.deleted_at.isoformat()},
        reason="admin_delete",
    )
    return True


def support_storage_stats() -> dict:
    """Aggregate storage metrics for active support attachments shown on admin overview."""
    row = (
        db.session.query(
            func.count(SupportAttachment.id),
            func.coalesce(func.sum(SupportAttachment.bytes_stored), 0),
            func.min(SupportAttachment.created_at),
        )
        .filter(SupportAttachment.deleted_at.is_(None))
        .first()
    )
    total_count = int(row[0] or 0) if row else 0
    total_bytes = int(row[1] or 0) if row else 0
    oldest_at = row[2] if row else None
    deleted_count = SupportAttachment.query.filter(SupportAttachment.deleted_at.isnot(None)).count()
    return {
        "total_count": total_count,
        "deleted_count": deleted_count,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "avg_kb": round((total_bytes / total_count) / 1024, 1) if total_count else 0.0,
        "oldest_at": oldest_at,
    }
