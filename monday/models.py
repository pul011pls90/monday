"""Database models for Monday.

Overview
--------
ContentNode                       (Topic → Subtopic → Node tree, shared + teacher branches)
User ─┬─ StudentProfile           (exam, exam date, goal, region, school)
      ├─ Question (author)        (question bank, teacher-made)
      ├─ Work (author) ── WorkVersion (immutable snapshot of questions)
      ├─ StudentRecord (teacher's table row, linked to a student by invite code)
      ├─ Assignment (homework given to a StudentRecord)
      └─ Attempt ── AttemptAnswer (every answer a student gives)

Results always point to a WorkVersion, so re-publishing a corrected work never
changes scores that students already have.
"""
import json
import secrets
import string
import uuid
from datetime import date, datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    """Naive UTC timestamp (what the database stores)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JSONText(db.TypeDecorator):
    """Stores Python lists/dicts as JSON text (works on SQLite and PostgreSQL)."""

    impl = db.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value, dialect):
        return None if value is None else json.loads(value)


# --------------------------------------------------------------------------- users


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="student")  # student | teacher | assistant | sales_manager | supervisor | admin
    is_approved = db.Column(db.Boolean, nullable=False, default=True)  # teachers need approval
    language = db.Column(db.String(8), nullable=False, default="ru")
    theme = db.Column(db.String(8), nullable=False, default="light")  # light | dark | system
    prefs = db.Column(JSONText)  # personal settings from the profile: text size, motion, study days, practice options
    avatar_path = db.Column(db.String(255))  # profile picture, file name inside instance/uploads
    is_blocked = db.Column(db.Boolean, nullable=False, default=False)  # admin can block an account
    is_methodist = db.Column(db.Boolean, nullable=False, default=False)  # teacher who reviews assistants' questions
    auth_provider = db.Column(db.String(16), nullable=False, default="password")  # password | google
    google_sub = db.Column(db.String(64), unique=True, nullable=True, index=True)  # immutable Google OIDC subject ID
    session_version = db.Column(db.Integer, nullable=False, default=1)  # bumped on password change/reset or block
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)  # force password rotation on first login
    is_on_shift = db.Column(db.Boolean, nullable=False, default=True)  # manager CRM availability for auto-assignment
    login_count = db.Column(db.Integer, nullable=False, default=0)  # total successful sign-ins
    last_seen_at = db.Column(db.DateTime)  # updated at most every few minutes
    total_visits = db.Column(db.Integer, nullable=False, default=0)  # cached by daily analytics job
    average_visit_duration = db.Column(db.Integer, nullable=False, default=0)  # average seconds per visit
    legacy_access_until = db.Column(db.DateTime, nullable=True)  # grandfathered full bank access deadline for pre-Stage-4 unlinked students
    created_at = db.Column(db.DateTime, default=utcnow)

    profile = db.relationship("StudentProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    visits = db.relationship("Visit", back_populates="user", lazy="dynamic", passive_deletes=True)

    def pref(self, key, default=None):
        return (self.prefs or {}).get(key, default)

    def set_prefs(self, **values):
        prefs = dict(self.prefs or {})
        prefs.update(values)
        self.prefs = prefs  # reassign so the JSON column is saved

    def get_id(self):
        return f"{self.id}:{self.session_version or 1}"

    def invalidate_sessions(self):
        self.session_version = (self.session_version or 1) + 1

    def set_password(self, raw):
        if self.password_hash:
            self.invalidate_sessions()
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_teacher(self):
        return self.role in ("teacher", "admin")

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_assistant(self):
        return self.role == "assistant"

    @property
    def is_sales_manager(self):
        return self.role == "sales_manager"

    @property
    def is_supervisor(self):
        return self.role == "supervisor"

    @property
    def is_manager(self):
        return self.role in ("sales_manager", "supervisor", "admin")

    @property
    def is_crm_supervisor(self):
        return self.role in ("supervisor", "admin")

    def has_perm(self, perm: str) -> bool:
        from .access import has_permission
        return has_permission(self, perm)

    @property
    def can_review(self):
        """Reviews questions uploaded by assistants: admins and teachers marked as methodists."""
        return self.role == "admin" or (self.role == "teacher" and self.is_methodist)

    @property
    def initials(self):
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    @property
    def public_name(self):
        """How the author of shared content is signed for students: the platform for admins."""
        return "Monday Academy" if self.role == "admin" else self.name

    @property
    def first_name(self):
        return self.name.split()[0] if self.name else ""


class StudentProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), unique=True, nullable=False)
    exam = db.Column(db.String(8))
    exam_date = db.Column(db.Date)
    goal_score = db.Column(db.Integer)
    grade = db.Column(db.String(16))
    country = db.Column(db.String(64))
    region = db.Column(db.String(64))
    school = db.Column(db.String(120))
    onboarded = db.Column(db.Boolean, default=False)
    daily_goal = db.Column(db.Integer, default=15)  # minutes of practice a day (streak on the home page)
    session_presets = db.Column(JSONText, default=list)  # «мои режимы»: [{"name": .., "cfg": {..}}]
    sessions_cleared_at = db.Column(db.DateTime)  # «Очистить» in recent sessions: older ones are hidden (stats stay)

    user = db.relationship("User", back_populates="profile")


# --------------------------------------------------------------------------- content


NODE_LEVELS = ("topic", "subtopic", "node")  # Тема → Подтема → Навык


class ContentNode(db.Model):
    """One entry of the content tree: Topic → Subtopic → Node (skill).

    Questions, answers and progress always point to a *node* (the third level) by its
    permanent id, so new topics and branches can be attached at any time without
    touching existing results. Nothing is deleted — entries are archived.

    owner_id is empty for the shared tree (looked after by the admin); a teacher's own
    branches carry the teacher's id and are visible to that teacher and their students.
    """

    __tablename__ = "content_node"

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("content_node.id"), index=True)
    level = db.Column(db.String(10), nullable=False, default="node")  # topic | subtopic | node
    code = db.Column(db.String(64), unique=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="")
    position = db.Column(db.Integer, default=0)
    exams = db.Column(JSONText, default=list)
    weight = db.Column(db.Integer, default=1)  # importance, used by progress and penalties
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    parent = db.relationship("ContentNode", remote_side=[id], backref=db.backref("children", order_by="ContentNode.position"))
    owner = db.relationship("User")

    def in_exam(self, exam):
        return exam in (self.exams or [])

    @property
    def is_shared(self):
        return self.owner_id is None

    def ancestor(self, level):
        n = self
        while n is not None and n.level != level:
            n = n.parent
        return n

    @property
    def topic_node(self):
        return self.ancestor("topic")

    @property
    def subtopic_node(self):
        return self.ancestor("subtopic")

    @property
    def topic(self):
        t = self.topic_node
        return t.name if t else ""

    @property
    def subtopic(self):
        s = self.subtopic_node
        return s.name if s else ""

    @property
    def path(self):
        parts, n = [], self
        while n is not None:
            parts.append(n.name)
            n = n.parent
        return " → ".join(reversed(parts))

    def active_children(self):
        return [c for c in self.children if not c.archived]


Skill = ContentNode  # a "skill" is a node on the third level; old name kept for readability


QUESTION_WORD_LIMIT = 150
MATERIAL_TYPES = ("heading", "passage", "columns", "image")
INPUT_FORMATS = ("whole", "fraction", "decimal")  # what a free-input answer may be written as


class Question(db.Model):
    """One question.

    A question has two parts:
    - material (optional): blocks shown on the left — image, reading passage,
      side-by-side columns, a heading. Stored as a list of dicts in `material`.
    - the question itself: `text` (up to 150 words) with the answer controls.
    With material the page shows two columns; without, one centred column.
    """

    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    skill_id = db.Column(db.Integer, db.ForeignKey("content_node.id"))  # the tree node
    exams = db.Column(JSONText, default=list)
    difficulty = db.Column(db.Integer, default=2)
    language = db.Column(db.String(8), default="ru")
    material = db.Column(JSONText, default=list)  # [{"type": "passage", "title": .., "text": ..}, ...]
    text = db.Column(db.Text, default="")  # the question, may contain $...$ LaTeX
    image_path = db.Column(db.String(255))  # main picture, file name inside instance/uploads
    weight = db.Column(db.Integer, nullable=False, default=1)  # marks
    answer_type = db.Column(db.String(8), default="choice")  # choice | number (free input) | written (full solution)
    options = db.Column(JSONText, default=list)  # list of strings (choice)
    correct = db.Column(db.Text, nullable=False)  # option index, the value as text, or a written answer
    input_formats = db.Column(JSONText, default=lambda: ["whole", "fraction", "decimal"])
    precision = db.Column(db.Integer)  # free input: accepted rounding (1 = tenths, 2 = hundredths)
    explanation = db.Column(db.Text, default="")
    video_url = db.Column(db.String(255))
    source = db.Column(db.String(40))  # content pack id for questions from compilations (None = made by a teacher)
    pack_item_id = db.Column(db.String(120), nullable=True, index=True)  # stable "<pack_id>:<item_id>" key for idempotent pack sync
    rubric = db.Column(JSONText)  # written: [{"points": 2, "text": "…"}, …] — scoring criteria, best first
    tags = db.Column(JSONText)  # kinds of question: word, graph, nocalc, compare (see taxonomy.TAGS)
    status = db.Column(db.String(12), default="published")  # draft | pending (assistant's, waits for review) | published
    is_public_sample = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false(), index=True)
    public_image_key = db.Column(db.String(64), nullable=True, unique=True, index=True)
    review_note = db.Column(db.Text)  # reviewer's comment when a question is sent back
    replaces_id = db.Column(db.Integer, db.ForeignKey("question.id"))  # an assistant's correction of this published question
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    author = db.relationship("User", foreign_keys=[author_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])
    replaces = db.relationship("Question", remote_side="Question.id", foreign_keys=[replaces_id])
    skill = db.relationship("ContentNode")

    @property
    def node(self):
        return self.skill

    def snapshot(self):
        """Frozen copy stored inside a WorkVersion."""
        return {
            "question_id": self.id,
            "skill_id": self.skill_id,
            "difficulty": self.difficulty,
            "material": list(self.material or []),
            "text": self.text,
            "image_path": self.image_path,
            "weight": self.weight or 1,
            "answer_type": self.answer_type,
            "options": list(self.options or []),
            "correct": self.correct,
            "input_formats": list(self.input_formats or INPUT_FORMATS),
            "precision": self.precision,
            "explanation": self.explanation,
            "video_url": self.video_url,
            "tags": list(self.tags or []),
            "rubric": list(self.rubric or []),
            "language": self.language or "ru",
        }


class Work(db.Model):
    """A test, collection, homework or Monday test. Content lives in versions."""

    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    kind = db.Column(db.String(12), default="collection")  # collection | homework | monday
    category = db.Column(db.String(12), default="full")  # full | thematic
    exam = db.Column(db.String(8))
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="")
    time_limit_min = db.Column(db.Integer, default=30)
    status = db.Column(db.String(12), default="draft")  # draft | published | archived
    draft_question_ids = db.Column(JSONText, default=list)  # editor state
    week_start = db.Column(db.Date)  # Monday tests: the Monday they belong to
    node_id = db.Column(db.Integer, db.ForeignKey("content_node.id"))  # topic/subtopic it belongs to (thematic)
    format = db.Column(db.String(8), nullable=False, default="plain")  # see constants.TEST_FORMATS
    calculator = db.Column(db.Boolean, nullable=False, default=False)  # Desmos in the test
    module_split = db.Column(db.Integer)  # SAT: how many questions are in module 1
    per_page = db.Column(db.Integer, nullable=False, default=4)  # ORT: questions per page
    pack_item_id = db.Column(db.String(120), nullable=True, index=True)  # stable "<pack_id>:<collection_id>" key for idempotent pack sync
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    author = db.relationship("User")
    node = db.relationship("ContentNode")
    versions = db.relationship("WorkVersion", back_populates="work", order_by="WorkVersion.number",
                               cascade="all, delete-orphan")

    @property
    def current_version(self):
        return self.versions[-1] if self.versions else None

    @property
    def has_unpublished_changes(self):
        cur = self.current_version
        if not cur:
            return bool(self.draft_question_ids)
        return list(self.draft_question_ids or []) != [i["question_id"] for i in cur.items] or (
            cur.title != self.title or cur.time_limit_min != self.time_limit_min
        )


class WorkVersion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("work.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160))
    time_limit_min = db.Column(db.Integer)
    items = db.Column(JSONText, default=list)  # list of Question.snapshot()
    note = db.Column(db.String(255))  # what changed
    layout = db.Column(JSONText)  # {"format", "nav", "calculator", "per_page", "modules": [{"start", "end", "minutes"}]}
    published_at = db.Column(db.DateTime, default=utcnow)

    work = db.relationship("Work", back_populates="versions")

    __table_args__ = (UniqueConstraint("work_id", "number"),)

    @property
    def question_count(self):
        return len(self.items or [])

    @property
    def level(self):
        """Overall difficulty of the test from its questions' average: 1 easy, 2 medium, 3 hard (None if empty)."""
        ds = [i.get("difficulty") or 2 for i in (self.items or [])]
        if not ds:
            return None
        avg = sum(ds) / len(ds)
        return 1 if avg < 1.67 else 2 if avg < 2.34 else 3


# --------------------------------------------------------------------------- teacher ↔ student


INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 32 chars (5 bits/char), no 0/O/1/I
INVITE_CODE_LEN = 12  # 60 bits of entropy (32^12 ≈ 1.15e18)
INVITE_TTL_DAYS = 14


def default_invite_expiry(ttl_days=None):
    if ttl_days is None:
        try:
            from flask import current_app
            ttl_days = int(current_app.config.get("INVITE_CODE_TTL_DAYS", INVITE_TTL_DAYS) or INVITE_TTL_DAYS)
        except RuntimeError:
            ttl_days = INVITE_TTL_DAYS
    return utcnow() + timedelta(days=max(1, ttl_days))


def new_invite_code():
    """Generate a high-entropy (60-bit) invite code with DB collision retry when in an app context."""
    from flask import has_app_context
    for _attempt in range(16):
        code = "MND-" + "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LEN))
        if not has_app_context():
            return code
        if StudentRecord.query.filter_by(invite_code=code).first() is None:
            return code
    raise RuntimeError("Failed to generate a unique invite code after 16 attempts.")


CODE_STATUS_LABELS = {
    "pending": "Ожидает",
    "claimed": "Привязан",
    "expired": "Истёк",
    "revoked": "Отозван",
}


class StudentRecord(db.Model):
    """A row in a teacher's student table. Linked to a real account by invite code."""

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True, index=True)
    student_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    previous_student_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    source_lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("academic_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    claimed_at = db.Column(db.DateTime, nullable=True)
    claimed_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(40), nullable=True, index=True)
    email = db.Column(db.String(255), nullable=True, index=True)
    grade = db.Column(db.String(16))
    lesson_time = db.Column(db.String(5))  # "16:00"
    lesson_days = db.Column(JSONText, default=list)  # [0..6], 0 = Monday
    exam = db.Column(db.String(8))
    goal_score = db.Column(db.Integer)
    goal_text = db.Column(db.String(160))
    manual_progress = db.Column(db.Integer, default=0)  # used until the student links
    notes = db.Column(db.Text, default="")
    extra = db.Column(JSONText, default=dict)  # room for future columns
    invite_code = db.Column(db.String(32), unique=True, nullable=True, default=new_invite_code)
    invite_expires_at = db.Column(db.DateTime, nullable=True, default=default_invite_expiry)
    invite_revoked_at = db.Column(db.DateTime, nullable=True)
    linked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    student = db.relationship("User", foreign_keys=[student_user_id])
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    claimed_by = db.relationship("User", foreign_keys=[claimed_by_user_id])
    source_lead = db.relationship("Lead", foreign_keys=[source_lead_id])
    course = db.relationship("AcademicCourse", foreign_keys=[course_id])
    teacher_assignments = db.relationship(
        "TeacherAssignment",
        back_populates="student_record",
        order_by="TeacherAssignment.started_at.desc(), TeacherAssignment.id.desc()",
        cascade="all, delete-orphan",
    )

    @property
    def invite_is_expired(self):
        return bool(self.invite_expires_at and self.invite_expires_at <= utcnow())

    @property
    def invite_is_active(self):
        return bool(
            self.invite_code
            and not self.student_user_id
            and self.claimed_at is None
            and not self.invite_revoked_at
            and not self.invite_is_expired
        )

    @property
    def code_status(self):
        """Derive invite code lifecycle status from existing StudentRecord fields."""
        if self.student_user_id is not None or self.claimed_at is not None:
            return "claimed"
        if self.invite_revoked_at is not None or not self.invite_code:
            return "revoked"
        if self.invite_is_expired:
            return "expired"
        return "pending"

    @property
    def code_status_label(self):
        """Localized Russian label for the derived invite code status."""
        return CODE_STATUS_LABELS.get(self.code_status, "Ожидает")

    def rotate_invite_code(self, ttl_days=None):
        self.invite_code = new_invite_code()
        self.invite_expires_at = default_invite_expiry(ttl_days)
        self.invite_revoked_at = None
        if not self.student_user_id:
            self.claimed_at = None
            self.claimed_by_user_id = None
        return self.invite_code

    def revoke_invite_code(self):
        self.invite_code = None
        self.invite_revoked_at = utcnow()


class TeacherAssignment(db.Model):
    """Historical and active teacher assignments for a StudentRecord."""

    __tablename__ = "teacher_assignments"
    __table_args__ = (
        db.Index("ix_teacher_assignments_teacher_ended", "teacher_user_id", "ended_at"),
        db.Index("ix_teacher_assignments_student_record_id", "student_record_id"),
        db.Index(
            "uq_teacher_assignments_open_record_course",
            "student_record_id",
            "course_id",
            unique=True,
            sqlite_where=db.text("ended_at IS NULL AND course_id IS NOT NULL"),
            postgresql_where=db.text("ended_at IS NULL AND course_id IS NOT NULL"),
        ),
        db.Index(
            "uq_teacher_assignments_open_record_nocourse",
            "student_record_id",
            unique=True,
            sqlite_where=db.text("ended_at IS NULL AND course_id IS NULL"),
            postgresql_where=db.text("ended_at IS NULL AND course_id IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_record_id = db.Column(db.Integer, db.ForeignKey("student_record.id", ondelete="CASCADE"), nullable=False)
    teacher_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="RESTRICT"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("academic_courses.id", ondelete="SET NULL"), nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    assigned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ended_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    change_reason = db.Column(db.Text, nullable=True)

    student_record = db.relationship("StudentRecord", back_populates="teacher_assignments")
    teacher = db.relationship("User", foreign_keys=[teacher_user_id])
    course = db.relationship("AcademicCourse", foreign_keys=[course_id])
    assigned_by = db.relationship("User", foreign_keys=[assigned_by_id])
    ended_by = db.relationship("User", foreign_keys=[ended_by_id])

    @property
    def goal_label(self):
        if self.goal_text:
            return self.goal_text
        if self.goal_score and self.exam:
            from .constants import EXAMS
            return f"{self.goal_score}+ · {EXAMS.get(self.exam, {}).get('label', self.exam)}"
        return ""


class Assignment(db.Model):
    """Homework: a published Work given to one student record."""

    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.Integer, db.ForeignKey("work.id"), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    record_id = db.Column(db.Integer, db.ForeignKey("student_record.id"), nullable=False)
    due_at = db.Column(db.DateTime)
    message = db.Column(db.Text, default="")  # teacher's note when assigning
    teacher_comment = db.Column(db.Text, default="")  # feedback after checking
    checked_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

    work = db.relationship("Work")
    teacher = db.relationship("User")
    record = db.relationship("StudentRecord", backref=db.backref("assignments", cascade="all, delete-orphan"))


# --------------------------------------------------------------------------- results


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    mode = db.Column(db.String(12), nullable=False)  # franklin|feynman|darwin|einstein|collection|homework|monday
    work_version_id = db.Column(db.Integer, db.ForeignKey("work_version.id"))
    assignment_id = db.Column(db.Integer, db.ForeignKey("assignment.id"))
    plan = db.Column(JSONText, default=list)  # question ids for practice sessions
    position = db.Column(db.Integer, default=0)  # practice: index of the current question
    started_at = db.Column(db.DateTime, default=utcnow)
    finished_at = db.Column(db.DateTime)
    score = db.Column(db.Integer, default=0)  # marks earned (question weights)
    total = db.Column(db.Integer, default=0)  # marks available
    duration_sec = db.Column(db.Integer)
    draft = db.Column(JSONText, default=dict)  # timed tests: answers saved as the student goes {"q0": "2"}
    module = db.Column(db.Integer, nullable=False, default=1)  # SAT: current module (earlier ones are locked)
    module_started_at = db.Column(db.DateTime)
    active_at = db.Column(db.DateTime)  # collections: the last moment the test page was open (the timer pauses while away)

    user = db.relationship("User")
    work_version = db.relationship("WorkVersion")
    assignment = db.relationship("Assignment", backref="attempts")
    answers = db.relationship("AttemptAnswer", back_populates="attempt", cascade="all, delete-orphan",
                              order_by="AttemptAnswer.index")

    @property
    def percent(self):
        return round(100 * self.score / self.total) if self.total else 0

    @property
    def time_used(self):
        """Seconds spent, never more than the test's time limit (an open tab does not count)."""
        if not self.duration_sec:
            return self.duration_sec
        limit = self.work_version.time_limit_min if self.work_version else None
        return min(self.duration_sec, limit * 60) if limit else self.duration_sec


class AttemptAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("attempt.id"), nullable=False, index=True)
    index = db.Column(db.Integer, default=0)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"))
    skill_id = db.Column(db.Integer, db.ForeignKey("content_node.id"))
    given = db.Column(db.String(255))
    explanation_text = db.Column(db.Text)  # Feynman mode: the student's own explanation
    is_correct = db.Column(db.Boolean, default=False)
    mistake_reason = db.Column(db.String(12))  # careless | gap | misread | time
    points = db.Column(db.Integer)  # written answers: marks given (None = not assessed yet)
    points_by = db.Column(db.String(8))  # self | teacher
    photo_path = db.Column(db.String(255))  # written answers: photo of the solution (inside uploads)
    resolved = db.Column(db.Boolean, default=False)
    hint_used = db.Column(db.Boolean, default=False)  # custom sessions: a hint was opened (counts as half)
    answered_at = db.Column(db.DateTime, default=utcnow)

    attempt = db.relationship("Attempt", back_populates="answers")
    question = db.relationship("Question")
    skill = db.relationship("ContentNode")


SHEET_PLACES = ("bank", "sessions", "tests")


class ReferenceSheet(db.Model):
    """A student's own formula sheet (e.g. "CSCA формулы"). It opens in the sections chosen in `places`."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    exam = db.Column(db.String(8))
    enabled = db.Column(db.Boolean, nullable=False, default=True)  # false: off everywhere, whatever `places` says
    places = db.Column(db.String(40), default=",".join(SHEET_PLACES))
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)

    def is_on(self, place):
        return bool(self.enabled) and place in (self.places or "").split(",")

    def set_place(self, place, on):
        chosen = {p for p in SHEET_PLACES if self.is_on(p)} - {place} | ({place} if on else set())
        self.places = ",".join(p for p in SHEET_PLACES if p in chosen)
        self.enabled = bool(chosen)

    entries = db.relationship("SheetEntry", back_populates="sheet", cascade="all, delete-orphan",
                              order_by="SheetEntry.position")


class SheetEntry(db.Model):
    """Branch (topic) → name → small picture on top → formula underneath."""

    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey("reference_sheet.id"), nullable=False, index=True)
    branch = db.Column(db.String(80), default="")
    topic = db.Column(db.String(120), nullable=False)
    image_path = db.Column(db.String(255))
    formula = db.Column(db.Text, default="")  # LaTeX between $…$
    position = db.Column(db.Integer, default=0)

    sheet = db.relationship("ReferenceSheet", back_populates="entries")


# School days follow Bishkek time (UTC+6, no daylight saving), not the server's clock.
LOCAL_TZ = timezone(timedelta(hours=6))


def today():
    """Today's date in Bishkek."""
    return datetime.now(LOCAL_TZ).date()


def local_now():
    """Bishkek wall-clock time as a naive datetime (lesson times, the Monday test window)."""
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def local_date(dt):
    """Bishkek date of a naive UTC timestamp from the database."""
    return dt.replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ).date()


def local_midnight_utc():
    """Start of today in Bishkek, as a naive UTC timestamp (for database comparisons)."""
    start = datetime.combine(today(), datetime.min.time(), LOCAL_TZ)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


class ContentTranslation(db.Model):
    """A question's text in another language (made from known patterns, a translation service, or by hand).

    src_hash fingerprints the original text: after the question is edited the old translation stops applying.
    """

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id", ondelete="CASCADE"), nullable=False, index=True)
    lang = db.Column(db.String(8), nullable=False)
    src_hash = db.Column(db.String(40), nullable=False)
    data = db.Column(JSONText, default=dict)  # {"text", "options", "explanation", "material"}
    source = db.Column(db.String(12), default="pattern")  # pattern | machine | human
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("question_id", "lang", name="uq_translation_question_lang"),)


class BankState(db.Model):
    """A student's state for one question in the question bank: marked, tries, time, last result."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False, index=True)
    marked = db.Column(db.Boolean, nullable=False, default=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_correct = db.Column(db.Boolean)
    last_given = db.Column(db.String(255))
    seconds = db.Column(db.Integer, nullable=False, default=0)
    revealed = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("user_id", "question_id"),)


ATTENDANCE = ("present", "late", "absent")


class Attendance(db.Model):
    """One lesson of one student, marked by the teacher. Kept apart from knowledge (see spec)."""

    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey("student_record.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(8), nullable=False, default="present")  # present | late | absent
    created_at = db.Column(db.DateTime, default=utcnow)

    record = db.relationship("StudentRecord", backref=db.backref("attendance", cascade="all, delete-orphan",
                                                                 order_by="Attendance.day"))

    __table_args__ = (UniqueConstraint("record_id", "day"),)


DAILY_MAX = 3  # questions of the day per teacher per day


class DailyPick(db.Model):
    """A question of the day. Chosen by a teacher for their students (teacher_id set),
    or picked by Monday for an exam when the teacher hasn't chosen any (teacher_id empty)."""

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), nullable=False)
    day = db.Column(db.Date, nullable=False, index=True)
    exam = db.Column(db.String(8))  # only students of this exam see it (empty = all the teacher's students)
    position = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)

    teacher = db.relationship("User")
    question = db.relationship("Question")

    __table_args__ = (UniqueConstraint("teacher_id", "day", "question_id", "exam"),)


class DailyAnswer(db.Model):
    """One try per student per question of the day."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    pick_id = db.Column(db.Integer, db.ForeignKey("daily_pick.id"), nullable=False, index=True)
    given = db.Column(db.String(255))
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=utcnow)

    pick = db.relationship("DailyPick", backref=db.backref("answers", cascade="all, delete-orphan"))

    __table_args__ = (UniqueConstraint("user_id", "pick_id"),)


class AppMeta(db.Model):
    """Small key → value store for one-off upgrades (e.g. which skill map version is installed)."""

    key = db.Column(db.String(40), primary_key=True)
    value = db.Column(db.String(255))


class Report(db.Model):
    """A student (or staff member) reports an issue with a question, map node, or support topic."""

    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    sender_role = db.Column(db.String(32), nullable=False, default="student", index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id"), index=True)
    node_id = db.Column(db.Integer, db.ForeignKey("content_node.id"), index=True)
    kind = db.Column(db.String(12), nullable=False, default="other")  # answer | typo | unclear | other | node
    message = db.Column(db.Text, default="")
    status = db.Column(db.String(10), nullable=False, default="open")  # open | fixed | rejected
    reply = db.Column(db.Text)
    handled_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime, default=utcnow)
    handled_at = db.Column(db.DateTime)
    seen = db.Column(db.Boolean, nullable=False, default=False)  # the author has seen the reply

    author = db.relationship("User", foreign_keys=[author_id])
    handled_by = db.relationship("User", foreign_keys=[handled_by_id])
    question = db.relationship("Question")
    node = db.relationship("ContentNode")
    attachments = db.relationship(
        "SupportAttachment",
        backref=db.backref("message", lazy="joined"),
        lazy="selectin",
        order_by="SupportAttachment.id.asc()",
        cascade="all, delete-orphan",
    )


class SupportAttachment(db.Model):
    """Compressed WebP image attachment belonging to a support message (Report)."""

    __tablename__ = "support_attachments"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(
        db.Integer,
        db.ForeignKey("report.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key = db.Column(db.String(120), nullable=False, unique=True)
    mime = db.Column(db.String(32), nullable=False, default="image/webp")
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    bytes_original = db.Column(db.Integer, nullable=False)
    bytes_stored = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    def full_object_name(self) -> str:
        return f"support/{self.storage_key}.webp"

    def thumb_object_name(self) -> str:
        return f"support/{self.storage_key}_thumb.webp"


class ActivityDraft(db.Model):
    """Unified in-progress/completed/abandoned state per (user, type)."""

    __tablename__ = "activity_draft"
    __table_args__ = (
        db.UniqueConstraint("user_id", "activity_type", name="uq_activity_draft_user_type"),
        db.Index("ix_activity_draft_user_status", "user_id", "status", "updated_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    activity_type = db.Column(db.String(24), nullable=False)  # test | bank | session | homework | practice
    activity_id = db.Column(db.String(120), nullable=False, default="")
    title = db.Column(db.String(200), nullable=False, default="")
    subtitle = db.Column(db.String(200), nullable=False, default="")
    resume_url = db.Column(db.String(500), nullable=False, default="")
    answered = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False, default=0)
    state_json = db.Column(db.Text, nullable=False, default="{}")
    status = db.Column(db.String(20), nullable=False, default="in_progress")  # in_progress | completed | abandoned
    version = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("activity_drafts", lazy="dynamic", cascade="all, delete-orphan"))

    def state_dict(self) -> dict:
        import json
        try:
            data = json.loads(self.state_json or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.activity_type,
            "activity_id": self.activity_id,
            "title": self.title,
            "subtitle": self.subtitle,
            "resume_url": self.resume_url,
            "answered": self.answered,
            "total": self.total,
            "state": self.state_dict(),
            "status": self.status,
            "version": self.version,
            "updated_at": (self.updated_at.isoformat() + "Z") if self.updated_at else None,
        }


class ClientOp(db.Model):
    """Idempotency log for client-generated operation UUIDs."""

    __tablename__ = "client_op"
    __table_args__ = (
        db.UniqueConstraint("user_id", "op_id", name="uq_client_op_user_op"),
        db.Index("ix_client_op_created", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    op_id = db.Column(db.String(80), nullable=False)
    activity_type = db.Column(db.String(24), nullable=False, default="")
    response_json = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class MaintenanceState(db.Model):
    """Singleton maintenance notice state stored in DB so it survives restarts."""

    __tablename__ = "maintenance_state"

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(20), nullable=False, default="off")  # off | scheduled | active
    message = db.Column(db.String(500), nullable=False, default="")
    expected_minutes = db.Column(db.Integer, nullable=False, default=15)
    starts_at = db.Column(db.DateTime, nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    updated_by_name = db.Column(db.String(120), nullable=False, default="")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "state": self.state or "off",
            "message": self.message or "",
            "expected_minutes": int(self.expected_minutes or 15),
            "starts_at": (self.starts_at.isoformat() + "Z") if self.starts_at else None,
            "updated_by": self.updated_by_name or "",
            "updated_at": (self.updated_at.isoformat() + "Z") if self.updated_at else None,
        }


class MaintenanceLog(db.Model):
    """Audit log of maintenance state changes."""

    __tablename__ = "maintenance_log"

    id = db.Column(db.Integer, primary_key=True)
    state = db.Column(db.String(20), nullable=False)
    message = db.Column(db.String(500), nullable=False, default="")
    expected_minutes = db.Column(db.Integer, nullable=False, default=15)
    starts_at = db.Column(db.DateTime, nullable=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    actor = db.Column(db.String(120), nullable=False, default="")
    source = db.Column(db.String(40), nullable=False, default="admin")  # admin | cli
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class RoadmapMilestone(db.Model):
    """Database-backed roadmap milestone (content seeded idempotently)."""

    __tablename__ = "roadmap_milestone"
    __table_args__ = (db.UniqueConstraint("exam", "key", name="uq_roadmap_milestone_exam_key"),)

    id = db.Column(db.Integer, primary_key=True)
    exam = db.Column(db.String(20), nullable=False, default="SAT")
    key = db.Column(db.String(64), nullable=False)
    step = db.Column(db.Integer, nullable=False, default=1)
    title_ru = db.Column(db.String(200), nullable=False)
    title_en = db.Column(db.String(200), nullable=False)
    description_ru = db.Column(db.String(500), nullable=False, default="")
    official_question_share = db.Column(db.String(40), nullable=False, default="")
    gate_json = db.Column(db.Text, nullable=False, default="")
    guide_ru = db.Column(db.Text, nullable=False, default="")
    guide_en = db.Column(db.Text, nullable=False, default="")
    guide_draft_ru = db.Column(db.Text, nullable=False, default="")
    guide_status = db.Column(db.String(20), nullable=False, default="published")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class RoadmapNode(db.Model):
    """Database-backed roadmap node inside a milestone."""

    __tablename__ = "roadmap_node"

    id = db.Column(db.Integer, primary_key=True)
    milestone_id = db.Column(db.Integer, db.ForeignKey("roadmap_milestone.id", ondelete="CASCADE"), nullable=False)
    side = db.Column(db.String(10), nullable=False, default="left")  # left | right
    group_ru = db.Column(db.String(200), nullable=False, default="")
    group_en = db.Column(db.String(200), nullable=False, default="")
    position = db.Column(db.Integer, nullable=False, default=0)
    key = db.Column(db.String(80), nullable=False, unique=True)
    title_ru = db.Column(db.String(200), nullable=False)
    title_en = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(32), nullable=False, default="info")
    tier = db.Column(db.String(24), nullable=False, default="foundation")  # foundation | medium | advanced | challenge
    status_hint = db.Column(db.String(32), nullable=False, default="")
    link_hint_json = db.Column(db.Text, nullable=False, default="{}")
    soft_prereqs_json = db.Column(db.Text, nullable=False, default="[]")
    summary_ru = db.Column(db.Text, nullable=False, default="")
    body_ru = db.Column(db.Text, nullable=False, default="")
    body_en = db.Column(db.Text, nullable=False, default="")
    body_draft_ru = db.Column(db.Text, nullable=False, default="")
    body_status = db.Column(db.String(20), nullable=False, default="published")
    widget_json = db.Column(db.Text, nullable=False, default="")
    skill_ids_json = db.Column(db.Text, nullable=False, default="[]")
    formula_tpl = db.Column(db.String(64), nullable=False, default="")
    formula_topic_id = db.Column(db.String(64), nullable=False, default="")

    milestone = db.relationship("RoadmapMilestone", backref=db.backref("nodes", lazy="dynamic", cascade="all, delete-orphan"))


class RoadmapProgress(db.Model):
    """Per-user completion/mastery state for roadmap nodes."""

    __tablename__ = "roadmap_progress"
    __table_args__ = (db.UniqueConstraint("user_id", "node_key", name="uq_roadmap_prog_user_node"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    node_id = db.Column(db.Integer, db.ForeignKey("roadmap_node.id", ondelete="CASCADE"), nullable=True, index=True)
    node_key = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(24), nullable=False, default="completed")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    node = db.relationship("RoadmapNode")


class CourseUnit(db.Model):
    """Khan-style 14-unit course structure (DB-backed, idempotently seeded)."""

    __tablename__ = "course_unit"
    __table_args__ = (db.UniqueConstraint("exam", "slug", name="uq_course_unit_exam_slug"),)

    id = db.Column(db.Integer, primary_key=True)
    exam = db.Column(db.String(20), nullable=False, default="SAT")
    number = db.Column(db.Integer, nullable=False)
    slug = db.Column(db.String(80), nullable=False)
    title_ru = db.Column(db.String(200), nullable=False)
    tier = db.Column(db.String(24), nullable=False, default="foundation")  # intro|foundation|medium|advanced|challenge
    domain = db.Column(db.String(32), nullable=False, default="")
    description_ru = db.Column(db.String(500), nullable=False, default="")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class CourseLesson(db.Model):
    """Interactive lesson / practice set / unit quiz inside a CourseUnit."""

    __tablename__ = "course_lesson"
    __table_args__ = (db.UniqueConstraint("unit_id", "slug", name="uq_course_lesson_unit_slug"),)

    id = db.Column(db.Integer, primary_key=True)
    unit_id = db.Column(db.Integer, db.ForeignKey("course_unit.id", ondelete="CASCADE"), nullable=False)
    slug = db.Column(db.String(80), nullable=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    title_ru = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(24), nullable=False, default="practice")  # article | practice | quiz
    article_md = db.Column(db.Text, nullable=False, default="")
    hints_json = db.Column(db.Text, nullable=False, default="[]")
    desmos_preset_json = db.Column(db.Text, nullable=False, default="")
    youtube_url = db.Column(db.String(400), nullable=False, default="")
    formula_tpl = db.Column(db.String(64), nullable=False, default="")
    formula_topic_id = db.Column(db.String(64), nullable=False, default="")
    question_ids_json = db.Column(db.Text, nullable=False, default="[]")
    inline_quiz_json = db.Column(db.Text, nullable=False, default="[]")
    skill_ids_json = db.Column(db.Text, nullable=False, default="[]")
    difficulty = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    unit = db.relationship("CourseUnit", backref=db.backref("lessons", lazy="dynamic", cascade="all, delete-orphan"))


class CourseMastery(db.Model):
    """4-tier Khan-style mastery per user and lesson (not_started|familiar|proficient|mastered)."""

    __tablename__ = "course_mastery"
    __table_args__ = (db.UniqueConstraint("user_id", "lesson_key", name="uq_course_mastery_user_lesson"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("course_lesson.id", ondelete="CASCADE"), nullable=True, index=True)
    lesson_key = db.Column(db.String(160), nullable=False)
    level = db.Column(db.String(24), nullable=False, default="not_started")
    best_score = db.Column(db.Integer, nullable=False, default=0)
    total_q = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    lesson = db.relationship("CourseLesson")


# --------------------------------------------------------------------------- analytics


class Visit(db.Model):
    """One browsing session (30-minute inactivity window) for registered or anonymous visitors.

    Raw IP addresses are never stored: only a salted SHA-256 hash (`ip_hash`) and
    coarse GeoIP location (`country`, `city`) resolved at visit creation time.
    """

    __tablename__ = "visit"
    __table_args__ = (
        db.Index("ix_visit_cookie_ended", "session_cookie_id", "ended_at"),
        db.Index("ix_visit_user_started", "user_id", "started_at"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_cookie_id = db.Column(db.String(64), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    ip_hash = db.Column(db.String(64), nullable=True, index=True)
    country = db.Column(db.String(80), nullable=True, index=True)
    city = db.Column(db.String(120), nullable=True)
    device_type = db.Column(db.String(16), nullable=False, default="desktop", index=True)  # desktop | mobile | tablet
    os = db.Column(db.String(64), nullable=True)
    browser = db.Column(db.String(64), nullable=True)
    referer = db.Column(db.String(512), nullable=True)
    language = db.Column(db.String(16), nullable=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    ended_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    page_count = db.Column(db.Integer, nullable=False, default=0)

    user = db.relationship("User", back_populates="visits")
    page_views = db.relationship(
        "PageView",
        back_populates="visit",
        cascade="all, delete-orphan",
        order_by="PageView.created_at.asc()",
    )

    @property
    def duration_seconds(self) -> int:
        if not self.started_at or not self.ended_at:
            return 0
        return max(0, int((self.ended_at - self.started_at).total_seconds()))


class PageView(db.Model):
    """Single page hit within a Visit; records older than 90 days are purged daily."""

    __tablename__ = "page_view"
    __table_args__ = (
        db.Index("ix_page_view_visit_created", "visit_id", "created_at"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    visit_id = db.Column(db.String(36), db.ForeignKey("visit.id", ondelete="CASCADE"), nullable=False, index=True)
    path = db.Column(db.String(512), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    time_spent_seconds = db.Column(db.Integer, nullable=False, default=0)

    visit = db.relationship("Visit", back_populates="page_views")


class LoginEvent(db.Model):
    """Per-login audit record: auth method, device/OS/browser, GeoIP, and salted IP hash."""

    __tablename__ = "login_event"
    __table_args__ = (
        db.Index("ix_login_event_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    auth_provider = db.Column(db.String(16), nullable=False, default="password")
    device_type = db.Column(db.String(16), nullable=False, default="desktop")
    os = db.Column(db.String(64), nullable=True)
    browser = db.Column(db.String(64), nullable=True)
    ip_hash = db.Column(db.String(64), nullable=True)
    country = db.Column(db.String(80), nullable=True)
    city = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    user = db.relationship("User", backref=db.backref("login_events", lazy="dynamic", cascade="all, delete-orphan"))


# --------------------------------------------------------------------------- CRM & Audit


LEAD_SOURCES = ("instagram", "whatsapp", "telegram", "site", "referral", "other")
LEAD_STATUSES = ("new", "contacted", "trial_scheduled", "trial_done", "negotiation", "won", "lost")
LEAD_ACTIVITY_TYPES = ("call", "message", "note", "status_change", "reassign")
LEAD_MODE_PREFERENCES = ("", "online", "offline", "any")
LEAD_TEMPERATURES = ("cold", "warm", "hot")


class Lead(db.Model):
    """Prospective student tracked in the Sales CRM (separate from Student/User until conversion)."""

    __tablename__ = "leads"
    __table_args__ = (
        db.Index("ix_leads_status_assigned", "status", "assigned_manager_id"),
        db.Index("ix_leads_created_status", "created_at", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(40), nullable=True, index=True)
    phone_e164 = db.Column(db.String(20), nullable=True, index=True)
    messenger_handle = db.Column(db.String(120), nullable=True)
    messenger_norm = db.Column(db.String(120), nullable=True, index=True)
    telegram_chat_id = db.Column(db.String(64), nullable=True, index=True)
    telegram_username = db.Column(db.String(120), nullable=True, index=True)
    source = db.Column(db.String(32), nullable=False, default="other", index=True)
    interest = db.Column(db.String(160), nullable=False, default="")
    mode_preference = db.Column(db.String(16), nullable=False, default="")
    temperature = db.Column(db.String(16), nullable=False, default="cold")
    priority_score = db.Column(db.Integer, nullable=False, default=50)
    ai_summary = db.Column(db.Text, nullable=True)
    previous_lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    status = db.Column(db.String(24), nullable=False, default="new", index=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    archive_reason = db.Column(db.String(120), nullable=False, default="")
    assigned_manager_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    first_contact_at = db.Column(db.DateTime, nullable=True)
    last_contact_at = db.Column(db.DateTime, nullable=True)
    converted_student_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    lost_reason = db.Column(db.String(255), nullable=False, default="")

    assigned_manager = db.relationship("User", foreign_keys=[assigned_manager_id])
    converted_student = db.relationship("User", foreign_keys=[converted_student_id])
    previous_lead = db.relationship("Lead", remote_side=[id], foreign_keys=[previous_lead_id])
    activities = db.relationship(
        "LeadActivity",
        back_populates="lead",
        order_by="LeadActivity.created_at.desc()",
        cascade="all, delete-orphan",
    )
    tasks = db.relationship(
        "LeadTask",
        back_populates="lead",
        order_by="LeadTask.due_at.asc()",
        cascade="all, delete-orphan",
    )
    reply_feedback = db.relationship(
        "BotReplyFeedback",
        back_populates="lead",
        order_by="BotReplyFeedback.created_at.desc()",
        cascade="all, delete-orphan",
    )


class LeadActivity(db.Model):
    """Chronological timeline entry on a Lead (call, message, note, status_change, reassign)."""

    __tablename__ = "lead_activities"
    __table_args__ = (
        db.Index("ix_lead_activities_lead_created", "lead_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    type = db.Column(db.String(24), nullable=False, default="note")
    body = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    lead = db.relationship("Lead", back_populates="activities")
    actor = db.relationship("User", foreign_keys=[actor_id])


class LeadTask(db.Model):
    """Follow-up task assigned to a manager for a Lead."""

    __tablename__ = "lead_tasks"
    __table_args__ = (
        db.Index("ix_lead_tasks_assignee_due", "assignee_id", "due_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    due_at = db.Column(db.DateTime, nullable=False, index=True)
    done_at = db.Column(db.DateTime, nullable=True, index=True)
    note = db.Column(db.String(300), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    lead = db.relationship("Lead", back_populates="tasks")
    assignee = db.relationship("User", foreign_keys=[assignee_id])


class ReplyTemplate(db.Model):
    """Optima-style bilingual (RU/KY) reply macro with {variable} slots seeded from docs/crm_bot/reply_macros.md."""

    __tablename__ = "reply_templates"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    category = db.Column(db.String(48), nullable=False, default="general", index=True)
    title = db.Column(db.String(160), nullable=False)
    body_ru = db.Column(db.Text, nullable=False)
    body_ky = db.Column(db.Text, nullable=False)
    variables_json = db.Column(JSONText, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class BotReplyFeedback(db.Model):
    """Manager feedback on bot reply drafts used for dynamic few-shot retrieval and DSPy optimization."""

    __tablename__ = "bot_reply_feedback"
    __table_args__ = (
        db.Index("ix_bot_reply_feedback_lookup", "intent", "subject", "language", "was_accepted"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True)
    template_slug = db.Column(db.String(80), nullable=True, index=True)
    intent = db.Column(db.String(48), nullable=False, default="hot_lead", index=True)
    subject = db.Column(db.String(80), nullable=False, default="", index=True)
    language = db.Column(db.String(12), nullable=False, default="ru", index=True)
    draft_text = db.Column(db.Text, nullable=False, default="")
    final_sent_text = db.Column(db.Text, nullable=False, default="")
    was_accepted = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    lead = db.relationship("Lead", back_populates="reply_feedback")
    created_by = db.relationship("User", foreign_keys=[created_by_id])


class AuditLog(db.Model):
    """Immutable audit trail for role changes, lead reassignments/deletions/conversions, and retroactive edits."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        db.Index("ix_audit_logs_entity", "entity_type", "entity_id"),
        db.Index("ix_audit_logs_action_ts", "action", "timestamp"),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=True, index=True)
    old_value = db.Column(JSONText, nullable=True)
    new_value = db.Column(JSONText, nullable=True)
    reason = db.Column(db.String(300), nullable=False, default="")
    timestamp = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    actor = db.relationship("User", foreign_keys=[actor_id])


# --------------------------------------------------------------------------- Academic Operations (MVP-1)


LESSON_MODES = ("online", "offline")
LESSON_ATTENDANCE_STATUSES = ("present", "absent", "late", "excused")
ENROLLMENT_STATUSES = ("active", "completed", "transferred", "dropped")


class Location(db.Model):
    """Physical classroom / campus location for offline lessons."""

    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=False, default="")
    room = db.Column(db.String(80), nullable=False, default="")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_public = db.Column(db.Boolean, nullable=False, default=False, index=True)
    public_name = db.Column(db.String(160), nullable=False, default="")
    map_url = db.Column(db.String(400), nullable=False, default="")
    working_hours = db.Column(db.String(160), nullable=False, default="")
    phone = db.Column(db.String(40), nullable=False, default="")
    photo = db.Column(db.String(255), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_public_dict(self) -> dict:
        """Expose strictly public-safe fields (never internal room/capacity/notes)."""
        return {
            "id": self.id,
            "name": (self.public_name or self.name or "").strip(),
            "address": (self.address or "").strip(),
            "map_url": (self.map_url or "").strip(),
            "working_hours": (self.working_hours or "").strip(),
            "phone": (self.phone or "").strip(),
            "photo": (self.photo or "").strip(),
        }


class AcademicCourse(db.Model):
    """Academy course offering (e.g. SAT Math, ORT Intensive, CSCA) linked to study groups & enrollments."""

    __tablename__ = "academic_courses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(40), unique=True, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    exam = db.Column(db.String(16), nullable=False, default="")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_public = db.Column(db.Boolean, nullable=False, default=False, index=True)
    public_summary = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_public_dict(self) -> dict:
        """Expose strictly public-safe course attributes."""
        return {
            "id": self.id,
            "name": (self.name or "").strip(),
            "exam": (self.exam or "").strip(),
            "public_summary": (self.public_summary or "").strip(),
        }


class StudyGroup(db.Model):
    """Scheduled teaching cohort for an AcademicCourse led by a Teacher."""

    __tablename__ = "study_groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("academic_courses.id", ondelete="RESTRICT"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    default_location_id = db.Column(db.Integer, db.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    course = db.relationship("AcademicCourse")
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    default_location = db.relationship("Location", foreign_keys=[default_location_id])
    enrollments = db.relationship("GroupEnrollment", back_populates="group", cascade="all, delete-orphan")
    lessons = db.relationship("Lesson", back_populates="group", order_by="Lesson.starts_at.desc()", cascade="all, delete-orphan")


class GroupEnrollment(db.Model):
    """Many-to-many Student <-> Group/Course enrollment with full history (left_at preserves past enrollments)."""

    __tablename__ = "group_enrollments"
    __table_args__ = (
        db.Index("ix_group_enrollments_student_active", "student_user_id", "left_at"),
        db.Index("ix_group_enrollments_group_active", "group_id", "left_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    student_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("academic_courses.id", ondelete="RESTRICT"), nullable=False, index=True)
    enrolled_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    left_at = db.Column(db.DateTime, nullable=True, index=True)
    status = db.Column(db.String(24), nullable=False, default="active")
    note = db.Column(db.String(255), nullable=False, default="")

    group = db.relationship("StudyGroup", back_populates="enrollments")
    student = db.relationship("User", foreign_keys=[student_user_id])
    course = db.relationship("AcademicCourse", foreign_keys=[course_id])


class Lesson(db.Model):
    """Individual scheduled class session. `lesson_mode` (online/offline) lives on the Lesson, never the Student."""

    __tablename__ = "lessons"
    __table_args__ = (
        db.Index("ix_lessons_mode_starts", "lesson_mode", "starts_at"),
        db.Index("ix_lessons_group_starts", "group_id", "starts_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    duration_min = db.Column(db.Integer, nullable=False, default=90)
    lesson_mode = db.Column(db.String(16), nullable=False, default="offline", index=True)  # online | offline
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id", ondelete="SET NULL"), nullable=True, index=True)
    meeting_url = db.Column(db.String(400), nullable=False, default="")
    topic = db.Column(db.String(200), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    group = db.relationship("StudyGroup", back_populates="lessons")
    teacher = db.relationship("User", foreign_keys=[teacher_id])
    location = db.relationship("Location", foreign_keys=[location_id])
    attendances = db.relationship("LessonAttendance", back_populates="lesson", cascade="all, delete-orphan")


class LessonAttendance(db.Model):
    """Per-lesson attendance record (Present/Absent/Late/Excused) with retroactive edit auditing."""

    __tablename__ = "lesson_attendance"
    __table_args__ = (
        UniqueConstraint("lesson_id", "student_user_id", name="uq_lesson_attendance_lesson_student"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    student_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    status = db.Column(db.String(16), nullable=False, default="present", index=True)  # present|absent|late|excused
    note = db.Column(db.String(255), nullable=False, default="")
    marked_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    marked_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    lesson = db.relationship("Lesson", back_populates="attendances")
    student = db.relationship("User", foreign_keys=[student_user_id])
    marked_by = db.relationship("User", foreign_keys=[marked_by_id])


# --------------------------------------------------------------------------- Finance, Passes & Payroll (Phase B)


PASS_STATUSES = ("active", "frozen", "depleted", "expired", "cancelled")
PAYMENT_METHODS = ("cash", "mbank", "transfer", "card")
PAYMENT_KINDS = ("payment", "refund")
PAY_RATE_TYPES = ("per_lesson", "per_student", "fixed_month")


# Naming convention (see docs/naming.md):
# - MembershipPlan (`membership_plans`) = «Абонемент» for teacher-led offline/online lesson packages.
# - SubscriptionPlan (`subscription_plans`) / Subscription (`bank_subscriptions`) = «Подписка на банк вопросов»
#   for self-study access without teachers. Never mix the two models or branches.
class MembershipPlan(db.Model):
    """Catalog plan / subscription package (e.g. 8 SAT lessons / 30 days)."""

    __tablename__ = "membership_plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("academic_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    total_lessons = db.Column(db.Integer, nullable=True)  # None = time-bounded unlimited lessons
    duration_days = db.Column(db.Integer, nullable=False, default=30)
    price_amount = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(8), nullable=False, default="KGS")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    course = db.relationship("AcademicCourse")


class StudentPass(db.Model):
    """Issued student pass/membership tracking remaining lessons, expiry, and payment balance."""

    __tablename__ = "student_passes"
    __table_args__ = (
        db.Index("ix_student_passes_student_status", "student_user_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("membership_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("group_enrollments.id", ondelete="SET NULL"), nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    lessons_total = db.Column(db.Integer, nullable=True)
    lessons_remaining = db.Column(db.Integer, nullable=True)
    starts_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=True, index=True)
    agreed_price = db.Column(db.Integer, nullable=False, default=0)
    paid_amount = db.Column(db.Integer, nullable=False, default=0)
    note = db.Column(db.String(255), nullable=False, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    student = db.relationship("User", foreign_keys=[student_user_id])
    plan = db.relationship("MembershipPlan")
    enrollment = db.relationship("GroupEnrollment")
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    @property
    def debt_amount(self) -> int:
        return max(0, int(self.agreed_price or 0) - int(self.paid_amount or 0))


class PaymentTransaction(db.Model):
    """Immutable financial ledger row (payment or refund) for a student / pass."""

    __tablename__ = "payment_transactions"

    id = db.Column(db.Integer, primary_key=True)
    student_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    pass_id = db.Column(db.Integer, db.ForeignKey("student_passes.id", ondelete="SET NULL"), nullable=True, index=True)
    amount = db.Column(db.Integer, nullable=False)
    method = db.Column(db.String(24), nullable=False, default="cash")
    kind = db.Column(db.String(16), nullable=False, default="payment")  # payment | refund
    note = db.Column(db.String(255), nullable=False, default="")
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    paid_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    student = db.relationship("User", foreign_keys=[student_user_id])
    student_pass = db.relationship("StudentPass", foreign_keys=[pass_id])
    recorded_by = db.relationship("User", foreign_keys=[recorded_by_id])


class LessonPassUsage(db.Model):
    """Idempotency ledger tying one lesson attendance consumption to a StudentPass."""

    __tablename__ = "lesson_pass_usages"
    __table_args__ = (
        UniqueConstraint("lesson_id", "student_user_id", name="uq_lesson_pass_usage_lesson_student"),
    )

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    student_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    pass_id = db.Column(db.Integer, db.ForeignKey("student_passes.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    lesson = db.relationship("Lesson")
    student_pass = db.relationship("StudentPass")


class TeacherPayRate(db.Model):
    """Compensation rule per teacher (optionally scoped to a course)."""

    __tablename__ = "teacher_pay_rates"

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("academic_courses.id", ondelete="SET NULL"), nullable=True, index=True)
    rate_type = db.Column(db.String(24), nullable=False, default="per_lesson")  # per_lesson | per_student | fixed_month
    rate_amount = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(8), nullable=False, default="KGS")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    course = db.relationship("AcademicCourse")


# --------------------------------------------------------------------------- Self-Study Question-Bank Subscriptions (Stage 4)
# Naming convention (see docs/naming.md):
# - MembershipPlan (`membership_plans`) / StudentPass (`student_passes`) = «Абонемент» (school lessons with teachers).
# - SubscriptionPlan (`subscription_plans`) / Subscription (`bank_subscriptions`) = «Подписка на банк вопросов»
#   (self-study question-bank product without teachers). Never merge or reuse the same tables.


SUBSCRIPTION_STATUSES = ("active", "trialing", "past_due", "cancelled", "expired")


class SubscriptionPlan(db.Model):
    """Product plan for «Подписка на банк вопросов» (prices & durations live in DB/config, never hardcoded)."""

    __tablename__ = "subscription_plans"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(48), nullable=False, unique=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    price_amount = db.Column(db.Integer, nullable=False, default=800)  # minor units
    currency = db.Column(db.String(8), nullable=False, default="USD")
    billing_period = db.Column(db.String(16), nullable=False, default="monthly")
    duration_days = db.Column(db.Integer, nullable=False, default=30)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class Subscription(db.Model):
    """Self-study question-bank subscription grant / lifecycle row (`bank_subscriptions`)."""

    __tablename__ = "bank_subscriptions"
    __table_args__ = (
        db.Index("ix_bank_subscriptions_user_status", "user_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="active", index=True)
    starts_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    current_period_end = db.Column(db.DateTime, nullable=True, index=True)
    trial_ends_at = db.Column(db.DateTime, nullable=True)
    granted_by_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    note = db.Column(db.String(255), nullable=False, default="")
    cancelled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    user = db.relationship("User", foreign_keys=[user_id])
    plan = db.relationship("SubscriptionPlan", foreign_keys=[plan_id])
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])
    events = db.relationship("SubscriptionEvent", back_populates="subscription", cascade="all, delete-orphan")


class SubscriptionEvent(db.Model):
    """Immutable audit trail for manual subscription grants, plan changes, renewals and cancellations."""

    __tablename__ = "subscription_events"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("bank_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    event_type = db.Column(db.String(32), nullable=False)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=True)
    payload = db.Column(JSONText, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    subscription = db.relationship("Subscription", back_populates="events")
    user = db.relationship("User", foreign_keys=[user_id])
    actor = db.relationship("User", foreign_keys=[actor_id])


class DailyQuestionAccess(db.Model):
    """Server-side atomic ledger of distinct non-sample questions opened by free-tier users per local day."""

    __tablename__ = "daily_question_access"
    __table_args__ = (
        UniqueConstraint("user_id", "access_date", "question_id", name="uq_daily_q_access_user_date_q"),
        db.Index("ix_daily_q_access_user_date", "user_id", "access_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    access_date = db.Column(db.Date, nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("question.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


# Safety net for PostgreSQL, which (unlike SQLite) rejects a string longer than its column:
# anything typed into a limited field (an answer, a school name…) is cut to fit instead of failing the request.
from sqlalchemy import String as _String, event as _event, inspect as _inspect  # noqa: E402
from sqlalchemy.orm import Session as _Session  # noqa: E402


@_event.listens_for(_Session, "before_flush")
def _fit_strings(session, _ctx, _instances):
    for obj in list(session.new) + list(session.dirty):
        mapper = _inspect(obj).mapper
        for col in mapper.columns:
            limit = getattr(col.type, "length", None) if isinstance(col.type, _String) else None
            if not limit:
                continue
            key = mapper.get_property_by_column(col).key
            value = getattr(obj, key, None)
            if isinstance(value, str) and len(value) > limit:
                setattr(obj, key, value[:limit])
