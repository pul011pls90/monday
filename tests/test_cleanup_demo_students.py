"""Test that remove_demo_students deletes templated seed students without touching real students."""
import os
import tempfile

from config import Config


def test_remove_demo_students_keeps_real_students():
    tmp = tempfile.mkdtemp()

    class CleanupTestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = True
        DATA_FIXES = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "cleanup_test.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    from monday.cleanup import remove_demo_students
    from monday.models import StudentProfile, StudentRecord, User, db

    app = create_app(CleanupTestConfig)
    with app.app_context():
        assert User.query.filter_by(role="student").count() > 0

        # Add a real student + real StudentRecord
        teacher = User.query.filter_by(role="teacher").first()
        real_stu = User(email="real.student@gmail.com", name="Асан Реальный", role="student")
        real_stu.set_password("secret123")
        real_stu.profile = StudentProfile(exam="ORT", onboarded=True)
        db.session.add(real_stu)
        db.session.flush()
        real_rec = StudentRecord(teacher_id=teacher.id, name=real_stu.name, exam="ORT", student_user_id=real_stu.id)
        db.session.add(real_rec)
        db.session.commit()

        remove_demo_students()
        db.session.commit()

        # student@monday.kg (showcase student) and real students are kept; student1..N are removed
        remaining = {u.email for u in User.query.filter_by(role="student").all()}
        assert remaining == {"student@monday.kg", "real.student@gmail.com"}
        assert StudentRecord.query.filter_by(student_user_id=real_stu.id).count() == 1

        # If student@monday.kg was deleted earlier, ensure_showcase_student restores it cleanly
        from monday.cleanup import ensure_showcase_student
        stu_demo = User.query.filter_by(email="student@monday.kg").first()
        StudentRecord.query.filter_by(student_user_id=stu_demo.id).delete()
        db.session.delete(stu_demo)
        db.session.commit()
        assert User.query.filter_by(email="student@monday.kg").first() is None

        ensure_showcase_student()
        db.session.commit()
        restored = User.query.filter_by(email="student@monday.kg").first()
        assert restored is not None and restored.check_password("student123") and restored.profile is not None


def test_remove_extra_teachers_keeps_admin_and_aibek_and_preserves_questions():
    tmp = tempfile.mkdtemp()

    class TeacherCleanupConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SEED_DEMO = True
        DATA_FIXES = False
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(tmp, "teacher_cleanup_test.db")
        UPLOAD_FOLDER = os.path.join(tmp, "uploads")
        SERVER_NAME = "localhost"

    from monday import create_app
    from monday.cleanup import remove_extra_teachers
    from monday.models import Question, User, db

    app = create_app(TeacherCleanupConfig)
    with app.app_context():
        q_before = Question.query.count()
        assert User.query.filter_by(role="teacher").count() > 1

        remove_extra_teachers()
        db.session.commit()

        teachers = User.query.filter_by(role="teacher").all()
        assert [t.email for t in teachers] == ["aibek@monday.kg"]
        assert User.query.filter_by(role="admin").count() == 1
        assert Question.query.count() == q_before
