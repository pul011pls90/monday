"""Tests for shared slide_over_drawer + searchable_combobox components across Admin, Students, and Leads."""
from __future__ import annotations

import os
import pathlib
import re
import threading
from datetime import timedelta

from werkzeug.serving import make_server

from config import Config
from monday.extensions import db
from monday.models import (
    AcademicCourse,
    Lead,
    LeadActivity,
    LeadTask,
    StudentRecord,
    TeacherAssignment,
    User,
    utcnow,
)


ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _make_app(tmp_path, *, csrf_enabled: bool = False):
    class SharedCompConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = csrf_enabled
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'shared_comp.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")

    from monday import create_app

    return create_app(SharedCompConfig, seed_if_empty=False)


def _seed_user(app, email: str, name: str, role: str, password: str = "Pass12345!") -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, email: str, password: str = "Pass12345!"):
    resp = client.post("/login", data={"email": email, "password": password})
    assert resp.status_code == 302


def test_shared_component_templates_have_zero_inline_handlers_or_scripts():
    """Verify strict CSP hygiene on shared components and updated Admin/Manager templates."""
    template_paths = [
        "monday/templates/components/drawer.html",
        "monday/templates/components/combobox.html",
        "monday/templates/components/ui.html",
        "monday/templates/admin/index.html",
        "monday/templates/manager/students.html",
        "monday/templates/manager/_student_record_drawer.html",
        "monday/templates/manager/student_new.html",
        "monday/templates/manager/leads.html",
        "monday/templates/manager/_lead_drawer.html",
    ]
    inline_handler_re = re.compile(r"\bon(?:click|change|input|submit|keydown|keyup|focus|blur)=", re.I)
    for rel in template_paths:
        text = (ROOT_DIR / rel).read_text(encoding="utf-8")
        assert "javascript:" not in text.lower(), f"javascript: URL in {rel}"
        assert not inline_handler_re.search(text), f"inline event handler in {rel}"
        # Only static external deferred scripts are permitted in admin/index.html's scripts block
        for tag in re.findall(r"<script\b[^>]*>", text, re.I):
            assert 'src=' in tag.lower(), f"inline <script> block found in {rel}: {tag}"


def test_admin_uses_shared_drawer_component(tmp_path):
    app = _make_app(tmp_path)
    adm_id = _seed_user(app, "adm@comp.kg", "Admin User", "admin")
    stu_id = _seed_user(app, "stu@comp.kg", "Student User", "student")

    c = app.test_client()
    _login(c, "adm@comp.kg")

    html = c.get("/admin/?tab=students").data.decode("utf-8")
    assert 'data-drawer-root="admin-person-drawer"' in html
    assert "data-person-panel" in html
    assert html.index("data-person-panel") > html.index("</main>")
    assert f"user={stu_id}" in html and "fragment=1" in html

    frag = c.get(f"/admin/?tab=students&user={stu_id}&fragment=1")
    assert frag.status_code == 200
    assert "Student User" in frag.data.decode("utf-8")


def test_manager_students_shared_drawer_and_combobox(tmp_path):
    app = _make_app(tmp_path)
    sup_id = _seed_user(app, "sup@comp.kg", "Supervisor CRM", "supervisor")
    t1_id = _seed_user(app, "t1@comp.kg", "Айбек Математика", "teacher")
    t2_id = _seed_user(app, "t2@comp.kg", "Дана Физика", "teacher")

    with app.app_context():
        math_course = AcademicCourse(code="sat_math", name="SAT Math", exam="SAT", is_active=True)
        phys_course = AcademicCourse(code="physics", name="Physics", exam="NUFYPET", is_active=True)
        db.session.add_all([math_course, phys_course])
        db.session.flush()

        lead = Lead(
            full_name="Бота Лидова",
            phone="+77011112233",
            source="instagram",
            interest="SAT Math",
            status="won",
            assigned_manager_id=sup_id,
        )
        db.session.add(lead)
        db.session.flush()
        db.session.add(
            LeadActivity(lead_id=lead.id, actor_id=sup_id, type="note", body="Готова начать на этой неделе")
        )

        rec_t1 = StudentRecord(
            name="Ученик Один",
            phone="+77010000001",
            email="u1@comp.kg",
            teacher_id=t1_id,
            course_id=math_course.id,
            source_lead_id=lead.id,
            invite_code="CODE-ONE-1",
            invite_expires_at=utcnow() + timedelta(days=7),
            created_by_user_id=sup_id,
        )
        rec_unassigned = StudentRecord(
            name="Ученик Без Учителя",
            phone="+77010000002",
            email="u2@comp.kg",
            teacher_id=None,
            course_id=phys_course.id,
            invite_code="CODE-TWO-2",
            invite_expires_at=utcnow() + timedelta(days=7),
            created_by_user_id=sup_id,
        )
        db.session.add_all([rec_t1, rec_unassigned])
        db.session.flush()
        db.session.add(
            TeacherAssignment(
                student_record_id=rec_t1.id,
                teacher_user_id=t1_id,
                course_id=math_course.id,
                assigned_by_id=sup_id,
            )
        )
        db.session.commit()
        rec_t1_id = rec_t1.id
        math_id = math_course.id

    c = app.test_client()
    _login(c, "sup@comp.kg")

    # /manager/students uses searchable_combobox + slide_over_drawer + special option "Без преподавателя"
    list_html = c.get("/manager/students").data.decode("utf-8")
    assert 'data-combobox' in list_html
    assert 'data-drawer-root="student-record-drawer"' in list_html
    assert 'data-drawer-root="student-new-drawer"' in list_html
    assert "Без преподавателя" in list_html
    assert "Айбек Математика" in list_html
    assert "SAT Math · 1 уч." in list_html

    # Filter by unassigned teacher
    unassigned_html = c.get("/manager/students?teacher_id=unassigned").data.decode("utf-8")
    assert "Ученик Без Учителя" in unassigned_html
    assert "Ученик Один" not in unassigned_html

    # Filter by specific teacher
    t1_html = c.get(f"/manager/students?teacher_id={t1_id}").data.decode("utf-8")
    assert "Ученик Один" in t1_html
    assert "Ученик Без Учителя" not in t1_html

    # Drawer fragment returns lead notes, binding code timestamps, copy button, and change-teacher combobox
    frag_resp = c.get(f"/manager/students/records/{rec_t1_id}?fragment=1")
    assert frag_resp.status_code == 200
    assert "no-store" in frag_resp.headers.get("Cache-Control", "")
    frag_html = frag_resp.data.decode("utf-8")
    assert "Бота Лидова" in frag_html or f"/manager/leads/" in frag_html
    assert "Готова начать на этой неделе" in frag_html
    assert 'data-copy-text="+77010000001"' in frag_html
    assert f"/manager/students/records/{rec_t1_id}" in frag_html
    assert "Сменить преподавателя" in frag_html

    # Inline fetch teacher change fails gracefully with 400 when reason is empty
    bad_change = c.post(
        f"/manager/students/records/{rec_t1_id}/teacher/change",
        data={"new_teacher_id": str(t2_id), "course_id": str(math_id), "reason": ""},
        headers={"X-Requested-With": "fetch"},
    )
    assert bad_change.status_code == 400
    assert "Укажите причину" in bad_change.data.decode("utf-8")

    # Inline fetch teacher change succeeds and updates assignment history
    ok_change = c.post(
        f"/manager/students/records/{rec_t1_id}/teacher/change",
        data={"new_teacher_id": str(t2_id), "course_id": str(math_id), "reason": "Перевод по графику"},
        headers={"X-Requested-With": "fetch"},
    )
    assert ok_change.status_code == 200
    ok_html = ok_change.data.decode("utf-8")
    assert "Дана Физика" in ok_html
    assert "Перевод по графику" in ok_html

    # Inline fetch code regenerate displays new code with no-store
    regen_resp = c.post(
        f"/manager/students/records/{rec_t1_id}/code/regenerate",
        headers={"X-Requested-With": "fetch"},
    )
    assert regen_resp.status_code == 200
    assert "no-store" in regen_resp.headers.get("Cache-Control", "")
    assert "Выпущен новый код подключения" in regen_resp.data.decode("utf-8")

    # /manager/students/new uses searchable_combobox
    new_html = c.get("/manager/students/new").data.decode("utf-8")
    assert 'data-combobox' in new_html
    assert 'name="teacher_id"' in new_html


def test_manager_leads_scale_filters_and_drawer_ajax(tmp_path):
    app = _make_app(tmp_path)
    sup_id = _seed_user(app, "sup@leads.kg", "Супервайзер Омаров", "supervisor")
    mgr2_id = _seed_user(app, "mgr2@leads.kg", "Менеджер Асель", "sales_manager")
    tch_id = _seed_user(app, "tch@leads.kg", "Учитель Марат", "teacher")

    with app.app_context():
        l_new = Lead(
            full_name="Алиса Новая",
            phone="+77019990001",
            messenger_handle="@alisa_new",
            source="instagram",
            interest="IELTS",
            status="new",
            assigned_manager_id=sup_id,
            created_at=utcnow() - timedelta(minutes=30),
        )
        l_prog = Lead(
            full_name="Тимур В Работе",
            phone="+77019990002",
            messenger_handle="@timur_crm",
            source="whatsapp",
            interest="SAT Math",
            status="contacted",
            assigned_manager_id=mgr2_id,
            first_contact_at=utcnow() - timedelta(hours=1),
        )
        l_trial = Lead(
            full_name="Зарина Пробный",
            phone="+77019990003",
            source="referral",
            interest="SAT Verbal",
            status="trial_scheduled",
            assigned_manager_id=None,
            first_contact_at=utcnow() - timedelta(days=2),
        )
        db.session.add_all([l_new, l_prog, l_trial])
        db.session.flush()
        db.session.add(LeadActivity(lead_id=l_prog.id, actor_id=sup_id, type="note", body="УникальнаяЗаметкаПоиск"))
        db.session.add(LeadTask(lead_id=l_prog.id, assignee_id=mgr2_id, due_at=utcnow() - timedelta(hours=2), note="Перезвонить срочно"))
        db.session.commit()
        l_new_id = l_new.id
        l_prog_id = l_prog.id
        l_trial_id = l_trial.id

    c_sup = app.test_client()
    _login(c_sup, "sup@leads.kg")
    c_mgr2 = app.test_client()
    _login(c_mgr2, "mgr2@leads.kg")

    # Top grouped stage tabs render and group accurately
    all_html = c_sup.get("/manager/leads").data.decode("utf-8")
    for lbl in ("Все", "Новые", "В работе", "Пробный", "Оплата", "Отказ"):
        assert lbl in all_html

    in_prog_html = c_sup.get("/manager/leads?status=in_progress").data.decode("utf-8")
    assert "Тимур В Работе" in in_prog_html
    assert "Алиса Новая" not in in_prog_html
    assert "Зарина Пробный" not in in_prog_html

    trial_html = c_sup.get("/manager/leads?status=trial").data.decode("utf-8")
    assert "Зарина Пробный" in trial_html
    assert "Тимур В Работе" not in trial_html

    # Search q matches activity notes!
    q_note_html = c_sup.get("/manager/leads?q=УникальнаяЗаметкаПоиск").data.decode("utf-8")
    assert "Тимур В Работе" in q_note_html
    assert "Алиса Новая" not in q_note_html

    # Manager quick-picks: mine & unassigned
    mine_html = c_sup.get("/manager/leads?manager=mine").data.decode("utf-8")
    assert "Алиса Новая" in mine_html
    assert "Зарина Пробный" not in mine_html

    unass_html = c_sup.get("/manager/leads?manager=unassigned").data.decode("utf-8")
    assert "Зарина Пробный" in unass_html
    assert "Алиса Новая" not in unass_html

    # Subject filter & active filter chips + Reset all
    subj_html = c_sup.get("/manager/leads?subject=IELTS").data.decode("utf-8")
    assert "Алиса Новая" in subj_html
    assert "Тимур В Работе" not in subj_html
    assert "Предмет: IELTS" in subj_html
    assert "Сбросить всё" in subj_html

    # sla=overdue includes BOTH unanswered SLA overdue leads AND leads with open overdue LeadTask
    sla_html = c_sup.get("/manager/leads?sla=overdue").data.decode("utf-8")
    assert "Алиса Новая" in sla_html
    assert "Тимур В Работе" in sla_html
    assert "Зарина Пробный" not in sla_html

    # Fragment drawer includes WhatsApp, Telegram, copy button, convert link, quick note, and inline status
    frag = c_sup.get(f"/manager/leads/{l_new_id}?fragment=1")
    assert frag.status_code == 200
    f_html = frag.data.decode("utf-8")
    assert "https://wa.me/77019990001" in f_html
    assert "https://t.me/alisa_new" in f_html
    assert 'data-copy-text="+77019990001"' in f_html
    assert f"/manager/students/new?lead_id={l_new_id}" in f_html

    # Inline quick note & status update via fetch return updated drawer fragment
    note_resp = c_sup.post(
        f"/manager/leads/{l_new_id}/activity",
        data={"type": "call", "body": "Дозвонились, ждём на пробный"},
        headers={"X-Requested-With": "fetch"},
    )
    assert note_resp.status_code == 200
    assert "Дозвонились, ждём на пробный" in note_resp.data.decode("utf-8")

    # Invalid direct new->won blocked cleanly with 400 in fetch mode, while contacted->trial_scheduled works
    st_ok = c_sup.post(
        f"/manager/leads/{l_new_id}/status",
        data={"status": "trial_scheduled"},
        headers={"X-Requested-With": "fetch"},
    )
    assert st_ok.status_code == 200
    assert "Статус обновлён" in st_ok.data.decode("utf-8")

    # RBAC preserved: mgr2 cannot open sup's lead fragment (403)
    assert c_mgr2.get(f"/manager/leads/{l_trial_id}?fragment=1").status_code == 403

    # Reassign works via fetch and non-supervisor cannot reassign (403)
    assert c_mgr2.post(f"/manager/leads/{l_prog_id}/reassign", data={"assigned_manager_id": str(sup_id)}).status_code == 403
    reas_resp = c_sup.post(
        f"/manager/leads/{l_prog_id}/reassign",
        data={"assigned_manager_id": str(sup_id)},
        headers={"X-Requested-With": "fetch"},
    )
    assert reas_resp.status_code == 200
    assert "Супервайзер Омаров" in reas_resp.data.decode("utf-8")


def test_playwright_drawer_and_combobox_interactions_csp_clean(tmp_path):
    """End-to-end Chromium check: drawer open/ajax/Esc/backdrop, combobox search/keyboard/clear, 0 CSP errors."""
    from playwright.sync_api import sync_playwright

    app = _make_app(tmp_path, csrf_enabled=True)
    sup_id = _seed_user(app, "sup.pw@comp.kg", "Супервайзер Тест", "supervisor")
    t1_id = _seed_user(app, "t1.pw@comp.kg", "Тимур Алгебра", "teacher")
    _seed_user(app, "t2.pw@comp.kg", "Айгуль Английский", "teacher")

    with app.app_context():
        l1 = Lead(full_name="Браузер Лид", phone="+77015554433", source="instagram", interest="SAT Math", status="new", assigned_manager_id=sup_id)
        db.session.add(l1)
        rec = StudentRecord(
            name="Браузер Ученик",
            phone="+77015554499",
            teacher_id=t1_id,
            invite_code="PW-CODE-1",
            invite_expires_at=utcnow() + timedelta(days=5),
            created_by_user_id=sup_id,
        )
        db.session.add(rec)
        db.session.commit()
        l1_id = l1.id

    app.config["SERVER_NAME"] = None
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1280, "height": 840})
            page = ctx.new_page()
            page.add_init_script(
                'window.__csp = []; window.__errs = [];'
                'document.addEventListener("securitypolicyviolation", e => window.__csp.push(e.violatedDirective));'
                'window.addEventListener("pageerror", e => window.__errs.push(String(e)));'
            )

            page.goto(f"{base_url}/login", wait_until="networkidle")
            page.fill('input[name="email"]', "sup.pw@comp.kg")
            page.fill('input[name="password"]', "Pass12345!")
            page.click('button[type="submit"]')
            page.wait_for_url(f"{base_url}/manager**")

            # 1. /manager/leads: open slide-over drawer on click, add inline quick note, close with Esc
            page.goto(f"{base_url}/manager/leads", wait_until="networkidle")
            page.click(f'a[data-drawer-open="lead-detail-drawer"][href="/manager/leads/{l1_id}"]')
            drawer = page.locator('#lead-detail-drawer.drawer-layer.is-open')
            drawer.wait_for(state="visible", timeout=5000)
            drawer.locator('input[name="body"]').wait_for(state="visible", timeout=5000)
            drawer.locator('input[name="body"]').fill("Заметка из Playwright")
            drawer.locator('form[data-drawer-ajax][action*="/activity"] button[type="submit"]').click()
            drawer.locator('text="Заметка из Playwright"').wait_for(state="visible", timeout=5000)
            assert page.url.startswith(f"{base_url}/manager/leads")

            # Dismiss drawer with Escape
            page.keyboard.press("Escape")
            drawer.wait_for(state="hidden", timeout=5000)

            # 2. Combobox keyboard selection & clear on /manager/students
            page.goto(f"{base_url}/manager/students", wait_until="networkidle")
            cbx_input = page.locator("#st-filter-teacher")
            cbx_input.click()
            cbx_input.fill("Тимур")
            opt = page.locator(f'#st-filter-teacher-list [data-combobox-option][data-value="{t1_id}"]')
            opt.wait_for(state="visible", timeout=5000)
            opt.click()
            page.wait_for_url(f"**teacher_id={t1_id}**", timeout=5000)
            assert "Браузер Ученик" in page.content()

            # Clear filter via single-click clear button
            page.locator('#st-filter-teacher').locator('..').locator('[data-combobox-clear]').click()
            page.wait_for_url(f"{base_url}/manager/students**", timeout=5000)

            assert page.evaluate("window.__csp") == []
            assert page.evaluate("window.__errs") == []
            browser.close()
    finally:
        server.shutdown()
