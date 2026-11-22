"""Telegram Bot runner (long polling CLI & CSRF-exempt secret-verified Flask webhook)."""
from __future__ import annotations

import hmac
import json
import logging
import os
import urllib.request
from typing import Any

from flask import Blueprint, current_app, jsonify, request
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import AIORateLimiter, Application, CommandHandler, ContextTypes, MessageHandler, filters

from monday.extensions import csrf
from .classifier import CrmBotConfigError, classify_lead_message, get_gemini_api_key
from .lead_sync import sync_telegram_lead
from .macros_loader import seed_reply_templates

logger = logging.getLogger(__name__)

bot_bp = Blueprint("crm_telegram_bot", __name__)

WELCOME_TEXT = (
    "Здравствуйте! Это бот Monday Academy (ОРТ, SAT, IELTS, школьная математика).\n"
    "Напишите, какой курс вас интересует, или нажмите кнопку ниже, чтобы поделиться номером телефона — "
    "менеджер быстро подберёт группу и расписание.\n\n"
    "Саламатсызбы! Бул Monday Academy боту (ЖРТ/ОРТ, SAT, IELTS, мектеп математикасы). "
    "Кайсы курс кызыктырганын жазыңыз же номериңизди бөлүшүңүз."
)


def get_telegram_bot_token(*, required: bool = False) -> str:
    tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not tok:
        try:
            tok = (current_app.config.get("TELEGRAM_BOT_TOKEN") or "").strip()
        except RuntimeError:
            tok = ""
    if required and not tok:
        raise CrmBotConfigError(
            "TELEGRAM_BOT_TOKEN is not set in environment variables. Export TELEGRAM_BOT_TOKEN first."
        )
    return tok


def contact_share_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text="Поделиться контактом / Номер бөлүшүү", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def process_incoming_telegram_event(
    *,
    chat_id: int | str,
    username: str | None,
    sender_name: str,
    text: str,
    shared_phone: str | None = None,
    gemini_client: Any | None = None,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    """Process one inbound Telegram text/contact event synchronously inside Flask app context."""
    effective_text = (text or "").strip()
    if not effective_text and shared_phone:
        effective_text = f"Поделился контактом: {shared_phone}"

    classification = classify_lead_message(
        effective_text,
        sender_name=sender_name,
        shared_phone=shared_phone,
        client=gemini_client,
        allow_fallback=allow_fallback,
    )
    lead, outcome, _audit = sync_telegram_lead(
        telegram_chat_id=chat_id,
        telegram_username=username,
        sender_name=sender_name,
        message_text=effective_text,
        classification=classification,
        shared_phone=shared_phone,
    )

    if outcome == "archived_spam" or classification.intent == "spam":
        return {
            "lead_id": lead.id,
            "outcome": outcome,
            "status": lead.status,
            "is_archived": bool(lead.is_archived),
            "intent": classification.intent,
            "reply_text": None,
            "ask_contact": False,
        }

    reply_text = classification.draft_reply or (
        "Спасибо! Заявка передана менеджеру Monday Academy."
        if classification.language != "ky"
        else "Рахмат! Өтүнүчүңүз Monday Academy менеджерине жөнөтүлдү."
    )
    if shared_phone and not text.strip():
        reply_text = (
            "Спасибо! Номер получен, менеджер скоро свяжется с вами и подберёт удобный вариант."
            if classification.language != "ky"
            else "Рахмат! Номериңиз алынды, менеджерибиз жакында байланышат."
        )
    return {
        "lead_id": lead.id,
        "outcome": outcome,
        "status": lead.status,
        "is_archived": bool(lead.is_archived),
        "intent": classification.intent,
        "priority_score": lead.priority_score,
        "reply_text": reply_text,
        "ask_contact": not bool(lead.phone_e164),
    }


def _send_telegram_reply_http(token: str, chat_id: int | str, text: str, ask_contact: bool) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if ask_contact:
        payload["reply_markup"] = {
            "keyboard": [[{"text": "Поделиться контактом / Номер бөлүшүү", "request_contact": True}]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


@bot_bp.post("/api/telegram/webhook")
@csrf.exempt
def telegram_webhook():
    """Secret-token-verified Telegram Bot webhook for Render production."""
    expected = (current_app.config.get("TELEGRAM_WEBHOOK_SECRET") or os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    if not expected:
        return jsonify({"ok": False, "error": "telegram_webhook_secret_not_configured"}), 503

    provided = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    update_data = request.get_json(silent=True)
    if not isinstance(update_data, dict):
        return jsonify({"ok": False, "error": "invalid_json"}), 400

    msg = update_data.get("message") or update_data.get("edited_message")
    if not isinstance(msg, dict):
        return jsonify({"ok": True, "ignored": True})

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return jsonify({"ok": False, "error": "missing_chat_id"}), 400

    sender = msg.get("from") or {}
    sender_name = " ".join(
        p for p in (sender.get("first_name"), sender.get("last_name")) if isinstance(p, str) and p.strip()
    ).strip()
    username = sender.get("username") if isinstance(sender.get("username"), str) else None
    text = str(msg.get("text") or "").strip()
    contact = msg.get("contact") if isinstance(msg.get("contact"), dict) else None
    shared_phone = str(contact.get("phone_number") or "").strip() or None if contact else None

    token = get_telegram_bot_token(required=False)
    if text.startswith("/start"):
        if token and os.environ.get("MONDAY_DISABLE_TG_SEND", "0") != "1":
            try:
                _send_telegram_reply_http(token, chat_id, WELCOME_TEXT, ask_contact=True)
            except Exception as exc:
                logger.warning("Failed sending Telegram /start reply: %s", exc)
        return jsonify({"ok": True, "command": "start", "reply_text": WELCOME_TEXT})

    if not text and not shared_phone:
        return jsonify({"ok": True, "ignored": True})

    result = process_incoming_telegram_event(
        chat_id=chat_id,
        username=username,
        sender_name=sender_name,
        text=text,
        shared_phone=shared_phone,
        allow_fallback=True,
    )
    if result.get("reply_text") and token and os.environ.get("MONDAY_DISABLE_TG_SEND", "0") != "1":
        try:
            _send_telegram_reply_http(token, chat_id, result["reply_text"], ask_contact=bool(result.get("ask_contact")))
        except Exception as exc:
            logger.warning("Failed sending Telegram reply: %s", exc)
    return jsonify({"ok": True, **result})


def build_telegram_application(token: str, flask_app, *, allow_fallback: bool = True) -> Application:
    """Build python-telegram-bot Application bound to a Flask app context."""
    tg_app = Application.builder().token(token).rate_limiter(AIORateLimiter()).build()

    async def _on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        await update.message.reply_text(WELCOME_TEXT, reply_markup=contact_share_keyboard())

    async def _on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message
        if msg is None or update.effective_chat is None:
            return
        user = update.effective_user
        sender_name = " ".join(p for p in (getattr(user, "first_name", None), getattr(user, "last_name", None)) if p).strip()
        username = getattr(user, "username", None)
        shared_phone = msg.contact.phone_number if msg.contact else None
        text = msg.text or ""

        with flask_app.app_context():
            # Startup already validated GEMINI_API_KEY unless --allow-fallback was used;
            # keep runtime resilient to transient 503 API spikes by allowing graceful fallback.
            res = process_incoming_telegram_event(
                chat_id=update.effective_chat.id,
                username=username,
                sender_name=sender_name,
                text=text,
                shared_phone=shared_phone,
                allow_fallback=True,
            )

        if res.get("reply_text"):
            markup = contact_share_keyboard() if res.get("ask_contact") else ReplyKeyboardRemove()
            await msg.reply_text(res["reply_text"], reply_markup=markup)

    async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Unhandled Telegram update error: %s", context.error)

    tg_app.add_handler(CommandHandler("start", _on_start))
    tg_app.add_handler(MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), _on_message))
    tg_app.add_error_handler(_on_error)
    return tg_app


def run_polling_bot(flask_app, *, allow_fallback: bool = False) -> None:
    """Start local Telegram long-polling loop for development testing."""
    token = get_telegram_bot_token(required=True)
    get_gemini_api_key(required=not allow_fallback)
    with flask_app.app_context():
        seed_reply_templates()
    tg_app = build_telegram_application(token, flask_app, allow_fallback=allow_fallback)
    tg_app.run_polling(drop_pending_updates=False)
