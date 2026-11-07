"""Sign in with Google: a new Google account is a new student who sees the first steps; the same email is the same
account, so progress made once is there on the next Google sign-in and after the app restarts."""
from urllib.parse import parse_qs, urlparse

import pytest

from monday import auth
from test_app import APP, client, ok


@pytest.fixture
def google(monkeypatch):
    """A stand-in for Google: the person who picks their account on Google's page."""
    person = {"email": "aidana.google@gmail.com", "email_verified": True, "name": "Айдана Google"}
    seen = {}

    def post(url, fields):
        assert url == auth.GOOGLE_TOKEN and fields["code"] == "good-code" and fields["client_secret"] == "secret"
        seen["redirect_uri"] = fields["redirect_uri"]
        return {"access_token": "tok"}

    def get(url, token):
        assert url == auth.GOOGLE_USER and token == "tok"
        return dict(person)

    monkeypatch.setattr(auth, "_google_post", post)
    monkeypatch.setattr(auth, "_google_get", get)
    monkeypatch.setitem(APP.config, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setitem(APP.config, "GOOGLE_CLIENT_SECRET", "secret")
    return person, seen


def sign_in(c, code="good-code", **headers):
    r = c.get("/login/google", headers=headers)
    assert r.status_code == 302 and r.headers["Location"].startswith(auth.GOOGLE_AUTH)
    q = parse_qs(urlparse(r.headers["Location"]).query)
    assert q["client_id"] == ["client-id"] and q["scope"] == ["openid email profile"]
    return c.get(f"/login/google/callback?state={q['state'][0]}&code={code}", headers=headers), q


def test_button_shows_only_when_google_is_set_up(google):
    ok(client(), "/login", contains="Продолжить с Google")
    APP.config["GOOGLE_CLIENT_ID"] = ""
    try:
        assert "Продолжить с Google" not in client().get("/login").data.decode()
    finally:
        APP.config["GOOGLE_CLIENT_ID"] = "client-id"


def test_new_google_student_gets_first_steps_and_keeps_progress(google):
    from monday.models import Attempt, User, Work
    person, seen = google
    c = client()
    r, q = sign_in(c, **{"X-Forwarded-Proto": "https"})
    assert q["redirect_uri"] == ["https://localhost/login/google/callback"] == [seen["redirect_uri"]]  # https behind Render
    assert r.status_code == 302 and "/onboarding" in r.headers["Location"]          # the welcome page
    ok(c, "/onboarding", contains=["Расскажи о себе", "Мой уровень сейчас", "data-hero-bg"])
    with APP.app_context():
        u = User.query.filter_by(email=person["email"]).first()
        assert u.role == "student" and u.name == "Айдана Google" and u.profile and not u.profile.onboarded
    assert c.post("/onboarding", data={"exam": "ORT", "goal_score": "180", "language": "ru", "name": "Айдана Google", "grade": "11"}).status_code == 302
    with APP.app_context():
        w = Work.query.filter_by(title="Геометрия: площади").first()
        wid, first = w.id, w.current_version.items[0]
    run = c.post(f"/works/{wid}/start").headers["Location"]
    assert "/result" in c.post(run, data={"q0": first["correct"]}).headers["Location"]
    c.post("/logout")

    c2 = client()                                       # another day, another device: Google again
    r, _ = sign_in(c2)
    assert r.headers["Location"].endswith("/home")       # no first steps the second time
    from monday import create_app
    restarted = create_app(type("Again", (), {k: APP.config[k] for k in APP.config if k.isupper()}))
    with restarted.app_context():                       # a fresh start of the app on the same database
        u = User.query.filter_by(email=person["email"]).first()
        assert User.query.filter_by(email=person["email"]).count() == 1
        assert u.profile.exam == "ORT" and u.profile.goal_score == 180
        assert Attempt.query.filter_by(user_id=u.id).filter(Attempt.finished_at.isnot(None)).count() == 1


def test_existing_email_signs_into_that_account_and_nobody_else_gets_in(google):
    person, _ = google
    person.update(email="Student@Monday.kg")             # the demo student, written in other letters
    r, _ = sign_in(client())
    assert r.headers["Location"].endswith("/home")
    person.update(email="new.unverified@gmail.com", email_verified=False)
    c = client()
    r, _ = sign_in(c)
    assert r.headers["Location"].endswith("/login")
    assert "Google не подтвердил" in c.get("/login").data.decode()
    c = client()
    c.get("/login/google")
    assert c.get("/login/google/callback?state=forged&code=good-code").headers["Location"].endswith("/login")
    assert c.get("/home").status_code == 302                                    # still signed out
