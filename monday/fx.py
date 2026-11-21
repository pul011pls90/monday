"""Daily display FX rates service (NBKR XML feed + 12h cache + safe offline fallback) and read-only API."""
from __future__ import annotations

import os
import ssl
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from flask import Blueprint, jsonify

from .access import permission_required

bp = Blueprint("fx", __name__)

NBKR_DAILY_XML_URL = "https://www.nbkr.kg/XML/daily.xml"
SUPPORTED_CURRENCIES = ("KGS", "USD", "EUR", "KZT", "RUB")

# Approximate KGS per 1 unit of foreign currency used only when NBKR is unreachable or times out.
_FALLBACK_KGS_PER_UNIT: dict[str, float] = {
    "KGS": 1.0,
    "USD": 87.45,
    "EUR": 94.50,
    "KZT": 0.175,
    "RUB": 0.90,
}

_CACHE_TTL_OK_SEC = 12 * 3600
_CACHE_TTL_FALLBACK_SEC = 300
_MAX_XML_BYTES = 256 * 1024

_FX_LOCK = threading.Lock()
_FX_CACHE: dict[str, object] | None = None
_FX_CACHE_EXPIRES_AT: float = 0.0


def _build_rates_payload(kgs_per_unit: dict[str, float], *, source: str, updated_at: str) -> dict:
    rates: dict[str, float] = {"KGS": 1.0}
    clean_per_unit: dict[str, float] = {"KGS": 1.0}
    for code in SUPPORTED_CURRENCIES:
        if code == "KGS":
            continue
        unit_kgs = float(kgs_per_unit.get(code) or _FALLBACK_KGS_PER_UNIT[code])
        if unit_kgs <= 0:
            unit_kgs = _FALLBACK_KGS_PER_UNIT[code]
        clean_per_unit[code] = round(unit_kgs, 6)
        rates[code] = round(1.0 / unit_kgs, 6)
    return {
        "base": "KGS",
        "rates": rates,
        "kgs_per_unit": clean_per_unit,
        "updated_at": updated_at,
        "source": source,
    }


def parse_nbkr_daily_xml(raw_xml: bytes | str) -> dict[str, float]:
    """Parse NBKR daily XML into {ISO_CODE: kgs_per_1_unit}."""
    root = ET.fromstring(raw_xml)
    parsed: dict[str, float] = {"KGS": 1.0}
    for cur in root.findall(".//Currency"):
        code = (cur.attrib.get("ISOCode") or "").strip().upper()
        if code not in SUPPORTED_CURRENCIES or code == "KGS":
            continue
        nominal_el = cur.find("Nominal")
        value_el = cur.find("Value")
        if nominal_el is None or value_el is None:
            continue
        try:
            nominal = float((nominal_el.text or "1").strip().replace(",", "."))
            value = float((value_el.text or "0").strip().replace(",", "."))
        except ValueError:
            continue
        if nominal > 0 and value > 0:
            parsed[code] = value / nominal
    return parsed


def _ssl_context() -> ssl.SSLContext:
    """Use default CA paths or fall back to the OS CA bundle when Python lacks a bundled cafile."""
    paths = ssl.get_default_verify_paths()
    if paths.cafile or paths.capath:
        return ssl.create_default_context()
    for candidate in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.isfile(candidate):
            return ssl.create_default_context(cafile=candidate)
    return ssl.create_default_context()


def _fetch_nbkr_rates(timeout: float = 3.0) -> dict:
    req = urllib.request.Request(
        NBKR_DAILY_XML_URL,
        headers={"User-Agent": "MondayAcademy/1.0 (+https://monday.kg)"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        raw = resp.read(_MAX_XML_BYTES)
    parsed = parse_nbkr_daily_xml(raw)
    required = {"USD", "EUR", "KZT", "RUB"}
    if not required.issubset(parsed.keys()):
        raise ValueError("Incomplete currency set in NBKR feed")
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return _build_rates_payload(parsed, source="NBKR", updated_at=now_iso)


def clear_fx_cache() -> None:
    """Reset the in-memory FX rate cache (intended for tests)."""
    global _FX_CACHE, _FX_CACHE_EXPIRES_AT
    with _FX_LOCK:
        _FX_CACHE = None
        _FX_CACHE_EXPIRES_AT = 0.0


def get_fx_rates(*, force_refresh: bool = False, timeout: float = 3.0) -> dict:
    """Return cached NBKR KGS exchange rates or safe fallback if the feed is unreachable."""
    global _FX_CACHE, _FX_CACHE_EXPIRES_AT
    now_mono = time.monotonic()
    with _FX_LOCK:
        if not force_refresh and _FX_CACHE is not None and now_mono < _FX_CACHE_EXPIRES_AT:
            return dict(_FX_CACHE)

    try:
        payload = _fetch_nbkr_rates(timeout=timeout)
        ttl = _CACHE_TTL_OK_SEC
    except Exception:
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        payload = _build_rates_payload(_FALLBACK_KGS_PER_UNIT, source="fallback", updated_at=now_iso)
        ttl = _CACHE_TTL_FALLBACK_SEC

    with _FX_LOCK:
        _FX_CACHE = payload
        _FX_CACHE_EXPIRES_AT = time.monotonic() + ttl
        return dict(payload)


@bp.get("/api/fx/rates")
@permission_required("crm.finance.read")
def api_fx_rates():
    """Return display conversion rates anchored on KGS for authenticated CRM/Admin staff."""
    data = get_fx_rates()
    return jsonify({"ok": True, **data})
