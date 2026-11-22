"""Stage 1 tests: student_links service layer, RBAC, audit safety, partial unique constraint, and Postgres round-trip."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from datetime import timedelta

import pytest
from flask_migrate import upgrade as alembic_upgrade, downgrade as alembic_downgrade
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from monday import create_app
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    AuditLog,
    Lead,
    StudentRecord,
    TeacherAssignment,
    User,
    utcnow,
)
from monday.student_links import (
    StudentLinkConflictError,
    StudentLinkPermissionError,
    StudentLinkValidationError,
    assign_teacher,
    change_teacher,
    claim_code,
    create_student_with_code,
    regenerate_code,
    revoke_code,
)


def _fresh_sqlite_app(tmp_path):
    class Cfg:
        TESTING = True
        SECRET_KEY = "test-stage1-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'stage1.db'}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        SQLALCHEMY_ENGINE_OPTIONS = {}
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        LANGUAGES = ["ru", "en", "ky"]
        BABEL_DEFAULT_LOCALE = "ru"
        INVITE_CODE_TTL_DAYS = 14
        SEED_DEMO = True

    app = create_app(Cfg, seed_if_empty=False)
    with app.app_context():
        db.create_all()
        admin = User(email="admin@t.kg", name="Admin", role="admin", is_approved=True)
        admin.set_password("StrongAdminPass12!")
        mgr = User(email="mgr@t.kg", name="Manager", role="sales_manager", is_approved=True)
        mgr.set_password("StrongManagerPass12!")
        t1 = User(email="t1@t.kg", name="Teacher One", role="teacher", is_approved=True)
        t1.set_password("StrongTeacherPass12!")
        t2 = User(email="t2@t.kg", name="Teacher Two", role="teacher", is_approved=True)
        t2.set_password("StrongTeacherPass12!")
        t_pending = User(email="tp@t.kg", name="Unapproved Teacher", role="teacher", is_approved=False)
        t_pending.set_password("StrongTeacherPass12!")
        t_blocked = User(email="tb@t.kg", name="Blocked Teacher", role="teacher", is_approved=True, is_blocked=True)
        t_blocked.set_password("StrongTeacherPass12!")
        stu = User(email="s1@t.kg", name="Student One", role="student", is_approved=True)
        stu.set_password("StudentPass12")
        course1 = AcademicCourse(code="SAT_M", name="SAT Math", exam="SAT", is_active=True)
        course2 = AcademicCourse(code="ORT_M", name="ORT Math", exam="ORT", is_active=True)
        lead = Lead(full_name="Lead Student", phone="+996555000111", source="instagram", status="qualified")
        db.session.add_all([admin, mgr, t1, t2, t_pending, t_blocked, stu, course1, course2, lead])
        db.session.commit()
    return app


def test_student_links_lifecycle_rbac_and_audit(tmp_path):
    app = _fresh_sqlite_app(tmp_path)
    with app.app_context():
        mgr = User.query.filter_by(email="mgr@t.kg").one()
        t1 = User.query.filter_by(email="t1@t.kg").one()
        t2 = User.query.filter_by(email="t2@t.kg").one()
        t_pending = User.query.filter_by(email="tp@t.kg").one()
        t_blocked = User.query.filter_by(email="tb@t.kg").one()
        stu = User.query.filter_by(email="s1@t.kg").one()
        course1 = AcademicCourse.query.filter_by(code="SAT_M").one()
        course2 = AcademicCourse.query.filter_by(code="ORT_M").one()
        lead = Lead.query.first()

        # RBAC: student or teacher cannot create manager-issued student records
        with pytest.raises(StudentLinkPermissionError):
            create_student_with_code(stu, "Ученик", "+996555111222", None, t1.id, course1.id)
        with pytest.raises(StudentLinkPermissionError):
            create_student_with_code(t1, "Ученик", "+996555111222", None, t1.id, course1.id)

        # Inactive/unapproved/blocked teacher rejected
        with pytest.raises(StudentLinkValidationError):
            create_student_with_code(mgr, "Ученик", "+996555111222", None, t_pending.id, course1.id)
        with pytest.raises(StudentLinkValidationError):
            create_student_with_code(mgr, "Ученик", "+996555111222", None, t_blocked.id, course1.id)

        # Create student record with connection code
        rec, code1 = create_student_with_code(
            mgr,
            "Алихан Тест",
            "0555 223 344",
            "alihan@example.com",
            t1.id,
            course1.id,
            lead_id=lead.id,
        )
        assert rec.id is not None
        assert rec.teacher_id == t1.id
        assert rec.created_by_user_id == mgr.id
        assert rec.source_lead_id == lead.id
        assert rec.course_id == course1.id
        assert rec.phone == "+996555223344"
        assert rec.email == "alihan@example.com"
        assert rec.exam == "SAT"
        assert rec.code_status == "pending"
        assert rec.code_status_label == "Ожидает"
        assert code1.startswith("MND-") and len(code1) == 16

        # Derived expired state
        rec.invite_expires_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
        assert rec.code_status == "expired"
        assert rec.code_status_label == "Истёк"

        # Regenerate code -> invalidates old code and resets status to pending
        rec, code2 = regenerate_code(mgr, rec.id)
        assert code2 != code1
        assert rec.code_status == "pending"
        ok_old, _ = claim_code(stu, code1)
        assert ok_old is False

        # Revoke code -> status Отозван
        rec = revoke_code(mgr, rec.id, reason="Ошибка номера")
        assert rec.invite_code is None
        assert rec.code_status == "revoked"
        assert rec.code_status_label == "Отозван"

        # Regenerate again and claim as student
        rec, code3 = regenerate_code(mgr, rec.id)
        ok_claim, msg = claim_code(stu, code3)
        assert ok_claim is True
        assert t1.name in msg
        db.session.refresh(rec)
        assert rec.student_user_id == stu.id
        assert rec.claimed_by_user_id == stu.id
        assert rec.claimed_at is not None
        assert rec.code_status == "claimed"
        assert rec.code_status_label == "Привязан"

        # Claiming a used code a second time fails (one-time)
        ok_again, _ = claim_code(stu, code3)
        assert ok_again is False
        with pytest.raises(StudentLinkConflictError):
            regenerate_code(mgr, rec.id)

        # Change teacher atomically preserves history and updates legacy teacher_id
        with pytest.raises(StudentLinkPermissionError):
            change_teacher(t1, rec.id, t2.id, course1.id, "Попытка без прав")

        new_ta = change_teacher(mgr, rec.id, t2.id, course1.id, "Смена расписания")
        db.session.refresh(rec)
        assert rec.teacher_id == t2.id
        assert new_ta.teacher_user_id == t2.id
        assert new_ta.ended_at is None
        history = TeacherAssignment.query.filter_by(
            student_record_id=rec.id, course_id=course1.id
        ).order_by(TeacherAssignment.id.asc()).all()
        assert len(history) == 2
        assert history[0].teacher_user_id == t1.id
        assert history[0].ended_at is not None
        assert history[0].ended_by_id == mgr.id
        assert history[1].teacher_user_id == t2.id
        assert history[1].ended_at is None
        assert history[1].change_reason == "Смена расписания"

        # Assign separate teacher for a second course on same record
        ta_c2 = assign_teacher(mgr, rec.id, t1.id, course2.id, "Второй предмет")
        assert ta_c2.course_id == course2.id
        assert (
            TeacherAssignment.query.filter_by(student_record_id=rec.id, ended_at=None).count() == 2
        )

        # Partial unique constraint blocks duplicate open assignment even for course_id IS NULL
        ta_null = assign_teacher(mgr, rec.id, t1.id, None, "Кураторство")
        assert ta_null.course_id is None
        with pytest.raises(IntegrityError):
            db.session.add(
                TeacherAssignment(
                    student_record_id=rec.id,
                    teacher_user_id=t2.id,
                    course_id=None,
                    assigned_by_id=mgr.id,
                )
            )
            db.session.commit()
        db.session.rollback()

        # Security check: NO full code ever appears in any AuditLog entry
        all_audits = AuditLog.query.all()
        actions = {a.action for a in all_audits}
        assert {
            "student_code_created",
            "student_code_regenerated",
            "student_code_revoked",
            "student_code_claimed",
            "teacher_assigned",
            "teacher_changed",
        }.issubset(actions)
        serialized = json.dumps(
            [{"old": a.old_value, "new": a.new_value, "reason": a.reason} for a in all_audits],
            ensure_ascii=False,
        )
        for secret_code in (code1, code2, code3):
            assert secret_code not in serialized
            assert secret_code[-4:] in serialized


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.skipif(shutil.which("initdb") is None or shutil.which("pg_ctl") is None, reason="Local PostgreSQL tools not installed")
def test_postgres_alembic_roundtrip_zero_drift_and_concurrent_change_teacher():
    """Spin up a throwaway Postgres instance, seed before migration, test upgrade->downgrade->upgrade, flask db check, and concurrency."""
    # Keep Unix socket directory short (<104 bytes on macOS).
    pgroot = tempfile.mkdtemp(prefix="pg_s1_", dir="/tmp")
    pgdata = os.path.join(pgroot, "pgdata")
    pglog = os.path.join(pgroot, "pg.log")
    port = _free_port()
    env = {**os.environ, "LC_ALL": "C"}

    subprocess.run(
        ["initdb", "-D", pgdata, "-U", "postgres", "-A", "trust", "--encoding=UTF8"],
        check=True,
        capture_output=True,
        env=env,
    )
    start_res = subprocess.run(
        ["pg_ctl", "-D", pgdata, "-o", f"-p {port} -k {pgroot}", "-l", pglog, "start"],
        capture_output=True,
        text=True,
        env=env,
    )
    if start_res.returncode != 0:
        with open(pglog, "r", encoding="utf-8", errors="replace") as f:
            raise AssertionError(f"pg_ctl start failed: {start_res.stderr}\nLOG:\n{f.read()}")

    try:
        subprocess.run(
            ["createdb", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "monday_test"],
            check=True,
            capture_output=True,
            env=env,
        )
        pg_url = f"postgresql+psycopg://postgres@127.0.0.1:{port}/monday_test"
        flask_bin = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".venv/bin/flask")
        if not os.path.exists(flask_bin):
            flask_bin = "/Users/apple/Desktop/Monday/venv/bin/flask"
        repo_root = os.path.dirname(os.path.dirname(__file__))
        pg_env = {**os.environ, "DATABASE_URL": pg_url, "LC_ALL": "C"}

        # 1. Upgrade throwaway Postgres to previous head (b7e2f4a9c102) via CLI
        subprocess.run(
            [flask_bin, "--app", "app", "db", "upgrade", "b7e2f4a9c102"],
            cwd=repo_root,
            env=pg_env,
            check=True,
            capture_output=True,
            text=True,
        )

        # Seed realistic legacy rows at b7e2f4a9c102
        engine = create_engine(pg_url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO "user" (email, name, password_hash, role, is_approved, language, theme, is_blocked, is_methodist, auth_provider, session_version, must_change_password, is_on_shift, login_count, total_visits, average_visit_duration, created_at)
                    VALUES
                      ('pg.t1@monday.kg', 'PG Teacher 1', 'hash', 'teacher', true, 'ru', 'light', false, false, 'password', 1, false, true, 0, 0, 0, NOW()),
                      ('pg.t2@monday.kg', 'PG Teacher 2', 'hash', 'teacher', true, 'ru', 'light', false, false, 'password', 1, false, true, 0, 0, 0, NOW()),
                      ('pg.t3@monday.kg', 'PG Teacher 3', 'hash', 'teacher', true, 'ru', 'light', false, false, 'password', 1, false, true, 0, 0, 0, NOW()),
                      ('pg.mgr@monday.kg', 'PG Manager', 'hash', 'sales_manager', true, 'ru', 'light', false, false, 'password', 1, false, true, 0, 0, 0, NOW()),
                      ('pg.stu@monday.kg', 'PG Student', 'hash', 'student', true, 'ru', 'light', false, false, 'password', 1, false, true, 0, 0, 0, NOW())
                    """
                )
            )
            t1_id = conn.execute(text("SELECT id FROM \"user\" WHERE email='pg.t1@monday.kg'")).scalar_one()
            stu_id = conn.execute(text("SELECT id FROM \"user\" WHERE email='pg.stu@monday.kg'")).scalar_one()
            conn.execute(
                text(
                    """
                    INSERT INTO student_record (teacher_id, student_user_id, previous_student_user_id, name, exam, manual_progress, notes, invite_code, linked_at, created_at)
                    VALUES
                      (:t1, :stu, :stu, 'Seeded Claimed', 'SAT', 0, '', 'MND-SEEDEDCLAIMD1', NOW() - INTERVAL '3 days', NOW() - INTERVAL '5 days'),
                      (:t1, NULL, NULL, 'Seeded Pending', 'ORT', 0, '', 'MND-SEEDEDPENDIN1', NULL, NOW() - INTERVAL '2 days')
                    """
                ),
                {"t1": t1_id, "stu": stu_id},
            )
        engine.dispose()

        # 2. Upgrade to head (c8d9e0f1a2b3) -> downgrade -> upgrade
        for cmd in (
            [flask_bin, "--app", "app", "db", "upgrade"],
            [flask_bin, "--app", "app", "db", "downgrade", "b7e2f4a9c102"],
            [flask_bin, "--app", "app", "db", "upgrade"],
        ):
            res = subprocess.run(cmd, cwd=repo_root, env=pg_env, capture_output=True, text=True)
            assert res.returncode == 0, f"{cmd} failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

        # 3. `flask db check` with 0 drift
        chk = subprocess.run(
            [flask_bin, "--app", "app", "db", "check"],
            cwd=repo_root,
            env=pg_env,
            capture_output=True,
            text=True,
        )
        assert chk.returncode == 0, f"flask db check drift:\nSTDOUT:\n{chk.stdout}\nSTDERR:\n{chk.stderr}"

        class PgCfg:
            TESTING = True
            SECRET_KEY = "pg-roundtrip-secret"
            SQLALCHEMY_DATABASE_URI = pg_url
            SQLALCHEMY_TRACK_MODIFICATIONS = False
            SQLALCHEMY_ENGINE_OPTIONS = {}
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False
            UPLOAD_FOLDER = os.path.join(pgroot, "uploads")
            LANGUAGES = ["ru", "en", "ky"]
            BABEL_DEFAULT_LOCALE = "ru"
            INVITE_CODE_TTL_DAYS = 14
            SEED_DEMO = False

        app = create_app(PgCfg, seed_if_empty=False)
        with app.app_context():
            # Verify backfill survived round-trip cleanly
            rows = TeacherAssignment.query.all()
            assert len(rows) == 2
            claimed_rec = StudentRecord.query.filter_by(name="Seeded Claimed").one()
            assert claimed_rec.claimed_by_user_id == stu_id
            assert claimed_rec.claimed_at is not None

            # 4. Concurrent change_teacher calls on Postgres -> at most 1 open assignment per (student_record_id, course_id)
            mgr = User.query.filter_by(email="pg.mgr@monday.kg").one()
            t1 = User.query.filter_by(email="pg.t1@monday.kg").one()
            t2 = User.query.filter_by(email="pg.t2@monday.kg").one()
            t3 = User.query.filter_by(email="pg.t3@monday.kg").one()
            course = AcademicCourse(code="PG_COURSE", name="PG Course", exam="SAT", is_active=True)
            db.session.add(course)
            db.session.commit()
            rec, _code = create_student_with_code(
                mgr, "Concurrent Student", "+996555889900", None, t1.id, course.id
            )
            rec_id, mgr_id, course_id = rec.id, mgr.id, course.id
            teacher_ids = [t2.id, t3.id, t1.id, t2.id, t3.id]

        barrier = threading.Barrier(len(teacher_ids))
        outcomes = []
        lock = threading.Lock()

        def worker(tid: int):
            with app.app_context():
                try:
                    barrier.wait(timeout=10)
                    actor = db.session.get(User, mgr_id)
                    ta = change_teacher(actor, rec_id, tid, course_id, f"Concurrent switch to {tid}")
                    with lock:
                        outcomes.append(("ok", ta.teacher_user_id))
                except Exception as exc:
                    with lock:
                        outcomes.append(("err", type(exc).__name__, str(exc)))
                finally:
                    db.session.remove()

        threads = [threading.Thread(target=worker, args=(tid,)) for tid in teacher_ids]
        for th in threads:
            th.start()
        for th in threads:
            th.join(timeout=15)

        with app.app_context():
            open_count = TeacherAssignment.query.filter_by(
                student_record_id=rec_id, course_id=course_id, ended_at=None
            ).count()
            assert open_count == 1
            open_row = TeacherAssignment.query.filter_by(
                student_record_id=rec_id, course_id=course_id, ended_at=None
            ).one()
            rec = db.session.get(StudentRecord, rec_id)
            assert rec.teacher_id == open_row.teacher_user_id
    finally:
        subprocess.run(
            ["pg_ctl", "-D", pgdata, "-m", "immediate", "stop"],
            capture_output=True,
            env=env,
        )
        shutil.rmtree(pgroot, ignore_errors=True)
