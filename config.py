import os
import secrets
from datetime import timedelta

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
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def _database_url():
    """DATABASE_URL (Render gives postgres://…, SQLAlchemy wants postgresql+psycopg://…), else local SQLite."""
    url = "".join(os.environ.get("DATABASE_URL", "").split())   # a pasted line break would break the address
    if not url:
        return "sqlite:///" + os.path.join(INSTANCE_DIR, "monday.db")
    for old in ("postgres://", "postgresql://"):
        if url.startswith(old):
            return "postgresql+psycopg://" + url[len(old):]
    return url


def _engine_options(url):
    """Postgres on a small plan: a few pooled connections, checked before use (the server may drop idle ones).
    Supabase's pooler (Supavisor, *.pooler.supabase.com) needs SSL, and in transaction mode (port 6543) it can't
    keep prepared statements, so psycopg is told not to make them; harmless in session mode (port 5432)."""
    if url.startswith("sqlite"):
        return {}
    opts = {"pool_pre_ping": True, "pool_recycle": 280}
    if "supabase.co" in url or "supabase.com" in url:
        opts.update(pool_size=3, max_overflow=4, connect_args={"prepare_threshold": None,
                                                               **({} if "sslmode=" in url else {"sslmode": "require"})})
    return opts


class Config:
    SECRET_KEY = _secret_key()

    # SQLite for local development. For production set DATABASE_URL,
    # e.g. postgresql://user:pass@host:5432/monday, or Supabase's pooler string (Connect → Session pooler).
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Postgres on a small plan: a few pooled connections, checked before use (the server may drop idle ones)
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)

    # Supabase Storage for uploads (photos, figures, avatars). Without these two the uploads folder below is used.
    # The service key stays on the server only; the bucket is private and created at start-up if missing.
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()      # https://<project>.supabase.co
    # the legacy service_role key (eyJ…) or a new secret key (sb_secret_…); spaces and line breaks from pasting are dropped
    SUPABASE_SERVICE_KEY = "".join(os.environ.get("SUPABASE_SERVICE_KEY", "").split())
    SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "uploads")

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
    # Desmos graphing calculator in SAT/CSCA tests (set via DESMOS_API_KEY env var; never hardcode keys).
    DESMOS_API_KEY = os.environ.get("DESMOS_API_KEY", "").strip()
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
    # Rankings of the Monday test (leaderboard, last test, school duel, places) are hidden for now; MONDAY_RANKINGS=1 shows them.
    MONDAY_RANKINGS = os.environ.get("MONDAY_RANKINGS", "0") == "1"

    # Content packs shipped in monday/data/packs/ (e.g. the Princeton Review SAT practice tests) are imported
    # into a database that doesn't have them yet. PUBLISH_PACKS=0 imports them as drafts for review instead.
    IMPORT_PACKS = os.environ.get("IMPORT_PACKS", "1") == "1"
    DATA_FIXES = os.environ.get("DATA_FIXES", "1") == "1"  # one-time fixes in monday/cleanup.py
    PUBLISH_PACKS = os.environ.get("PUBLISH_PACKS", "1") == "1"
    SHOW_JOURNAL = False

    # Production: no demo accounts in an empty database; the first admin comes from these two variables.
    SEED_DEMO = os.environ.get("SEED_DEMO", "1") == "1"
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
    ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN", "")
    RESUME_MAX_DAYS = int(os.environ.get("RESUME_MAX_DAYS", "30") or "30")
    INVITE_CODE_TTL_DAYS = int(os.environ.get("INVITE_CODE_TTL_DAYS", "14") or "14")
    NEW_TEACHER_SEES_EARLIER_PROGRESS = False
    APP_VERSION = (
        os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("APP_VERSION")
        or ""
    ).strip()[:12] or secrets.token_hex(6)
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"  # 1 behind HTTPS (Render)
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_DURATION = timedelta(days=14)
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    ANALYTICS_IP_SALT = os.environ.get("ANALYTICS_IP_SALT", "").strip()
    TRUST_PROXY_GEO_HEADERS = os.environ.get("TRUST_PROXY_GEO_HEADERS", "1") == "1"
    CRM_SLA_MINUTES = int(os.environ.get("CRM_SLA_MINUTES", "15") or "15")
    CRM_WEBHOOK_SECRET = os.environ.get("CRM_WEBHOOK_SECRET", "").strip()
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
    GEMINI_CRM_MODEL = os.environ.get("GEMINI_CRM_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"

    # Public website & question-bank product flags (Stage 2+)
    IS_PRODUCTION = False
    PUBLIC_SITE_ENABLED = os.environ.get("PUBLIC_SITE_ENABLED", "1") == "1"
    PUBLIC_PREFLIGHT_STRICT = os.environ.get("PUBLIC_PREFLIGHT_STRICT", "0") == "1"
    PUBLIC_LEGAL_REVIEWED = os.environ.get("PUBLIC_LEGAL_REVIEWED", "0") == "1"
    LEGAL_ENTITY_NAME = os.environ.get("LEGAL_ENTITY_NAME", "").strip()
    LEGAL_ENTITY_ID = os.environ.get("LEGAL_ENTITY_ID", "").strip()
    LEGAL_ENTITY_ADDRESS = os.environ.get("LEGAL_ENTITY_ADDRESS", "").strip()
    LEGAL_CONTACT_EMAIL = os.environ.get("LEGAL_CONTACT_EMAIL", "").strip()
    LEGAL_JURISDICTION = os.environ.get("LEGAL_JURISDICTION", "").strip()
    LEGAL_EFFECTIVE_DATE = os.environ.get("LEGAL_EFFECTIVE_DATE", "").strip()
    LEGAL_REFUND_WINDOW_DAYS = int(os.environ.get("LEGAL_REFUND_WINDOW_DAYS", "0") or "0")
    SELF_STUDY_SIGNUP_ENABLED = os.environ.get("SELF_STUDY_SIGNUP_ENABLED", "0") == "1"
    SUBSCRIPTION_REQUIRED = os.environ.get("SUBSCRIPTION_REQUIRED", "0") == "1"
    LEGACY_ACCESS_DAYS = int(os.environ.get("LEGACY_ACCESS_DAYS", "30") or "30")
    FREE_DAILY_QUESTION_LIMIT = int(os.environ.get("FREE_DAILY_QUESTION_LIMIT", "10") or "10")
    COURSE_INCLUDED_IN_SUBSCRIPTION = os.environ.get("COURSE_INCLUDED_IN_SUBSCRIPTION", "1") == "1"
    PUBLIC_SAMPLE_MEDIA_FOLDER = os.environ.get("PUBLIC_SAMPLE_MEDIA_FOLDER") or os.path.join(
        os.path.dirname(UPLOAD_FOLDER),
        "public_sample_media",
    )
    PUBLIC_QBANK_PRICE_AMOUNT = int(os.environ.get("PUBLIC_QBANK_PRICE_AMOUNT", "800") or "800")  # minor units (e.g. 800 = $8.00)
    PUBLIC_QBANK_PRICE_CURRENCY = os.environ.get("PUBLIC_QBANK_PRICE_CURRENCY", "USD").strip() or "USD"
    PUBLIC_SAMPLE_PER_EXAM = int(os.environ.get("PUBLIC_SAMPLE_PER_EXAM", "2") or "2")
    PUBLIC_STATS_TTL_SECONDS = int(os.environ.get("PUBLIC_STATS_TTL_SECONDS", "60") or "60")

    # Stage 6: anti-scraping, velocity & abuse rate-limiting thresholds (never hardcoded in handlers)
    ABUSE_PROTECTION_ENABLED = os.environ.get("ABUSE_PROTECTION_ENABLED", "1") == "1"
    ABUSE_PROTECTION_IN_TESTING = False
    QBANK_RATE_LIMIT_VIEW = os.environ.get("QBANK_RATE_LIMIT_VIEW", "120 per minute; 1000 per hour")
    QBANK_RATE_LIMIT_ACTION = os.environ.get("QBANK_RATE_LIMIT_ACTION", "90 per minute; 600 per hour")
    QBANK_RATE_LIMIT_EXPORT = os.environ.get("QBANK_RATE_LIMIT_EXPORT", "10 per minute; 60 per hour")
    PUBLIC_RATE_LIMIT_PAGE = os.environ.get("PUBLIC_RATE_LIMIT_PAGE", "120 per minute")
    QBANK_SCRAPE_WINDOW_SECONDS = int(os.environ.get("QBANK_SCRAPE_WINDOW_SECONDS", "60") or "60")
    QBANK_SCRAPE_MAX_PER_WINDOW = int(os.environ.get("QBANK_SCRAPE_MAX_PER_WINDOW", "150") or "150")
    QBANK_SCRAPE_MAX_PER_HOUR = int(os.environ.get("QBANK_SCRAPE_MAX_PER_HOUR", "600") or "600")
    ABUSE_404_WINDOW_SECONDS = int(os.environ.get("ABUSE_404_WINDOW_SECONDS", "60") or "60")
    ABUSE_404_MAX_PER_WINDOW = int(os.environ.get("ABUSE_404_MAX_PER_WINDOW", "30") or "30")

    # Stage 5: Stripe Hosted Checkout & Webhooks (no card data ever stored on Monday)
    STRIPE_ENABLED = os.environ.get("STRIPE_ENABLED", "0") == "1"
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
    STRIPE_API_VERSION = os.environ.get("STRIPE_API_VERSION", "2024-06-20").strip() or "2024-06-20"
    STRIPE_WEBHOOK_TOLERANCE_SECONDS = int(os.environ.get("STRIPE_WEBHOOK_TOLERANCE_SECONDS", "300") or "300")
    STRIPE_TRIAL_DAYS = int(os.environ.get("STRIPE_TRIAL_DAYS", "0") or "0")
