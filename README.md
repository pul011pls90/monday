# Monday

Math exam preparation for ORT, ENT, EGE, OGE, SAT and CSCA — a Flask web app with
student, teacher and admin areas, light (blue) and dark (green) themes, and a
translation layer ready for Kyrgyz, Kazakh, Uzbek, Tajik and English.

## Run it on a Mac

```bash
cd Monday
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Open http://127.0.0.1:5000. The first run creates `instance/monday.db` and fills it with demo data.

| Role    | Email                   | Password    |
|---------|-------------------------|-------------|
| Student | student@monday.kg       | student123  |
| Teacher | aibek@monday.kg         | teacher123  |
| Admin   | admin@monday.kg         | monday2026  |
| Teacher waiting for approval | new.teacher@monday.kg | teacher123 |

After updating the code, if the app says the database was created by an older
version, recreate it (demo data only — there are no real users yet):

```bash
flask --app app reset-db
```

Start over with fresh demo data:

```bash
flask --app app reset-db            # demo data
flask --app app reset-db --no-seed  # empty database
```

Run the checks (21 end-to-end tests covering every page and flow):

```bash
pip install pytest
python3 -m pytest -q
```

## What is inside

```
app.py                 entry point (python3 app.py)
config.py              settings: database, uploads, languages, Monday-test window
monday/
  __init__.py          app factory, template filters, CLI commands
  models.py            database tables (see the diagram at the top of the file)
  services.py          rules: mastery, forecast, rankings, homework states, publishing
  auth.py              login, registration, invite codes, theme and language switches
  student.py           student pages
  teacher.py           teacher pages
  admin.py             admin pages
  seed.py              demo data (answers are computed, so keys are correct)
  constants.py         exams, session modes, statuses — all labels translatable
  templates/           pages (Jinja); icons/ holds one SVG per icon
  static/css/monday.css  the design system: every colour is a token, light + dark
  static/js/app.js     small enhancements (theme switch, timer, editors, KaTeX)
  static/fonts, static/vendor/katex   bundled, so the site works without CDNs
translations/          language catalogs (ky, kk, uz, tg, en)
tests/test_app.py      end-to-end tests
```

## Content packs

Ready-made questions live in `monday/data/packs/` (one JSON file + a folder of figures per pack). On start-up
the app imports every pack the database doesn't have yet (once), so a fresh database — locally or on Render —
always gets them. Set `IMPORT_PACKS=0` to switch this off, or `PUBLISH_PACKS=0` to import as drafts for review.

```bash
flask --app app import-pack                      # import any pack that isn't in the database yet
flask --app app import-pack princeton_dsat_2025 --draft
```

`princeton_dsat_2025` — the Math part of both practice tests from *The Princeton Review Digital SAT Premium
Prep 2025* (Reading & Writing skipped): 132 questions with answers, explanations, skills and figures, and four
SAT collections (Module 1 + Module 2 Easier / Harder, 22 + 22 questions, 35 min per module). Questions marked
`adapted` in the JSON had blank choices or a missing graph in the ebook and were rebuilt — check them first.

A free-input answer may list several accepted values separated by `|` (e.g. `7|-7`, or `-5/9|-0.555|-0.556`).

## Pages

**Student:** login/registration (with invite code) → exam choice → Home (Mondays left,
forecast, time-based mode picker) · Skill map (search, exam route, focused practice) ·
Sessions (Franklin, Feynman, Darwin, Einstein; Tesla is marked "soon") · Collections
(search, filters, recommendations) → timed test → result with explanations ·
Homework (status, deadline, teacher comment) · Lab Journal (mistake reasons, resolve,
Darwin investigation) · Monday test + ranking by country / region / school and school duel ·
Profile (exam, goal, language, teacher codes, password).

**Teacher:** Overview (today's lessons, work to check, students who need attention) ·
Students table (name, grade, lesson time and days, progress, goal, invite code) →
student page (code + join link + WhatsApp/Telegram share, progress, weak skills,
mistakes, homework) · Works (draft / published / archived, versions, assign, copy,
archive) → editor (pick and order questions from the bank, publish new version) ·
Review (submitted / not submitted / checked) → check with comment · Question bank →
question editor (formula toolbar, image upload, choice or number answer, live preview) ·
Account.

**Admin:** approve teachers, moderate questions from new teachers, change roles.

## Content tree (Abilities Map)

Everything hangs on one tree: **Topic → Subtopic → Node** (Тема → Подтема → Навык),
table `content_node`. Questions, homework, tests and progress point to a node by its
permanent id, so new branches can be attached at any time without breaking results.

- The shared tree is looked after by the admin; teachers add their own branches under it
  (`owner_id`), visible to them and their linked students. Nothing is deleted — archived.
- Teacher page **Карта** (`/teacher/tree`): add subtopics/nodes, rename, set importance, archive.
- Question form: Topic → Subtopic → Node selects (or type a new branch), exams, difficulty,
  marks (weight), optional **material** (picture, reading passage, two columns, heading),
  question text up to 150 words, answers as options (up to 6) or **free input**
  (whole / fraction / decimal, optional rounding to tenths or hundredths).
- One question layout everywhere: with material — material left, question and answers right;
  without — one centred column.
- Works page groups everything by Topic → Subtopic (switch to a plain list with «Списком»).
- Timed tests save each answer as the student goes (`/attempts/<id>/save`); a reload brings
  the student back to the same answers with the same time left. Practice sessions answer,
  continue and record mistake reasons without reloading the page.

## How the key rules work

- **Invite codes.** Every row in a teacher's table gets a code like `MND-4K7Q` and a link
  `/join/MND-4K7Q`. A student enters the code at registration, onboarding or in the
  profile; the row then shows real progress instead of the manual percentage.
- **Versions.** Publishing a work freezes its questions into a version. Editing and
  re-publishing creates version 2; results already given stay attached to version 1.
- **Question moderation.** New teachers' questions go to the admin for approval; after
  20 approved questions a teacher publishes directly (`TRUSTED_TEACHER_THRESHOLD`).
- **Mastery.** A skill is mastered when the last 5–8 answers are at least 80% correct.
  The forecast maps skill accuracy onto the exam's score scale (`EXAMS` in constants.py).
- **Monday test.** Opens Mondays 19:00–24:00. For the demo it is open every day;
  set `MONDAY_TEST_ALWAYS_OPEN=0` to enforce the window.
- **Images.** Teachers upload PNG/JPG/WEBP up to 8 MB; files go to `instance/uploads/`.
  On a phone turned sideways, the picture sits left and the answers right.

## Translations

All interface text is wrapped for translation; Russian is the source language.
To translate, fill `msgstr` lines in `translations/<lang>/LC_MESSAGES/messages.po`
(Poedit makes this easy), then compile:

```bash
pybabel compile -d translations
```

After adding new text to templates or code, refresh the catalogs:

```bash
pybabel extract -F babel.cfg -k _l -o translations/messages.pot .
pybabel update -i translations/messages.pot -d translations
```

English already has the navigation translated as a working example. Question content
has its own `language` field, so teachers can write questions in any language.

## Moving to production later

- Database: set `DATABASE_URL` to PostgreSQL (Supabase works) — no code changes.
- Secret key: set `MONDAY_SECRET_KEY` (locally one is generated in `instance/`).
- Run with a production server, e.g. `pip install gunicorn && gunicorn "app:app"`.
- Keep `instance/` out of git — it holds the database, uploads and the secret key.

## Not built yet (space left for it)

AI tutor (Feynman explanations are already saved for it), photo check of scratch work,
Tesla interactive graphs, Monday Report sharing image, payments, mobile app wrapper.

## Put it online (Render, free)

1. Push this folder to a GitHub repository (the `instance/` folder with the database and secret key is not uploaded).
2. On render.com: **New → Blueprint**, pick the repository. `render.yaml` sets everything up.
3. After the first deploy the site lives at `https://monday-xxxx.onrender.com` with the demo accounts.

Free plan notes: the site sleeps after ~15 minutes without visitors (the first visit then takes ~50 s),
and the database is rebuilt from demo data on each restart. Add the Render address to the Desmos key's
allowed sites at desmos.com/my-api.
