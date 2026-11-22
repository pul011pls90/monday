"""Public sample question media & sanitized sample helpers (Stage 3)."""
from __future__ import annotations

import hashlib
import os
import re
import secrets

from flask import current_app

from . import storage
from .constants import DIFFICULTIES, EXAMS
from .content_i18n import localize
from .models import Question
from .packs import PACK_DIR, available as available_packs

_KEY_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|jpeg|webp)$")
_MIME_BY_EXT = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}
_ALLOWED_EXTS = frozenset(_MIME_BY_EXT.keys())
_FORBIDDEN_SOURCE_PREFIXES = ("solutions/", "support/", "avatar-", "sheet-")


def is_valid_public_sample_key(key: str | None) -> bool:
    return bool(key and _KEY_RE.fullmatch(key))


def mime_for_public_sample_key(key: str) -> str:
    m = _KEY_RE.fullmatch(key or "")
    if not m:
        return "application/octet-stream"
    return _MIME_BY_EXT[m.group(1)]


def _public_media_folder() -> str:
    return current_app.config.get("PUBLIC_SAMPLE_MEDIA_FOLDER") or os.path.join(
        os.path.dirname(current_app.config["UPLOAD_FOLDER"]),
        "public_sample_media",
    )


def _supabase_object_name(key: str) -> str:
    return f"public-samples/{key}"


def _read_source_stem_bytes(image_path: str) -> tuple[bytes, str] | None:
    """Read ONLY stem figure bytes (never solutions/support/avatars/sheets)."""
    raw = (image_path or "").strip()
    if not raw or raw.startswith("/") or "\\" in raw or ".." in raw.split("/"):
        return None
    if raw.startswith(_FORBIDDEN_SOURCE_PREFIXES):
        return None

    ext = raw.rsplit(".", 1)[-1].lower() if "." in raw else ""
    if ext not in _ALLOWED_EXTS:
        return None

    if raw.startswith("packs/"):
        parts = raw.split("/")
        if len(parts) != 3 or not parts[1] or not parts[2]:
            return None
        _, pack, fname = parts
        if pack not in available_packs():
            return None
        fig_path = os.path.join(PACK_DIR, pack, "figures", fname)
        if not os.path.isfile(fig_path):
            return None
        with open(fig_path, "rb") as f:
            return f.read(), ext

    data = storage.read_bytes(raw)
    if not data:
        return None
    return data, ext


def write_public_sample_bytes(key: str, data: bytes, mime: str) -> None:
    if not is_valid_public_sample_key(key):
        raise ValueError("Invalid public sample media key")
    if storage.using_supabase():
        storage.save(_supabase_object_name(key), data, mime)
        return
    folder = _public_media_folder()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, key)
    with open(path, "wb") as f:
        f.write(data)


def read_public_sample_bytes(key: str) -> bytes | None:
    if not is_valid_public_sample_key(key):
        return None
    if storage.using_supabase():
        return storage.read_bytes(_supabase_object_name(key))
    path = os.path.join(_public_media_folder(), key)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def public_media_copy_exists(key: str | None) -> bool:
    if not is_valid_public_sample_key(key):
        return False
    assert key is not None
    if storage.using_supabase():
        return storage.read_bytes(_supabase_object_name(key)) is not None
    path = os.path.join(_public_media_folder(), key)
    return os.path.isfile(path)


def delete_public_sample_bytes(key: str | None) -> None:
    if not is_valid_public_sample_key(key):
        return
    assert key is not None
    if storage.using_supabase():
        storage.delete(_supabase_object_name(key))
        return
    path = os.path.join(_public_media_folder(), key)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def list_local_public_sample_files() -> list[str]:
    """List filenames currently present in local PUBLIC_SAMPLE_MEDIA_FOLDER (preflight audit)."""
    folder = _public_media_folder()
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))


def sync_question_public_sample(question: Question) -> None:
    """Keep public sample stem media strictly synchronized with Question.is_public_sample."""
    old_key = question.public_image_key
    should_expose_media = (
        bool(question.is_public_sample)
        and question.status == "published"
        and bool((question.image_path or "").strip())
    )
    if not should_expose_media:
        if old_key:
            delete_public_sample_bytes(old_key)
        question.public_image_key = None
        return

    loaded = _read_source_stem_bytes(question.image_path)
    if not loaded:
        if old_key:
            delete_public_sample_bytes(old_key)
        question.public_image_key = None
        return

    data, ext = loaded
    digest = hashlib.sha256(secrets.token_bytes(32)).hexdigest()[:32]
    new_key = f"{digest}.{ext}"
    write_public_sample_bytes(new_key, data, _MIME_BY_EXT[ext])
    if old_key and old_key != new_key:
        delete_public_sample_bytes(old_key)
    question.public_image_key = new_key


def set_question_public_sample(question: Question, enabled: bool) -> Question:
    """Flag or unflag a question as a public sample and sync/delete its public media copy."""
    if enabled:
        if question.status != "published":
            raise ValueError("Only published questions can be marked as public samples.")
        if question.answer_type == "written":
            raise ValueError("Written-solution questions cannot be marked as public samples.")
        question.is_public_sample = True
    else:
        question.is_public_sample = False
    sync_question_public_sample(question)
    return question


def sanitize_public_sample(question: Question, exam_code: str) -> dict:
    """Return a strictly sanitized sample dict (never includes correct answer, explanation, or /uploads path)."""
    snap = localize(question.snapshot())
    skill_name = question.skill.name if question.skill else ""
    pub_key = question.public_image_key if is_valid_public_sample_key(question.public_image_key) else None
    return {
        "id": question.id,
        "exam": exam_code,
        "exam_label": str(EXAMS[exam_code]["label"]) if exam_code in EXAMS else exam_code,
        "difficulty": question.difficulty or 2,
        "difficulty_label": str(DIFFICULTIES.get(question.difficulty or 2, "")),
        "skill_name": skill_name,
        "material": list(snap.get("material") or []),
        "text": snap.get("text") or "",
        "answer_type": question.answer_type or "choice",
        "options": list(snap.get("options") or []) if (question.answer_type or "choice") == "choice" else [],
        "public_image_key": pub_key,
    }


def get_public_samples_by_exam(limit_per_exam: int | None = None) -> list[dict]:
    """Return advertised exams with their flagged & published public sample questions."""
    per_exam = int(
        limit_per_exam
        if limit_per_exam is not None
        else (current_app.config.get("PUBLIC_SAMPLE_PER_EXAM", 2) or 2)
    )
    rows = (
        Question.query.filter_by(status="published", is_public_sample=True)
        .order_by(Question.id.asc())
        .all()
    )
    groups: list[dict] = []
    for code, meta in EXAMS.items():
        matched = [
            q for q in rows
            if code in (q.exams or []) and q.answer_type != "written"
        ][: max(1, per_exam)]
        if matched:
            groups.append(
                {
                    "code": code,
                    "label": str(meta["label"]),
                    "note": str(meta.get("note", "")),
                    "samples": [sanitize_public_sample(q, code) for q in matched],
                }
            )
    return groups
