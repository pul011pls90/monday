"""Stage 7 tests: legal scaffolding (/terms, /privacy, /refund), dynamic config metadata, and preflight blockers."""
from __future__ import annotations

from config import Config
from monday import create_app
from monday.extensions import db
from monday.models import StudentProfile, User
from monday.public_site import collect_site_preflight_blockers


def _make_app(tmp_path, **overrides):
    class Cfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'stage7.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    for k, v in overrides.items():
        setattr(Cfg, k, v)
    return create_app(Cfg, seed_if_empty=False)


def test_legal_pages_show_draft_notice_and_markers_when_unreviewed(tmp_path):
    app = _make_app(
        tmp_path,
        PUBLIC_SITE_ENABLED=True,
        PUBLIC_LEGAL_REVIEWED=False,
        PUBLIC_QBANK_PRICE_AMOUNT=950,
        PUBLIC_QBANK_PRICE_CURRENCY="USD",
    )
    client = app.test_client()

    for path in ("/terms", "/privacy", "/refund"):
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Черновик юридического документа" in body
        assert "[требует подтверждения:" in body
        assert "TODO" not in body
        assert "Lorem" not in body
        assert 'href="/refund"' in body
        assert 'href="/terms"' in body
        assert 'href="/privacy"' in body

    # Pricing from config (not hardcoded $8) flows into Terms & Refund
    terms_body = client.get("/terms").get_data(as_text=True)
    assert "Условия использования" in terms_body
    assert "$9.50" in terms_body

    refund_body = client.get("/refund").get_data(as_text=True)
    assert "$9.50" in refund_body
    assert "Подписка на банк вопросов" in refund_body
    assert "Абонемент" in refund_body

    privacy_body = client.get("/privacy").get_data(as_text=True)
    assert "Cookies" in privacy_body

    # Preflight reports missing legal config keys alongside PUBLIC_LEGAL_REVIEWED=0
    with app.app_context():
        blockers = collect_site_preflight_blockers()
        joined = "\n".join(blockers)
        assert "PUBLIC_LEGAL_REVIEWED=0" in joined
        assert "LEGAL_ENTITY_NAME" in joined
        assert "LEGAL_ENTITY_ID" in joined
        assert "LEGAL_CONTACT_EMAIL" in joined
        assert "LEGAL_REFUND_WINDOW_DAYS" in joined


def test_legal_pages_clean_when_reviewed_and_configured(tmp_path):
    app = _make_app(
        tmp_path,
        PUBLIC_SITE_ENABLED=True,
        PUBLIC_LEGAL_REVIEWED=True,
        LEGAL_ENTITY_NAME="ОсОО «Мандей Академи»",
        LEGAL_ENTITY_ID="12345678901234",
        LEGAL_ENTITY_ADDRESS="г. Бишкек, ул. Токтогула, 77",
        LEGAL_CONTACT_EMAIL="legal@monday.example",
        LEGAL_JURISDICTION="Законодательство Кыргызской Республики",
        LEGAL_EFFECTIVE_DATE="2026-12-01",
        LEGAL_REFUND_WINDOW_DAYS=14,
    )
    client = app.test_client()

    for path in ("/terms", "/privacy", "/refund"):
        resp = client.get(path)
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Черновик юридического документа" not in body
        assert "[требует подтверждения" not in body
        assert "TODO" not in body
        assert "Lorem" not in body
        assert "ОсОО «Мандей Академи»" in body
        assert "12345678901234" in body
        assert "legal@monday.example" in body

    refund_body = client.get("/refund").get_data(as_text=True)
    assert "14" in refund_body

    # Legal config blockers are all resolved
    with app.app_context():
        blockers = collect_site_preflight_blockers()
        legal_blockers = [b for b in blockers if "LEGAL_" in b or "Legal" in b]
        assert legal_blockers == []


def test_legal_links_across_layouts_and_sitemap(tmp_path):
    app = _make_app(tmp_path, PUBLIC_SITE_ENABLED=True, PUBLIC_LEGAL_REVIEWED=True)
    with app.app_context():
        student = User(email="s7@test.local", name="Student 7", role="student", is_approved=True)
        student.set_password("Pass123456!")
        db.session.add(student)
        db.session.flush()
        db.session.add(StudentProfile(user_id=student.id, exam="SAT", onboarded=True))
        db.session.commit()

    client = app.test_client()

    # Sitemap lists /terms, /privacy, /refund
    sm = client.get("/sitemap.xml")
    assert sm.status_code == 200
    sm_xml = sm.get_data(as_text=True)
    assert "/terms" in sm_xml
    assert "/privacy" in sm_xml
    assert "/refund" in sm_xml

    # Public pricing page links to /refund, /terms, /privacy
    pricing_html = client.get("/pricing").get_data(as_text=True)
    assert 'href="/refund"' in pricing_html
    assert 'href="/terms"' in pricing_html
    assert 'href="/privacy"' in pricing_html

    # Logged-in student sees /refund links on /subscription, /support, and legal pages render cleanly in app layout
    assert client.post("/login", data={"email": "s7@test.local", "password": "Pass123456!"}).status_code == 302
    assert 'href="/refund"' in client.get("/subscription").get_data(as_text=True)
    assert 'href="/refund"' in client.get("/support").get_data(as_text=True)
    assert client.get("/refund").status_code == 200
