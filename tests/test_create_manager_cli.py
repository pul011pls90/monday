"""Tests for `flask --app app create-manager` CLI, forced first-login password change, audit log, and RBAC."""
import re

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

    # Changing to a new strong password clears must_change_password, increments session_version, and revokes c2!
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

    # c1 reaches /manager (200) and receives 403 on admin & teacher routes
    assert c1.get("/manager").status_code == 200
    assert c1.get("/manager/leads").status_code == 200
    assert c1.get("/admin/").status_code == 403
    assert c1.get("/teacher/").status_code == 403
    assert c1.get("/teacher/students").status_code == 403
    assert c1.get("/home").status_code == 403
