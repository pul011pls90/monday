# Monday Academy — Technical & Security Audit (MVP-0)

**Audit Scope:** Read-only backend, database, authentication/authorization, deployment, and secrets audit of the Monday Academy Flask platform prior to MVP-1.
**Audit Date:** 2026-11-21
**Repository State:** Audited without modifying application code or database files.

---

## 1. Stack & Environment

### 1.1 Runtime & Library Versions
- **Production Python (Render):** `3.12.7` (`PYTHON_VERSION: "3.12.7"` in `render.yaml:10-11` and `render.production.yaml:19-20`).
- **Local Development venv:** `Python 3.14.8` (**2-minor-version drift** from Render production `3.12.7`).
- **Dependency Pinning (`requirements.txt` vs. local venv):**

| Package | `requirements.txt` Spec | Installed (Local venv) | Role |
|---|---|---|---|
| `Flask` | `>=3.1,<3.2` | `3.1.3` | Web framework |
| `Werkzeug` | `>=3.0` | `3.1.9` | WSGI / password hashing (`scrypt`) |
| `Jinja2` | *(transitive)* | `3.1.6` | Template engine |
| `Flask-SQLAlchemy` | `>=3.1,<3.2` | `3.1.1` | ORM integration |
| `SQLAlchemy` | `>=2.0` | `2.1.5` | ORM / DBAL |
| `Flask-Login` | `>=0.6,<0.7` | `0.6.3` | Session authentication |
| `Flask-WTF` | `>=1.2,<2` | `1.3.0` | Global `CSRFProtect` |
| `Flask-Babel` | `>=4.0,<5` | `4.0.0` | i18n (`ru`, `ky`, `kk`, `uz`, `tg`, `en`) |
| `Flask-Compress` | `>=1.15` | `1.25` | Gzip response compression |
| `gunicorn` | `>=22` | `26.2.0` | Production WSGI server |
| `psycopg[binary]` | `>=3.1` | `3.3.6` | PostgreSQL v3 driver |
| `Pillow` / `pillow-heif` | `>=10` / `>=0.18` | `13.0.0` / `1.8.1` | Image resizing & HEIC conversion |
| `reportlab` | `>=4.2` | `5.1.0` | Student results PDF export |

**Stack Gaps Observed:**
- **No lockfile** (`requirements.txt` uses unbounded upper limits like `SQLAlchemy>=2.0`, `gunicorn>=22`, `Pillow>=10`, allowing silent breaking upgrades on Render rebuilds).
- **No rate-limiting library** (`Flask-Limiter` absent).
- **No security headers middleware** (`Flask-Talisman` / custom CSP / HSTS / `X-Frame-Options` absent).
- **No OAuth client library** (Google OAuth 2.0 is hand-rolled with `urllib.request` in `monday/auth.py:89-179`).

### 1.2 Database Engine & ORM Setup (`config.py:22-54`)
- **Local Development:** SQLite at `instance/monday.db` when `DATABASE_URL` is unset.
- **Production:** PostgreSQL via `DATABASE_URL` (auto-rewrites `postgres://` and `postgresql://` to `postgresql+psycopg://`).
- **Connection Pooling (`config.py:33-43`):** `pool_pre_ping=True`, `pool_recycle=280`. When targeting Supabase (`supabase.co` / `supabase.com`), sets `pool_size=3`, `max_overflow=4`, `prepare_threshold=None`, and `sslmode=require`.
- **Supabase PostgREST Guard (`monday/__init__.py:180-189`):** Enables Row Level Security (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY`) with no policies on all `public` tables when connected to Supabase, blocking PostgREST exposure while allowing table-owner access.
- **String-Truncation Hook (`monday/models.py:994-1005`):** A global SQLAlchemy `before_flush` listener silently truncates any string exceeding its `String(N)` column limit to prevent PostgreSQL errors.
- **Media Storage (`monday/storage.py`):** Local disk (`UPLOAD_FOLDER`, `/var/data/uploads` on Render) or private Supabase Storage bucket with 2-hour signed URLs cached in process memory (`_signed`).

### 1.3 Schema Migration Tooling (Critical Gap)
- **No Flask-Migrate / Alembic.** There is no `migrations/` directory, `alembic.ini`, or versioned migration history.
- Schema changes are currently handled by **four separate ad-hoc runtime DDL paths**:
  1. `db.create_all()` + `_check_schema()` (`monday/__init__.py:151-224`): inspects missing columns and runs `ALTER TABLE ... ADD COLUMN` only for nullable columns or columns with scalar defaults. For any non-nullable column without a scalar default, it exits the process (`SystemExit`) and instructs the operator to run `flask --app app reset-db` (which calls **`db.drop_all()`**). Cannot rename columns, alter types, add/drop constraints, or manage indexes safely.
  2. `deploy_safety.ensure_deploy_safety_tables()` (`monday/deploy_safety.py:22-25`).
  3. `analytics_schema.ensure_analytics_schema()` (`monday/analytics_schema.py:9-36`).
  4. `roadmap.ensure_roadmap_schema()` (`monday/roadmap.py:42-72`) and `CourseUnit/CourseLesson/CourseMastery.__table__.create(checkfirst=True)` inside `course.build_course()` (`monday/course.py:174-175`), which executes DDL **inside a user `GET` request handler**.
- **Startup Side Effects:** `app.py:13` executes `create_app()` at module import time, running schema checks, taxonomy sync, content pack imports, and `cleanup.run_fixes()` before Gunicorn forks workers (relying on `preload_app = True` in `gunicorn.conf.py:12` to prevent worker races).

### 1.4 Render Deployment Configuration
- **Procfile:** None. Render uses Blueprint YAML files + `gunicorn.conf.py`.
- **`gunicorn.conf.py`:** `gunicorn app:app -c gunicorn.conf.py`, `workers = WEB_CONCURRENCY` (default `2`), `threads = GUNICORN_THREADS` (default `4`), `timeout = 60`, `preload_app = True`, with `post_fork` calling `db.engine.dispose(close=False)`.
- **`render.yaml` (Free Demo Service — `monday`):**
  - `plan: free`, `WEB_CONCURRENCY: 1`, **no attached PostgreSQL database or persistent disk** → uses ephemeral SQLite inside the container (wiped on every deploy/sleep/restart).
  - `COOKIE_SECURE` is unset (`0`), `SEED_DEMO` is unset (`1` — creates known demo accounts including `admin@monday.kg / monday2026`).
  - Kept awake via `.github/workflows/keep-awake.yml` curling `https://monday-k3zr.onrender.com/login` every 5 minutes.
- **`render.production.yaml` (Paid Production Blueprint — `monday-app` + `monday-db`):**
  - Region: `frankfurt`, web plan `0.5c-512mb`, `WEB_CONCURRENCY: 2`, `healthCheckPath: /login`, 5 GB persistent disk mounted at `/var/data` (`UPLOAD_FOLDER: /var/data/uploads`).
  - PostgreSQL `monday-db` (`0.1c-256mb`, `ipAllowList: []` private-network-only).
  - Env vars configured: `PYTHON_VERSION=3.12.7`, `DATABASE_URL` (from DB), `UPLOAD_FOLDER`, `MONDAY_SECRET_KEY` (`generateValue: true`), `MONDAY_DEBUG=0`, `COOKIE_SECURE=1`, `SEED_DEMO=0`, `ADMIN_EMAIL`/`ADMIN_PASSWORD` (`sync: false`), `MONDAY_TEST_ALWAYS_OPEN=0`.
  - **Missing env vars in `render.production.yaml`:** `DATA_FIXES=0` (critical — see Section 4.1), `ADMIN_API_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `DESMOS_API_KEY`, `ANALYTICS_IP_SALT`.

---

## 2. Current Data Models & Relationships

### 2.1 Complete Model Map (`monday/models.py`)

| Model (`__tablename__`) | Primary Key | Foreign Keys | Key Constraints / Relationships |
|---|---|---|---|
| `User` (`user`) | `id` (Int) | — | `email` UNIQUE; `role` (`student\|teacher\|assistant\|admin`); `is_approved`, `is_blocked`, `is_methodist`, `auth_provider`; 1:1 `StudentProfile`, 1:N `Visit`, `LoginEvent`, `ActivityDraft` |
| `StudentProfile` (`student_profile`) | `id` (Int) | `user_id → user.id` (UNIQUE, NOT NULL) | Exam, `exam_date`, `goal_score`, `grade`, `country`, `region`, `school`, `onboarded`, `daily_goal`, `session_presets` (JSON) |
| `ContentNode` / `Skill` (`content_node`) | `id` (Int) | `parent_id → content_node.id`, `owner_id → user.id` | Self-referential 3-level tree (`topic → subtopic → node`); `code` UNIQUE; `exams` (JSON); `owner_id=NULL` = shared tree |
| `Question` (`question`) | `id` (Int) | `author_id → user.id`, `skill_id → content_node.id`, `replaces_id → question.id`, `reviewed_by_id → user.id` | `answer_type` (`choice\|number\|written`), `status` (`draft\|pending\|published`), `source` (pack id string), `exams`/`options`/`material`/`rubric`/`tags` (JSON) |
| `Work` (`work`) | `id` (Int) | `author_id → user.id`, `node_id → content_node.id` | `kind` (`collection\|homework\|monday`), `draft_question_ids` (JSON); 1:N `WorkVersion` (cascade delete) |
| `WorkVersion` (`work_version`) | `id` (Int) | `work_id → work.id` (NOT NULL) | UNIQUE `(work_id, number)`; immutable `items` snapshot (JSON) and `layout` (JSON) |
| `StudentRecord` (`student_record`) | `id` (Int) | `teacher_id → user.id` (NOT NULL), `student_user_id → user.id` (nullable) | Teacher roster row; `invite_code` UNIQUE NOT NULL; 1:N `Assignment`, `Attendance` (cascade delete) |
| `Assignment` (`assignment`) | `id` (Int) | `work_id → work.id`, `teacher_id → user.id`, `record_id → student_record.id` | Homework assigned to a `StudentRecord`; `due_at`, `message`, `teacher_comment`, `checked_at` |
| `Attempt` (`attempt`) | `id` (Int) | `user_id → user.id`, `work_version_id → work_version.id`, `assignment_id → assignment.id` | Practice/test/homework/monday/bank/daily attempt; `plan` (JSON), `draft` (JSON); 1:N `AttemptAnswer` (cascade delete) |
| `AttemptAnswer` (`attempt_answer`) | `id` (Int) | `attempt_id → attempt.id`, `question_id → question.id`, `skill_id → content_node.id` | Per-question answer, `is_correct`, `mistake_reason`, `points`/`points_by`, `photo_path`, `resolved`, `hint_used` |
| `ReferenceSheet` (`reference_sheet`) | `id` (Int) | `user_id → user.id` | Student formula sheets; 1:N `SheetEntry` (cascade delete) |
| `SheetEntry` (`sheet_entry`) | `id` (Int) | `sheet_id → reference_sheet.id` | Formula text/image entry |
| `ContentTranslation` (`content_translation`) | `id` (Int) | `question_id → question.id` (`ON DELETE CASCADE`) | UNIQUE `(question_id, lang)`; `src_hash`, `data` (JSON) |
| `BankState` (`bank_state`) | `id` (Int) | `user_id → user.id`, `question_id → question.id` | UNIQUE `(user_id, question_id)`; per-question bank bookmark/tries/time |
| `Attendance` (`attendance`) | `id` (Int) | `record_id → student_record.id` | UNIQUE `(record_id, day)`; `present\|late\|absent` |
| `DailyPick` (`daily_pick`) | `id` (Int) | `teacher_id → user.id` (nullable), `question_id → question.id` | UNIQUE `(teacher_id, day, question_id, exam)` |
| `DailyAnswer` (`daily_answer`) | `id` (Int) | `user_id → user.id`, `pick_id → daily_pick.id` | UNIQUE `(user_id, pick_id)` |
| `AppMeta` (`app_meta`) | `key` (Str 40) | — | Key-value flags for taxonomy version, imported packs, and `cleanup.py` fixes |
| `Report` (`report`) | `id` (Int) | `author_id → user.id`, `question_id → question.id`, `node_id → content_node.id`, `handled_by_id → user.id` | Error reports on questions/skills |
| `ActivityDraft` (`activity_draft`) | `id` (Int) | `user_id → user.id` (`ON DELETE CASCADE`) | UNIQUE `(user_id, activity_type)`; autosave/resume state |
| `ClientOp` (`client_op`) | `id` (Int) | `user_id → user.id` (`ON DELETE CASCADE`) | UNIQUE `(user_id, op_id)`; client idempotency log |
| `MaintenanceState` (`maintenance_state`) | `id` (Int) | `updated_by_id → user.id` (`ON DELETE SET NULL`) | Singleton maintenance banner state |
| `MaintenanceLog` (`maintenance_log`) | `id` (Int) | — *(none)* | Audit log of maintenance changes |
| `RoadmapMilestone` (`roadmap_milestone`) | `id` (Int) | — | UNIQUE `(exam, key)`; 1:N `RoadmapNode` (cascade delete) |
| `RoadmapNode` (`roadmap_node`) | `id` (Int) | `milestone_id → roadmap_milestone.id` (`ON DELETE CASCADE`) | `key` UNIQUE; `skill_ids_json` (JSON) |
| `RoadmapProgress` (`roadmap_progress`) | `id` (Int) | `user_id → user.id` (`ON DELETE CASCADE`) | UNIQUE `(user_id, node_key)` — **no FK to `roadmap_node`** |
| `CourseUnit` (`course_unit`) | `id` (Int) | — | UNIQUE `(exam, slug)`; 1:N `CourseLesson` (cascade delete) |
| `CourseLesson` (`course_lesson`) | `id` (Int) | `unit_id → course_unit.id` (`ON DELETE CASCADE`) | UNIQUE `(unit_id, slug)`; `question_ids_json`, `skill_ids_json` |
| `CourseMastery` (`course_mastery`) | `id` (Int) | `user_id → user.id` (`ON DELETE CASCADE`) | UNIQUE `(user_id, lesson_key)` — **no FK to `course_lesson`** |
| `Visit` (`visit`) | `id` (UUID Str 36) | `user_id → user.id` (`ON DELETE SET NULL`) | Visitor analytics session; 1:N `PageView` |
| `PageView` (`page_view`) | `id` (UUID Str 36) | `visit_id → visit.id` (`ON DELETE CASCADE`) | Page hit within a visit |
| `LoginEvent` (`login_event`) | `id` (Int) | `user_id → user.id` (`ON DELETE CASCADE`) | Per-login audit record |

### 2.2 Entities Linked by Name, Email, Text, or String Keys Instead of Permanent Internal IDs
*(Note: No phone-number column exists in the schema.)*

1. **Google OAuth identity linked solely by `User.email` (`monday/auth.py:156-173`):**
   - `User` has **no immutable `google_sub` (OIDC subject) column**. Google sign-in performs `User.query.filter_by(email=email)` and logs directly into any matching account (including password-registered teachers or admins), mutating `auth_provider = "google"`. If a user changes their email in `/profile` (`student.py:1573`), their Google identity detaches.
2. **Unlinked `StudentRecord` roster rows identified only by free-text `name` (`monday/models.py:373-395`):**
   - Before a student redeems an invite code, `student_user_id` is `NULL`; no email or external identifier is stored.
   - `Assignment` points to `StudentRecord.id` (`record_id`), **not** `User.id`. If a teacher unlinks Student A from a `StudentRecord` and links Student B to the same row, `Assignment` rows remain attached to the record while historical `Attempt` rows still belong to Student A (`Attempt.user_id`), splitting assignment ownership from attempt history.
3. **`RoadmapProgress.node_key` (`monday/models.py:839`):**
   - References `RoadmapNode.key` as a plain `String(80)` with no foreign key. Renaming a node key silently orphans student completion history.
4. **`CourseMastery.lesson_key` (`monday/models.py:896`, `monday/course.py:200,510`):**
   - Stores a synthetic composite slug `f"{unit.slug}:{lesson.slug}"` with no FK to `course_lesson.id`. Renaming either slug silently loses student mastery progress.
5. **`MaintenanceLog.actor` & `MaintenanceState.updated_by_name` (`monday/models.py:748,772`):**
   - `MaintenanceLog` has no `user_id` FK and records only a free-text `actor` name/email string.
6. **Content pack synchronization matched by text/title (`monday/packs.py:59,126-145`):**
   - `_foreign_questions()` matches borrowed questions by `(Question.text, Question.correct)`.
   - `sync_pack()` matches existing questions by `(Question.explanation, Question.correct)` and collections by `Work.title` rather than a persisted external `pack_item_id`. Editing an explanation or title breaks idempotent pack syncing and creates duplicate/orphaned questions.
7. **Startup cleanup matched by hardcoded emails & names (`monday/cleanup.py:16-17,46,53,157,179,188,255,330,353`):**
   - `cleanup.py` identifies accounts/records via email literals (`student@monday.kg`, `aibek@monday.kg`, `admin@monday.kg`), email regex `^student\d+@monday\.kg$`, and hardcoded display names (`DEMO_UNLINKED_RECORDS`, `DEMO_COLLECTIONS`).
8. **JSON ID arrays without referential integrity:**
   - `Work.draft_question_ids`, `Attempt.plan`, `RoadmapNode.skill_ids_json`, `CourseLesson.question_ids_json`, and `CourseLesson.skill_ids_json` store integer IDs inside `Text`/`JSONText` columns with no DB foreign-key constraints.
9. **Other minor schema hygiene issues:**
   - `DailyPick` has `UniqueConstraint("teacher_id", "day", "question_id", "exam")` (`models.py:622`), but in PostgreSQL `NULL != NULL` in unique indexes, so multiple auto-picked rows (`teacher_id=NULL`) or all-exam picks (`exam=NULL`) can collide/duplicate under concurrency.
   - Newer models (`ActivityDraft`, `ClientOp`, `MaintenanceState`, `MaintenanceLog`, `Roadmap*`, `Course*`) use deprecated `default=datetime.utcnow` instead of `utcnow`.

---

## 3. Authentication & Authorization Audit

### 3.1 Standard Login, Registration & Session Management
- **Password Hashing:** `User.set_password()` uses Werkzeug's `generate_password_hash` (`scrypt` default in Werkzeug 3.1) — strong. Minimum password length is 8 characters (`auth.py:196`, `student.py:1589`).
- **Missing Brute-Force / Rate-Limit Controls:** Zero rate limiting or account lockout on `POST /login`, `POST /register`, `GET /join/<code>`, or `POST /profile` (`action=join`).
- **Email Enumeration:** `POST /register` explicitly reveals whether an email exists (`"Этот email уже зарегистрирован."` at `auth.py:199`). No email verification is required at registration.
- **Session & Remember-Me Weaknesses (`config.py:118-123`):**
  - `SESSION_COOKIE_HTTPONLY = True`, `REMEMBER_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE = "Lax"`.
  - `REMEMBER_COOKIE_SAMESITE` is **not set** explicitly.
  - `PERMANENT_SESSION_LIFETIME` and `REMEMBER_COOKIE_DURATION` are **not configured** → Flask-Login's remember cookie defaults to **365 days**.
  - `login_manager.session_protection` is left at `"basic"` (not `"strong"`), and `session.clear()` is not called before `login_user()` on login/registration.
  - **No session invalidation on password change/reset:** `User.get_id()` returns bare `str(self.id)` with no `session_token` / `password_version`. Changing or resetting a password (`student.py:1592`, `admin.py:228`, `teacher.py:511`) does **not** revoke active sessions or 365-day remember cookies.
  - **Temporary passwords transmitted via cookie-backed flash messages:** `admin.py:230` and `teacher.py:513` flash plaintext temporary passwords (`temporary_password()` uses 10 chars from a 31-char alphabet, ~49.5 bits), which are stored inside the client-side Flask session cookie (signed, **not encrypted** — readable in cleartext by anyone inspecting the cookie/browser storage) and never expire or force rotation.
- **Open Redirect Bypass (`auth.py:28-31`, `content_i18n.py:260`):**
  - `_safe_next(target)` checks `urlparse(target).netloc == "" and target.startswith("/")`. Inputs like `/\evil.com` pass this check in Python `urlparse` (`netloc == ""`) while modern browsers normalize `\` to `/` and redirect off-site to `https://evil.com`.
- **Missing Security Headers:** No `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, or `Referrer-Policy` headers are set anywhere in the application.

### 3.2 Google OAuth Audit (`monday/auth.py:89-179`)
- **Strengths:** Generates a 24-byte random `state` stored in session to prevent login CSRF; validates `info.get("email_verified")` before signing in; sets `prompt=select_account`; never auto-creates teacher/admin accounts.
- **Vulnerabilities & Gaps:**
  1. **Account takeover / silent elevation via email-only matching (`auth.py:156-173`):** Matching solely on `email` with no `google_sub` allows Google sign-in into existing password-protected **admin or teacher** accounts, and overwrites `user.auth_provider = "google"`.
  2. **Forced 365-day persistence (`auth.py:173`):** Hardcodes `login_user(user, remember=True)` with no user opt-in — dangerous on shared school/academy computers.
  3. **No PKCE (`code_challenge`) and no `id_token` / `nonce` verification:** Relies only on server-side `client_secret` exchange and `/userinfo` fetch.
  4. **Silent misconfiguration edge case:** `google_login` checks `GOOGLE_CLIENT_ID` (`auth.py:120`) but not `GOOGLE_CLIENT_SECRET`, allowing OAuth flow initiation even if the secret is missing.

### 3.3 Server-Side Role & Permission Audit (All ~154 Routes Reviewed)
Overall, blueprint decorators (`@student_required`, `@teacher_required`, `@admin_required`, `@staff_required`, `@reviewer_required` in `monday/access.py`) and object-ownership helpers (`_own_attempt`, `_own_assignment`, `_own_record`, `_own_work`, `_own_question`, `_own_bank_attempt`) cover the vast majority of routes. **The following server-side authorization gaps were identified:**

| Severity | Route / Endpoint | Location | Issue |
|---|---|---|---|
| **High** | `GET /uploads/<path:filename>` | `monday/__init__.py:132-146` | Protected only by `@login_required` — **no per-object ownership check**. Any logged-in student who knows/guesses a filename can download other students' private written-solution photos (`solutions/a<id>_<idx>_<hex>.jpg`), avatars, or formula sheet uploads, or obtain a 2-hour Supabase signed URL cached globally in `_signed`. Additionally, `packs/<pack>/<name>` does not validate `pack` against `packs.available()`. |
| **High** | `POST /api/course/complete` | `monday/course.py:480-543` | Trusts client-supplied `score` and `total` JSON fields with **zero server-side grading verification**. Any authenticated student can POST fabricated scores to mark any lesson or entire unit as `"mastered"`. |
| **Medium** | `GET /dev/visuals` | `monday/trig_formulas.py:468-475` | **Completely unauthenticated** QA/dev endpoint exposed in production; reads all SVG files from `static/img/examples` and `static/img/formulas` on every request and renders them publicly. |
| **Medium** | `GET /api/trigonometry-formulas` | `monday/trig_formulas.py:462-465` | **Unauthenticated** JSON endpoint (inconsistent with `/formulas/trigonometry`, which requires `@login_required`). |
| **Medium** | `GET/POST /teacher/questions/<id>/redact` | `monday/teacher.py:1315-1320` | Uses `@staff_required` and loads any `Question` by ID without checking `status == "published"` or authorship, allowing any assistant or teacher to read and submit redactions against another teacher's private draft question. |
| **Medium** | `POST /api/admin/maintenance` | `monday/deploy_safety.py:353-375` | Marked `@csrf.exempt`; compares `Authorization` header against `Bearer <ADMIN_API_TOKEN>` using `==` instead of constant-time `hmac.compare_digest()`. (Browser session branch does explicitly call `validate_csrf()`.) |
| **Low** | `GET /prefs/original` | `monday/content_i18n.py:256-267` | Mutates cookie state via `GET` (no CSRF check) and has the same `/\` open-redirect edge case. |
| **Low** | Analytics middleware | `monday/analytics_tracking.py:50-61,110-129` | Trusts leftmost `X-Forwarded-For` and raw `CF-IPCountry` / `X-Country-Code` headers directly, allowing clients to spoof IP hashes and GeoIP data in `/admin/analytics`. |

### 3.4 Teacher-Generated Student Linking Code Audit
Files: `monday/models.py:366-390`, `monday/auth.py:34-55,222-240`, `monday/teacher.py:401-528`, `monday/student.py:1497-1499,1600-1614`.

| Risk Dimension | Current Implementation | Verdict & Impact |
|---|---|---|
| **Entropy / Brute-Force** | `MND-XXXX` using 4 chars from 32-char `INVITE_ALPHABET` = $32^4 = 1{,}048{,}576$ possible codes (**20 bits**). **Zero rate limiting** on `GET /join/<code>`, `POST /profile` (`action=join`), and `POST /onboarding`. | **CRITICAL:** Trivial to brute-force. With 100 unlinked roster rows, ~5,000 requests suffice to find a valid code. An attacker can hijack a student's roster slot, view teacher-assigned homework, and access private teacher skill branches and daily picks. |
| **Information Disclosure Oracle** | Unauthenticated `GET /join/<code>` (`auth.py:222-239`) returns different redirects/messages for valid vs. invalid codes and **leaks `record.teacher.name`** even when the code is already claimed. Authenticated `link_invite_code()` distinguishes nonexistent vs. already-used vs. already-linked. | **HIGH:** Allows unauthenticated enumeration of active codes and teacher rosters. |
| **Expiration** | No `invite_expires_at` / TTL column exists on `StudentRecord`. | **HIGH:** Unused codes remain valid indefinitely unless manually rotated. |
| **Revocation** | Teachers can rotate an unlinked code (`POST /teacher/students/<id>/code`) or unlink (`POST /teacher/students/<id>/unlink`, which also rotates). However, `invite_code` is `NOT NULL`, so a code **cannot be disabled/revoked without creating a new active code**. | **MEDIUM:** No way to disable self-joining on an unlinked roster row. |
| **Reuse Risk** | Linked codes reject other students (`auth.py:44-45`). **HOWEVER**, when a student self-deletes their account (`_delete_account()` at `student.py:1611-1612`), it clears `rec.student_user_id = None` **without rotating `rec.invite_code` or clearing `rec.linked_at`**. | **HIGH:** Account deletion silently re-activates the student's old invite code for reuse by anyone who previously saw it. |
| **Collision Risk** | `invite_code` has `unique=True`, but `new_invite_code()` does not check for duplicates or retry on `IntegrityError`. | **MEDIUM:** Birthday collision probability reaches 50% at ~1,200 `StudentRecord` rows, causing unhandled 500 errors on teacher student creation/code rotation. |

---

## 4. Data Safety & Secrets

### 4.1 Hardcoded Passwords, Keys & Secrets Found

| Severity | File & Line | Finding | Impact |
|---|---|---|---|
| **CRITICAL** | `monday/cleanup.py:325-382` | `ensure_showcase_student()` runs inside `run_fixes()` whenever `DATA_FIXES=1` (the **default** in `config.py:103`, and **not overridden** in `render.production.yaml`). Even with `SEED_DEMO=0`, it **creates `student@monday.kg` with hardcoded password `student123`** in production! Additionally, `remove_extra_teachers()` (`cleanup.py:235-322`) deletes all teacher accounts except `aibek@monday.kg` (or the first approved teacher) on first execution. | Active hardcoded backdoor account in production + destructive teacher-deletion logic running outside seed mode. |
| **HIGH** | `config.py:76` | Hardcoded Desmos API key fallback: `DESMOS_API_KEY = os.environ.get("DESMOS_API_KEY", "9daae6e774bc4c34b328b6599b77571c")`. | API key exposed in git history/source; should be env-only (with safe non-secret default or disabled calculator if unset). |
| **MEDIUM** | `monday/seed.py:400-437` | Hardcoded demo credentials: `admin@monday.kg / monday2026`, teachers `teacher123`, `assistant@monday.kg / assistant123`, students `student123`. | Because `render.yaml` leaves `SEED_DEMO=1`, the public free Render demo (`monday-k3zr.onrender.com`) runs with a publicly known admin password. |
| **MEDIUM** | `monday/analytics_tracking.py:69` | `ANALYTICS_IP_SALT` falls back to `SECRET_KEY` (reusing the session-signing key for analytics hashing) or hardcoded `"monday-salt"`. | Key-purpose conflation / predictable salt if misconfigured. |
| **LOW** | `config.py:14-17` | Local `instance/secret_key` file created without restricting permissions (`0600`). | Readable by other local OS users under default umask. |
| **LOW** | `.github/workflows/keep-awake.yml:19` | Public Render URL `https://monday-k3zr.onrender.com/login` hardcoded in workflow. | Exposes demo instance endpoint in repo history. |

### 4.2 Safe Staging Environment & Render Database Backup/Restore Runbook

#### Creating an Isolated Staging Environment on Render
1. **Separate Infrastructure (Never share DB, disk, or bucket with production):**
   - Create a dedicated `render.staging.yaml` (or a separate Render Blueprint/Environment pointing to a `staging` git branch) provisioning:
     - Web service `monday-staging` (same `PYTHON_VERSION: 3.12.7` and `gunicorn app:app -c gunicorn.conf.py` as production).
     - Dedicated PostgreSQL instance `monday-staging-db` (`ipAllowList: []` by default).
     - Separate upload storage: either a dedicated Render disk (`/var/data/uploads`) or a separate Supabase Storage bucket (`SUPABASE_BUCKET=uploads-staging`) with separate credentials.
2. **Staging Environment Variables:**
   - `MONDAY_SECRET_KEY`: newly generated (`generateValue: true`), **distinct from production**.
   - `DATABASE_URL`: bound strictly to `monday-staging-db`.
   - `COOKIE_SECURE=1`, `MONDAY_DEBUG=0`, `SEED_DEMO=0`, `DATA_FIXES=0` (once `cleanup.py` is gated/retired).
   - `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_API_TOKEN`: staging-only credentials (`sync: false`).
   - `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: staging OAuth client (or add the staging callback URL `https://<staging-host>/login/google/callback` in Google Cloud Console).
   - `ANALYTICS_IP_SALT` and `DESMOS_API_KEY`: explicitly set via Render dashboard.
   - Optional: enable `MONDAY_TEST_ALWAYS_OPEN=1` in staging for QA.
3. **Data Sanitization for Staging:**
   - Never copy raw production user PII (emails, password hashes, student photos) directly into staging unless anonymized. If cloning production data to test a migration, scrub `user.email`, `user.password_hash`, `user.name`, `student_record.notes`, and `login_event`/`visit` tables immediately after restore.

#### Database Backups & Restores on Render PostgreSQL
1. **Automated Backups (Render Managed):**
   - On Render paid Postgres plans (`0.1c-256mb` and above), enable/verify **Daily Automated Backups** (and Point-in-Time Recovery if upgrading plan tier) in the Render Dashboard → `monday-db` → **Backups**.
   - Note: `render.production.yaml` currently sets `ipAllowList: []` (private network only), which is good for runtime security.
2. **Manual On-Demand Logical Backup (Before Every Schema Change or Deploy):**
   - Temporarily add your operator IP (`/32`) to `monday-db` → **Access Control** (or run from a Render one-off Shell attached to `monday-app` over the private internal network, which avoids exposing Postgres publicly).
   - Export a compressed custom-format dump:
     ```bash
     pg_dump "$DATABASE_URL" \
       --format=custom \
       --no-owner \
       --no-acl \
       --file="monday_backup_$(date -u +%Y%m%dT%H%M%SZ).dump"
     ```
   - Verify the archive integrity immediately:
     ```bash
     pg_restore --list monday_backup_<timestamp>.dump | head -n 40
     ```
   - Store encrypted backups off-Render (e.g., private S3/R2/GCS bucket with retention policy) and remove any temporary operator IP from `ipAllowList`.
3. **Media / Uploads Backup:**
   - **If using Render Disk (`/var/data/uploads`):** Render disks are **not** included in Postgres backups; enable Render Disk Snapshots or periodically sync `/var/data/uploads` to object storage (`tools/move_to_supabase.py --uploads /var/data/uploads` already exists for one-time migration to Supabase Storage).
   - **If using Supabase Storage:** Back up the private `uploads` bucket separately via Supabase Storage API/S3-compatible sync.
4. **Restore Procedure (Test on Staging First!):**
   - Enable maintenance mode before restoring production (`POST /api/admin/maintenance` or `/admin/maintenance`, per `docs/RELEASE_CHECKLIST.md`).
   - Restore into a clean target database (never overwrite a live DB in place without a fresh pre-restore dump):
     ```bash
     pg_restore \
       --dbname="$TARGET_DATABASE_URL" \
       --clean --if-exists \
       --no-owner --no-acl \
       --single-transaction \
       monday_backup_<timestamp>.dump
     ```
   - Verify row counts across critical tables (`user`, `student_record`, `assignment`, `attempt`, `attempt_answer`, `question`, `work`, `work_version`) and smoke-test `/api/site-status`, `/api/version`, `/login`, and student/teacher views before disabling maintenance mode.

---

## 5. Existing Working Features to Protect

Any MVP-1 refactoring (migrations, auth hardening, invite-code overhaul) must preserve the following live routes, templates, and service contracts:

### 5.1 Student Registration, Login, OAuth, Linking & Onboarding
- **Routes (`monday/auth.py`, `monday/student.py`):**
  - `GET /` (`auth.index`), `GET/POST /login` (`auth.login`), `POST /logout` (`auth.logout`)
  - `GET /login/google` (`auth.google_login`), `GET /login/google/callback` (`auth.google_callback`)
  - `GET/POST /register` (`auth.register`), `GET /join/<code>` (`auth.join`), `GET /pending` (`auth.pending`)
  - `POST /prefs/theme`, `POST /prefs/lang`, `POST /prefs/avatar`, `GET /prefs/original` (`content_i18n.toggle_original`)
  - `GET/POST /onboarding` (`student.onboarding`)
  - `GET/POST /profile` (`student.profile` — includes `action=join`, `action=profile`, `action=field`, `action=email`, `action=password`, `action=delete`, `action=appearance`, `action=study`, `action=practice`, `action=privacy`)
- **Templates:**
  - `auth/welcome.html`, `auth/pending.html`
  - `student/onboarding.html`, `student/profile.html`
  - `base.html`, `layout.html`, `partials/profile_head.html`, `partials/site_footer.html`

### 5.2 Assignments / Homework (Student & Teacher Lifecycle)
- **Student Routes (`monday/student.py`):**
  - `GET /homework` (`student.homework` — calendar + todo/done grouping)
  - `GET /homework/<int:assignment_id>` (`student.homework_detail`)
  - `POST /homework/<int:assignment_id>/start` (`student.homework_start`)
  - Shared Timed Test & Submission Runner:
    - `GET/POST /attempts/<int:attempt_id>` (`student.attempt_run`)
    - `POST /attempts/<int:attempt_id>/save` (`student.attempt_save`)
    - `POST /attempts/<int:attempt_id>/alive` (`student.attempt_alive`)
    - `POST /attempts/<int:attempt_id>/next-module` (`student.attempt_next_module`)
    - `POST /attempts/<int:attempt_id>/photo` (`student.attempt_photo`)
    - `POST /attempts/<int:attempt_id>/assess/<int:idx>` (`student.attempt_assess`)
    - `GET /attempts/<int:attempt_id>/result` (`student.attempt_result`)
- **Teacher Routes (`monday/teacher.py`):**
  - `GET/POST /teacher/assign` (`teacher.assign`)
  - `POST /teacher/assignments/<int:assignment_id>/due` (`teacher.assignment_due`)
  - `GET /teacher/review` (`teacher.review`), `GET/POST /teacher/review/<int:assignment_id>` (`teacher.review_detail`)
  - `GET/POST /teacher/attempts/<int:attempt_id>/written` (`teacher.written_review`)
  - Works CRUD & Publishing: `/teacher/works`, `/teacher/works/new`, `/teacher/works/<id>/edit`, `/status`, `/duplicate`, `/delete`
  - Student Roster & Linking: `/teacher/students`, `/students/new`, `/students/<id>`, `/edit`, `/code`, `/reset-password`, `/unlink`, `/delete`, `/teacher/attendance`
- **Templates:**
  - Student: `student/homework.html`, `student/homework_detail.html`, `student/attempt.html`, `student/result.html`, `student/_review_steps.html`, `partials/session_bar.html`, `partials/tool_panes.html`, `partials/macros.html`
  - Teacher: `teacher/assign.html`, `teacher/review.html`, `teacher/review_detail.html`, `teacher/written_review.html`, `teacher/students.html`, `teacher/student_detail.html`, `teacher/_record_form.html`, `teacher/works.html`, `teacher/work_edit.html`, `teacher/dashboard.html`

### 5.3 Progress Tracking, Practice, Bank, Course & Exports
- **Student Progress & Practice Routes:**
  - Dashboard & Skill Map: `GET /home`, `GET /skills`, `POST /goal`, `POST /exam/switch` (`monday/student.py`)
  - Practice Sessions: `GET /sessions`, `POST /sessions/start/<mode>`, `GET/POST /sessions/<id>`, `GET /sessions/<id>/done`, `POST /sessions/custom`, `POST /sessions/<id>/again`, `POST /sessions/<id>/retry`, `POST /sessions/presets`, `POST /sessions/clear` (`monday/student.py`)
  - Collections & Monday Test: `GET /collections`, `GET /works/<id>`, `POST /works/<id>/start`, `GET /monday`, `POST /monday/start` (`monday/student.py`)
  - Mistake Journal: `GET /journal`, `GET /journal/attempt/<id>`, `POST /journal/attempt/<id>/blank-reason`, `POST /journal/attempt/<id>/practice`, `POST /journal/<answer_id>` (`monday/student.py`)
  - Question Bank: `GET /bank/`, `POST /bank/start`, `GET /bank/s/<id>`, `GET /bank/s/<id>/sheet`, `POST /bank/s/<id>/check`, `POST /bank/s/<id>/reveal`, `POST /bank/mark`, `POST /bank/time` (`monday/bank.py`)
  - Daily Questions: `GET /daily/`, `POST /daily/<pick_id>/answer` (`monday/daily.py`)
  - SAT/CSCA Course & Roadmap: `GET /roadmap/<exam>/<unit_slug>/<lesson_slug>`, `POST /api/course/check`, `POST /api/course/complete` (`monday/course.py`); `POST /api/roadmap/node/<node_key>/complete`, `POST /api/roadmap/goal`, `POST /api/roadmap/checklist` (`monday/roadmap.py`)
  - Deploy-Safety Autosave/Resume: `POST /api/activity/save`, `GET /api/activity/latest`, `POST /api/activity/complete` (`monday/deploy_safety.py`)
  - Exports: `GET /profile/export.csv`, `GET /profile/export.pdf` (`monday/student.py`, `monday/results_pdf.py`)
- **Core Service Contracts:** `progress_summary()`, `skill_map()`, `skill_stats()`, `record_progress()`, `homework_state()`, `latest_attempt()`, `student_assignments()`, `grade_version_attempt()`, `open_mistakes()`, `mistake_breakdown()` (`monday/services.py`), and `attendance_summary()`, `score_trend()`, `class_dots()`, `homework_week()` (`monday/insights.py`).
- **Templates:**
  - `student/home.html`, `student/skills.html`, `student/_skills_roadmap.html`, `student/_course_overview.html`, `student/course_player.html`, `student/sessions.html`, `student/session.html`, `student/session_done.html`, `student/collections.html`, `student/work_detail.html`, `student/monday.html`, `student/bank.html`, `student/bank_play.html`, `student/bank_sheet.html`, `student/daily.html`, `student/journal.html`, `student/journal_review.html`.

---

## 6. Prioritized List of Blockers to Fix Before MVP-1

### P0 — Critical Blockers (Must Fix Before Production / MVP-1 Launch)

1. **Remove / Gate `cleanup.py` Production Backdoor & Destructive Fixes (`monday/cleanup.py:235-382`, `render.production.yaml`)**
   - `ensure_showcase_student()` currently creates `student@monday.kg / student123` on every DB with `DATA_FIXES=1` (default, even when `SEED_DEMO=0`), and `remove_extra_teachers()` deletes teacher accounts.
   - **Fix:** Immediately gate demo-only fixes (`remove_demo_students`, `remove_extra_teachers`, `ensure_showcase_student`, `rename_demo_*`) behind explicit opt-in or remove them from `run_fixes()`, and set `DATA_FIXES=0` in `render.production.yaml`. Audit any existing production DB and delete/lock `student@monday.kg`.

2. **Harden Teacher-Generated Student Invite Codes (`monday/models.py:366-390`, `monday/auth.py:34-55,222-240`, `monday/student.py:1611`)**
   - Increase entropy from 20 bits (4 chars) to at least **40–64 bits** (e.g., 8+ chars or 128-bit URL token for `/join/<token>` + collision-retry loop).
   - Add `invite_expires_at` (e.g., 7–14 day TTL) and explicit revocation (`invite_code` nullable or `invite_revoked_at`).
   - Add rate limiting on `/join/<code>`, `/login`, `/register`, and `/profile` (`action=join`).
   - Remove the teacher-name disclosure oracle on unauthenticated `GET /join/<code>` (or reject already-linked/expired codes generically without revealing teacher PII).
   - Rotate/clear `rec.invite_code` and `rec.linked_at` inside `_delete_account()` (`monday/student.py:1611-1612`) so deleted students' old codes cannot be reused.

3. **Fix Cross-User File Access (IDOR) on `/uploads/<path:filename>` (`monday/__init__.py:132-146`)**
   - Enforce per-file authorization before serving or generating Supabase signed URLs:
     - `solutions/a<attempt_id>_...`: allow only the attempt's owning student, their linked teacher(s), or admins.
     - Question figures / pack figures: validate `pack in packs.available()` and allow authenticated users.
     - Reference sheet images: allow only the sheet owner (or admin).
     - Avatars: allow authenticated users (or public-safe scope) without exposing arbitrary disk/bucket paths.

4. **Introduce Versioned Database Migrations (Flask-Migrate / Alembic)**
   - Replace `db.create_all()`, `_check_schema()` (`SystemExit` / `reset-db`), `ensure_analytics_schema()`, `ensure_roadmap_schema()`, and request-time DDL in `course.build_course()` with Alembic migrations run as a pre-deploy release command (`flask db upgrade`) instead of inside `create_app()`.

5. **Fix Google OAuth Identity Binding & Account Takeover Vector (`monday/auth.py:156-178`, `monday/models.py:50`)**
   - Add a unique `google_sub` column on `User` and bind OAuth logins by `sub`, not mutable `email`.
   - Block silent email-based auto-linking into existing password-authenticated **admin/teacher/assistant** accounts (require explicit verified linking inside account settings).
   - Add PKCE (`code_challenge`) and OIDC `id_token` validation, and stop hardcoding `remember=True` unconditionally.

### P1 — High-Priority Blockers (Fix Before Opening to Real Schools / Scale)

6. **Server-Side Verification for Course Mastery (`monday/course.py:480-543`)**
   - Stop trusting client-submitted `score` and `total` on `POST /api/course/complete`; record graded answers server-side in `api_check_question()` and derive lesson/quiz mastery from server-stored results.

7. **Lock Down Unauthenticated Dev & API Endpoints (`monday/trig_formulas.py:462-475`)**
   - Gate `GET /dev/visuals` behind `@admin_required` (or disable when `MONDAY_DEBUG=0`).
   - Require `@login_required` on `GET /api/trigonometry-formulas` (consistent with `/formulas/trigonometry`).
   - Enforce publication/ownership check on `GET/POST /teacher/questions/<id>/redact` (`monday/teacher.py:1315-1320`).

8. **Session Security, Secret Hygiene & Rate Limiting (`config.py`, `monday/auth.py`, `monday/deploy_safety.py`)**
   - Remove hardcoded `DESMOS_API_KEY` fallback from `config.py:76` and move to env var.
   - Add `Flask-Limiter` (Redis or DB-backed across Gunicorn workers) on `/login`, `/register`, `/join/<code>`, `/profile` join, and API endpoints.
   - Add `User.session_version` (included in `get_id()`) and bump it on password change, admin/teacher password reset, and block — immediately revoking stolen cookies.
   - Set explicit `REMEMBER_COOKIE_DURATION` (e.g., 14–30 days), `REMEMBER_COOKIE_SAMESITE = "Lax"`, `session_protection = "strong"`, and call `session.clear()` before `login_user()`.
   - Stop putting plaintext temporary passwords in cookie-backed Flask `flash()` messages (render once in the POST response or deliver out-of-band, and require password change on first login).
   - Use `hmac.compare_digest()` for `ADMIN_API_TOKEN` in `deploy_safety.py:358`.
   - Fix `_safe_next()` (`auth.py:28`) and `toggle_original()` (`content_i18n.py:260`) to reject backslashes (`\` not in target) and `//`.

9. **Pin Dependencies & Align Python Versions (`requirements.txt`, `render.production.yaml`)**
   - Pin exact tested versions (or generate a `requirements.lock`) and align local development Python with Render's `3.12.7`.
   - Provision a dedicated staging environment (`render.staging.yaml`) and run a tested `pg_dump` + `pg_restore` drill before MVP-1.

### P2 — Medium-Priority Structural Fixes (Plan for MVP-1 / Early Post-MVP)

10. **Replace String-Key Entity Linkages with Foreign Keys (`monday/models.py`, `monday/packs.py`)**
    - Migrate `RoadmapProgress.node_key` → `node_id` FK (`roadmap_node.id`) and `CourseMastery.lesson_key` → `lesson_id` FK (`course_lesson.id`).
    - Add `actor_id` FK on `MaintenanceLog`.
    - Add a stable `external_id` / `pack_item_id` column on `Question` and `Work` so `packs.py` stops matching by `(explanation, correct)` and `title`.
    - Guard `StudentRecord` unlink/re-link behavior so existing `Assignment` rows cannot be inherited by a different student account.

11. **Add HTTP Security Headers & Fix Analytics Proxy-Header Trust**
    - Add `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security` (when `COOKIE_SECURE=1`), and an explicit CSP compatible with KaTeX/Desmos.
    - Use `request.remote_addr` (after `ProxyFix` resolves trusted proxy hops) instead of leftmost `X-Forwarded-For` in `monday/analytics_tracking.py:50-61`, and require a dedicated `ANALYTICS_IP_SALT` env var instead of falling back to `SECRET_KEY`.
    - Disable `SEED_DEMO` or lock down the public free Render demo (`monday-k3zr.onrender.com`) so known default admin credentials are not exposed publicly.
