"""Stage 3 tests: public sample questions, /question-bank/media/<key>, preflight rules, and gating completeness."""
import os
import re

from config import Config
from monday import create_app
from monday.constants import EXAMS
from monday.extensions import db
from monday.models import AcademicCourse, AuditLog, ContentNode, Location, Question, User

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_app(tmp_path, *, public_enabled=True, self_study_signup=False, legal_reviewed=False):
    class Cfg(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        PUBLIC_SITE_ENABLED = public_enabled
        PUBLIC_LEGAL_REVIEWED = legal_reviewed
        SELF_STUDY_SIGNUP_ENABLED = self_study_signup
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'stage3.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        PUBLIC_SAMPLE_MEDIA_FOLDER = str(tmp_path / "public_sample_media")

    return create_app(Cfg, seed_if_empty=False)


def test_public_sample_media_copy_isolation_security_and_unflag(tmp_path):
    from monday import storage
    from monday.public_samples import set_question_public_sample

    app = _make_app(tmp_path, public_enabled=True)
    with app.app_context():
        node = ContentNode(code="s3_alg", name="Algebra", level="node", exams=["ORT", "SAT"])
        admin = User(email="admin_s3@monday.test", name="Admin", role="admin", is_approved=True)
        admin.set_password("StrongAdminPass123!")
        db.session.add_all([node, admin])
        db.session.flush()

        priv_stem = storage.save("q-stem-secret.png", PNG_1PX, "image/png")
        non_sample_stem = storage.save("q-nonsample.png", PNG_1PX, "image/png")

        sample_q = Question(
            author=admin,
            skill=node,
            exams=["ORT"],
            difficulty=2,
            text="Решите уравнение $2x = 10$.",
            image_path=priv_stem,
            answer_type="choice",
            options=["2", "5", "8", "10"],
            correct="1",
            explanation="SECRET_EXPLANATION_SHOULD_NEVER_LEAK",
            video_url="https://example.com/secret-video",
            status="published",
        )
        non_sample_q = Question(
            author=admin,
            skill=node,
            exams=["SAT"],
            difficulty=2,
            text="Private bank question",
            image_path=non_sample_stem,
            answer_type="choice",
            options=["A", "B", "C", "D"],
            correct="0",
            explanation="Private explanation",
            status="published",
        )
        draft_q = Question(
            author=admin,
            skill=node,
            exams=["ORT"],
            difficulty=1,
            text="Draft question",
            answer_type="choice",
            options=["1", "2"],
            correct="0",
            status="draft",
        )
        db.session.add_all([sample_q, non_sample_q, draft_q])
        db.session.commit()

        # Drafts cannot be marked as public samples
        try:
            set_question_public_sample(draft_q, True)
            assert False, "Expected ValueError when flagging non-published question"
        except ValueError:
            pass

        # Flag published question -> copies stem image under a random hashed key into separate storage
        set_question_public_sample(sample_q, True)
        db.session.commit()
        key = sample_q.public_image_key
        assert key and re.fullmatch(r"[0-9a-f]{32}\.png", key)
        assert key != priv_stem
        pub_path = os.path.join(app.config["PUBLIC_SAMPLE_MEDIA_FOLDER"], key)
        assert os.path.isfile(pub_path)
        sample_qid = sample_q.id

    client = app.test_client()

    # /question-bank shows sanitized sample + /question-bank/media/<key>, never answer/explanation or /uploads/
    r_page = client.get("/question-bank")
    assert r_page.status_code == 200
    html = r_page.data.decode("utf-8")
    assert "Решите уравнение" in html
    assert f"/question-bank/media/{key}" in html
    assert "SECRET_EXPLANATION_SHOULD_NEVER_LEAK" not in html
    assert "https://example.com/secret-video" not in html
    assert "/uploads/" not in html
    assert "q-stem-secret.png" not in html

    # Valid key serves PNG with nosniff + public cache headers
    r_img = client.get(f"/question-bank/media/{key}")
    assert r_img.status_code == 200
    assert r_img.data == PNG_1PX
    assert r_img.headers["Content-Type"].startswith("image/png")
    assert r_img.headers.get("X-Content-Type-Options") == "nosniff"
    assert "public" in (r_img.headers.get("Cache-Control") or "")

    # Path traversal, non-sample upload name, random key, and listing are all 404 (not enumerable)
    assert client.get(f"/question-bank/media/{non_sample_stem}").status_code == 404
    assert client.get("/question-bank/media/q-nonsample.png").status_code == 404
    assert client.get("/question-bank/media/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/question-bank/media/../../../../etc/passwd").status_code == 404
    assert client.get(f"/question-bank/media/{'0' * 32}.png").status_code == 404
    assert client.get("/question-bank/media/").status_code == 404
    assert client.get("/question-bank/media").status_code == 404

    # /uploads/<name> MUST continue requiring login
    r_up = client.get(f"/uploads/{non_sample_stem}", follow_redirects=False)
    assert r_up.status_code == 302 and "/login" in r_up.headers["Location"]

    # Unflagging via admin route deletes the public copy, logs audit entry, and 404s old key
    r_login = client.post("/login", data={"email": "admin_s3@monday.test", "password": "StrongAdminPass123!"}, follow_redirects=False)
    assert r_login.status_code in (302, 303)
    r_toggle = client.post(
        f"/admin/questions/{sample_qid}/public-sample",
        data={"enabled": "0"},
        headers={"X-Requested-With": "fetch"},
    )
    assert r_toggle.status_code == 200
    assert r_toggle.get_json()["is_public_sample"] is False
    assert r_toggle.get_json()["public_image_key"] is None

    assert not os.path.exists(pub_path)
    assert client.get(f"/question-bank/media/{key}").status_code == 404
    with app.app_context():
        audit = AuditLog.query.filter_by(action="question_public_sample_toggle", entity_id=sample_qid).first()
        assert audit is not None


def test_question_bank_and_pricing_hide_signup_unless_flag_enabled(tmp_path):
    app_off = _make_app(tmp_path / "off", public_enabled=True, self_study_signup=False)
    c_off = app_off.test_client()
    qb_off = c_off.get("/question-bank").data.decode("utf-8")
    pr_off = c_off.get("/pricing").data.decode("utf-8")
    assert 'href="/register"' not in qb_off
    assert 'href="/register"' not in pr_off
    assert 'href="/login"' in qb_off
    assert 'href="/login"' in pr_off

    app_on = _make_app(tmp_path / "on", public_enabled=True, self_study_signup=True)
    c_on = app_on.test_client()
    qb_on = c_on.get("/question-bank").data.decode("utf-8")
    pr_on = c_on.get("/pricing").data.decode("utf-8")
    assert 'href="/register"' in qb_on
    assert 'href="/register"' in pr_on


def test_site_preflight_stage3_sample_and_media_integrity_checks(tmp_path):
    from monday import storage
    from monday.public_samples import set_question_public_sample
    from monday.public_site import collect_site_preflight_blockers

    app = _make_app(tmp_path, public_enabled=True, legal_reviewed=True)
    clean_dir = tmp_path / "clean_tpl"
    clean_dir.mkdir()
    (clean_dir / "about.html").write_text("<h1>Monday Academy</h1>", encoding="utf-8")
    full_contacts = {
        "instagram": "https://instagram.com/x",
        "telegram": "https://t.me/x",
        "whatsapp": "https://wa.me/996700111222",
        "trial_lesson": "https://monday.kg/contact",
        "address": "Токтогула 77",
    }

    with app.app_context():
        node = ContentNode(code="s3_all", name="All", level="node", exams=list(EXAMS.keys()))
        db.session.add(node)
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
                code="SAT-1",
                name="SAT",
                exam="SAT",
                public_summary="Полная подготовка SAT.",
                is_active=True,
                is_public=True,
            )
        )
        img_name = storage.save("q-preflight.png", PNG_1PX, "image/png")
        q = Question(
            skill=node,
            exams=["ORT"],  # Intentionally missing ENT/EGE/OGE/SAT/CSCA samples first
            difficulty=2,
            text="Sample question",
            image_path=img_name,
            options=["A", "B"],
            correct="0",
            status="published",
        )
        db.session.add(q)
        db.session.flush()
        set_question_public_sample(q, True)
        db.session.commit()

        # Missing public samples for remaining advertised exams
        blockers = collect_site_preflight_blockers(contacts_override=full_contacts, template_dirs=(clean_dir,))
        for missing_exam in ("ENT", "EGE", "OGE", "SAT", "CSCA"):
            assert any(f"'{missing_exam}'" in b for b in blockers), blockers

        # Cover all advertised exams -> 0 blockers
        q.exams = list(EXAMS.keys())
        db.session.commit()
        assert collect_site_preflight_blockers(contacts_override=full_contacts, template_dirs=(clean_dir,)) == []

        # Deleting physical media copy causes preflight failure
        key = q.public_image_key
        pub_file = os.path.join(app.config["PUBLIC_SAMPLE_MEDIA_FOLDER"], key)
        os.remove(pub_file)
        blockers_missing_media = collect_site_preflight_blockers(contacts_override=full_contacts, template_dirs=(clean_dir,))
        assert any("missing its public media copy" in b for b in blockers_missing_media)

        # Unflagged question keeping public_image_key or orphaned file causes preflight failure
        with open(pub_file, "wb") as f:
            f.write(PNG_1PX)
        q.is_public_sample = False
        # Note: intentionally leaving q.public_image_key stale to test preflight catches unflagged copies
        q_filler = Question(
            skill=node,
            exams=list(EXAMS.keys()),
            difficulty=1,
            text="Text-only sample",
            options=["1", "2"],
            correct="0",
            status="published",
            is_public_sample=True,
        )
        db.session.add(q_filler)
        db.session.commit()
        blockers_unflagged = collect_site_preflight_blockers(contacts_override=full_contacts, template_dirs=(clean_dir,))
        assert any("Unflagged Question" in b for b in blockers_unflagged)
        assert any("Orphaned public sample media file" in b for b in blockers_unflagged)


def test_every_question_serving_route_has_gating_decorator(tmp_path):
    """Completeness guard: fails if any question/session/test/solution/formula/export route lacks @question_bank_access_required."""
    app = _make_app(tmp_path, public_enabled=True)

    # Routes serving questions, sessions, tests, solutions, formulas, or exports (must all carry @question_bank_access_required)
    expected_gated_endpoints = {
        "analytics.export_csv",
        "assistant.branch_request",
        "assistant.fixes",
        "assistant.gaps",
        "assistant.home",
        "assistant.import_preview",
        "assistant.import_save",
        "assistant.mine",
        "bank.check",
        "bank.index",
        "bank.mark",
        "bank.play",
        "bank.reveal",
        "bank.sheet",
        "bank.start",
        "bank.time_spent",
        "course.admin_course",
        "course.admin_course_preview",
        "course.api_check_question",
        "course.api_complete_lesson",
        "course.player",
        "daily.answer",
        "daily.play",
        "picker.pick_random",
        "picker.plan",
        "picker.preview",
        "picker.results",
        "reports.create",
        "review.approve_all",
        "review.decide",
        "review.queue",
        "roadmap.admin_roadmap",
        "roadmap.api_checklist",
        "roadmap.api_complete_node",
        "roadmap.api_set_goal",
        "student.attempt_alive",
        "student.attempt_assess",
        "student.attempt_next_module",
        "student.attempt_photo",
        "student.attempt_result",
        "student.attempt_run",
        "student.attempt_save",
        "student.collections",
        "student.formula_add",
        "student.formula_sheet_place",
        "student.formula_template",
        "student.formulas",
        "student.home",
        "student.homework",
        "student.homework_detail",
        "student.homework_start",
        "student.journal",
        "student.journal_blank_reason",
        "student.journal_practice",
        "student.journal_review",
        "student.journal_update",
        "student.monday",
        "student.monday_start",
        "student.profile_export",
        "student.profile_export_pdf",
        "student.session_again",
        "student.session_custom",
        "student.session_done",
        "student.session_play",
        "student.session_presets",
        "student.session_retry",
        "student.sessions",
        "student.sessions_clear",
        "student.skills",
        "student.start_session",
        "student.start_work",
        "student.work_detail",
        "teacher.assign",
        "teacher.bank",
        "teacher.bank_add",
        "teacher.daily_remove",
        "teacher.question_delete",
        "teacher.question_edit",
        "teacher.question_new",
        "teacher.question_redact",
        "teacher.questions",
        "teacher.review",
        "teacher.review_detail",
        "teacher.tree",
        "teacher.tree_add",
        "teacher.tree_edit",
        "teacher.tree_move",
        "teacher.work_delete",
        "teacher.work_duplicate",
        "teacher.work_edit",
        "teacher.work_new",
        "teacher.work_status",
        "teacher.works",
        "teacher.written_review",
        "trig_block.dev_visuals",
        "trig_block.trig_api",
        "trig_block.trig_level",
        "trig_block.trig_sections",
        "uploaded_file",
    }

    # Explicitly audited non-question-serving routes (auth, public showcase, CRM, academic schedule/attendance, system ops, account prefs)
    non_question_endpoints = {
        "static",
        "pwa_manifest",
        "pwa_offline",
        "pwa_sw",
        "content_i18n.toggle_original",
        "fx.api_fx_rates",
        "crm_intake.public_apply",
        "crm_intake.webhook_lead",
        "crm_telegram_bot.telegram_webhook",
        "deploy_safety.admin_maintenance",
        "deploy_safety.api_activity_complete",
        "deploy_safety.api_activity_latest",
        "deploy_safety.api_activity_save",
        "deploy_safety.api_admin_maintenance",
        "deploy_safety.api_site_status",
        "deploy_safety.api_version",
        "auth.about",
        "auth.force_password_change",
        "auth.google_callback",
        "auth.google_login",
        "auth.index",
        "auth.join",
        "auth.login",
        "auth.logout",
        "auth.pending",
        "auth.privacy",
        "auth.refund",
        "auth.register",
        "auth.set_avatar",
        "auth.set_language",
        "auth.terms",
        "auth.toggle_theme",
        "public_site.contact",
        "public_site.faq",
        "public_site.offline_courses",
        "public_site.online_courses",
        "public_site.pricing",
        "public_site.public_sample_media",
        "public_site.question_bank",
        "public_site.robots_txt",
        "public_site.sitemap_xml",
        "student.onboarding",
        "student.profile",
        "student.set_goal",
        "student.subscription",
        "student.support",
        "student.switch_exam",
        "teacher.account",
        "teacher.assignment_due",
        "teacher.attendance",
        "teacher.dashboard",
        "teacher.lessons",
        "teacher.student_delete",
        "teacher.student_detail",
        "teacher.student_edit",
        "teacher.student_new",
        "teacher.student_new_code",
        "teacher.student_reset_password",
        "teacher.student_revoke_code",
        "teacher.student_unlink",
        "teacher.students",
        "admin.account",
        "admin.approve",
        "admin.block",
        "admin.index",
        "admin.methodist",
        "admin.reset_password",
        "admin.review_work",
        "admin.set_role",
        "admin.simulate",
        "admin.simulate_credentials",
        "admin.simulate_exit",
        "admin.subscription_cancel",
        "admin.subscription_change_plan",
        "admin.subscription_grant",
        "admin.subscription_plan_create",
        "admin.toggle_public_sample",
        "analytics.api_live",
        "analytics.api_summary",
        "analytics.api_user_block",
        "analytics.api_user_detail",
        "analytics.api_visit_detail",
        "analytics.api_visits",
        "analytics.dashboard",
        "academic.course_create",
        "academic.enrollment_close",
        "academic.group_create",
        "academic.group_enroll",
        "academic.lesson_create",
        "academic.lesson_detail",
        "academic.lesson_mark_attendance",
        "academic.location_create",
        "academic.schedule",
        "manager.account",
        "manager.audit",
        "manager.dashboard",
        "manager.finance",
        "manager.lead_add_activity",
        "manager.lead_add_task",
        "manager.lead_convert",
        "manager.lead_create",
        "manager.lead_delete",
        "manager.lead_detail",
        "manager.lead_edit",
        "manager.lead_merge",
        "manager.lead_reassign",
        "manager.lead_status",
        "manager.leads",
        "manager.pass_update_status",
        "manager.payroll_rate_create",
        "manager.pipeline",
        "manager.plan_create",
        "manager.student_detail",
        "manager.student_new",
        "manager.student_pass_create",
        "manager.student_payment_create",
        "manager.student_record_change_teacher",
        "manager.student_record_detail",
        "manager.student_record_regenerate",
        "manager.student_record_revoke",
        "manager.students",
        "manager.task_toggle",
        "manager.teacher_detail",
        "manager.toggle_shift",
        "reports.attachment_delete",
        "reports.attachment_view",
        "reports.handle",
        "reports.inbox",
        "reports.request_delete",
        "reports.seen",
    }

    registered = set(app.view_functions.keys())
    for ep in expected_gated_endpoints:
        fn = app.view_functions.get(ep)
        assert fn is not None, f"Missing expected gated endpoint {ep}"
        assert getattr(fn, "_question_bank_gated", False) is True, (
            f"Endpoint {ep} serves questions/sessions/tests/solutions/formulas/exports "
            "and must carry @question_bank_access_required"
        )

    unclassified = registered - expected_gated_endpoints - non_question_endpoints
    missing_decorator = [ep for ep in unclassified if not getattr(app.view_functions[ep], "_question_bank_gated", False)]
    assert not missing_decorator, (
        f"New route(s) added without @question_bank_access_required or non-question audit classification: {missing_decorator}"
    )
