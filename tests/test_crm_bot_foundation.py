"""Tests for Telegram CRM Lead Bot, docs/crm_bot knowledge base, ReplyTemplate/BotReplyFeedback models, and CLI/webhook."""
from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from config import Config
from monday.extensions import db
from monday.models import AuditLog, BotReplyFeedback, Lead, LeadActivity, ReplyTemplate, User
from services.crm_bot.classifier import CrmBotConfigError, LeadClassificationResult, classify_lead_message
from services.crm_bot.lead_sync import sync_telegram_lead
from services.crm_bot.macros_loader import render_macro_text, seed_reply_templates
from services.crm_bot.memory import (
    CrmReplyModule,
    format_few_shot_block,
    get_few_shot_examples,
    record_reply_feedback,
    sync_learned_rules_from_feedback,
)

ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent


def _make_app(tmp_path, *, webhook_secret: str = "tg-secret-xyz"):
    class BotTestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = True
        SEED_DEMO = False
        DATA_FIXES = False
        IMPORT_PACKS = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'crm_bot.db'}"
        UPLOAD_FOLDER = str(tmp_path / "uploads")
        TELEGRAM_WEBHOOK_SECRET = webhook_secret
        TELEGRAM_BOT_TOKEN = ""
        GEMINI_API_KEY = ""

    from monday import create_app

    return create_app(BotTestConfig, seed_if_empty=False)


def _seed_manager(app, email: str = "mgr.bot@monday.kg", name: str = "Менеджер Алия") -> int:
    with app.app_context():
        u = User(email=email, name=name, role="sales_manager", is_approved=True, is_on_shift=True)
        u.set_password("Pass12345!")
        db.session.add(u)
        db.session.commit()
        return u.id


def test_docs_knowledge_base_and_root_agent_instructions():
    expected_docs = (
        "docs/crm_bot/catalog_and_pricing.md",
        "docs/crm_bot/scenarios_and_objections.md",
        "docs/crm_bot/reply_macros.md",
        "docs/crm_bot/learned_rules.md",
    )
    for rel in expected_docs:
        p = ROOT_DIR / rel
        assert p.is_file(), f"Missing {rel}"
        assert len(p.read_text(encoding="utf-8").strip()) > 100

    catalog = (ROOT_DIR / "docs/crm_bot/catalog_and_pricing.md").read_text(encoding="utf-8")
    for course in ("ОРТ", "SAT", "IELTS", "Школьная математика"):
        assert course in catalog
    assert "PLACEHOLDER" in catalog

    claude_md = (ROOT_DIR / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@docs/crm_bot/" in claude_md


def test_seed_reply_templates_idempotent_and_bilingual_rendering(tmp_path):
    app = _make_app(tmp_path)
    with app.app_context():
        # Migration e1f2a3b4c5d6 already seeded macros idempotently; calling seeder again creates 0 duplicates
        initial_count = ReplyTemplate.query.count()
        assert initial_count >= 6
        assert seed_reply_templates() == 0
        assert ReplyTemplate.query.count() == initial_count

        # Deleting one template and re-running seed_reply_templates recreates just that 1 row
        tpl = ReplyTemplate.query.filter_by(slug="greeting_hot_lead").first()
        assert tpl is not None
        assert "name" in tpl.variables_json
        db.session.delete(tpl)
        db.session.commit()
        assert seed_reply_templates() == 1
        assert ReplyTemplate.query.count() == initial_count

        tpl = ReplyTemplate.query.filter_by(slug="greeting_hot_lead").first()
        rendered_ru = render_macro_text(tpl, "ru", {"name": "Айдай", "subject": "SAT", "manager_name": "Алия"})
        rendered_ky = render_macro_text(tpl, "ky", {"name": "Айдай", "subject": "SAT", "manager_name": "Алия"})
        assert "Айдай" in rendered_ru and "Monday Academy" in rendered_ru
        assert "Саламатсызбы, Айдай!" in rendered_ky


def test_classifier_structured_output_with_mocked_gemini_and_missing_key(tmp_path, monkeypatch):
    app = _make_app(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with app.app_context():
        seed_reply_templates()

        # Strict mode fails gracefully with clear message when GEMINI_API_KEY is missing
        with pytest.raises(CrmBotConfigError, match="GEMINI_API_KEY"):
            classify_lead_message("Хочу записаться на SAT", allow_fallback=False)

        # Mock google-genai client returning structured Pydantic result
        mock_parsed = LeadClassificationResult(
            full_name="Бекзат",
            phone="+996700123456",
            subject="SAT",
            language="ru",
            intent="trial_booking",
            priority_score=92,
            matched_template_slug="trial_lesson_booking",
            variables={"name": "Бекзат", "subject": "SAT", "trial_time": "суббота 15:00", "branch": "онлайн"},
        )
        fake_client = SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **_kw: SimpleNamespace(parsed=mock_parsed, text="")
            )
        )
        res = classify_lead_message(
            "Здравствуйте! Я Бекзат, хочу на пробный по SAT онлайн в субботу, +996700123456",
            client=fake_client,
            allow_fallback=False,
        )
        assert res.used_fallback is False
        assert res.intent == "trial_booking"
        assert res.priority_score == 92
        assert res.phone == "+996700123456"
        assert "Бекзат" in res.draft_reply
        assert "суббота 15:00" in res.draft_reply


def test_memory_few_shot_retrieval_and_learned_rules(tmp_path):
    app = _make_app(tmp_path)
    mgr_id = _seed_manager(app)
    rules_copy = tmp_path / "learned_rules.md"
    rules_copy.write_text("# Test\n\n<!-- AUTO_RULES_START -->\n", encoding="utf-8")

    with app.app_context():
        record_reply_feedback(
            lead_id=None,
            template_slug="course_price_overview",
            intent="price_question",
            subject="SAT",
            language="ru",
            draft_text="Draft 1",
            final_sent_text="Одобренный ответ по SAT с приглашением на диагностику.",
            was_accepted=True,
            created_by_id=mgr_id,
        )
        record_reply_feedback(
            lead_id=None,
            template_slug="course_price_overview",
            intent="price_question",
            subject="IELTS",
            language="ru",
            draft_text="Draft 2",
            final_sent_text="Исправленный менеджером ответ по IELTS.",
            was_accepted=False,
            created_by_id=mgr_id,
        )
        # Ignored unaccepted empty final_sent_text row
        record_reply_feedback(
            lead_id=None,
            template_slug="course_price_overview",
            intent="price_question",
            subject="SAT",
            language="ru",
            draft_text="Bad draft",
            final_sent_text="",
            was_accepted=False,
            created_by_id=mgr_id,
        )

        examples = get_few_shot_examples(intent="price_question", subject="SAT", language="ru", limit=3)
        assert len(examples) == 2
        assert examples[0]["subject"] == "sat"
        assert "диагностику" in examples[0]["final_sent_text"]
        block = format_few_shot_block(examples)
        assert "edited_by_manager" in block and "accepted" in block

        written = sync_learned_rules_from_feedback(limit=5, path=rules_copy)
        assert written == 2
        assert "Одобренный ответ по SAT" in rules_copy.read_text(encoding="utf-8")
        assert isinstance(CrmReplyModule(), CrmReplyModule)


def test_lead_sync_dedup_chat_id_and_phone_plus_spam_soft_archive(tmp_path):
    app = _make_app(tmp_path)
    mgr_id = _seed_manager(app)

    with app.app_context():
        # 1. Create initial lead via Telegram chat_id (without phone yet)
        c1 = LeadClassificationResult(
            full_name="Алина К",
            subject="ОРТ",
            language="ru",
            intent="price_question",
            priority_score=72,
            matched_template_slug="course_price_overview",
        )
        lead1, outcome1, audit1 = sync_telegram_lead(
            telegram_chat_id=9001001,
            telegram_username="alina_k",
            sender_name="Алина",
            message_text="Сколько стоит курс ОРТ?",
            classification=c1,
        )
        assert outcome1 == "created"
        assert lead1.status == "new"
        assert lead1.assigned_manager_id == mgr_id
        assert lead1.telegram_chat_id == "9001001"
        assert audit1.action == "bot_lead_create"

        # 2. Same user shares contact via phone in different chat/reconnect -> dedupe by normalized phone_e164 too
        c2 = LeadClassificationResult(
            full_name="Алина К",
            phone="0701555666",
            subject="ОРТ",
            language="ru",
            intent="trial_booking",
            priority_score=91,
            matched_template_slug="trial_lesson_booking",
        )
        lead2, outcome2, audit2 = sync_telegram_lead(
            telegram_chat_id=9001001,
            telegram_username="alina_k",
            sender_name="Алина",
            message_text="Запишите на пробный",
            classification=c2,
            shared_phone="0701 555 666",
        )
        assert outcome2 == "updated"
        assert lead2.id == lead1.id
        assert lead2.phone_e164 == "+996701555666"
        assert lead2.status == "contacted"
        assert lead2.priority_score == 91
        assert audit2.action == "bot_lead_update"

        # Different chat_id with SAME normalized phone deduplicates into lead1 cleanly
        lead3, outcome3, _ = sync_telegram_lead(
            telegram_chat_id=9999999,
            telegram_username="alina_second",
            sender_name="Алина",
            message_text="Уточню время",
            classification=c2,
            shared_phone="+996701555666",
        )
        assert outcome3 == "updated"
        assert lead3.id == lead1.id
        assert LeadActivity.query.filter_by(lead_id=lead1.id).count() >= 3

        # 3. Spam message soft-archives without deleting
        spam_cls = LeadClassificationResult(
            full_name="Spam Bot",
            subject="",
            language="ru",
            intent="spam",
            priority_score=3,
        )
        spam_lead, spam_outcome, spam_audit = sync_telegram_lead(
            telegram_chat_id=7770001,
            telegram_username="crypto_spammer",
            sender_name="Promo",
            message_text="Заработок на крипте без вложений казино",
            classification=spam_cls,
        )
        assert spam_outcome == "archived_spam"
        assert spam_lead.is_archived is True
        assert spam_lead.archive_reason == "spam"
        assert spam_audit.action == "bot_lead_archive"
        assert db.session.get(Lead, spam_lead.id) is not None


def test_telegram_webhook_security_and_cli_missing_token_fails_gracefully(tmp_path, monkeypatch):
    app = _make_app(tmp_path, webhook_secret="super-secret-tg")
    _seed_manager(app)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("MONDAY_DISABLE_TG_SEND", "1")

    with app.app_context():
        seed_reply_templates()

    # CLI check: fails gracefully with ClickException message if TELEGRAM_BOT_TOKEN is missing
    runner = app.test_cli_runner()
    cli_res = runner.invoke(args=["run-telegram-bot"])
    assert cli_res.exit_code != 0
    assert "TELEGRAM_BOT_TOKEN" in cli_res.output

    client = app.test_client()

    # Wrong or missing secret rejected 401
    assert client.post("/api/telegram/webhook", json={"update_id": 1}).status_code == 401
    assert (
        client.post(
            "/api/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            json={"update_id": 1},
        ).status_code
        == 401
    )

    headers = {"X-Telegram-Bot-Api-Secret-Token": "super-secret-tg"}

    # 1. /start command asks for phone contact
    res_start = client.post(
        "/api/telegram/webhook",
        headers=headers,
        json={
            "update_id": 10,
            "message": {"chat": {"id": 12345}, "from": {"first_name": "Тимур", "username": "timur"}, "text": "/start"},
        },
    )
    assert res_start.status_code == 200
    assert res_start.get_json()["command"] == "start"

    # 2. Text inquiry creates lead & drafts reply asking for contact
    res_msg = client.post(
        "/api/telegram/webhook",
        headers=headers,
        json={
            "update_id": 11,
            "message": {
                "chat": {"id": 12345},
                "from": {"first_name": "Тимур", "username": "timur"},
                "text": "Сколько стоит подготовка к IELTS?",
            },
        },
    )
    assert res_msg.status_code == 200
    data_msg = res_msg.get_json()
    assert data_msg["outcome"] == "created"
    assert data_msg["intent"] == "price_question"
    assert data_msg["ask_contact"] is True
    assert data_msg["reply_text"]

    # 3. Contact sharing captures normalized phone into the same lead
    res_contact = client.post(
        "/api/telegram/webhook",
        headers=headers,
        json={
            "update_id": 12,
            "message": {
                "chat": {"id": 12345},
                "from": {"first_name": "Тимур", "username": "timur"},
                "contact": {"phone_number": "996777112233", "first_name": "Тимур"},
            },
        },
    )
    assert res_contact.status_code == 200
    data_contact = res_contact.get_json()
    assert data_contact["lead_id"] == data_msg["lead_id"]
    assert data_contact["outcome"] == "updated"
    assert data_contact["ask_contact"] is False
    with app.app_context():
        lead = db.session.get(Lead, data_msg["lead_id"])
        assert lead.phone_e164 == "+996777112233"
        assert lead.status == "contacted"
        assert AuditLog.query.filter_by(entity_id=lead.id).count() == 2
