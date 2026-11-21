"""Targeted security & data-integrity tests for all P2 items (items 10-11)."""
import hashlib
import json
import os
import tempfile

from config import Config
from monday.extensions import db
from monday.models import (
    Assignment,
    CourseLesson,
    CourseMastery,
    CourseUnit,
    MaintenanceLog,
    Question,
    RoadmapMilestone,
    RoadmapNode,
    RoadmapProgress,
    StudentRecord,
    User,
    Work,
)
from test_app import APP, client, login


# --------------------------------------------------------------------------- P2-10: FKs & pack_item_id


def test_p2_10_roadmap_progress_and_course_mastery_survive_slug_rename_via_fk():
    c = login(client(), "student@monday.kg", "student123")
    with APP.app_context():
        stu = User.query.filter_by(email="student@monday.kg").first()
        ms = RoadmapMilestone(exam="SAT", key="p2-ms", step=99, title_ru="P2 MS", title_en="P2 MS")
        db.session.add(ms)
        db.session.flush()
        node = RoadmapNode(milestone_id=ms.id, key="p2-node-old", title_ru="Old Node", title_en="Old Node", kind="topic")
        db.session.add(node)

        unit = CourseUnit(exam="SAT", number=98, slug="p2-unit-old", title_ru="P2 Unit")
        db.session.add(unit)
        db.session.flush()
        lesson = CourseLesson(unit_id=unit.id, slug="p2-lesson-old", position=1, title_ru="P2 Art", kind="article")
        db.session.add(lesson)
        db.session.commit()
        ms_id, node_id, unit_id, lesson_id, stu_id = ms.id, node.id, unit.id, lesson.id, stu.id

    try:
        # 1. Mark roadmap node completed -> saves node_id FK
        r1 = c.post("/api/roadmap/node/p2-node-old/complete", json={"done": True})
        assert r1.status_code == 200
        with APP.app_context():
            rp = RoadmapProgress.query.filter_by(user_id=stu_id, node_id=node_id).first()
            assert rp is not None and rp.node_id == node_id
            # Rename node key -> progress must still resolve by node_id FK!
            n = db.session.get(RoadmapNode, node_id)
            n.key = "p2-node-renamed"
            db.session.commit()

            from monday.roadmap import build_sat_roadmap
            with APP.test_request_context("/"):
                rm = build_sat_roadmap(stu_id, [], lang="ru")
            found = [
                nd
                for m in rm["milestones"] if m["key"] == "p2-ms"
                for g in (m["left_groups"] + m["right_groups"])
                for nd in g["nodes"] if nd["key"] == "p2-node-renamed"
            ]
            assert len(found) == 1 and found[0]["status"] == "completed"

        # 2. Complete course lesson -> saves lesson_id FK
        r2 = c.post("/api/course/complete", json={"exam": "SAT", "unit_slug": "p2-unit-old", "lesson_slug": "p2-lesson-old"})
        assert r2.status_code == 200
        with APP.app_context():
            cm = CourseMastery.query.filter_by(user_id=stu_id, lesson_id=lesson_id).first()
            assert cm is not None and cm.lesson_id == lesson_id
            # Rename unit and lesson slugs -> mastery must survive via lesson_id FK!
            u = db.session.get(CourseUnit, unit_id)
            l = db.session.get(CourseLesson, lesson_id)
            u.slug = "p2-unit-renamed"
            l.slug = "p2-lesson-renamed"
            db.session.commit()

            from monday.course import build_course
            with APP.test_request_context("/"):
                course_data = build_course(stu_id, exam="SAT")
            found_l = [
                it
                for cu in course_data["units"] if cu["slug"] == "p2-unit-renamed"
                for it in cu["lessons"] if it["slug"] == "p2-lesson-renamed"
            ]
            assert len(found_l) == 1 and found_l[0]["level"] == "familiar"
    finally:
        with APP.app_context():
            RoadmapProgress.query.filter_by(user_id=stu_id, node_id=node_id).delete()
            CourseMastery.query.filter_by(user_id=stu_id, lesson_id=lesson_id).delete()
            ms_obj = db.session.get(RoadmapMilestone, ms_id)
            if ms_obj:
                db.session.delete(ms_obj)
            u_obj = db.session.get(CourseUnit, unit_id)
            if u_obj:
                db.session.delete(u_obj)
            db.session.commit()


def test_p2_10_maintenance_log_records_actor_id_fk():
    adm = login(client(), "admin@monday.kg", "monday2026")
    with APP.app_context():
        admin_id = User.query.filter_by(email="admin@monday.kg").first().id
    r = adm.post("/admin/maintenance", data={"state": "scheduled", "message": "P2 check", "expected_minutes": "10"})
    assert r.status_code in (200, 302)
    with APP.app_context():
        log_row = MaintenanceLog.query.order_by(MaintenanceLog.id.desc()).first()
        assert log_row is not None and log_row.actor_id == admin_id
    # Restore off state
    adm.post("/admin/maintenance", data={"state": "off", "message": "", "expected_minutes": "15"})


def test_p2_10_packs_sync_matches_by_pack_item_id_even_after_edits(monkeypatch):
    from monday import packs

    tmp_pack_dir = tempfile.mkdtemp()
    pack_id = "p2_test_pack"
    pack_json = {
        "title": "P2 Pack",
        "exam": "SAT",
        "language": "en",
        "questions": [
            {"id": "q1", "skill": None, "text": "2+2=?", "answer_type": "number", "correct": "4", "explanation": "Original exp"},
        ],
        "collections": [
            {"id": "col1", "title": "Original Collection", "questions": ["q1"]},
        ],
    }
    pfile = os.path.join(tmp_pack_dir, pack_id + ".json")
    with open(pfile, "w", encoding="utf-8") as f:
        json.dump(pack_json, f)

    monkeypatch.setattr(packs, "PACK_DIR", tmp_pack_dir)
    with APP.app_context():
        q_cnt, w_cnt = packs.import_pack(pack_id, publish=True)
        assert q_cnt == 1 and w_cnt == 1
        q = Question.query.filter_by(pack_item_id=f"{pack_id}:q1").first()
        w = Work.query.filter_by(pack_item_id=f"{pack_id}:col1").first()
        assert q is not None and w is not None
        orig_qid, orig_wid = q.id, w.id

        # Simulate teacher editing explanation & collection title, then running sync_pack with updated text
        q.explanation = "Edited explanation by teacher"
        w.title = "Renamed Collection Title"
        db.session.commit()

        pack_json["questions"][0]["text"] = "2+2=? (updated)"
        with open(pfile, "w", encoding="utf-8") as f:
            json.dump(pack_json, f)
        packs.sync_pack(pack_id, publish=True)

        # Must update the EXISTING question in place (no duplicate created!)
        qs = Question.query.filter_by(source=pack_id).all()
        assert len(qs) == 1 and qs[0].id == orig_qid and qs[0].text == "2+2=? (updated)"
        ws = Work.query.filter_by(pack_item_id=f"{pack_id}:col1").all()
        assert len(ws) == 1 and ws[0].id == orig_wid

        # Cleanup
        for row in ws:
            db.session.delete(row)
        for row in qs:
            db.session.delete(row)
        from monday.models import AppMeta
        meta = db.session.get(AppMeta, packs._meta_key(pack_id))
        if meta:
            db.session.delete(meta)
        db.session.commit()


def test_p2_10_student_record_unlink_blocks_assignment_transfer_to_different_student():
    tch = login(client(), "aibek@monday.kg", "teacher123")
    s1 = client()
    s1.post("/register", data={"name": "Stu One", "email": "p2.s1@example.com", "password": "Password123", "role": "student"})
    s1.post("/onboarding", data={"exam": "ORT", "name": "Stu One", "grade": "11"})
    s2 = client()
    s2.post("/register", data={"name": "Stu Two", "email": "p2.s2@example.com", "password": "Password123", "role": "student"})
    s2.post("/onboarding", data={"exam": "ORT", "name": "Stu Two", "grade": "11"})

    with APP.app_context():
        aibek = User.query.filter_by(email="aibek@monday.kg").first()
        u1 = User.query.filter_by(email="p2.s1@example.com").first()
        u2 = User.query.filter_by(email="p2.s2@example.com").first()
        work = Work.query.first()
        rec = StudentRecord(teacher_id=aibek.id, name="Locked Row", exam="ORT")
        db.session.add(rec)
        db.session.flush()
        rec.student_user_id = u1.id
        rec.previous_student_user_id = u1.id
        asn = Assignment(work_id=work.id, teacher_id=aibek.id, record_id=rec.id)
        db.session.add(asn)
        db.session.commit()
        rec_id, u1_id, u2_id = rec.id, u1.id, u2.id

    try:
        # Unlinking a record that owns assignments must revoke its invite code immediately
        r_un = tch.post(f"/teacher/students/{rec_id}/unlink")
        assert r_un.status_code == 302
        with APP.app_context():
            rec = db.session.get(StudentRecord, rec_id)
            assert rec.student_user_id is None
            assert rec.previous_student_user_id == u1_id
            assert rec.invite_revoked_at is not None

        # Even if teacher rotates a new code, a DIFFERENT student (u2) must be blocked from inheriting u1's assignments
        tch.post(f"/teacher/students/{rec_id}/code")
        with APP.test_request_context("/"):
            rec = db.session.get(StudentRecord, rec_id)
            new_code = rec.invite_code
            from monday.auth import link_invite_code
            ok_other, _msg = link_invite_code(db.session.get(User, u2_id), new_code)
            assert ok_other is False
            assert db.session.get(StudentRecord, rec_id).student_user_id is None

            # Re-linking the ORIGINAL student (u1) IS allowed
            ok_same, _msg2 = link_invite_code(db.session.get(User, u1_id), new_code)
            assert ok_same is True
            assert db.session.get(StudentRecord, rec_id).student_user_id == u1_id
    finally:
        with APP.app_context():
            rec = db.session.get(StudentRecord, rec_id)
            if rec:
                db.session.delete(rec)
            db.session.commit()


# --------------------------------------------------------------------------- P2-11: Security Headers, Analytics & Demo


def test_p2_11_security_headers_and_hsts_behind_https():
    c = client()
    r = c.get("/login")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "https://www.desmos.com" in csp
    assert "object-src 'none'" in csp

    # HSTS is set when SESSION_COOKIE_SECURE=True
    tmp = tempfile.mkdtemp()

    class SecureHeaderConfig(Config):
        TESTING = True
        SESSION_COOKIE_SECURE = True
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "hsts.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app
    app_https = create_app(SecureHeaderConfig, seed_if_empty=False)
    r_https = app_https.test_client().get("/login")
    assert "max-age=31536000" in r_https.headers.get("Strict-Transport-Security", "")


def test_p2_11_analytics_proxy_ip_spoof_resistance_and_salt_separation(monkeypatch):
    from monday.analytics_tracking import get_client_ip, hash_ip
    from monday.models import Visit

    # With ProxyFix(x_for=1), if attacker sends X-Forwarded-For: 1.2.3.4 and Render appends real IP 198.51.100.9,
    # get_client_ip() MUST resolve 198.51.100.9 (rightmost trusted hop), NOT spoofed leftmost 1.2.3.4!
    tmp = tempfile.mkdtemp()

    class ProbeConfig(Config):
        TESTING = True
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        ANALYTICS_IP_SALT = "dedicated-prod-salt-xyz"
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "probe.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app
    probe_app = create_app(ProbeConfig, seed_if_empty=False)
    captured = {}

    @probe_app.route("/_p2_ip_probe")
    def _p2_ip_probe():
        captured["ip"] = get_client_ip()
        return "ok"

    pc = probe_app.test_client()
    r = pc.get("/_p2_ip_probe", headers={"X-Forwarded-For": "1.2.3.4, 198.51.100.9", "X-Real-IP": "9.9.9.9"})
    assert r.status_code == 200
    assert captured["ip"] == "198.51.100.9"

    # Also verify full Visit tracking hashes the real hop (198.51.100.9), not spoofed 1.2.3.4
    r_visit = pc.get("/login", headers={
        "X-Forwarded-For": "1.2.3.4, 198.51.100.9",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
    })
    assert r_visit.status_code == 200
    with probe_app.app_context():
        v = Visit.query.first()
        assert v is not None
        assert v.ip_hash == hashlib.sha256(b"dedicated-prod-salt-xyz:198.51.100.9").hexdigest()

        # Dedicated ANALYTICS_IP_SALT must be used and fallback must NOT hash raw SECRET_KEY directly
        monkeypatch.delenv("ANALYTICS_IP_SALT", raising=False)
        probe_app.config["ANALYTICS_IP_SALT"] = ""
        h_fallback = hash_ip("198.51.100.9")
        raw_secret_hash = hashlib.sha256(f"{probe_app.config['SECRET_KEY']}:198.51.100.9".encode()).hexdigest()
        assert h_fallback != raw_secret_hash

        monkeypatch.setenv("ANALYTICS_IP_SALT", "dedicated-prod-salt-xyz")
        h_dedicated = hash_ip("198.51.100.9")
        assert h_dedicated == hashlib.sha256(b"dedicated-prod-salt-xyz:198.51.100.9").hexdigest()
        assert h_dedicated != h_fallback


def test_p2_11_free_render_blueprint_locks_down_demo_admin():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "render.yaml"), encoding="utf-8") as f:
        text = f.read()
    assert "key: SEED_DEMO" in text and 'value: "0"' in text
    assert "key: DATA_FIXES" in text
    assert "key: COOKIE_SECURE" in text and 'value: "1"' in text
