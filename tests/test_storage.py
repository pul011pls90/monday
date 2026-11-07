"""Uploads in Supabase Storage: saved under the same names, opened through /uploads with a signed link, pack figures
from the repository. Supabase itself is replaced by a small fake of its REST API."""
import io
import json
import urllib.error

from monday import storage
from test_app import APP, client, login

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\x8d\xf1\x00\x00\x00\x00IEND\xaeB`\x82")


class FakeSupabase:
    def __init__(self):
        self.files, self.calls = {}, []

    def __call__(self, path, data=None, headers=None, timeout=20):
        self.calls.append(path)
        if path == "bucket":
            return b"{}"
        kind, _, rest = path.partition("/")
        if kind == "object" and rest.startswith("sign/"):
            name = rest[len("sign/uploads/"):]
            if name not in self.files:
                raise urllib.error.HTTPError(path, 400, "Object not found", {}, None)
            assert json.loads(data)["expiresIn"] == storage.SIGNED_SECONDS
            return json.dumps({"signedURL": f"/object/sign/uploads/{name}?token=t"}).encode()
        assert kind == "object" and rest.startswith("uploads/") and headers["x-upsert"] == "true"
        self.files[rest[len("uploads/"):]] = (data, headers["Content-Type"])
        return b"{}"


def with_supabase(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(storage, "_api", fake)
    monkeypatch.setitem(APP.config, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setitem(APP.config, "SUPABASE_SERVICE_KEY", "service-key")
    storage._signed.clear()
    return fake


def test_avatar_goes_to_supabase_and_opens_through_a_signed_link(monkeypatch):
    from monday.models import User
    fake = with_supabase(monkeypatch)
    c = login(client(), "student@monday.kg", "student123")
    c.post("/prefs/avatar", data={"next": "/profile", "avatar": (io.BytesIO(PNG), "me.png")}, content_type="multipart/form-data")
    with APP.app_context():
        path = User.query.filter_by(email="student@monday.kg").first().avatar_path
    assert path in fake.files and fake.files[path][1].startswith("image/")
    r = c.get(f"/uploads/{path}")
    assert r.status_code == 302 and r.headers["Location"] == f"https://proj.supabase.co/storage/v1/object/sign/uploads/{path}?token=t"
    assert r.headers["Cache-Control"] == "private, max-age=3600"   # shorter than the link itself
    c.get(f"/uploads/{path}")
    assert sum(p.startswith("object/sign/") for p in fake.calls) == 1   # signed once, then remembered
    assert c.get("/uploads/nothing-here.jpg").status_code == 404
    assert client().get(f"/uploads/{path}").status_code == 302 and "login" in client().get(f"/uploads/{path}").headers["Location"]
    c.post("/prefs/avatar", data={"remove": "1", "next": "/profile"})


def test_pack_figures_come_from_the_repository(monkeypatch):
    from monday.models import Question
    with APP.app_context():
        path = Question.query.filter(Question.image_path.like("packs/%")).first().image_path
    c = login(client(), "student@monday.kg", "student123")
    for supabase in (False, True):
        if supabase:
            fake = with_supabase(monkeypatch)
        r = c.get(f"/uploads/{path}")
        assert r.status_code == 200 and r.data[:4] == b"\x89PNG"
    assert not fake.calls
    assert c.get("/uploads/packs/../../config.py").status_code == 404


def test_supabase_database_settings():
    from config import _engine_options
    assert _engine_options("sqlite:///x.db") == {}
    assert "connect_args" not in _engine_options("postgresql+psycopg://u:p@db.example.com/monday")
    o = _engine_options("postgresql+psycopg://postgres.abc:p@aws-0-eu-central-1.pooler.supabase.com:6543/postgres")
    assert o["connect_args"] == {"prepare_threshold": None, "sslmode": "require"} and o["pool_size"] == 3


def test_new_secret_keys_and_a_broken_key_never_stop_the_site(monkeypatch):
    sent = []

    class Reply:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    def urlopen(req, timeout=20):
        sent.append(dict(req.header_items()))
        if "\n" in req.get_header("Apikey"):
            raise ValueError("Invalid header value")
        return Reply()

    monkeypatch.setattr(storage.urllib.request, "urlopen", urlopen)
    monkeypatch.setitem(APP.config, "SUPABASE_URL", "https://proj.supabase.co")
    with APP.app_context():
        monkeypatch.setitem(APP.config, "SUPABASE_SERVICE_KEY", "sb_secret_abc")
        storage.ensure_bucket()
        assert sent[-1]["Apikey"] == "sb_secret_abc" and "Authorization" not in sent[-1]
        monkeypatch.setitem(APP.config, "SUPABASE_SERVICE_KEY", "eyJhbGc")
        storage.ensure_bucket()
        assert sent[-1]["Authorization"] == "Bearer eyJhbGc"
        monkeypatch.setitem(APP.config, "SUPABASE_SERVICE_KEY", "sb_secret_a\nb")
        storage.ensure_bucket()   # logs a warning, doesn't raise


def test_pasted_line_breaks_are_dropped(monkeypatch):
    import importlib
    import config
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", " sb_secret_ab\ncd \n")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p%40x@host:5432/postgres\n")
    try:
        importlib.reload(config)
        assert config.Config.SUPABASE_SERVICE_KEY == "sb_secret_abcd"
        assert config.Config.SQLALCHEMY_DATABASE_URI == "postgresql+psycopg://u:p%40x@host:5432/postgres"
    finally:
        monkeypatch.undo()
        importlib.reload(config)
