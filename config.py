import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")


def _secret_key():
    """Use MONDAY_SECRET_KEY if set, otherwise create one and keep it in instance/."""
    env = os.environ.get("MONDAY_SECRET_KEY")
    if env:
        return env
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    path = os.path.join(INSTANCE_DIR, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def _database_url():
    """DATABASE_URL (Render gives postgres://…, SQLAlchemy wants postgresql+psycopg://…), else local SQLite."""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return "sqlite:///" + os.path.join(INSTANCE_DIR, "monday.db")
    for old in ("postgres://", "postgresql://"):
        if url.startswith(old):
            return "postgresql+psycopg://" + url[len(old):]
    return url


class Config:
    SECRET_KEY = _secret_key()

    # SQLite for local development. For production set DATABASE_URL,
    # e.g. postgresql://user:pass@host:5432/monday (Supabase works too).
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Postgres on a small plan: a few pooled connections, checked before use (the server may drop idle ones)
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280} if not SQLALCHEMY_DATABASE_URI.startswith("sqlite") else {}

    # Uploaded photos and figures. On Render this points at the persistent disk (e.g. /var/data/uploads).
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER") or os.path.join(INSTANCE_DIR, "uploads")
    # Photos are shrunk on upload: longest side and JPEG quality (a phone photo goes from ~3 MB to ~200 KB).
    PHOTO_MAX_SIDE = 1600
    PHOTO_QUALITY = 78
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8 MB per upload
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # Languages. Russian is the source language; the others are ready
    # for translators (see translations/ and README).
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")  # sign in with Google (later)
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    # Desmos graphing calculator in SAT/CSCA tests (Monday's own key from desmos.com/my-api).
    DESMOS_API_KEY = os.environ.get("DESMOS_API_KEY", "9daae6e774bc4c34b328b6599b77571c")
    # Questions are translated for students: known sentence patterns instantly, anything new through
    # MyMemory (free, no key). An email here raises its free limit from ~5k to ~50k characters a day.
    TRANSLATE_ONLINE = os.environ.get("TRANSLATE_ONLINE", "1") == "1"
    TRANSLATE_EMAIL = os.environ.get("TRANSLATE_EMAIL", "")
    DESMOS_API_VERSION = os.environ.get("DESMOS_API_VERSION", "v1.12")

    LANGUAGES = {
        "ru": "Русский",
        "ky": "Кыргызча",
        "kk": "Қазақша",
        "uz": "O‘zbekcha",
        "tg": "Тоҷикӣ",
        "en": "English",
    }
    BABEL_DEFAULT_LOCALE = "ru"
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(BASE_DIR, "translations")

    # Demo convenience: lets students take the Monday test any day.
    # Set MONDAY_TEST_ALWAYS_OPEN=0 to enforce the Monday 19:00–24:00 window.
    MONDAY_TEST_ALWAYS_OPEN = os.environ.get("MONDAY_TEST_ALWAYS_OPEN", "1") == "1"
    # Rankings of the Monday test (leaderboard, school duel, places) are hidden for now; MONDAY_RANKINGS=1 shows them.
    MONDAY_RANKINGS = os.environ.get("MONDAY_RANKINGS", "0") == "1"

    # Content packs shipped in monday/data/packs/ (e.g. the Princeton Review SAT practice tests) are imported
    # into a database that doesn't have them yet. PUBLISH_PACKS=0 imports them as drafts for review instead.
    IMPORT_PACKS = os.environ.get("IMPORT_PACKS", "1") == "1"
    DATA_FIXES = os.environ.get("DATA_FIXES", "1") == "1"  # one-time fixes in monday/cleanup.py
    PUBLISH_PACKS = os.environ.get("PUBLISH_PACKS", "1") == "1"

    # Production: no demo accounts in an empty database; the first admin comes from these two variables.
    SEED_DEMO = os.environ.get("SEED_DEMO", "1") == "1"
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"  # 1 behind HTTPS (Render)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
