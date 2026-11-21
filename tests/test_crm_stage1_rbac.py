"""Stage 1 RBAC foundation tests: roles, permission map, landing routes, and 403 isolation."""
from monday.access import PERMISSIONS, ROLES, has_permission
from monday.extensions import db
from monday.models import User
from test_app import APP, client, login


def _ensure_user(email: str, name: str, role: str, password: str = "Pass12345", *, is_approved: bool = True, is_blocked: bool = False):
    with APP.app_context():
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(email=email, name=name, role=role, is_approved=is_approved, is_blocked=is_blocked)
            u.set_password(password)
            db.session.add(u)
        else:
            u.role = role
            u.is_approved = is_approved
            u.is_blocked = is_blocked
            u.set_password(password)
        db.session.commit()
        return u.id


def test_stage1_permission_map_covers_all_roles():
    uid_stu = _ensure_user("rbac.stu@example.com", "RBAC Student", "student")
    uid_tch = _ensure_user("rbac.tch@example.com", "RBAC Teacher", "teacher")
    uid_tch_un = _ensure_user("rbac.tch.un@example.com", "Unapproved Teacher", "teacher", is_approved=False)
    uid_ast = _ensure_user("rbac.ast@example.com", "RBAC Assistant", "assistant")
    uid_mgr = _ensure_user("rbac.mgr@example.com", "RBAC Manager", "sales_manager")
    uid_sup = _ensure_user("rbac.sup@example.com", "RBAC Supervisor", "supervisor")
    uid_adm = _ensure_user("rbac.adm@example.com", "RBAC Admin", "admin")
    uid_blk = _ensure_user("rbac.blk@example.com", "Blocked Manager", "sales_manager", is_blocked=True)

    assert set(ROLES) == {"student", "teacher", "assistant", "sales_manager", "supervisor", "admin"}
    assert "crm.access" in PERMISSIONS and "crm.audit.view" in PERMISSIONS

    with APP.app_context():
        stu = db.session.get(User, uid_stu)
        tch = db.session.get(User, uid_tch)
        tch_un = db.session.get(User, uid_tch_un)
        ast = db.session.get(User, uid_ast)
        mgr = db.session.get(User, uid_mgr)
        sup = db.session.get(User, uid_sup)
        adm = db.session.get(User, uid_adm)
        blk = db.session.get(User, uid_blk)

        # Sales Manager permissions
        assert mgr.is_sales_manager and mgr.is_manager and not mgr.is_crm_supervisor
        assert mgr.has_perm("crm.access")
        assert mgr.has_perm("crm.leads.view_own")
        assert mgr.has_perm("crm.leads.convert")
        assert mgr.has_perm("academic.schedule.read")
        assert mgr.has_perm("academic.attendance.read")
        assert not mgr.has_perm("crm.leads.view_all")
        assert not mgr.has_perm("crm.leads.reassign")
        assert not mgr.has_perm("crm.audit.view")
        assert not mgr.has_perm("academic.attendance.mark")
        assert not mgr.has_perm("admin.manage")

        # Supervisor permissions
        assert sup.is_supervisor and sup.is_manager and sup.is_crm_supervisor
        assert sup.has_perm("crm.access")
        assert sup.has_perm("crm.leads.view_all")
        assert sup.has_perm("crm.leads.reassign")
        assert sup.has_perm("crm.leads.delete")
        assert sup.has_perm("crm.audit.view")
        assert sup.has_perm("academic.schedule.manage")
        assert sup.has_perm("academic.attendance.edit_retro")
        assert not sup.has_perm("admin.manage")
        assert not sup.has_perm("admin.roles.change")

        # Content assistant stays strictly isolated from CRM
        assert ast.is_assistant and not ast.is_manager
        assert ast.has_perm("assistant.workspace")
        assert not ast.has_perm("crm.access")
        assert not ast.has_perm("crm.audit.view")

        # Teacher, Student, Blocked, Unapproved
        assert not tch.has_perm("crm.access")
        assert tch.has_perm("academic.attendance.mark")
        assert not tch_un.has_perm("teacher.workspace")
        assert not stu.has_perm("crm.access")
        assert not blk.has_perm("crm.access")
        assert has_permission(None, "crm.access") is False

        # Admin has full CRM + Supervisor + Admin permissions
        assert adm.is_admin and adm.is_manager and adm.is_crm_supervisor
        assert adm.has_perm("crm.access") and adm.has_perm("crm.audit.view") and adm.has_perm("admin.manage")


def test_stage1_manager_and_supervisor_login_land_on_manager():
    _ensure_user("mgr.land@example.com", "Sales Manager", "sales_manager", "MgrPass123")
    _ensure_user("sup.land@example.com", "Supervisor", "supervisor", "SupPass123")

    c_mgr = client()
    r_mgr = c_mgr.post("/login", data={"email": "mgr.land@example.com", "password": "MgrPass123"})
    assert r_mgr.status_code == 302
    assert r_mgr.headers["Location"].rstrip("/").endswith("/manager")
    assert c_mgr.get("/").headers["Location"].rstrip("/").endswith("/manager")
    assert c_mgr.get("/manager").status_code == 200

    c_sup = client()
    r_sup = c_sup.post("/login", data={"email": "sup.land@example.com", "password": "SupPass123"})
    assert r_sup.status_code == 302
    assert r_sup.headers["Location"].rstrip("/").endswith("/manager")
    assert c_sup.get("/manager").status_code == 200
    assert c_sup.get("/manager/audit").status_code == 200


def test_stage1_strict_403_role_isolation():
    _ensure_user("iso.mgr@example.com", "Sales Manager", "sales_manager", "Pass12345")
    _ensure_user("iso.sup@example.com", "Supervisor", "supervisor", "Pass12345")
    _ensure_user("iso.ast@example.com", "Content Assistant", "assistant", "Pass12345")

    anon = client()
    stu = login(client(), "student@monday.kg", "student123")
    tch = login(client(), "aibek@monday.kg", "teacher123")
    ast = login(client(), "iso.ast@example.com", "Pass12345")
    mgr = login(client(), "iso.mgr@example.com", "Pass12345")
    sup = login(client(), "iso.sup@example.com", "Pass12345")
    adm = login(client(), "admin@monday.kg", "monday2026")

    # Anonymous -> 302 to login
    assert anon.get("/manager").status_code == 302
    assert anon.get("/manager/audit").status_code == 302

    # Non-CRM roles -> 403 on /manager and /manager/audit
    for c in (stu, tch, ast):
        assert c.get("/manager").status_code == 403
        assert c.get("/manager/audit").status_code == 403

    # Sales Manager -> 200 on /manager; 403 on supervisor audit, student, teacher, assistant, admin routes
    assert mgr.get("/manager").status_code == 200
    assert mgr.get("/manager/audit").status_code == 403
    assert mgr.get("/home").status_code == 403
    assert mgr.get("/homework").status_code == 403
    assert mgr.get("/teacher/").status_code == 403
    assert mgr.get("/teacher/students").status_code == 403
    assert mgr.get("/assistant/").status_code == 403
    assert mgr.get("/admin/").status_code == 403

    # Supervisor -> 200 on /manager & /manager/audit; 403 on student, teacher, assistant, admin routes
    assert sup.get("/manager").status_code == 200
    assert sup.get("/manager/audit").status_code == 200
    assert sup.get("/home").status_code == 403
    assert sup.get("/teacher/").status_code == 403
    assert sup.get("/assistant/").status_code == 403
    assert sup.get("/admin/").status_code == 403

    # Admin -> 200 on /manager, /manager/audit, /admin/, /teacher/
    assert adm.get("/manager").status_code == 200
    assert adm.get("/manager/audit").status_code == 200
    assert adm.get("/admin/").status_code == 200
    assert adm.get("/admin/?tab=managers").status_code == 200
    assert adm.get("/admin/?tab=supervisors").status_code == 200


def test_stage1_admin_can_assign_manager_and_supervisor_roles():
    uid = _ensure_user("promote.me@example.com", "Promote User", "student", "Pass12345")
    adm = login(client(), "admin@monday.kg", "monday2026")

    r1 = adm.post(f"/admin/users/{uid}/role", data={"role": "sales_manager"})
    assert r1.status_code == 302
    with APP.app_context():
        assert db.session.get(User, uid).role == "sales_manager"
    assert adm.get(f"/admin/?tab=managers&user={uid}").status_code == 200

    r2 = adm.post(f"/admin/users/{uid}/role", data={"role": "supervisor"})
    assert r2.status_code == 302
    with APP.app_context():
        assert db.session.get(User, uid).role == "supervisor"
    assert adm.get(f"/admin/?tab=supervisors&user={uid}").status_code == 200
