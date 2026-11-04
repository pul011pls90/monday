"""The ОРТ logarithm practice pack (kept apart from test_app.py, reuses its app and helpers)."""
from test_app import APP, client, login, ok


def test_ort_logs_pack_starts_and_hands_in():
    from monday.models import Question, Work
    with APP.app_context():
        qs = Question.query.filter_by(source="ort_logs_practice_2026").all()
        assert len(qs) == 30 and all(q.exams == ["ORT"] and q.skill.code in ("log_def", "log_props") for q in qs)
        assert all(q.answer_type == "choice" and len(set(q.options)) == 5 and 0 <= int(q.correct) < 5 for q in qs)
        w = Work.query.filter_by(title="ОРТ Математика · Логарифмы (Monday)").first()
        assert w.category == "thematic" and w.format == "ort" and w.time_limit_min == 45 and not w.calculator
        wid, items = w.id, w.current_version.items
    assert len(items) == 30
    c = login(client(), "student@monday.kg", "student123")
    run = c.post(f"/works/{wid}/start").headers["Location"]
    body = ok(c, run).data.decode()
    assert "log_" in body and 'id="question-29"' in body
    r = c.post(run, data={"q0": items[0]["correct"], "q29": items[29]["correct"]})
    assert "/result" in r.headers["Location"]
