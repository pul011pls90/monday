"""Gemini Flash structured lead classifier grounded in docs/crm_bot/ and BotReplyFeedback memory."""
from __future__ import annotations

import logging
import os
import pathlib
import re
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from monday.models import ReplyTemplate
from monday.phone_utils import normalize_phone
from .macros_loader import load_macros_from_docs, render_macro_text
from .memory import format_few_shot_block, get_few_shot_examples

logger = logging.getLogger(__name__)

DOCS_DIR = pathlib.Path(__file__).resolve().parents[2] / "docs" / "crm_bot"

INTENT_TO_DEFAULT_SLUG = {
    "hot_lead": "greeting_hot_lead",
    "price_question": "course_price_overview",
    "trial_booking": "trial_lesson_booking",
    "reschedule": "reschedule_lesson",
    "spam": "greeting_hot_lead",
}

_PHONE_CANDIDATE_RE = re.compile(r"(?:\+?\d[\d\s\-()]{7,18}\d)")


class CrmBotConfigError(RuntimeError):
    """Raised when required bot environment secrets are missing."""


class TemplateVariableItem(BaseModel):
    key: str = Field(description="Macro slot name, e.g. name, subject, schedule, branch, trial_time, manager_name")
    value: str = Field(description="Extracted string value for this variable slot")


class _GeminiClassificationSchema(BaseModel):
    """Gemini Developer API-compatible schema (no dict/additionalProperties)."""

    full_name: str | None = Field(default=None, description="Extracted name of student/parent if stated")
    phone: str | None = Field(default=None, description="Extracted phone number if present")
    subject: str = Field(default="", description="Course/subject interest e.g. ОРТ, SAT, IELTS, Школьная математика")
    language: Literal["ru", "ky", "en"] = Field(default="ru", description="Detected user language")
    intent: Literal["hot_lead", "price_question", "trial_booking", "reschedule", "spam"] = Field(
        default="hot_lead",
        description="Primary CRM intent",
    )
    priority_score: int = Field(default=60, ge=1, le=100, description="Urgency/quality score 1..100")
    matched_template_slug: str = Field(
        default="greeting_hot_lead",
        description="Best matching slug from reply_macros.md / ReplyTemplate",
    )
    variables: list[TemplateVariableItem] = Field(
        default_factory=list,
        description="Extracted {variable} key/value pairs for rendering the matched reply macro",
    )
    draft_reply: str = Field(default="", description="Optional rendered Optima-style draft reply")


class LeadClassificationResult(BaseModel):
    full_name: str | None = Field(default=None, description="Extracted name of student/parent if stated")
    phone: str | None = Field(default=None, description="Extracted phone number if present")
    subject: str = Field(default="", description="Course/subject interest e.g. ОРТ, SAT, IELTS, Школьная математика")
    language: Literal["ru", "ky", "en"] = Field(default="ru", description="Detected user language")
    intent: Literal["hot_lead", "price_question", "trial_booking", "reschedule", "spam"] = Field(
        default="hot_lead",
        description="Primary CRM intent",
    )
    priority_score: int = Field(default=60, ge=1, le=100, description="Urgency/quality score 1..100")
    matched_template_slug: str = Field(
        default="greeting_hot_lead",
        description="Best matching slug from reply_macros.md / ReplyTemplate",
    )
    variables: dict[str, str] = Field(
        default_factory=dict,
        description="Extracted {variable} values for rendering the matched reply macro",
    )
    draft_reply: str = Field(default="", description="Optional rendered Optima-style draft reply")
    used_fallback: bool = Field(default=False, description="True if heuristic fallback ran instead of live Gemini")


def get_gemini_api_key(*, required: bool = False) -> str:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        try:
            from flask import current_app
            key = (current_app.config.get("GEMINI_API_KEY") or "").strip()
        except RuntimeError:
            key = ""
    if required and not key:
        raise CrmBotConfigError(
            "GEMINI_API_KEY is not set in environment variables. Export GEMINI_API_KEY before calling Gemini."
        )
    return key


def _load_kb_context() -> str:
    parts = []
    for fname in ("catalog_and_pricing.md", "scenarios_and_objections.md", "reply_macros.md", "learned_rules.md"):
        p = DOCS_DIR / fname
        if p.is_file():
            parts.append(f"=== {fname} ===\n{p.read_text(encoding='utf-8')[:3500]}")
    return "\n\n".join(parts)


def _detect_language_heuristic(text: str) -> Literal["ru", "ky", "en"]:
    low = (text or "").lower()
    if any(ch in low for ch in ("ө", "ү", "ң")) or any(
        w in low for w in ("салам", "саламатсыз", "канча", "баасы", "сабак", "жазыл", "окуу", "кыргыз")
    ):
        return "ky"
    if re.search(r"[a-z]{3,}", low) and not re.search(r"[а-яёөүң]", low):
        return "en"
    return "ru"


def _extract_subject_heuristic(text: str) -> str:
    low = (text or "").lower()
    if "sat" in low or "сат" in low:
        return "SAT"
    if "ielts" in low or "айлтс" in low:
        return "IELTS"
    if "орт" in low or "ort" in low or "жрт" in low:
        return "ОРТ"
    if any(k in low for k in ("матем", "алгебр", "геометр", "ент", "егэ", "огэ", "школ")):
        return "Школьная математика"
    return ""


def _classify_heuristic(text: str, *, sender_name: str = "", shared_phone: str | None = None) -> LeadClassificationResult:
    low = (text or "").lower()
    lang = _detect_language_heuristic(text)
    subject = _extract_subject_heuristic(text)

    phone = shared_phone
    if not phone:
        for m in _PHONE_CANDIDATE_RE.findall(text or ""):
            if normalize_phone(m):
                phone = m.strip()
                break

    spam_markers = ("казино", "крипт", "заработок без", "ставки на спорт", "crypto", "airdrop", "porn", "betting")
    if any(tok in low for tok in spam_markers):
        intent: Literal["hot_lead", "price_question", "trial_booking", "reschedule", "spam"] = "spam"
        score = 5
    elif any(k in low for k in ("перенес", "перенос", "опозда", "жылдыр", "reschedule", "другое время")):
        intent = "reschedule"
        score = 80
    elif any(k in low for k in ("пробн", "диагност", "запис", "сынамык", "жазыл", "trial")):
        intent = "trial_booking"
        score = 90
    elif any(k in low for k in ("сколько", "цена", "стоим", "прайс", "оплат", "баасы", "канча", "price", "cost")):
        intent = "price_question"
        score = 72
    else:
        intent = "hot_lead"
        score = 82 if (phone or subject) else 65

    slug = INTENT_TO_DEFAULT_SLUG.get(intent, "greeting_hot_lead")
    variables = {
        "name": (sender_name or ("друг" if lang != "ky" else "досум")).split()[0],
        "subject": subject or ("подготовка" if lang != "ky" else "даярдык"),
    }
    return LeadClassificationResult(
        full_name=sender_name or None,
        phone=phone,
        subject=subject,
        language=lang,
        intent=intent,
        priority_score=score,
        matched_template_slug=slug,
        variables=variables,
        used_fallback=True,
    )


def _render_template_reply(res: LeadClassificationResult, *, manager_name: str = "") -> str:
    if res.intent == "spam":
        return ""
    slug = res.matched_template_slug or INTENT_TO_DEFAULT_SLUG.get(res.intent, "greeting_hot_lead")
    tpl = None
    try:
        tpl = ReplyTemplate.query.filter_by(slug=slug, is_active=True).first()
    except Exception:
        tpl = None
    if tpl is None:
        for item in load_macros_from_docs():
            if item["slug"] == slug:
                tpl = item
                break
    if tpl is None:
        return res.draft_reply or ""

    vars_ctx = dict(res.variables or {})
    if res.full_name and "name" not in vars_ctx:
        vars_ctx["name"] = res.full_name.split()[0]
    if res.subject and "subject" not in vars_ctx:
        vars_ctx["subject"] = res.subject
    if manager_name and "manager_name" not in vars_ctx:
        vars_ctx["manager_name"] = manager_name
    return render_macro_text(tpl, res.language, vars_ctx)


def classify_lead_message(
    text: str,
    *,
    sender_name: str = "",
    shared_phone: str | None = None,
    manager_name: str = "",
    client: Any | None = None,
    model_name: str | None = None,
    allow_fallback: bool = True,
) -> LeadClassificationResult:
    """Classify an inbound Telegram message into strict Pydantic output and render an Optima-style reply."""
    heuristic = _classify_heuristic(text, sender_name=sender_name, shared_phone=shared_phone)
    examples = []
    try:
        examples = get_few_shot_examples(
            intent=heuristic.intent,
            subject=heuristic.subject,
            language=heuristic.language,
            limit=5,
        )
    except Exception:
        examples = []

    api_key = ""
    if client is None:
        try:
            api_key = get_gemini_api_key(required=not allow_fallback)
        except CrmBotConfigError:
            if not allow_fallback:
                raise
            api_key = ""

    result = heuristic
    if client is not None or api_key:
        try:
            gm_client = client or genai.Client(api_key=api_key)
            chosen_model = model_name or os.environ.get("GEMINI_CRM_MODEL", "gemini-3.8-flash")
            candidate_models = [chosen_model] if model_name else list(
                dict.fromkeys([
                    chosen_model,
                    "gemini-3.7-flash",
                    "gemini-3.6-flash",
                    "gemini-3.5-flash",
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-flash-lite",
                ])
            )
            system_prompt = (
                "Ты CRM-ассистент образовательной академии Monday Academy. "
                "Классифицируй входящее сообщение от ученика или родителя в Telegram, "
                "извлеки поля и выбери подходящий шаблон matched_template_slug из базы знаний. "
                "Никогда не выдумывай цены, если в каталоге стоит плейсхолдер.\n\n"
                f"{_load_kb_context()}\n\n"
                f"{format_few_shot_block(examples)}"
            ).strip()
            user_prompt = (
                f"Имя профиля Telegram: {sender_name or 'не указано'}\n"
                f"Переданный телефон: {shared_phone or 'нет'}\n"
                f"Сообщение клиента: {text}"
            )
            resp = None
            last_exc = None
            for mdl in candidate_models:
                try:
                    resp = gm_client.models.generate_content(
                        model=mdl,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                            response_schema=_GeminiClassificationSchema,
                            temperature=0.1,
                        ),
                    )
                    break
                except Exception as exc:
                    last_exc = exc
                    msg_low = str(exc).lower()
                    if len(candidate_models) > 1 and ("503" in msg_low or "unavailable" in msg_low or "404" in msg_low):
                        logger.warning("Gemini model %s unavailable (%s); trying next candidate", mdl, exc)
                        continue
                    raise
            if resp is None and last_exc is not None:
                raise last_exc
            parsed = getattr(resp, "parsed", None)
            if isinstance(parsed, LeadClassificationResult):
                result = parsed
            elif isinstance(parsed, _GeminiClassificationSchema):
                data = parsed.model_dump()
                data["variables"] = {item["key"]: item["value"] for item in data.get("variables") or [] if item.get("key")}
                result = LeadClassificationResult.model_validate(data)
            elif isinstance(parsed, dict):
                if isinstance(parsed.get("variables"), list):
                    parsed = {**parsed, "variables": {i["key"]: i["value"] for i in parsed["variables"] if i.get("key")}}
                result = LeadClassificationResult.model_validate(parsed)
            else:
                raw_text = (getattr(resp, "text", None) or "").strip()
                if raw_text:
                    wire = _GeminiClassificationSchema.model_validate_json(raw_text)
                    data = wire.model_dump()
                    data["variables"] = {item["key"]: item["value"] for item in data.get("variables") or [] if item.get("key")}
                    result = LeadClassificationResult.model_validate(data)
            result.used_fallback = False
        except Exception as exc:
            logger.warning("Gemini CRM classifier fallback triggered: %s", exc)
            if not allow_fallback:
                raise
            result = heuristic

    if shared_phone and not result.phone:
        result.phone = shared_phone
    if not result.full_name and sender_name:
        result.full_name = sender_name
    if not result.draft_reply:
        result.draft_reply = _render_template_reply(result, manager_name=manager_name)
    return result
