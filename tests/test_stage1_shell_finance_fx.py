"""Stage 1 QA tests: FX NBKR endpoint & fallback, frosted shell panel, Finance KPI/FX UI, and Account settings."""
from __future__ import annotations

import os
import re
import tempfile
import urllib.request

from flask_migrate import upgrade

from config import Config
from monday import fx as fx_mod
from monday.extensions import db
from monday.models import MembershipPlan, PaymentTransaction, StudentPass, StudentProfile, User

_SAMPLE_NBKR_XML = b"""<?xml version="1.0" encoding="windows-1251"?>
<CurrencyRates Name="Daily Exchange Rates" Date="22.11.2026">
  <Currency ISOCode="USD"><Nominal>1</Nominal><Value>87,4500</Value></Currency>
  <Currency ISOCode="EUR"><Nominal>1</Nominal><Value>94,5000</Value></Currency>
  <Currency ISOCode="KZT"><Nominal>10</Nominal><Value>1,7500</Value></Currency>
  <Currency ISOCode="RUB"><Nominal>1</Nominal><Value>0,9000</Value></Currency>
</CurrencyRates>
"""


def _make_app(*, csrf_enabled: bool = False):
    tmp = tempfile.mkdtemp()

    class Stage1Config(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "stage1.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(Stage1Config, seed_if_empty=False)
    with app.app_context():
        upgrade()
    return app


def _seed_user(app, email: str, name: str, role: str, pw: str = "StrongStaff12!") -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True, is_blocked=False)
        u.set_password(pw)
        db.session.add(u)
        db.session.flush()
        if role == "student":
            db.session.add(StudentProfile(user_id=u.id, exam="ORT", onboarded=True))
        db.session.commit()
        return u.id


def _login(client, email: str, pw: str = "StrongStaff12!"):
    r = client.post("/login", data={"email": email, "password": pw})
    assert r.status_code == 302
    return client


def test_parse_nbkr_xml_commas_and_nominal():
    xml_payload = b"""<?xml version="1.0" encoding="windows-1251" ?>
<CurrencyRates Name="Daily Exchange Rates" Date="22.11.2026">
  <Currency ISOCode="USD"><Nominal>1</Nominal><Value>87,4500</Value></Currency>
  <Currency ISOCode="EUR"><Nominal>1</Nominal><Value>95,8977</Value></Currency>
  <Currency ISOCode="KZT"><Nominal>100</Nominal><Value>19,2300</Value></Currency>
  <Currency ISOCode="RUB"><Nominal>10</Nominal><Value>10,6650</Value></Currency>
</CurrencyRates>
"""
    parsed = fx_mod.parse_nbkr_daily_xml(xml_payload)
    assert abs(parsed["USD"] - 87.45) < 1e-6
    assert abs(parsed["EUR"] - 95.8977) < 1e-6
    assert abs(parsed["KZT"] - 0.1923) < 1e-6
    assert abs(parsed["RUB"] - 1.0665) < 1e-6


def test_fx_api_rbac_nbkr_parse_and_offline_fallback(monkeypatch):
    app = _make_app(csrf_enabled=False)
    _seed_user(app, "mgr@monday.kg", "Sales Manager", "sales_manager")
    _seed_user(app, "sup@monday.kg", "Supervisor", "supervisor")
    _seed_user(app, "adm@monday.kg", "Admin", "admin")
    _seed_user(app, "tch@monday.kg", "Teacher", "teacher")
    _seed_user(app, "ast@monday.kg", "Assistant", "assistant")
    _seed_user(app, "stu@monday.kg", "Student", "student")

    # 1. RBAC checks (with mocked NBKR feed)
    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, _limit=None):
            return _SAMPLE_NBKR_XML

    calls = {"count": 0}

    def _fake_urlopen(_req, timeout=3.0, context=None):
        calls["count"] += 1
        return _FakeResp()

    fx_mod.clear_fx_cache()
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    for allowed_email in ("mgr@monday.kg", "sup@monday.kg", "adm@monday.kg"):
        c = _login(app.test_client(), allowed_email)
        r = c.get("/api/fx/rates")
        assert r.status_code == 200
        body = r.get_json()
        assert body["ok"] is True
        assert body["base"] == "KGS"
        assert body["source"] == "NBKR"
        assert body["rates"]["KGS"] == 1
        for cur in ("USD", "EUR", "KZT", "RUB"):
            assert isinstance(body["rates"][cur], float) and body["rates"][cur] > 0
        # 10 KZT = 1.75 KGS => 1 KZT = 0.175 KGS
        assert abs(body["kgs_per_unit"]["KZT"] - 0.175) < 1e-5

    # Cache hit: only 1 upstream call across all 3 requests
    assert calls["count"] == 1

    for denied_email in ("stu@monday.kg", "tch@monday.kg", "ast@monday.kg"):
        c = _login(app.test_client(), denied_email)
        assert c.get("/api/fx/rates").status_code == 403

    # 2. Timeout / network error falls back cleanly without throwing
    fx_mod.clear_fx_cache()

    def _timeout_urlopen(_req, timeout=3.0, context=None):
        raise TimeoutError("NBKR unreachable")

    monkeypatch.setattr(urllib.request, "urlopen", _timeout_urlopen)
    c = _login(app.test_client(), "mgr@monday.kg")
    r = c.get("/api/fx/rates")
    assert r.status_code == 200
    fb = r.get_json()
    assert fb["ok"] is True
    assert fb["base"] == "KGS"
    assert fb["source"] == "fallback"
    assert fb["rates"]["KGS"] == 1
    for cur in ("USD", "EUR", "KZT", "RUB"):
        assert isinstance(fb["rates"][cur], float) and fb["rates"][cur] > 0


def test_shell_panel_finance_fx_hooks_and_account_controls():
    app = _make_app(csrf_enabled=True)
    _seed_user(app, "sup@monday.kg", "Supervisor", "supervisor")
    _seed_user(app, "mgr@monday.kg", "Manager", "sales_manager")
    stu_id = _seed_user(app, "stu@monday.kg", "Student", "student")

    with app.app_context():
        plan = MembershipPlan(name="SAT 8", total_lessons=8, duration_days=30, price_amount=12000)
        db.session.add(plan)
        db.session.flush()
        sp = StudentPass(
            student_user_id=stu_id,
            plan_id=plan.id,
            status="active",
            lessons_total=8,
            lessons_remaining=2,
            agreed_price=12000,
            paid_amount=8000,
        )
        db.session.add(sp)
        db.session.flush()
        db.session.add(
            PaymentTransaction(
                student_user_id=stu_id,
                pass_id=sp.id,
                amount=8000,
                method="cash",
                kind="payment",
                note="Предоплата",
            )
        )
        db.session.commit()

    def _login_csrf(client, email, pw="StrongStaff12!"):
        pg = client.get("/login").data.decode()
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pg)
        assert m
        r = client.post("/login", data={"email": email, "password": pw, "csrf_token": m.group(1)})
        assert r.status_code == 302
        return client

    sup = _login_csrf(app.test_client(), "sup@monday.kg")

    # All workspace pages render inside the unified frosted shell panel
    for url in ("/manager/", "/manager/leads", "/manager/pipeline", "/manager/finance", "/manager/audit", "/manager/account", "/academic/schedule"):
        res = sup.get(url)
        assert res.status_code == 200, url
        html = res.data.decode()
        assert 'class="app-shell-panel"' in html, url

    # Finance page: colorful money cards, equal-height grid, currency switcher, data-kgs-amount
    fin_html = sup.get("/manager/finance").data.decode()
    assert "mgr-kpi--money-ok" in fin_html
    assert "mgr-kpi--money-bad" in fin_html
    assert "mgr-kpi--money-accent" in fin_html
    assert "mgr-kpi--money-warn" in fin_html
    assert "mgr-finance-grid" in fin_html
    assert "mgr-finance-col" in fin_html
    assert "data-fx-switcher" in fin_html
    assert fin_html.count("data-kgs-amount=") >= 4
    for cur in ("KGS", "USD", "EUR", "KZT", "RUB"):
        assert f'data-fx-currency="{cur}"' in fin_html

    # Account page: transparency slider (60..100 step 5), currency select, and CSRF on every POST form
    acc_html = sup.get("/manager/account").data.decode()
    assert 'id="shell-alpha-slider"' in acc_html
    assert 'min="60" max="100" step="5"' in acc_html
    assert 'id="crm-currency-select"' in acc_html
    for cur in ("KGS", "USD", "EUR", "KZT", "RUB"):
        assert f'value="{cur}"' in acc_html
    post_forms = re.findall(r"<form\b[^>]*method=[\"']post[\"'][^>]*>.*?</form>", acc_html, flags=re.I | re.S)
    assert len(post_forms) >= 4
    for form_html in post_forms:
        assert 'name="csrf_token"' in form_html

    # Student workspace remains untouched by Stage 1 wrapper
    stu = _login_csrf(app.test_client(), "stu@monday.kg")
    home_html = stu.get("/home").data.decode()
    assert 'class="app-shell-panel"' not in home_html


def test_pipeline_shell_toolbar_csrf_and_rbac():
    from monday.models import Lead

    app = _make_app(csrf_enabled=True)
    mgr_id = _seed_user(app, "mgr@monday.kg", "Manager", "sales_manager")
    _seed_user(app, "sup@monday.kg", "Supervisor", "supervisor")
    _seed_user(app, "stu@monday.kg", "Student", "student")
    _seed_user(app, "tch@monday.kg", "Teacher", "teacher")

    with app.app_context():
        db.session.add(Lead(full_name="Тестовый Лид", phone="+996700111222", source="site", status="new", assigned_manager_id=mgr_id))
        db.session.commit()

    def _login_csrf(client, email, pw="StrongStaff12!"):
        pg = client.get("/login").data.decode()
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pg)
        assert m
        r = client.post("/login", data={"email": email, "password": pw, "csrf_token": m.group(1)})
        assert r.status_code == 302
        return client

    for email in ("mgr@monday.kg", "sup@monday.kg"):
        c = _login_csrf(app.test_client(), email)
        for url in ("/manager/pipeline", "/manager/pipeline?tab=clients", "/manager/pipeline?mode=students"):
            res = c.get(url)
            assert res.status_code == 200, (email, url)
            html = res.data.decode()
            assert 'class="app-shell-panel"' in html
            post_forms = re.findall(r"<form\b[^>]*method=[\"']post[\"'][^>]*>.*?</form>", html, flags=re.I | re.S)
            for form_html in post_forms:
                assert 'name="csrf_token"' in form_html

        leads_html = c.get("/manager/pipeline").data.decode()
        assert "Сделки по этапам — от первого обращения до оплаты." in leads_html
        assert "mgr-pipeline-filter" in leads_html
        assert "mgr-col--new" in leads_html

    for denied_email in ("stu@monday.kg", "tch@monday.kg"):
        c = _login_csrf(app.test_client(), denied_email)
        assert c.get("/manager/pipeline").status_code == 403
        assert c.get("/manager/pipeline?tab=clients").status_code == 403

