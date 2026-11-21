"""Stage 1 tests: .mgr scoping, zero leakage to student pages, and shared UI macro rendering."""
import os
import tempfile

from flask import render_template_string
from flask_migrate import upgrade

from config import Config
from monday.extensions import db
from monday.models import User


def _make_app():
    tmp = tempfile.mkdtemp()

    class Stage1UiConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = True
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "stage1.db") + "?check_same_thread=False"
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")

    from monday import create_app

    app = create_app(Stage1UiConfig, seed_if_empty=False)
    with app.app_context():
        upgrade()
    return app


def _seed(app, email: str, name: str, role: str, pw: str = "StrongPass12!") -> int:
    with app.app_context():
        u = User(email=email, name=name, role=role, is_approved=True, is_blocked=False)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, email: str, pw: str = "StrongPass12!"):
    login_html = client.get("/login").get_data(as_text=True)
    import re
    m = re.search(r'<input[^>]*name="csrf_token"[^>]*value="([^"]+)"', login_html)
    assert m
    resp = client.post("/login", data={"email": email, "password": pw, "csrf_token": m.group(1)})
    assert resp.status_code in (200, 302)


def test_mgr_scope_applied_only_to_manager_and_academic_pages():
    app = _make_app()
    _seed(app, "sup@example.com", "Supervisor", "supervisor")
    _seed(app, "stu@example.com", "Student", "student", pw="StudentPw1!")

    # Student pages never get body class="mgr" and never load manager.css
    c_stu = app.test_client()
    _login(c_stu, "stu@example.com", pw="StudentPw1!")
    for path in ("/home", "/sessions", "/profile", "/support"):
        html = c_stu.get(path, follow_redirects=True).get_data(as_text=True)
        assert 'class="mgr"' not in html
        assert "css/manager.css" not in html

    # Manager and Academic pages get body class="mgr" and load manager.css
    c_sup = app.test_client()
    _login(c_sup, "sup@example.com")
    for path in ("/manager", "/manager/leads", "/manager/pipeline", "/manager/finance", "/manager/audit", "/manager/account", "/academic/schedule"):
        html = c_sup.get(path).get_data(as_text=True)
        assert '<body class="mgr"' in html, f"Expected body.mgr on {path}"
        assert "css/manager.css" in html, f"Expected manager.css link on {path}"


def test_stage1_macros_render_all_shared_building_blocks():
    app = _make_app()
    template_src = """
    {% import "manager/_ui.html" as mui with context %}
    {% call mui.page_header("Лиды", "Поиск и обработка входящих заявок", back_href="/manager", back_label="К обзору") %}
      {{ mui.btn("Новый лид", variant="primary", icon_name="plus") }}
      {{ mui.btn("Воронка", href="/manager/pipeline", variant="secondary", icon_name="list") }}
      {{ mui.btn("Экспорт", variant="ghost") }}
    {% endcall %}
    <div class="mgr-kpi-grid">
      {{ mui.kpi("Новые лиды", 14, "всего: 120", tone="accent", href="/manager/leads?status=new") }}
      {{ mui.kpi("Просрочка SLA", 3, "требуют ответа", tone="bad") }}
      {{ mui.kpi("На сегодня", 5, "звонки и пробные", tone="warn") }}
      {{ mui.kpi("Активные", 48, "без замечаний", tone="neutral") }}
    </div>
    {{ mui.filter_tabs([
      {"label": "Все", "href": "/manager/leads", "active": true, "count": 120},
      {"label": "Новый", "href": "/manager/leads?status=new", "active": false, "count": 14}
    ], aria_label="Этапы") }}
    <div>
      {{ mui.badge("Новый", tone="accent", dot=true) }}
      {{ mui.badge("SLA 42м", tone="bad", icon_name="clock") }}
      {{ mui.badge("Instagram", tone="neutral") }}
    </div>
    {% call mui.card() %}
      {{ mui.section_head("users", "Список лидов", count=14) }}
      {% call mui.table_wrap() %}
        <table class="mgr-table"><thead><tr><th>Имя</th></tr></thead><tbody><tr><td>Айдана</td></tr></tbody></table>
      {% endcall %}
    {% endcall %}
    {% call mui.empty("Пока пусто", "Создайте первого лида.") %}{{ mui.btn("Добавить", variant="secondary") }}{% endcall %}
    {% call mui.row_card("shield", "Безопасность", "Обновление пароля и сессий.") %}
      {% call mui.row_edit("Пароль задан", label="Изменить") %}
        <input class="input" type="password" name="new" required>
        <button class="mgr-btn mgr-btn--primary mgr-btn--sm" type="submit">Сохранить</button>
      {% endcall %}
    {% endcall %}
    """
    with app.test_request_context("/manager"):
        rendered = render_template_string(template_src)

    for marker in (
        'class="mgr-head"',
        'class="mgr-kpi-grid"',
        'class="mgr-kpi is-bad"',
        'class="mgr-kpi is-warn"',
        'class="mgr-dot mgr-dot--accent"',
        'class="mgr-tabs"',
        'class="mgr-tab is-active"',
        'class="mgr-badge mgr-badge--bad"',
        'class="mgr-btn mgr-btn--secondary mgr-btn--sm"',
        'class="mgr-btn mgr-btn--ghost mgr-btn--sm"',
        'class="mgr-card"',
        'class="mgr-section-head"',
        'class="mgr-table-wrap"',
        'class="mgr-table"',
        'class="mgr-empty"',
        'class="mgr-row-card"',
        'class="mgr-row-edit"',
        'Изменить',
    ):
        assert marker in rendered, f"Missing expected markup: {marker}"
