"""Targeted security & migration tests for all 5 P0 blockers."""
import base64
import io
import json
import os
import tempfile
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import inspect as sa_inspect

from config import Config
from monday import auth
from monday.extensions import db
from monday.models import (
    Attempt,
    AttemptAnswer,
    INVITE_ALPHABET,
    INVITE_CODE_LEN,
    Question,
    ReferenceSheet,
    SheetEntry,
    StudentProfile,
    StudentRecord,
    User,
    Work,
    new_invite_code,
    utcnow,
)
from test_app import APP, client, login

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\x8d\xf1\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_fake_id_token(claims: dict) -> str:
    hdr = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    pay = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{hdr}.{pay}.fakesig"


# --------------------------------------------------------------------------- P0-1: Dangerous startup scripts


def test_p0_1_startup_fixes_do_not_create_backdoor_or_delete_teachers():
    tmp = tempfile.mkdtemp()

    class ProdLikeConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = True
        IMPORT_PACKS = False
        ADMIN_EMAIL = "prod.admin@example.com"
        ADMIN_PASSWORD = "StrongProdPassword!1"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "prod.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    from monday.cleanup import ensure_showcase_student, remove_extra_teachers, run_fixes

    app = create_app(ProdLikeConfig)
    with app.app_context():
        # Showcase student MUST NOT be created when SEED_DEMO=False even if DATA_FIXES=True
        assert User.query.filter_by(email="student@monday.kg").first() is None

        # Create two real teachers and re-run run_fixes() — neither may be deleted
        t1 = User(email="t1@school.edu", name="Teacher One", role="teacher", is_approved=True)
        t2 = User(email="t2@school.edu", name="Teacher Two", role="teacher", is_approved=True)
        t1.set_password("TeacherPass1!")
        t2.set_password("TeacherPass2!")
        db.session.add_all([t1, t2])
        db.session.commit()

        run_fixes()
        assert User.query.filter_by(role="teacher").count() == 2
        assert User.query.filter_by(email="student@monday.kg").first() is None

        # Direct calls must refuse to run when SEED_DEMO=False
        with pytest.raises(RuntimeError):
            ensure_showcase_student()
        with pytest.raises(RuntimeError):
            remove_extra_teachers()


def test_p0_1_render_production_yaml_disables_data_fixes_and_runs_migrations():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "render.production.yaml"), encoding="utf-8") as f:
        text = f.read()
    assert "key: DATA_FIXES" in text
    assert "preDeployCommand: flask --app app db upgrade" in text


# --------------------------------------------------------------------------- P0-2: Alembic / Flask-Migrate


def test_p0_2_alembic_upgrade_downgrade_and_no_silent_create_all():
    from flask_migrate import downgrade, upgrade
    from monday import MIGRATIONS_DIR, create_app

    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "mig_check.db")

    class FreshNonTestingConfig(Config):
        TESTING = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + db_path
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    # Non-testing startup on empty DB must NOT silently run db.create_all()
    app = create_app(FreshNonTestingConfig, seed_if_empty=False)
    with app.app_context():
        assert not sa_inspect(db.engine).has_table("user")

        # Running Alembic upgrade builds all tables including P0 security columns
        upgrade(directory=MIGRATIONS_DIR)
        insp = sa_inspect(db.engine)
        tables = set(insp.get_table_names())
        assert {"alembic_version", "user", "student_record", "visit", "activity_draft", "course_unit", "roadmap_node"}.issubset(tables)
        user_cols = {c["name"] for c in insp.get_columns("user")}
        sr_cols = {c["name"] for c in insp.get_columns("student_record")}
        assert "google_sub" in user_cols
        assert {"invite_expires_at", "invite_revoked_at"}.issubset(sr_cols)

        # Downgrading the P0 revision and re-upgrading works cleanly
        downgrade(directory=MIGRATIONS_DIR, revision="868bb7177ced")
        assert "google_sub" not in {c["name"] for c in sa_inspect(db.engine).get_columns("user")}
        upgrade(directory=MIGRATIONS_DIR)
        assert "google_sub" in {c["name"] for c in sa_inspect(db.engine).get_columns("user")}


# --------------------------------------------------------------------------- P0-3: File IDOR (/uploads/)


def test_p0_3_uploads_idor_enforced_for_solutions_sheets_avatars_drafts_and_packs():
    from monday.images import store_image

    c_owner = login(client(), "student@monday.kg", "student123")
    c_other = login(client(), "student1@monday.kg", "student123")
    c_linked_teacher = login(client(), "aibek@monday.kg", "teacher123")
    c_other_teacher = login(client(), "nurai@monday.kg", "teacher123")
    c_admin = login(client(), "admin@monday.kg", "monday2026")

    with APP.app_context():
        owner = User.query.filter_by(email="student@monday.kg").first()
        other = User.query.filter_by(email="student1@monday.kg").first()
        aibek = User.query.filter_by(email="aibek@monday.kg").first()
        nurai = User.query.filter_by(email="nurai@monday.kg").first()
        assert StudentRecord.query.filter_by(teacher_id=aibek.id, student_user_id=owner.id).first() is not None
        assert StudentRecord.query.filter_by(teacher_id=nurai.id, student_user_id=owner.id).first() is None

        # 1. Written solution photo
        att = Attempt(user_id=owner.id, mode="collection", total=1, score=0)
        db.session.add(att)
        db.session.flush()
        sol_name = store_image(
            type("U", (), {"filename": "sol.png", "stream": io.BytesIO(PNG)})(),
            f"solutions/a{att.id}_0_abcdef123456",
            kind="photo",
        )
        ans = AttemptAnswer(attempt_id=att.id, index=0, photo_path=sol_name)
        db.session.add(ans)

        # 2. Formula sheet image
        sheet = ReferenceSheet(user_id=owner.id, title="Private Sheet", exam="ORT")
        db.session.add(sheet)
        db.session.flush()
        sheet_img = store_image(
            type("U", (), {"filename": "f.png", "stream": io.BytesIO(PNG)})(),
            f"sheet-{owner.id}-1234567890",
            kind="figure",
        )
        entry = SheetEntry(sheet_id=sheet.id, topic="Alg", image_path=sheet_img, formula="$x=1$")
        db.session.add(entry)

        # 3. Avatar image
        av_name = store_image(
            type("U", (), {"filename": "a.png", "stream": io.BytesIO(PNG)})(),
            f"avatar-{owner.id}-deadbeef",
            kind="avatar",
        )
        old_av = owner.avatar_path
        owner.avatar_path = av_name

        # 4. Draft question figure authored by aibek
        draft_img = store_image(
            type("U", (), {"filename": "q.png", "stream": io.BytesIO(PNG)})(),
            "q-drafttest1234",
            kind="figure",
        )
        draft_q = Question(
            author_id=aibek.id, text="Draft?", answer_type="number", correct="1", status="draft", image_path=draft_img
        )
        db.session.add(draft_q)
        db.session.commit()
        att_id, sheet_id, draft_q_id = att.id, sheet.id, draft_q.id

    try:
        # Solution photo: owner, linked teacher, admin allowed; other student & unlinked teacher blocked (403)
        assert c_owner.get(f"/uploads/{sol_name}").status_code == 200
        assert c_linked_teacher.get(f"/uploads/{sol_name}").status_code == 200
        assert c_admin.get(f"/uploads/{sol_name}").status_code == 200
        assert c_other.get(f"/uploads/{sol_name}").status_code == 403
        assert c_other_teacher.get(f"/uploads/{sol_name}").status_code == 403

        # Formula sheet image: owner & admin allowed; other student & teachers blocked (403)
        assert c_owner.get(f"/uploads/{sheet_img}").status_code == 200
        assert c_admin.get(f"/uploads/{sheet_img}").status_code == 200
        assert c_other.get(f"/uploads/{sheet_img}").status_code == 403
        assert c_linked_teacher.get(f"/uploads/{sheet_img}").status_code == 403

        # Avatar: owner, linked teacher, admin allowed; unrelated student & unlinked teacher blocked (403)
        assert c_owner.get(f"/uploads/{av_name}").status_code == 200
        assert c_linked_teacher.get(f"/uploads/{av_name}").status_code == 200
        assert c_admin.get(f"/uploads/{av_name}").status_code == 200
        assert c_other.get(f"/uploads/{av_name}").status_code == 403
        assert c_other_teacher.get(f"/uploads/{av_name}").status_code == 403

        # Draft question figure: author & admin allowed; students & other teachers blocked (403)
        assert c_linked_teacher.get(f"/uploads/{draft_img}").status_code == 200
        assert c_admin.get(f"/uploads/{draft_img}").status_code == 200
        assert c_owner.get(f"/uploads/{draft_img}").status_code == 403
        assert c_other_teacher.get(f"/uploads/{draft_img}").status_code == 403

        # Pack whitelist & traversal
        assert c_owner.get("/uploads/packs/nonexistent_pack/fig.png").status_code == 404
        assert c_owner.get("/uploads/packs/../config.py").status_code == 404
    finally:
        with APP.app_context():
            owner = User.query.filter_by(email="student@monday.kg").first()
            owner.avatar_path = old_av
            for model, pk in ((Attempt, att_id), (ReferenceSheet, sheet_id), (Question, draft_q_id)):
                obj = db.session.get(model, pk)
                if obj:
                    db.session.delete(obj)
            db.session.commit()


# --------------------------------------------------------------------------- P0-4: Hardened Student Invite Codes


def test_p0_4_invite_code_entropy_expiry_revocation_no_oracle_and_delete_invalidation():
    # 1. Entropy >= 60 bits (12 chars from 32-char alphabet)
    with APP.app_context():
        code = new_invite_code()
        assert code.startswith("MND-")
        body = code[4:]
        assert len(body) == INVITE_CODE_LEN >= 10
        assert all(ch in INVITE_ALPHABET for ch in body)

    # 2. Teacher creates student -> valid code has expiry
    t = login(client(), "aibek@monday.kg", "teacher123")
    r = t.post("/teacher/students/new", data={"name": "Инвайт Тест", "grade": "11", "exam": "ORT"})
    assert r.status_code == 302
    rid = int(r.headers["Location"].rstrip("/").split("/")[-1])

    with APP.app_context():
        rec = db.session.get(StudentRecord, rid)
        valid_code = rec.invite_code
        assert valid_code and len(valid_code) == 4 + INVITE_CODE_LEN
        assert rec.invite_expires_at is not None and rec.invite_is_active

    # 3. Unauthenticated /join/<code> must NOT disclose validity or teacher name
    c_valid = client()
    r_valid = c_valid.get(f"/join/{valid_code}", follow_redirects=False)
    c_bad = client()
    r_bad = c_bad.get("/join/MND-NOTAREALCODE1", follow_redirects=False)
    assert r_valid.status_code == 302 and r_bad.status_code == 302
    assert r_valid.headers["Location"] == r_bad.headers["Location"]
    assert "/register" in r_valid.headers["Location"]
    assert "Айбек" not in c_valid.get("/register").data.decode()

    # 4. Expired code is rejected
    with APP.app_context():
        rec = db.session.get(StudentRecord, rid)
        rec.invite_expires_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
    stu_c = login(client(), "student2@monday.kg", "student123")
    r_exp = stu_c.post("/profile", data={"action": "join", "invite_code": valid_code}, follow_redirects=True)
    assert "Такого кода нет" in r_exp.data.decode()

    # 5. Teacher revokes code -> code is cleared and rejected; rotating creates a fresh active code
    with APP.app_context():
        rec = db.session.get(StudentRecord, rid)
        rec.invite_expires_at = utcnow() + timedelta(days=7)
        db.session.commit()
    assert t.post(f"/teacher/students/{rid}/code/revoke").status_code == 302
    with APP.app_context():
        rec = db.session.get(StudentRecord, rid)
        assert rec.invite_code is None and rec.invite_revoked_at is not None and not rec.invite_is_active
    r_rev = stu_c.post("/profile", data={"action": "join", "invite_code": valid_code}, follow_redirects=True)
    assert "Такого кода нет" in r_rev.data.decode()

    assert t.post(f"/teacher/students/{rid}/code").status_code == 302
    with APP.app_context():
        rec = db.session.get(StudentRecord, rid)
        fresh_code = rec.invite_code
        assert fresh_code and fresh_code != valid_code and rec.invite_is_active

    # 6. Register student with fresh code, then delete account -> old code is revoked & cannot be reused
    c_del = client()
    r_reg = c_del.post(
        "/register",
        data={
            "name": "Удалится Скоро",
            "email": "temp.del.invite@example.com",
            "password": "StrongPassword123",
            "role": "student",
            "invite_code": fresh_code,
        },
    )
    assert r_reg.status_code == 302
    c_del.post("/onboarding", data={"exam": "ORT", "name": "Удалится Скоро", "grade": "11"})
    with APP.app_context():
        rec = db.session.get(StudentRecord, rid)
        assert rec.student is not None and rec.student.email == "temp.del.invite@example.com"

    c_del.post("/profile", data={"action": "delete", "password": "StrongPassword123"})
    with APP.app_context():
        rec = db.session.get(StudentRecord, rid)
        assert rec.student_user_id is None
        assert rec.invite_code is None
        assert rec.invite_revoked_at is not None

    r_reuse = stu_c.post("/profile", data={"action": "join", "invite_code": fresh_code}, follow_redirects=True)
    assert "Такого кода нет" in r_reuse.data.decode()

    t.post(f"/teacher/students/{rid}/delete")


# --------------------------------------------------------------------------- P0-5: Google OAuth Binding


def test_p0_5_google_oauth_binds_by_sub_blocks_staff_validates_pkce_oidc_and_no_forced_remember(monkeypatch):
    person = {"sub": "oidc-sub-unique-1", "email": "oauth.student@gmail.com", "email_verified": True, "name": "OAuth Student"}
    token_extra = {}
    captured = {}

    def post(url, fields):
        captured["fields"] = dict(fields)
        out = {"access_token": "tok-abc"}
        if token_extra.get("id_token") is not None:
            out["id_token"] = token_extra["id_token"]
        return out

    def get(url, token):
        return dict(person)

    monkeypatch.setattr(auth, "_google_post", post)
    monkeypatch.setattr(auth, "_google_get", get)
    monkeypatch.setitem(APP.config, "GOOGLE_CLIENT_ID", "cid-p0")
    monkeypatch.setitem(APP.config, "GOOGLE_CLIENT_SECRET", "csec-p0")

    def run_oauth(c):
        r1 = c.get("/login/google")
        assert r1.status_code == 302
        q = parse_qs(urlparse(r1.headers["Location"]).query)
        assert q.get("code_challenge") and q.get("code_challenge_method") == ["S256"] and q.get("nonce")
        if token_extra.get("auto_id_token"):
            token_extra["id_token"] = _make_fake_id_token({
                "iss": "https://accounts.google.com",
                "aud": "cid-p0",
                "sub": person["sub"],
                "email": person["email"],
                "email_verified": person["email_verified"],
                "nonce": token_extra.get("force_nonce", q["nonce"][0]),
                "exp": int(time.time()) + 300,
            })
        r2 = c.get(f"/login/google/callback?state={q['state'][0]}&code=auth-code")
        return r2, q

    # 1. Valid OIDC id_token + PKCE creates student, binds google_sub, and does NOT set remember_token cookie
    token_extra["auto_id_token"] = True
    c1 = client()
    r, q = run_oauth(c1)
    assert r.status_code == 302 and "/onboarding" in r.headers["Location"]
    assert auth._pkce_challenge(captured["fields"]["code_verifier"]) == q["code_challenge"][0]
    set_cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "remember_token=" not in set_cookies

    with APP.app_context():
        u = User.query.filter_by(google_sub="oidc-sub-unique-1").first()
        assert u is not None and u.email == "oauth.student@gmail.com"
        uid = u.id
        # Change the student's email in Monday — subsequent login with same google_sub must still bind to same user
        u.email = "renamed.student@example.com"
        u.profile.onboarded = True
        u.profile.exam = "ORT"
        db.session.commit()

    c2 = client()
    r2, _ = run_oauth(c2)
    assert r2.status_code == 302 and r2.headers["Location"].endswith("/home")
    with APP.app_context():
        assert User.query.filter_by(google_sub="oidc-sub-unique-1").count() == 1
        assert User.query.filter_by(google_sub="oidc-sub-unique-1").first().id == uid

    # 2. Bad OIDC nonce is rejected
    token_extra["force_nonce"] = "wrong-nonce"
    c_bad_nonce = client()
    r_bn, _ = run_oauth(c_bad_nonce)
    assert r_bn.headers["Location"].endswith("/login")
    assert c_bad_nonce.get("/home").status_code == 302
    token_extra.pop("force_nonce", None)

    # 3. Silent email-linking into existing staff/admin accounts MUST be blocked
    for staff_email, sub_val in (
        ("admin@monday.kg", "oidc-sub-attack-admin"),
        ("aibek@monday.kg", "oidc-sub-attack-teacher"),
        ("assistant@monday.kg", "oidc-sub-attack-assistant"),
    ):
        person.update(sub=sub_val, email=staff_email, email_verified=True)
        c_atk = client()
        r_atk, _ = run_oauth(c_atk)
        assert r_atk.headers["Location"].endswith("/login")
        assert c_atk.get("/admin/").status_code == 302
        assert c_atk.get("/teacher/").status_code == 302
        with APP.app_context():
            staff_u = User.query.filter_by(email=staff_email).first()
            assert staff_u.google_sub is None and staff_u.auth_provider == "password"
