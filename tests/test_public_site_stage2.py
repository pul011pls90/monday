"""Stage 2 tests: public site pages behind PUBLIC_SITE_ENABLED, safe Location/Course fields, SEO, CRM intake, TODO guard."""
from __future__ import annotations

import re

from config import Config
from monday.extensions import db
from monday.models import AcademicCourse, Lead, LeadActivity, Location, User


def _make_app(tmp_path, *, public_enabled: bool = True, csrf_enabled: bool = False):
    class PublicCfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        PUBLIC_SITE_ENABLED = public_enabled
        PUBLIC_QBANK_PRICE_AMOUNT = 800
        PUBLIC_QBANK_PRICE_CURRENCY = "USD"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'public_site.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")

    from monday import create_app

    return create_app(PublicCfg, seed_if_empty=False)


def test_public_site_flag_off_preserves_legacy_behavior(tmp_path):
    app = _make_app(tmp_path, public_enabled=False)
    c = app.test_client()

    r_root = c.get("/", follow_redirects=False)
    assert r_root.status_code == 302 and "/login" in r_root.headers["Location"]

    for hidden in ("/offline-courses", "/online", "/question-bank", "/pricing", "/faq", "/contact"):
        assert c.get(hidden).status_code == 404

    # Existing PWA offline route, /about, /terms, /privacy, /apply remain intact
    assert c.get("/offline").status_code == 200
    assert "Нет подключения к интернету" in c.get("/offline").data.decode("utf-8")
    assert c.get("/about").status_code == 200
    assert c.get("/apply").status_code == 200


def test_public_pages_200_seo_no_personal_data_and_todo_lorem_guard(tmp_path):
    app = _make_app(tmp_path, public_enabled=True)
    with app.app_context():
        u = User(email="secret.mgr@monday.kg", name="Secret Manager", role="sales_manager", is_approved=True, is_on_shift=True)
        u.set_password("Pass12345!")
        db.session.add(u)
        db.session.flush()

        # Public location: room must NEVER leak
        loc_pub = Location(
            name="Филиал Центр",
            public_name="Кампус на Токтогула",
            address="ул. Токтогула 77",
            room="Кабинет 404 СЕКРЕТНЫЙ",
            map_url="https://maps.example.com/toktogula",
            working_hours="Пн–Сб 09:00–20:00",
            phone="+996700111222",
            is_active=True,
            is_public=True,
        )
        # Non-public location: must NEVER appear anywhere
        loc_priv = Location(
            name="Скрытый склад",
            public_name="Приватная Локация",
            address="Секретный адрес 99",
            room="Кабинет 999",
            is_active=True,
            is_public=False,
        )
        c_pub = AcademicCourse(
            code="SAT-PUB",
            name="Digital SAT Intensive",
            exam="SAT",
            is_active=True,
            is_public=True,
            public_summary="Онлайн-группы с практикой Desmos.",
        )
        c_priv = AcademicCourse(
            code="INT-PRIV",
            name="Внутренний закрытый курс",
            exam="ORT",
            is_active=True,
            is_public=False,
            public_summary="Не для публикации.",
        )
        db.session.add_all([loc_pub, loc_priv, c_pub, c_priv])
        db.session.commit()

    c = app.test_client()
    public_urls = ("/", "/about", "/offline-courses", "/online", "/question-bank", "/pricing", "/faq", "/contact")
    titles = set()

    for url in public_urls:
        res = c.get(url)
        assert res.status_code == 200, f"{url} returned {res.status_code}"
        html = res.data.decode("utf-8")
        assert "TODO" not in html and "Lorem" not in html and "lorem" not in html
        assert "[требует подтверждения" not in html
        assert "15 000" not in html
        assert "secret.mgr@monday.kg" not in html
        assert "Кабинет 404 СЕКРЕТНЫЙ" not in html
        assert "Приватная Локация" not in html
        assert "Внутренний закрытый курс" not in html
        assert '<meta name="description"' in html
        assert '<link rel="canonical"' in html
        assert 'property="og:title"' in html
        t_m = re.search(r"<title>(.*?)</title>", html, re.S)
        assert t_m, f"Missing <title> on {url}"
        titles.add(t_m.group(1).strip())

    assert len(titles) == len(public_urls)

    # Public location & course appear on their dedicated pages
    off_html = c.get("/offline-courses").data.decode("utf-8")
    assert "Кампус на Токтогула" in off_html
    assert "Пн–Сб 09:00–20:00" in off_html
    assert "LocalBusiness" in off_html

    onl_html = c.get("/online").data.decode("utf-8")
    assert "Digital SAT Intensive" in onl_html

    # PWA /offline stays unpersonalized & separate from /offline-courses
    pwa_off = c.get("/offline")
    assert pwa_off.status_code == 200
    assert "Нет подключения к интернету" in pwa_off.data.decode("utf-8")
    assert 'name="csrf-token"' not in pwa_off.data.decode("utf-8")


def test_sitemap_robots_and_public_lead_form_crm_dedupe(tmp_path):
    app = _make_app(tmp_path, public_enabled=True, csrf_enabled=True)
    with app.app_context():
        m = User(email="crm@monday.kg", name="CRM Mgr", role="sales_manager", is_approved=True, is_on_shift=True)
        m.set_password("Pass12345!")
        db.session.add(m)
        db.session.commit()

    c = app.test_client()

    robots = c.get("/robots.txt")
    assert robots.status_code == 200
    r_txt = robots.data.decode("utf-8")
    assert "Disallow: /admin/" in r_txt and "Sitemap:" in r_txt

    sitemap = c.get("/sitemap.xml")
    assert sitemap.status_code == 200
    assert "xml" in sitemap.headers["Content-Type"]
    sm_xml = sitemap.data.decode("utf-8")
    for expected in ("/offline-courses", "/online", "/question-bank", "/pricing", "/faq", "/contact"):
        assert expected in sm_xml
    for forbidden in ("/admin", "/manager", "/teacher", "/uploads"):
        assert forbidden not in sm_xml

    # Submit form from /contact with UTMs & consent required
    contact_html = c.get("/contact?utm_source=instagram&utm_campaign=fall2026").data.decode("utf-8")
    csrf_m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', contact_html)
    assert csrf_m

    # Missing consent fails cleanly without creating lead
    bad_res = c.post(
        "/apply",
        data={
            "csrf_token": csrf_m.group(1),
            "next": "/contact",
            "consent_required": "1",
            "full_name": "Нурлан Беков",
            "phone": "0701222333",
        },
        follow_redirects=False,
    )
    assert bad_res.status_code == 302
    with app.app_context():
        assert Lead.query.count() == 0

    ok_res = c.post(
        "/apply",
        data={
            "csrf_token": csrf_m.group(1),
            "next": "/contact",
            "consent_required": "1",
            "consent": "1",
            "utm_source": "instagram",
            "utm_campaign": "fall2026",
            "full_name": "Нурлан Беков",
            "phone": "0701 222 333",
            "interest": "ОРТ",
            "mode_preference": "offline",
            "note": "Хочу в вечернюю группу",
        },
        follow_redirects=True,
    )
    assert ok_res.status_code == 200
    assert "Спасибо! Мы уже получили вашу заявку" in ok_res.data.decode("utf-8")

    # Repeat inquiry with same normalized phone deduplicates into the SAME open Lead
    c.post(
        "/apply",
        data={
            "csrf_token": csrf_m.group(1),
            "next": "/contact",
            "consent_required": "1",
            "consent": "1",
            "full_name": "Нурлан Беков",
            "phone": "+996701222333",
            "note": "Повторное уточнение",
        },
    )
    with app.app_context():
        assert Lead.query.count() == 1
        lead = Lead.query.one()
        assert lead.source == "site"
        assert lead.phone_e164 == "+996701222333"
        acts = "\n".join(a.body for a in LeadActivity.query.filter_by(lead_id=lead.id).all())
        assert "utm_source=instagram" in acts
        assert "Повторное уточнение" in acts


def test_site_preflight_blockers_happy_path_and_production_guard(tmp_path, capsys, monkeypatch):
    from monday.models import ContentNode, Question

    # 1. Production mode ignores PUBLIC_SITE_ENABLED=True and logs a clear error when blockers exist
    class ProdBlockCfg(Config):
        TESTING = True
        IS_PRODUCTION = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        PUBLIC_SITE_ENABLED = True
        PUBLIC_LEGAL_REVIEWED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'prod_guard.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")
        PUBLIC_SAMPLE_PERSISTENT_DISK = True

    from monday import create_app
    from monday.public_site import collect_site_preflight_blockers

    prod_app = create_app(ProdBlockCfg, seed_if_empty=False)
    err_out = capsys.readouterr().err
    assert "PUBLIC_SITE_ENABLED=1 ignored in production" in err_out
    c_prod = prod_app.test_client()
    r_root = c_prod.get("/", follow_redirects=False)
    assert r_root.status_code == 302 and "/login" in r_root.headers["Location"]
    assert c_prod.get("/offline-courses").status_code == 404

    # CLI site-preflight exits non-zero and lists concrete blockers
    runner = prod_app.test_cli_runner()
    cli_fail = runner.invoke(args=["site-preflight"])
    assert cli_fail.exit_code != 0
    assert "Location" in cli_fail.output
    assert "AcademicCourse" in cli_fail.output
    assert "PUBLIC_LEGAL_REVIEWED" in cli_fail.output
    assert "[требует подтверждения" in cli_fail.output
    with prod_app.app_context():
        missing_wa = collect_site_preflight_blockers(contacts_override={"whatsapp": ""})
        assert any("whatsapp" in b for b in missing_wa), missing_wa

    # 2. When all blockers are resolved (and using reviewed clean templates dir), preflight passes 0 blockers
    with prod_app.app_context():
        from monday.constants import EXAMS
        node = ContentNode(code="pref_n", name="Alg", level="node", exams=list(EXAMS.keys()))
        db.session.add(node)
        db.session.flush()
        db.session.add(
            Question(
                skill=node,
                exams=list(EXAMS.keys()),
                difficulty=1,
                text="2+2?",
                options=["3", "4"],
                correct="1",
                status="published",
                is_public_sample=True,
            )
        )
        db.session.add(
            Location(
                name="Main",
                public_name="Токтогула",
                address="ул. Токтогула 77",
                working_hours="09:00-20:00",
                phone="+996700111222",
                photo="/static/img/icon-192.png",
                is_active=True,
                is_public=True,
            )
        )
        db.session.add(
            AcademicCourse(
                code="ORT-1",
                name="ОРТ Интенсив",
                exam="ORT",
                public_summary="Интенсив по математике ОРТ.",
                is_active=True,
                is_public=True,
            )
        )
        db.session.commit()
        prod_app.config["PUBLIC_LEGAL_REVIEWED"] = True

        clean_dir = tmp_path / "clean_tpl"
        clean_dir.mkdir()
        (clean_dir / "about.html").write_text("<h1>Monday Academy</h1>", encoding="utf-8")

        blockers = collect_site_preflight_blockers(
            contacts_override={
                "instagram": "https://instagram.com/x",
                "telegram": "https://t.me/x",
                "whatsapp": "https://wa.me/996700111222",
                "trial_lesson": "https://monday.kg/contact",
                "address": "Токтогула 77",
            },
            template_dirs=(clean_dir,),
        )
        assert blockers == []


def test_info_about_retains_confirmed_figure_marker_while_unverified(tmp_path):
    app = _make_app(tmp_path, public_enabled=False)
    html = app.test_client().get("/about").data.decode("utf-8")
    assert "[требует подтверждения: число выпускников]" in html
    assert "15 000" not in html

