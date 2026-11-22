"""QA & security tests for Admin role simulation and admin panel performance/safety."""
import secrets

from monday.extensions import db
from monday.models import AuditLog, User
from test_app import APP, client, login


def _mk_user(email: str, name: str, role: str, pw: str, *, blocked: bool = False) -> int:
    with APP.app_context():
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, role=role, is_approved=True, auth_provider="password")
            db.session.add(u)
        else:
            u.name = name
            u.role = role
            u.is_approved = True
            u.auth_provider = "password"
        u.is_blocked = blocked
        u.set_password(pw)
        db.session.commit()
        return u.id


def test_admin_tabs_simulation_lifecycle_and_rbac_security():
    pw_adm = secrets.token_urlsafe(12)
    pw_adm2 = secrets.token_urlsafe(12)
    pw_stu = secrets.token_urlsafe(12)
    pw_blk = secrets.token_urlsafe(12)

    adm_id = _mk_user("sim.adm1@example.com", "Sim Admin", "admin", pw_adm)
    adm2_id = _mk_user("sim.adm2@example.com", "Other Admin", "admin", pw_adm2)
    stu_id = _mk_user("sim.realstu@example.com", "Real Student", "student", pw_stu)
    blk_id = _mk_user("sim.blocked@example.com", "Blocked Student", "student", pw_blk, blocked=True)

    c_adm = login(client(), "sim.adm1@example.com", pw_adm)
    c_stu = login(client(), "sim.realstu@example.com", pw_stu)

    # 1. Non-admin cannot simulate or exit simulation
    assert c_stu.post("/admin/simulate", data={"role": "teacher"}).status_code == 403
    assert c_stu.post("/admin/simulate/exit").status_code == 403

    # 2. All admin tabs & drawer fragment render cleanly (200)
    for tab in ("overview", "apps", "moderation", "students", "teachers", "managers", "supervisors", "assistants", "admins"):
        r = c_adm.get(f"/admin/?tab={tab}")
        assert r.status_code == 200
        if tab == "overview":
            html = r.data.decode()
            assert "Симуляция ролей" in html
            for label in ("Ученик", "Учитель", "Ассистент", "Менеджер продаж", "Супервайзер"):
                assert label in html

    assert c_adm.get(f"/admin/?tab=students&user={stu_id}&fragment=1").status_code == 200

    # 3. Cannot simulate another admin or a blocked user
    r_adm_blk = c_adm.post("/admin/simulate", data={"user_id": str(adm2_id)}, follow_redirects=False)
    assert r_adm_blk.status_code == 302
    assert c_adm.get("/admin/").status_code == 200
    r_blk = c_adm.post("/admin/simulate", data={"user_id": str(blk_id)}, follow_redirects=False)
    assert r_blk.status_code == 302
    assert c_adm.get("/admin/").status_code == 200

    # 4. Simulate every role (including sandbox auto-created sales_manager & supervisor)
    expected_landing = {
        "student": "/home",
        "teacher": "/teacher/",
        "assistant": "/assistant/",
        "sales_manager": "/manager",
        "supervisor": "/manager",
    }
    for role, target_path in expected_landing.items():
        r_sim = c_adm.post("/admin/simulate", data={"role": role}, follow_redirects=False)
        assert r_sim.status_code == 302
        assert r_sim.headers["Location"].endswith(target_path)

        page = c_adm.get(target_path)
        assert page.status_code == 200
        body = page.data.decode()
        assert "Вернуться в админку" in body

        if role == "student":
            assert c_adm.get("/bank/").status_code == 200
            assert c_adm.get("/sessions").status_code == 200
        # While simulating non-admin, direct /admin/ is RBAC-enforced (403)
        assert c_adm.get("/admin/").status_code == 403

    # 5. Exit simulation cleanly restores admin session and logs audit trail
    r_exit = c_adm.post("/admin/simulate/exit", follow_redirects=False)
    assert r_exit.status_code == 302
    assert r_exit.headers["Location"].endswith("/admin/")
    back = c_adm.get("/admin/")
    assert back.status_code == 200
    assert "Вернуться в админку" not in back.data.decode()

    with APP.app_context():
        starts = AuditLog.query.filter_by(actor_id=adm_id, action="admin_simulate_start").count()
        stops = AuditLog.query.filter_by(actor_id=adm_id, action="admin_simulate_stop").count()
        assert starts >= 5
        assert stops >= 1

        # Sandbox supervisor has no polluted login_count
        sup_sim = User.query.filter_by(email="sim.supervisor@monday.kg").first() or User.query.filter_by(email="sup@monday.kg").first()
        assert sup_sim is not None and sup_sim.is_approved and not sup_sim.is_blocked

    # 6. Admin session_version invalidation revokes active simulation exit (403)
    assert c_adm.post("/admin/simulate", data={"role": "student"}).status_code == 302
    with APP.app_context():
        adm_obj = db.session.get(User, adm_id)
        adm_obj.invalidate_sessions()
        db.session.commit()
    assert c_adm.post("/admin/simulate/exit").status_code == 403

    # 7. Admin can issue & view fresh working dummy role passwords (no-store, audit logged without secret)
    assert c_stu.post("/admin/simulate/credentials", data={"role": "all"}).status_code == 403
    r_creds = c_adm_fresh = login(client(), "sim.adm1@example.com", pw_adm)
    resp_creds = r_creds.post("/admin/simulate/credentials", data={"role": "all"})
    assert resp_creds.status_code == 200
    assert "no-store" in resp_creds.headers.get("Cache-Control", "")
    creds_html = resp_creds.data.decode()
    import re
    matches = re.findall(r"<code>([^<]+)</code>\s*</td>\s*<td[^>]*>\s*<code>([^<]+)</code>", creds_html)
    assert len(matches) == 5
    creds_by_email = dict(matches)
    with APP.app_context():
        issue_logs = AuditLog.query.filter_by(actor_id=adm_id, action="admin_dummy_password_issue").all()
        assert len(issue_logs) >= 5
        for pw_val in creds_by_email.values():
            assert len(pw_val) >= 12
            for il in issue_logs:
                assert pw_val not in str(il.new_value)

    # Issued dummy credentials use dedicated sandbox accounts (never breaking seeded accounts) & log in via /login
    assert "sim.student@monday.kg" in creds_by_email
    assert "sim.supervisor@monday.kg" in creds_by_email
    c_sup_pw = login(client(), "sim.supervisor@monday.kg", creds_by_email["sim.supervisor@monday.kg"])
    assert c_sup_pw.get("/manager").status_code == 200

    # 8. CSRF enforcement on simulation & credential endpoints
    prev_csrf = APP.config.get("WTF_CSRF_ENABLED", False)
    APP.config["WTF_CSRF_ENABLED"] = True
    try:
        assert c_adm_fresh.post("/admin/simulate", data={"role": "student"}).status_code == 400
        assert c_adm_fresh.post("/admin/simulate/credentials", data={"role": "all"}).status_code == 400
    finally:
        APP.config["WTF_CSRF_ENABLED"] = prev_csrf
