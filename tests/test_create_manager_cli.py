"""Tests for `flask --app app create-manager` CLI, forced first-login password change, 12-char staff policy, CSRF, rate limiting, and non-testing limiter enforcement."""
import os
import re
import tempfile

from flask_migrate import upgrade

from config import Config
from monday.extensions import db
from monday.models import AuditLog, User
from test_app import APP, client


def test_create_manager_cli_forced_password_change_session_bump_audit_and_403():
    email = "cli.sales.mgr@example.com"
    runner = APP.test_cli_runner()
    res = runner.invoke(args=["create-manager", "--email", email, "--name", "CLI Sales Manager"])
    assert res.exit_code == 0, res.output

    m = re.search(r"Password:\s+(\S+)", res.output)
    assert m is not None, res.output
    temp_pw = m.group(1)
    assert len(temp_pw) >= 16

    # Duplicate email must fail cleanly
    dup = runner.invoke(args=["create-manager", "--email", email, "--name", "Dup"])
    assert dup.exit_code != 0

    # Verify DB state & audit_logs entry
    with APP.app_context():
        u = User.query.filter_by(email=email).first()
        assert u is not None
        assert u.role == "sales_manager"
        assert u.must_change_password is True
        assert u.session_version == 1
        assert u.check_password(temp_pw)
        uid = u.id

        al = AuditLog.query.filter_by(action="manager_create", entity_type="user", entity_id=uid).first()
        assert al is not None
        assert al.new_value["email"] == email
        assert al.new_value["role"] == "sales_manager"
        assert al.new_value["must_change_password"] is True

    # Two concurrent logins with the one-time password
    c1 = client()
    r_login = c1.post("/login", data={"email": email, "password": temp_pw})
    assert r_login.status_code == 302
    assert "/change-password" in r_login.headers["Location"]

    c2 = client()
    assert c2.post("/login", data={"email": email, "password": temp_pw}).status_code == 302

    # Before changing password, accessing /manager is blocked by forced redirect to /change-password
    r_blocked = c1.get("/manager")
    assert r_blocked.status_code == 302 and "/change-password" in r_blocked.headers["Location"]

    # Submitting the same temporary password is rejected (400)
    r_same = c1.post("/change-password", data={"current": temp_pw, "new": temp_pw, "confirm": temp_pw})
    assert r_same.status_code == 400

    # Staff/manager password policy requires >= 12 chars: 11-char password must be rejected (400)
    r_short = c1.post("/change-password", data={"current": temp_pw, "new": "ShortPass11", "confirm": "ShortPass11"})
    assert r_short.status_code == 400
    assert "12" in r_short.data.decode()

    # Changing to a 12+ char password clears must_change_password, increments session_version, and revokes c2!
    new_pw = "BrandNewStrongPass!2026"
    r_chg = c1.post("/change-password", data={"current": temp_pw, "new": new_pw, "confirm": new_pw})
    assert r_chg.status_code == 302
    assert r_chg.headers["Location"].rstrip("/").endswith("/manager")

    with APP.app_context():
        u = db.session.get(User, uid)
        assert u.must_change_password is False
        assert u.session_version == 2
        assert u.check_password(new_pw) and not u.check_password(temp_pw)

    # Prior session c2 is immediately invalidated by session_version bump
    assert c2.get("/manager").status_code == 302

    # /manager/account also rejects < 12 chars for managers
    r_acc_short = c1.post(
        "/manager/account",
        data={"action": "password", "current": new_pw, "new": "Only11Chars"},
        follow_redirects=True,
    )
    assert "12" in r_acc_short.data.decode()
    with APP.app_context():
        assert db.session.get(User, uid).check_password(new_pw)

    # c1 reaches /manager (200) and receives 403 on admin & teacher routes
    assert c1.get("/manager").status_code == 200
    assert c1.get("/manager/leads").status_code == 200
    assert c1.get("/admin/").status_code == 403
    assert c1.get("/teacher/").status_code == 403
    assert c1.get("/teacher/students").status_code == 403
    assert c1.get("/home").status_code == 403


def test_rate_limiter_active_under_non_testing_config_and_change_password_csrf_and_ratelimit():
    """Verify rate limiting stays active under normal (TESTING=False) config AND /change-password enforces CSRF + rate limit."""
    tmp = tempfile.mkdtemp()

    class ProdLikeConfig(Config):
        TESTING = False
        WTF_CSRF_ENABLED = True
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_STORAGE_URI = "memory://"
        SESSION_COOKIE_SECURE = False  # allow HTTP test_client cookies
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "prodlike.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app
    app = create_app(ProdLikeConfig, seed_if_empty=False)
    with app.app_context():
        upgrade()
        res = app.test_cli_runner().invoke(
            args=["create-manager", "--email", "prod.mgr@example.com", "--name", "Prod Manager"]
        )
        assert res.exit_code == 0, res.output
        temp_pw = re.search(r"Password:\s+(\S+)", res.output).group(1)

    c = app.test_client()

    # 1. Confirm CSRF is enforced on /change-password (and /login): extract CSRF token from /login to sign in
    login_html = c.get("/login").data.decode()
    csrf_tok = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_html).group(1)
    r_in = c.post("/login", data={"csrf_token": csrf_tok, "email": "prod.mgr@example.com", "password": temp_pw})
    assert r_in.status_code == 302 and "/change-password" in r_in.headers["Location"]

    # POST /change-password WITHOUT csrf_token must be rejected (400 Bad Request from CSRFProtect)
    r_no_csrf = c.post("/change-password", data={"current": temp_pw, "new": "ValidTwelve12!", "confirm": "ValidTwelve12!"})
    assert r_no_csrf.status_code == 400

    # 2. Confirm rate limiting IS active under normal (TESTING=False) config on /change-password (5/min limit)
    cp_html = c.get("/change-password").data.decode()
    cp_csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', cp_html).group(1)
    codes_cp = [
        c.post(
            "/change-password",
            data={"csrf_token": cp_csrf, "current": "wrong-pw", "new": "ValidTwelve12!", "confirm": "ValidTwelve12!"},
        ).status_code
        for _ in range(7)
    ]
    assert 429 in codes_cp, f"Expected 429 on /change-password under non-testing config, got {codes_cp}"

    # 3. Also confirm /login rate limiting stays active under normal (TESTING=False) config (10/min limit)
    c_anon = app.test_client()
    anon_html = c_anon.get("/login").data.decode()
    anon_csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', anon_html).group(1)
    codes_login = [
        c_anon.post(
            "/login",
            data={"csrf_token": anon_csrf, "email": "nobody@example.com", "password": "bad"},
        ).status_code
        for _ in range(12)
    ]
    assert 429 in codes_login, f"Expected 429 on /login under non-testing config, got {codes_login}"
