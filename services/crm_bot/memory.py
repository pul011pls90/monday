"""Dynamic few-shot feedback retrieval, learned rules sync, and DSPy signature wrapper."""
from __future__ import annotations

import pathlib
from typing import Any

import dspy

from monday.extensions import db
from monday.models import BotReplyFeedback, utcnow

LEARNED_RULES_PATH = pathlib.Path(__file__).resolve().parents[2] / "docs" / "crm_bot" / "learned_rules.md"
AUTO_MARKER = "<!-- AUTO_RULES_START -->"


class CrmReplySignature(dspy.Signature):
    """Generate a concise Optima-style CRM reply for Monday Academy using knowledge base & examples."""

    lead_message: str = dspy.InputField(desc="Incoming message text from prospective student or parent")
    intent: str = dspy.InputField(desc="Classified intent: hot_lead, price_question, trial_booking, reschedule, spam")
    language: str = dspy.InputField(desc="Target language code: ru, ky, or en")
    macro_template: str = dspy.InputField(desc="Selected Optima-style reply macro body")
    few_shot_examples: str = dspy.InputField(desc="Accepted or manager-corrected past replies for alignment")
    reply_text: str = dspy.OutputField(desc="Polite, concise Optima-style final reply")


class CrmReplyModule(dspy.Module):
    """DSPy module wrapper ready for offline BootstrapFewShot / MIPROv2 optimization."""

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.Predict(CrmReplySignature)

    def forward(
        self,
        lead_message: str,
        intent: str,
        language: str,
        macro_template: str,
        few_shot_examples: str = "",
    ):
        return self.generate(
            lead_message=lead_message,
            intent=intent,
            language=language,
            macro_template=macro_template,
            few_shot_examples=few_shot_examples,
        )


def _norm_subject(subject: str | None) -> str:
    return (subject or "").strip().casefold()[:80]


def get_few_shot_examples(
    *,
    intent: str,
    subject: str = "",
    language: str = "ru",
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return top `limit` (3..5) accepted or manager-corrected feedback rows for (intent, subject, language)."""
    cap = max(1, min(10, int(limit or 5)))
    clean_intent = (intent or "hot_lead").strip()
    clean_lang = (language or "ru").strip().lower()
    clean_subj = _norm_subject(subject)

    base_q = BotReplyFeedback.query.filter(
        BotReplyFeedback.intent == clean_intent,
        BotReplyFeedback.language == clean_lang,
        db.or_(BotReplyFeedback.was_accepted.is_(True), BotReplyFeedback.final_sent_text != ""),
    )

    rows: list[BotReplyFeedback] = []
    seen_ids: set[int] = set()
    if clean_subj:
        exact_rows = (
            base_q.filter(BotReplyFeedback.subject == clean_subj)
            .order_by(BotReplyFeedback.was_accepted.desc(), BotReplyFeedback.created_at.desc(), BotReplyFeedback.id.desc())
            .limit(cap)
            .all()
        )
        for r in exact_rows:
            rows.append(r)
            seen_ids.add(r.id)

    if len(rows) < cap:
        fallback_rows = (
            base_q.filter(~BotReplyFeedback.id.in_(seen_ids) if seen_ids else sa_true())
            .order_by(BotReplyFeedback.was_accepted.desc(), BotReplyFeedback.created_at.desc(), BotReplyFeedback.id.desc())
            .limit(cap - len(rows))
            .all()
        )
        rows.extend(fallback_rows)

    return [
        {
            "id": r.id,
            "lead_id": r.lead_id,
            "template_slug": r.template_slug,
            "intent": r.intent,
            "subject": r.subject,
            "language": r.language,
            "draft_text": r.draft_text,
            "final_sent_text": r.final_sent_text or r.draft_text,
            "was_accepted": bool(r.was_accepted),
        }
        for r in rows
    ]


def sa_true():
    return db.literal(True)


def record_reply_feedback(
    *,
    lead_id: int | None,
    template_slug: str | None,
    intent: str,
    subject: str = "",
    language: str = "ru",
    draft_text: str = "",
    final_sent_text: str = "",
    was_accepted: bool = False,
    created_by_id: int | None = None,
    commit: bool = True,
) -> BotReplyFeedback:
    """Persist a draft vs manager-sent reply record for the few-shot feedback loop."""
    row = BotReplyFeedback(
        lead_id=lead_id,
        template_slug=(template_slug or "")[:80] or None,
        intent=(intent or "hot_lead")[:48],
        subject=_norm_subject(subject),
        language=(language or "ru")[:12],
        draft_text=draft_text or "",
        final_sent_text=(final_sent_text or "").strip(),
        was_accepted=bool(was_accepted),
        created_by_id=created_by_id,
        created_at=utcnow(),
    )
    db.session.add(row)
    if commit:
        db.session.commit()
    return row


def format_few_shot_block(examples: list[dict[str, Any]]) -> str:
    """Format retrieved feedback items as compact prompt context."""
    if not examples:
        return ""
    lines = ["Примеры одобренных ответов менеджеров для ориентира (few-shot):"]
    for i, ex in enumerate(examples, start=1):
        status = "accepted" if ex.get("was_accepted") else "edited_by_manager"
        snippet = (ex.get("final_sent_text") or ex.get("draft_text") or "").strip().replace("\n", " ")[:240]
        lines.append(f"{i}. [{ex.get('intent')}/{ex.get('language')}/{status}] {snippet}")
    return "\n".join(lines)


def sync_learned_rules_from_feedback(limit: int = 10, path: pathlib.Path | None = None) -> int:
    """Refresh auto-generated feedback rules inside docs/crm_bot/learned_rules.md."""
    target = path or LEARNED_RULES_PATH
    if not target.is_file():
        return 0
    rows = (
        BotReplyFeedback.query.filter(
            db.or_(BotReplyFeedback.was_accepted.is_(True), BotReplyFeedback.final_sent_text != "")
        )
        .order_by(BotReplyFeedback.created_at.desc(), BotReplyFeedback.id.desc())
        .limit(max(1, limit))
        .all()
    )
    existing = target.read_text(encoding="utf-8")
    prefix = existing.split(AUTO_MARKER, 1)[0].rstrip()
    rule_lines = [prefix, "", AUTO_MARKER]
    for r in rows:
        text = (r.final_sent_text or r.draft_text or "").strip().replace("\n", " ")[:180]
        if text:
            subj = r.subject or "general"
            rule_lines.append(f"- `[feedback #{r.id} | {r.intent} | {subj} | {r.language}]` {text}")
    target.write_text("\n".join(rule_lines) + "\n", encoding="utf-8")
    return len(rows)
