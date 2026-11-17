"""Visitor tracking middleware, User-Agent parser, GeoIP lookup, and salted IP hashing."""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import uuid
from datetime import timedelta
from urllib.parse import unquote

from flask import current_app, g, request
from flask_login import current_user, user_logged_in

from .models import PageView, Visit, db, utcnow

log = logging.getLogger(__name__)

VISITOR_COOKIE_NAME = "monday_vid"
VISITOR_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year
VISIT_TIMEOUT_MINUTES = 30
MAX_PAGE_DURATION_SEC = 30 * 60

_IGNORED_PREFIXES = (
    "/static",
    "/assets",
    "/uploads",
    "/api",
    "/admin",
    "/course/admin",
    "/roadmap/admin",
    "/favicon.ico",
    "/robots.txt",
    "/sitemap.xml",
)

_BOT_RE = re.compile(
    r"(bot|crawl|spider|slurp|mediapartners|bingpreview|facebookexternalhit|"
    r"whatsapp|telegrambot|uptimerobot|pingdom|statuscake|ahrefs|semrush)",
    re.I,
)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

_GEOIP_READER = None
_GEOIP_PATH_TRIED = None


def get_client_ip() -> str:
    """Return the probable client IP from headers/remote_addr (never stored raw)."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        for part in xff.split(","):
            candidate = part.strip()
            if candidate:
                return candidate
    real_ip = (request.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip
    return (request.remote_addr or "").strip()


def hash_ip(raw_ip: str, salt: str = "") -> str | None:
    """Hash a raw IP address with SHA-256 + salt; return None if IP is empty."""
    if not raw_ip:
        return None
    if not salt:
        salt = os.environ.get("ANALYTICS_IP_SALT") or current_app.config.get("SECRET_KEY", "monday-salt")
    payload = f"{salt}:{raw_ip}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_private_ip(raw_ip: str) -> bool:
    if not raw_ip:
        return False
    try:
        ip_obj = ipaddress.ip_address(raw_ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved
    except ValueError:
        return False


def _get_geoip_reader():
    global _GEOIP_READER, _GEOIP_PATH_TRIED
    db_path = (
        os.environ.get("GEOIP2_DB_PATH")
        or current_app.config.get("GEOIP2_DB_PATH")
        or ""
    ).strip()
    if not db_path:
        default_mmdb = os.path.join(current_app.instance_path, "GeoLite2-City.mmdb")
        if os.path.exists(default_mmdb):
            db_path = default_mmdb
    if not db_path or not os.path.exists(db_path):
        return None
    if _GEOIP_PATH_TRIED == db_path and _GEOIP_READER is not None:
        return _GEOIP_READER
    _GEOIP_PATH_TRIED = db_path
    try:
        import geoip2.database  # type: ignore

        _GEOIP_READER = geoip2.database.Reader(db_path)
        return _GEOIP_READER
    except Exception as exc:
        log.debug("GeoIP2 reader unavailable: %s", exc)
        return None


def resolve_geoip(raw_ip: str) -> tuple[str | None, str | None]:
    """Resolve (country, city) via optional GeoLite2 MMDB or reverse-proxy headers."""
    # 1. Reverse-proxy Geo headers (Cloudflare / Vercel / Render / Nginx GeoIP)
    hdr_country = (
        request.headers.get("CF-IPCountry")
        or request.headers.get("X-Vercel-IP-Country")
        or request.headers.get("X-Country-Code")
        or request.headers.get("X-AppEngine-Country")
        or ""
    ).strip().upper()
    hdr_city = (
        request.headers.get("CF-IPCity")
        or request.headers.get("X-Vercel-IP-City")
        or request.headers.get("X-AppEngine-City")
        or ""
    ).strip()
    if hdr_city:
        hdr_city = unquote(hdr_city)[:120]
    if hdr_country and hdr_country not in ("XX", "T1"):
        return hdr_country[:80], (hdr_city or None)

    if not raw_ip:
        return None, None
    if _is_private_ip(raw_ip):
        return "LOCAL", "Localhost"

    # 2. Optional local GeoLite2 MMDB database
    reader = _get_geoip_reader()
    if reader is not None:
        try:
            res = reader.city(raw_ip)
            country = res.country.iso_code or res.country.name
            city = res.city.name
            return (country[:80] if country else None), (city[:120] if city else None)
        except Exception:
            try:
                res = reader.country(raw_ip)
                country = res.country.iso_code or res.country.name
                return (country[:80] if country else None), None
            except Exception:
                pass

    return None, None


def parse_user_agent(ua_string: str) -> tuple[str, str, str]:
    """Parse User-Agent into (device_type, os, browser)."""
    ua = (ua_string or "").strip()
    if not ua:
        return "desktop", "Unknown", "Unknown"

    # Optional external library if installed
    try:
        import user_agents  # type: ignore

        parsed = user_agents.parse(ua)
        if parsed.is_tablet:
            dev = "tablet"
        elif parsed.is_mobile:
            dev = "mobile"
        else:
            dev = "desktop"
        os_name = (parsed.os.family or "Other")[:64]
        br_name = (parsed.browser.family or "Other")[:64]
        return dev, os_name, br_name
    except Exception:
        pass

    low = ua.lower()

    # Device type
    if "ipad" in low or "tablet" in low or ("android" in low and "mobile" not in low) or "kindle" in low:
        device_type = "tablet"
    elif any(k in low for k in ("iphone", "ipod", "mobile", "windows phone", "blackberry", "opera mini")):
        device_type = "mobile"
    else:
        device_type = "desktop"

    # OS detection
    if "iphone" in low or "ipad" in low or "ipod" in low:
        os_name = "iOS"
    elif "android" in low:
        os_name = "Android"
    elif "windows" in low:
        os_name = "Windows"
    elif "cros" in low:
        os_name = "ChromeOS"
    elif "mac os x" in low or "macintosh" in low:
        os_name = "macOS"
    elif "linux" in low:
        os_name = "Linux"
    else:
        os_name = "Other"

    # Browser detection (order matters because Chrome/Safari tokens appear in Edge/Opera/YaBrowser)
    if "edg/" in low or "edge/" in low:
        browser = "Edge"
    elif "opr/" in low or "opera" in low:
        browser = "Opera"
    elif "yabrowser" in low:
        browser = "YaBrowser"
    elif "samsungbrowser" in low:
        browser = "Samsung Internet"
    elif "firefox/" in low or "fxios/" in low:
        browser = "Firefox"
    elif "chrome/" in low or "crios/" in low:
        browser = "Chrome"
    elif "safari/" in low:
        browser = "Safari"
    else:
        browser = "Other"

    return device_type, os_name, browser


def _detect_language() -> str | None:
    if current_user.is_authenticated and getattr(current_user, "language", None):
        return current_user.language[:16]
    cookie_lang = request.cookies.get("lang")
    if cookie_lang:
        return cookie_lang[:16]
    accept = request.accept_languages.best
    if accept:
        return accept.split("-")[0][:16].lower()
    return None


def should_track_request(resp) -> bool:
    """Return True only for trackable non-admin HTML GET page views."""
    if not current_app.config.get("ANALYTICS_ENABLED", True):
        return False
    if request.method != "GET":
        return False
    path = request.path or "/"
    for prefix in _IGNORED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return False
    if request.args.get("fragment"):
        return False
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return False
    if resp.status_code != 200 or resp.mimetype != "text/html":
        return False
    if current_user.is_authenticated and getattr(current_user, "role", None) == "admin":
        return False
    ua = request.headers.get("User-Agent", "")
    if ua and _BOT_RE.search(ua):
        return False
    return True


def _is_interactive_heartbeat(resp) -> bool:
    """Keep active logged-in non-admin users online during tests/bank/autosave without adding PageView noise."""
    if not current_app.config.get("ANALYTICS_ENABLED", True):
        return False
    if not current_user.is_authenticated or getattr(current_user, "role", None) == "admin":
        return False
    if resp.status_code >= 400:
        return False
    path = request.path or "/"
    for prefix in ("/static", "/assets", "/uploads", "/admin", "/course/admin", "/roadmap/admin", "/favicon.ico"):
        if path == prefix or path.startswith(prefix + "/"):
            return False
    if path in ("/api/version", "/api/site-status"):
        return False
    return True


def _valid_cookie_id(raw: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    if _UUID_RE.match(s):
        return s.lower()
    return None


def _get_or_create_cookie_id() -> tuple[str, bool]:
    existing = _valid_cookie_id(request.cookies.get(VISITOR_COOKIE_NAME))
    if existing:
        return existing, False
    cached = getattr(g, "_analytics_cookie_id", None)
    if cached:
        return cached, True
    new_id = str(uuid.uuid4())
    g._analytics_cookie_id = new_id
    return new_id, True


def _link_active_visit_on_login(sender, user, **extra) -> None:
    """When a visitor logs in or registers, link their open 30-min anonymous visit."""
    if getattr(user, "role", None) == "admin":
        return
    cookie_id = _valid_cookie_id(request.cookies.get(VISITOR_COOKIE_NAME)) or getattr(g, "_analytics_cookie_id", None)
    if not cookie_id:
        return
    try:
        cutoff = utcnow() - timedelta(minutes=VISIT_TIMEOUT_MINUTES)
        visit = (
            Visit.query.filter(
                Visit.session_cookie_id == cookie_id,
                Visit.ended_at >= cutoff,
                Visit.user_id.is_(None),
            )
            .order_by(Visit.ended_at.desc())
            .first()
        )
        if visit is not None:
            visit.user_id = user.id
            db.session.commit()
    except Exception as exc:
        db.session.rollback()
        log.debug("Failed to link visit on login: %s", exc)


def register_analytics_middleware(app) -> None:
    """Attach page-view tracking and login-linking hooks to the Flask app."""
    user_logged_in.connect(_link_active_visit_on_login, app)

    @app.after_request
    def _track_visit_and_pageview(response):
        track_page = should_track_request(response)
        heartbeat_only = (not track_page) and _is_interactive_heartbeat(response)
        if not track_page and not heartbeat_only:
            return response

        cookie_id, is_new_cookie = _get_or_create_cookie_id()
        now = utcnow()
        cutoff = now - timedelta(minutes=VISIT_TIMEOUT_MINUTES)

        try:
            visit = (
                Visit.query.filter(
                    Visit.session_cookie_id == cookie_id,
                    Visit.ended_at >= cutoff,
                )
                .order_by(Visit.ended_at.desc())
                .first()
            )

            user_id = current_user.id if current_user.is_authenticated else None

            if visit is None:
                raw_ip = get_client_ip()
                country, city = resolve_geoip(raw_ip)
                ip_hash = hash_ip(raw_ip)
                del raw_ip  # explicit drop of raw IP

                device_type, os_name, browser = parse_user_agent(request.headers.get("User-Agent", ""))
                referer = (request.referrer or "").strip()[:512] or None
                lang = _detect_language()

                visit = Visit(
                    session_cookie_id=cookie_id,
                    user_id=user_id,
                    ip_hash=ip_hash,
                    country=country,
                    city=city,
                    device_type=device_type,
                    os=os_name,
                    browser=browser,
                    referer=referer,
                    language=lang,
                    started_at=now,
                    ended_at=now,
                    page_count=0,
                )
                db.session.add(visit)
                db.session.flush()
            else:
                visit.ended_at = now
                if user_id and visit.user_id is None:
                    visit.user_id = user_id
                if not visit.language:
                    visit.language = _detect_language()

            if track_page:
                # Compute time spent on previous page in this visit
                prev_pv = (
                    PageView.query.filter_by(visit_id=visit.id)
                    .order_by(PageView.created_at.desc())
                    .first()
                )
                if prev_pv is not None and prev_pv.created_at is not None:
                    delta = int((now - prev_pv.created_at).total_seconds())
                    prev_pv.time_spent_seconds = max(0, min(delta, MAX_PAGE_DURATION_SEC))

                pv = PageView(
                    visit_id=visit.id,
                    path=(request.path or "/")[:512],
                    created_at=now,
                    time_spent_seconds=0,
                )
                db.session.add(pv)
                visit.page_count = (visit.page_count or 0) + 1
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            log.warning("Analytics tracking error: %s", exc)

        if is_new_cookie:
            response.set_cookie(
                VISITOR_COOKIE_NAME,
                cookie_id,
                max_age=VISITOR_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
            )
        return response
